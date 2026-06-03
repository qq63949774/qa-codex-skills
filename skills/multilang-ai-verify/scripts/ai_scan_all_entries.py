#!/usr/bin/env python3
import argparse
import csv
import json
import pathlib
import sys
import time
from typing import Dict, List, Sequence

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import deepseek_verify_suspects as shared


ALL_RESULTS_CSV = "language_ai_full_scan_results.csv"
ISSUES_CSV = "language_ai_full_scan_issues.csv"

SYSTEM_PROMPT = """你是多语言本地化 QA 扫描助手。
目标：直接检查每个题目 entry 是否存在明显的语言错误、未本地化、混合脚本污染或不自然的跨语言残留。

判断规则：
1. 如果 entry 中存在明显的其他语言残留、普通词未本地化、混合脚本污染，判定为 ISSUE。
2. 如果只有可接受的专有名词、缩写、文件格式、化学式、协议名、品牌名，判定为 OK。
3. 对于 zh-Hans / zh-Hant / ja / ru，普通英文单词或英文词组默认更偏向 ISSUE。
4. 如果拿不准，优先判 ISSUE。

输出必须是 JSON 对象，格式：
{
  "results": [
    {
      "index": 0,
      "decision": "ISSUE",
      "reason": "一句中文理由",
      "summary": "简短问题摘要"
    }
  ]
}

其中 decision 只能是 ISSUE 或 OK。"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AI directly on every multilingual entry in a data directory.")
    parser.add_argument("--data-dir", required=True, help="Folder containing language subfolders.")
    parser.add_argument("--config", default=None, help="Optional provider config file.")
    parser.add_argument("--provider", choices=sorted(shared.PROVIDERS.keys()), default=None, help="AI provider override.")
    parser.add_argument("--model", default=None, help="Model override.")
    parser.add_argument("--temperature", type=float, default=None, help="Temperature override.")
    parser.add_argument("--strictness", choices=["balanced", "strict"], default=None, help="Strictness override.")
    parser.add_argument("--batch-size", type=int, default=10, help="Entries per request. Default: 10")
    parser.add_argument("--limit", type=int, default=None, help="Optional max entries for smoke tests.")
    parser.add_argument("--output-all", default=None, help="Optional all-results CSV. If omitted, OK rows are not written.")
    parser.add_argument("--output-issues", default=ISSUES_CSV, help=f"Issues-only CSV. Default: {ISSUES_CSV}")
    parser.add_argument("--check-config", action="store_true", help="Resolve config and print effective settings without calling the API.")
    parser.add_argument("--no-progress-bar", action="store_true", help="Suppress progress output.")
    return parser.parse_args()


def iter_json_files(lang_dir: pathlib.Path) -> Sequence[pathlib.Path]:
    files = list(lang_dir.glob("*.json"))

    def sort_key(path: pathlib.Path):
        try:
            return (0, int(path.stem))
        except ValueError:
            return (1, path.stem)

    return sorted(files, key=sort_key)


def is_image_word(text: str) -> bool:
    return "#" in text


def extract_entry_text(entry: Dict) -> str:
    parts = []
    for key_item in entry.get("key", []):
        if not isinstance(key_item, dict):
            continue
        title = key_item.get("title")
        content = key_item.get("content")
        if isinstance(title, str) and is_image_word(title):
            title = None
        if isinstance(content, list):
            filtered_content = [
                item for item in content
                if isinstance(item, str) and not is_image_word(item)
            ]
        else:
            filtered_content = []

        if isinstance(title, str):
            if filtered_content:
                parts.append(f"{title}: {' | '.join(filtered_content)}")
            elif not is_image_word(title):
                parts.append(title)
        elif filtered_content:
            parts.append(" | ".join(filtered_content))
    return "\n".join(parts)


def build_entries(data_dir: pathlib.Path) -> List[Dict]:
    rows = []
    for lang_dir in sorted([path for path in data_dir.iterdir() if path.is_dir()], key=lambda path: path.name):
        lang = lang_dir.name
        for json_file in iter_json_files(lang_dir):
            try:
                file_index = int(json_file.stem)
            except ValueError:
                file_index = None
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception as exc:
                rows.append({
                    "语言": lang,
                    "关卡文件": json_file.name,
                    "关卡数": "",
                    "entry索引": "",
                    "entry文本": "",
                    "AI结论": "ISSUE",
                    "AI原因": f"JSON读取失败: {exc}",
                    "问题摘要": "文件无法读取",
                })
                continue
            if not isinstance(data, list):
                rows.append({
                    "语言": lang,
                    "关卡文件": json_file.name,
                    "关卡数": "",
                    "entry索引": "",
                    "entry文本": "",
                    "AI结论": "ISSUE",
                    "AI原因": f"JSON根节点不是数组: {type(data).__name__}",
                    "问题摘要": "数据结构异常",
                })
                continue
            for entry_index, entry in enumerate(data):
                level_number = ""
                if file_index is not None:
                    level_number = (file_index - 1) * len(data) + (entry_index + 1)
                entry_text = extract_entry_text(entry) if isinstance(entry, dict) else str(entry)
                if not entry_text.strip():
                    rows.append({
                        "语言": lang,
                        "关卡文件": json_file.name,
                        "关卡数": level_number,
                        "entry索引": entry_index,
                        "entry文本": "",
                        "AI结论": "SKIP",
                        "AI原因": "过滤掉带 # 的图片 token 后，该 entry 已无可分析文本。",
                        "问题摘要": "仅图片内容，跳过 AI",
                    })
                    continue
                rows.append({
                    "语言": lang,
                    "关卡文件": json_file.name,
                    "关卡数": level_number,
                    "entry索引": entry_index,
                    "entry文本": entry_text,
                })
    return rows


def make_user_prompt(batch: List[Dict]) -> str:
    items = []
    for index, row in enumerate(batch):
        items.append({
            "index": index,
            "语言": row.get("语言", ""),
            "关卡文件": row.get("关卡文件", ""),
            "关卡数": row.get("关卡数", ""),
            "entry索引": row.get("entry索引", ""),
            "entry文本": row.get("entry文本", ""),
        })
    return "请逐条判断这些题目 entry 是否存在真实本地化问题：\n" + json.dumps(items, ensure_ascii=False, indent=2)


def call_api(provider: Dict[str, str], batch: List[Dict]) -> Dict:
    request_url = shared.resolve_request_url(provider["base_url"])
    payload = {
        "model": provider["model"],
        "temperature": provider["temperature"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": make_user_prompt(batch)},
        ],
        "response_format": {"type": "json_object"},
    }
    request = shared.urllib.request.Request(
        request_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {provider['api_key']}",
        },
        method="POST",
    )
    try:
        with shared.urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
    except shared.urllib.error.HTTPError as exc:
        body = shared.read_error_body(exc)
        if "response_format" in body:
            payload.pop("response_format", None)
            request = shared.urllib.request.Request(
                request_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {provider['api_key']}",
                },
                method="POST",
            )
            with shared.urllib.request.urlopen(request, timeout=180) as response:
                data = json.loads(response.read().decode("utf-8"))
        else:
            raise RuntimeError(f"HTTP {exc.code}: {body or exc.reason}") from exc
    except shared.urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc

    choices = data.get("choices")
    if not choices:
        base_resp = data.get("base_resp") or {}
        raise RuntimeError(f"unexpected response shape: choices missing; base_resp={base_resp}")
    content = choices[0]["message"]["content"]
    return json.loads(shared.extract_json_text(content))


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
        summary = item.get("summary")
        if not isinstance(index, int) or index < 0 or index >= batch_size:
            continue
        if decision not in {"ISSUE", "OK"}:
            continue
        if not isinstance(reason, str) or not reason.strip():
            continue
        mapped[index] = {
            "decision": decision,
            "reason": reason.strip(),
            "summary": summary.strip() if isinstance(summary, str) and summary.strip() else "",
        }
    if len(mapped) != batch_size:
        raise ValueError(f"API returned {len(mapped)}/{batch_size} valid judgments")
    return mapped


def chunks(rows: List[Dict], size: int):
    for start in range(0, len(rows), size):
        yield start, rows[start:start + size]


def main() -> int:
    args = parse_args()
    try:
        provider = shared.resolve_provider(args)
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

    data_dir = pathlib.Path(args.data_dir)
    if not data_dir.exists() or not data_dir.is_dir():
        print(f"[ERR] data dir not found: {data_dir}", file=sys.stderr)
        return 1

    rows = build_entries(data_dir)
    if args.limit is not None:
        rows = rows[:args.limit]

    all_results = []
    issues = []
    prefilled_rows = [row for row in rows if row.get("AI结论")]
    ai_rows = [row for row in rows if not row.get("AI结论")]

    for row in prefilled_rows:
        all_results.append(row)
        if row["AI结论"] == "ISSUE":
            issues.append(row)

    for offset, batch in chunks(ai_rows, args.batch_size):
        shared.progress(f"[INFO] scanning entries {offset + 1}-{offset + len(batch)} / {len(rows)}", args.no_progress_bar)
        for attempt in range(3):
            try:
                result = call_api(provider, batch)
                decisions = validate_results(result, len(batch))
                for index, row in enumerate(batch):
                    decision = decisions[index]
                    new_row = dict(row)
                    new_row["AI结论"] = decision["decision"]
                    new_row["AI原因"] = decision["reason"]
                    new_row["问题摘要"] = decision["summary"]
                    all_results.append(new_row)
                    if decision["decision"] == "ISSUE":
                        issues.append(new_row)
                break
            except (RuntimeError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))

    fieldnames = ["语言", "关卡文件", "关卡数", "entry索引", "entry文本", "AI结论", "AI原因", "问题摘要"]
    if args.output_all:
        with open(args.output_all, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_results)
    with open(args.output_issues, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(issues)

    if args.output_all:
        print(f"[OK] provider={provider['name']} model={provider['model']} all_rows: {len(all_results)} -> {args.output_all}")
    print(f"[OK] issue_rows: {len(issues)} -> {args.output_issues}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
