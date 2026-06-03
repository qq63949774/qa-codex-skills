#!/usr/bin/env python3
import argparse
import csv
import json
import pathlib
import sys
import time
from collections import defaultdict
from typing import Dict, List, Sequence, Tuple

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import deepseek_verify_suspects as shared


TOKEN_ISSUES_CSV = "language_unique_token_issues.csv"
TOKEN_HITS_CSV = "language_unique_token_hits.csv"

SYSTEM_PROMPT = """你是多语言词条 QA 扫描助手。
目标：对给定语言的一组去重单词进行快速判断，找出“不属于当前语言”的词。

判定规则：
1. 如果词明显属于别的语言、明显未本地化、或混合脚本污染，判 ISSUE。
2. 如果词是当前语言正常词，判 OK。
3. 如果词是明显的专有名词、常见缩写、化学式、文件格式、字体名、协议名、品牌名，可判 OK。
4. 对 zh-Hans / zh-Hant / ja / ru 这类语言，如果是普通英文单词或英文词组，默认更偏向 ISSUE。
5. 如果拿不准，优先判 ISSUE。

为了提高速度，只返回判定为 ISSUE 的项目，OK 的项目不要输出。

输出必须是 JSON 对象，格式：
{
  "results": [
    {
      "index": 0,
      "decision": "ISSUE",
      "reason": "一句中文理由"
    }
  ]
}

其中：
1. `results` 里只放 ISSUE 项。
2. 没有出现在 `results` 里的 index 一律视为 OK。
3. `decision` 固定写 ISSUE。"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AI on deduplicated language+token pairs, then map issues back to files.")
    parser.add_argument("--data-dir", required=True, help="Folder containing language subfolders.")
    parser.add_argument("--config", default=None, help="Optional provider config file.")
    parser.add_argument("--provider", choices=sorted(shared.PROVIDERS.keys()), default=None, help="AI provider override.")
    parser.add_argument("--model", default=None, help="Model override.")
    parser.add_argument("--temperature", type=float, default=None, help="Temperature override.")
    parser.add_argument("--strictness", choices=["balanced", "strict"], default=None, help="Strictness override.")
    parser.add_argument("--batch-size", type=int, default=100, help="Max unique tokens per request. Default: 100")
    parser.add_argument("--max-chars-per-batch", type=int, default=3000, help="Approx max joined token chars per request. Default: 3000")
    parser.add_argument("--limit", type=int, default=None, help="Optional max unique tokens for smoke tests.")
    parser.add_argument("--output-token-issues", default=TOKEN_ISSUES_CSV, help=f"Token-level issues CSV. Default: {TOKEN_ISSUES_CSV}")
    parser.add_argument("--output-token-hits", default=TOKEN_HITS_CSV, help=f"Expanded file-hit CSV. Default: {TOKEN_HITS_CSV}")
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


def add_occurrence(index_map: Dict[Tuple[str, str], Dict], lang: str, token: str, json_name: str, entry_index: int, field_type: str) -> None:
    if "#" in token:
        return
    key = (lang, token)
    record = index_map.get(key)
    if record is None:
        record = {
            "语言": lang,
            "单词": token,
            "出现次数": 0,
            "来源类型": set(),
            "命中文件": [],
        }
        index_map[key] = record
    record["出现次数"] += 1
    record["来源类型"].add(field_type)
    record["命中文件"].append({
        "关卡文件": json_name,
        "entry索引": entry_index,
        "来源类型": field_type,
    })


def build_unique_token_index(data_dir: pathlib.Path) -> Dict[Tuple[str, str], Dict]:
    index_map: Dict[Tuple[str, str], Dict] = {}
    for lang_dir in sorted([path for path in data_dir.iterdir() if path.is_dir()], key=lambda path: path.name):
        lang = lang_dir.name
        for json_file in iter_json_files(lang_dir):
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                continue
            for entry_index, entry in enumerate(data):
                if not isinstance(entry, dict):
                    continue
                for key_item in entry.get("key", []):
                    if not isinstance(key_item, dict):
                        continue
                    title = key_item.get("title")
                    if isinstance(title, str) and "#" not in title:
                        add_occurrence(index_map, lang, title, json_file.name, entry_index, "title")
                    for content_item in key_item.get("content") or []:
                        if isinstance(content_item, str) and "#" not in content_item:
                            add_occurrence(index_map, lang, content_item, json_file.name, entry_index, "content")
    return index_map


def make_user_prompt(lang: str, batch: List[Dict]) -> str:
    items = []
    for index, row in enumerate(batch):
        items.append({
            "index": index,
            "单词": row["单词"],
        })
    payload = {
        "语言": lang,
        "单词列表": items,
    }
    return "请逐条判断这些单词是否不属于当前语言：\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def call_api(provider: Dict[str, str], lang: str, batch: List[Dict]) -> Dict:
    request_url = shared.resolve_request_url(provider["base_url"])
    payload = {
        "model": provider["model"],
        "temperature": provider["temperature"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": make_user_prompt(lang, batch)},
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
    return json.loads(shared.extract_json_text(choices[0]["message"]["content"]))


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
        if decision != "ISSUE":
            continue
        if not isinstance(reason, str) or not reason.strip():
            continue
        mapped[index] = {"decision": decision, "reason": reason.strip()}
    return mapped


def language_chunks(rows: List[Dict], max_items: int, max_chars: int):
    batch = []
    batch_lang = ""
    batch_chars = 0
    start = 0

    for index, row in enumerate(rows):
        row_lang = row["语言"]
        token = row["单词"]
        token_chars = len(token) + 8

        if not batch:
            batch = [row]
            batch_lang = row_lang
            batch_chars = token_chars
            start = index
            continue

        should_flush = (
            row_lang != batch_lang
            or len(batch) >= max_items
            or batch_chars + token_chars > max_chars
        )
        if should_flush:
            yield start, batch_lang, batch
            batch = [row]
            batch_lang = row_lang
            batch_chars = token_chars
            start = index
            continue

        batch.append(row)
        batch_chars += token_chars

    if batch:
        yield start, batch_lang, batch


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

    index_map = build_unique_token_index(data_dir)
    unique_rows = []
    for record in index_map.values():
        row = {
            "语言": record["语言"],
            "单词": record["单词"],
            "出现次数": record["出现次数"],
            "来源类型": "|".join(sorted(record["来源类型"])),
        }
        unique_rows.append(row)

    unique_rows.sort(key=lambda row: (row["语言"], row["单词"]))
    if args.limit is not None:
        unique_rows = unique_rows[:args.limit]

    token_issues = []
    token_hits = []

    batches = list(language_chunks(unique_rows, args.batch_size, args.max_chars_per_batch))

    for batch_index, (offset, lang, batch) in enumerate(batches, start=1):
        approx_chars = sum(len(row["单词"]) for row in batch)
        shared.progress(
            f"[INFO] scanning batch {batch_index}/{len(batches)} lang={lang} tokens={offset + 1}-{offset + len(batch)} / {len(unique_rows)} items={len(batch)} chars~{approx_chars}",
            args.no_progress_bar,
        )
        for attempt in range(3):
            try:
                started_at = time.time()
                shared.progress(
                    f"[INFO] request start batch={batch_index} attempt={attempt + 1} lang={lang} items={len(batch)}",
                    args.no_progress_bar,
                )
                result = call_api(provider, lang, batch)
                elapsed = time.time() - started_at
                shared.progress(
                    f"[INFO] request done batch={batch_index} attempt={attempt + 1} lang={lang} elapsed={elapsed:.1f}s",
                    args.no_progress_bar,
                )
                decisions = validate_results(result, len(batch))
                for index, row in enumerate(batch):
                    decision = decisions.get(index, {"decision": "OK", "reason": ""})
                    if decision["decision"] != "ISSUE":
                        continue
                    issue_row = dict(row)
                    issue_row["AI原因"] = decision["reason"]
                    token_issues.append(issue_row)

                    record = index_map[(row["语言"], row["单词"])]
                    for hit in record["命中文件"]:
                        token_hits.append({
                            "语言": row["语言"],
                            "单词": row["单词"],
                            "出现次数": row["出现次数"],
                            "AI原因": decision["reason"],
                            "关卡文件": hit["关卡文件"],
                            "entry索引": hit["entry索引"],
                            "来源类型": hit["来源类型"],
                        })
                break
            except (RuntimeError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
                elapsed = time.time() - started_at
                shared.progress(
                    f"[WARN] request failed batch={batch_index} attempt={attempt + 1} lang={lang} elapsed={elapsed:.1f}s err={exc}",
                    args.no_progress_bar,
                )
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))

    with open(args.output_token_issues, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["语言", "单词", "出现次数", "来源类型", "AI原因"],
        )
        writer.writeheader()
        writer.writerows(token_issues)

    with open(args.output_token_hits, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["语言", "单词", "出现次数", "AI原因", "关卡文件", "entry索引", "来源类型"],
        )
        writer.writeheader()
        writer.writerows(token_hits)

    print(f"[OK] provider={provider['name']} model={provider['model']} token_issue_rows: {len(token_issues)} -> {args.output_token_issues}")
    print(f"[OK] expanded_hit_rows: {len(token_hits)} -> {args.output_token_hits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
