#!/usr/bin/env python3
import argparse
import csv
import http.client
import json
import os
import pathlib
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List


SYSTEM_PROMPT = """你是多语言本地化 QA 复核助手。
目标：判断 CSV 中的异常示例是否真的是需要修复的本地化问题。

保留（KEEP）的情况：
1. 明显是其他语言残留，比如中文出现在德语/法语/俄语中。
2. 混合脚本污染，比如单词里夹了西里尔字母。
3. 普通常用词没有本地化，明显更像漏翻。
4. 对于 zh-Hans / zh-Hant / ja / ru，这些语言里如果出现普通英文单词或英文词组，应默认判为 KEEP。

过滤（OK）的情况：
1. 明显的专有名词、人名、品牌名、软件名、协议名。
2. 常见缩写、化学式、文件格式、操作系统、字体名。
3. 可以合理保持原文的术语。

额外严格规则：
1. 对于 zh-Hans / zh-Hant：如果异常示例是普通英文词、英文名词、英文形容词、英文数字词、英文几何/时间/自然类词汇，不要轻易判 OK。
2. 只有当你非常确定它属于专有名词、标准缩写、文件格式、化学式、品牌名、协议名，才可以判 OK。
3. 如果拿不准，优先判 KEEP，而不是 OK。

输出必须是 JSON 对象，格式：
{
  "results": [
    {
      "index": 0,
      "decision": "KEEP",
      "reason": "一句中文理由"
    }
  ]
}

其中 decision 只能是 KEEP 或 OK。"""


PROVIDERS = {
    "deepseek": {
        "key_env": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "base_url_default": "https://api.deepseek.com",
        "model_env": "DEEPSEEK_MODEL",
        "model_default": "deepseek-chat",
        "temperature_default": 0.0,
    },
    "minimax": {
        "key_env": "MINIMAX_API_KEY",
        "base_url_env": "MINIMAX_BASE_URL",
        "base_url_default": "https://api.minimax.io/v1",
        "model_env": "MINIMAX_MODEL",
        "model_default": "MiniMax-M2.5",
        "temperature_default": 0.1,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify suspect CSV rows with a supported chat-completions API.")
    parser.add_argument("--input", required=True, help="Input suspect CSV.")
    parser.add_argument("--output", required=True, help="Output CSV with AI原因.")
    parser.add_argument("--batch-size", type=int, default=50, help="Rows per request. Default: 50")
    parser.add_argument("--limit", type=int, default=None, help="Optional limit for test runs.")
    parser.add_argument(
        "--provider",
        choices=sorted(PROVIDERS.keys()),
        default=None,
        help="AI provider. Defaults to AI_VERIFY_PROVIDER env or deepseek.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Optional JSON/Markdown config file. Defaults to auto-detected files in the current directory.",
    )
    parser.add_argument("--model", default=None, help="Model name. Defaults depend on provider.")
    parser.add_argument("--temperature", type=float, default=None, help="Model temperature. Defaults depend on provider.")
    parser.add_argument("--check-config", action="store_true", help="Resolve config and print the effective settings without calling the API.")
    parser.add_argument(
        "--strictness",
        choices=["balanced", "strict"],
        default=None,
        help="Verification strictness. Defaults to config value or strict.",
    )
    parser.add_argument("--no-progress-bar", action="store_true", help="Suppress progress output.")
    return parser.parse_args()


def chunks(rows: List[Dict], size: int):
    for start in range(0, len(rows), size):
        yield start, rows[start:start + size]


def make_user_prompt(batch: List[Dict]) -> str:
    items = []
    for index, row in enumerate(batch):
        items.append({
            "index": index,
            "语言": row.get("语言", ""),
            "关卡文件": row.get("关卡文件", ""),
            "关卡数": row.get("关卡数", ""),
            "entry索引": row.get("entry索引", ""),
            "异常类型": row.get("异常类型", ""),
            "异常示例": row.get("异常示例", ""),
        })
    return "请逐条判断这些异常示例是否应保留为真实问题：\n" + json.dumps(items, ensure_ascii=False, indent=2)


def auto_detect_config_path() -> str:
    candidates = [
        "ai_verify_config.json",
        "ai_verify_config.md",
        ".ai_verify_config.json",
        ".ai_verify_config.md",
        "multilang_ai_verify_config.json",
        "multilang_ai_verify_config.md",
    ]
    cwd = pathlib.Path.cwd()
    for name in candidates:
        candidate = cwd / name
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return ""


def parse_markdown_config(text: str) -> Dict[str, str]:
    fenced_json = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
    if fenced_json:
        data = json.loads(fenced_json.group(1))
        if not isinstance(data, dict):
            raise ValueError("markdown config JSON block must be an object")
        return data

    data: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower().replace("-", "_")
        value = value.strip().strip("`").strip("\"'")
        if key and value:
            data[key] = value
    return data


def load_config_file(config_path: str) -> Dict[str, str]:
    if not config_path:
        return {}
    path = pathlib.Path(config_path)
    if not path.exists() or not path.is_file():
        raise ValueError(f"config file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("config JSON root must be an object")
        return data
    if path.suffix.lower() == ".md":
        return parse_markdown_config(text)
    raise ValueError(f"unsupported config file type: {path.suffix}")


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def resolve_provider(args: argparse.Namespace) -> Dict[str, str]:
    config_path = args.config or os.environ.get("AI_VERIFY_CONFIG") or auto_detect_config_path()
    file_config = load_config_file(config_path) if config_path else {}
    provider_name = str(args.provider or file_config.get("provider") or os.environ.get("AI_VERIFY_PROVIDER", "deepseek")).lower()
    if provider_name not in PROVIDERS:
        raise ValueError(f"unsupported provider: {provider_name}")
    provider = PROVIDERS[provider_name]
    api_key = str(file_config.get("api_key") or os.environ.get(provider["key_env"], ""))
    if not api_key:
        raise ValueError(f"{provider['key_env']} is required for provider {provider_name}")
    base_url = str(file_config.get("base_url") or os.environ.get(provider["base_url_env"], provider["base_url_default"]))
    model = str(args.model or file_config.get("model") or os.environ.get(provider["model_env"], provider["model_default"]))
    temperature_raw = args.temperature if args.temperature is not None else file_config.get("temperature")
    temperature = float(temperature_raw) if temperature_raw is not None else provider["temperature_default"]
    strictness = str(args.strictness or file_config.get("strictness") or "strict").lower()
    if strictness not in {"balanced", "strict"}:
        raise ValueError(f"unsupported strictness: {strictness}")
    return {
        "name": provider_name,
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "temperature": temperature,
        "strictness": strictness,
        "config_path": config_path or "",
        "api_key_masked": mask_secret(api_key),
    }


def read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    return body


def resolve_request_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions") or normalized.endswith("/text/chatcompletion_v2"):
        return normalized
    return f"{normalized}/chat/completions"


def extract_json_text(content: str) -> str:
    text = content.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.S)
    if fenced:
        return fenced.group(1).strip()
    return text


RE_LATIN = re.compile(r"[A-Za-z]")
RE_CJK = re.compile(r"[\u4e00-\u9fff]")
RE_MOSTLY_LATIN = re.compile(r"^[A-Za-z][A-Za-z0-9 .,'+&()/:-]*$")
RE_ALL_CAPS = re.compile(r"^[A-Z0-9][A-Z0-9.+/_-]*$")
RE_FILE_EXT = re.compile(r"^(mp3|mp4|wav|pdf|webp|heic|aac|mp2|json|html|css|js|exe|iso|dmg|apk)$", re.I)
RE_CHEM = re.compile(r"^[A-Z][a-z]?[A-Z]?[a-z]?\d*$")
RE_SHORT_TOKEN = re.compile(r"^[A-Za-z]{1,3}$")
LATIN_LANGS_STRICT = {"zh-Hans", "zh-Hant", "ja", "ru"}
SAFE_EXACT_TOKENS = {
    "Wi-Fi", "E.T.", "NaCl", "DeFi", "Cookie", "Email",
    "Linux", "Windows", "macOS", "Mac", "Android", "iOS",
    "Arial", "Verdana", "Tahoma", "Courier", "Times", "Roboto", "Calibri", "Futura",
    "HTML", "CSS", "JSON", "JS", "IMAP", "SNMP", "LDAP", "SSL", "TLS", "UDP",
    "PageUp", "NumLock", "Forbes", "Yandex", "Sputnik", "Netscape", "Mosaic", "Lynx", "Sleipnir",
}


def split_example_tokens(example: str) -> List[str]:
    return [token.strip() for token in example.split("|") if token.strip()]


def is_obviously_safe_token(token: str) -> bool:
    if token in SAFE_EXACT_TOKENS:
        return True
    if RE_FILE_EXT.fullmatch(token):
        return True
    if RE_ALL_CAPS.fullmatch(token):
        return True
    if RE_CHEM.fullmatch(token):
        return True
    if RE_SHORT_TOKEN.fullmatch(token):
        return True
    return False


def should_force_ok(row: Dict) -> str:
    example = row.get("异常示例", "")
    if not example:
        return ""
    tokens = split_example_tokens(example)
    if not tokens:
        return ""
    if all(is_obviously_safe_token(token) for token in tokens):
        shown = " | ".join(tokens[:4])
        return f"{shown} 属于允许保留的术语/缩写/专名白名单，直接放行。"
    return ""


def should_force_keep(row: Dict, strictness: str) -> str:
    if strictness != "strict":
        return ""
    lang = row.get("语言", "")
    example = row.get("异常示例", "")
    if lang not in LATIN_LANGS_STRICT or not example:
        return ""
    tokens = split_example_tokens(example)
    if not tokens:
        return ""

    forced = []
    for token in tokens:
        if RE_CJK.search(token):
            continue
        if not RE_LATIN.search(token):
            continue
        if is_obviously_safe_token(token):
            continue
        if RE_MOSTLY_LATIN.fullmatch(token):
            forced.append(token)

    if forced:
        shown = " | ".join(forced[:4])
        return f"{lang} 中出现了普通英文词/词组 {shown}，严格模式下默认视为未本地化，直接保留。"
    return ""


def call_api(
    base_url: str,
    api_key: str,
    model: str,
    temperature: float,
    batch: List[Dict],
    include_response_format: bool = True,
) -> Dict:
    request_url = resolve_request_url(base_url)
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": make_user_prompt(batch)},
        ],
    }
    if include_response_format:
        payload["response_format"] = {"type": "json_object"}
    request = urllib.request.Request(
        request_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
    except http.client.IncompleteRead as exc:
        raise RuntimeError(f"incomplete HTTP read: {exc}") from exc
    except http.client.HTTPException as exc:
        raise RuntimeError(f"http protocol error: {exc}") from exc
    except (ConnectionResetError, ssl.SSLError, socket.timeout, TimeoutError) as exc:
        raise RuntimeError(f"network read error: {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"os/network error: {exc}") from exc
    except urllib.error.HTTPError as exc:
        body = read_error_body(exc)
        if include_response_format and "response_format" in body:
            return call_api(base_url, api_key, model, temperature, batch, include_response_format=False)
        raise RuntimeError(f"HTTP {exc.code}: {body or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc
    choices = data.get("choices")
    if not choices:
        base_resp = data.get("base_resp") or {}
        status_code = base_resp.get("status_code")
        status_msg = base_resp.get("status_msg")
        raise RuntimeError(f"unexpected response shape: choices missing; base_resp={status_code}:{status_msg}")
    content = choices[0]["message"]["content"]
    return json.loads(extract_json_text(content))


def validate_results(result: Dict, batch_size: int) -> Dict[int, Dict[str, str]]:
    items = result.get("results")
    if not isinstance(items, list):
        raise ValueError("API result missing results array")
    mapped = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        decision = item.get("decision")
        reason = item.get("reason")
        if not isinstance(index, int) or index < 0 or index >= batch_size:
            continue
        if decision not in {"KEEP", "OK"}:
            continue
        if not isinstance(reason, str) or not reason.strip():
            continue
        mapped[index] = {"decision": decision, "reason": reason.strip()}
    if len(mapped) != batch_size:
        raise ValueError(f"API returned {len(mapped)}/{batch_size} valid judgments")
    return mapped


def progress(message: str, disabled: bool) -> None:
    if not disabled:
        print(message, file=sys.stderr)


def main() -> int:
    args = parse_args()
    try:
        provider = resolve_provider(args)
    except ValueError as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        return 1

    if args.check_config:
        config_source = provider["config_path"] or "(env/default)"
        print(f"[OK] config_source={config_source}")
        print(f"[OK] provider={provider['name']}")
        print(f"[OK] base_url={provider['base_url']}")
        print(f"[OK] model={provider['model']}")
        print(f"[OK] temperature={provider['temperature']}")
        print(f"[OK] strictness={provider['strictness']}")
        print(f"[OK] api_key={provider['api_key_masked']}")
        return 0

    with open(args.input, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    if args.limit is not None:
        rows = rows[:args.limit]

    output_rows = []
    for offset, batch in chunks(rows, args.batch_size):
        progress(f"[INFO] verifying rows {offset + 1}-{offset + len(batch)} / {len(rows)}", args.no_progress_bar)
        last_error = None
        for attempt in range(3):
            try:
                result = call_api(
                    provider["base_url"],
                    provider["api_key"],
                    provider["model"],
                    provider["temperature"],
                    batch,
                )
                decisions = validate_results(result, len(batch))
                for index, row in enumerate(batch):
                    forced_ok_reason = should_force_ok(row)
                    if forced_ok_reason:
                        continue
                    forced_reason = should_force_keep(row, provider["strictness"])
                    if forced_reason:
                        new_row = dict(row)
                        new_row["AI原因"] = forced_reason
                        output_rows.append(new_row)
                        continue
                    decision = decisions[index]
                    if decision["decision"] == "KEEP":
                        new_row = dict(row)
                        new_row["AI原因"] = decision["reason"]
                        output_rows.append(new_row)
                break
            except (RuntimeError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        if last_error and len(output_rows) == 0 and not batch:
            raise last_error

    fieldnames = list(rows[0].keys()) + ["AI原因"] if rows else ["AI原因"]
    with open(args.output, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"[OK] provider={provider['name']} model={provider['model']} kept: {len(output_rows)} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
