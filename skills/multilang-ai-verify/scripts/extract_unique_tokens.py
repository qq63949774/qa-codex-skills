#!/usr/bin/env python3
import argparse
import csv
import json
import pathlib
from collections import defaultdict


DEFAULT_OUTPUT = "language_unique_tokens.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract unique non-image tokens from multilingual data.")
    parser.add_argument("--data-dir", required=True, help="Folder containing language subfolders.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help=f"Output CSV path. Default: {DEFAULT_OUTPUT}")
    return parser.parse_args()


def iter_json_files(lang_dir: pathlib.Path):
    files = list(lang_dir.glob("*.json"))

    def sort_key(path: pathlib.Path):
        try:
            return (0, int(path.stem))
        except ValueError:
            return (1, path.stem)

    return sorted(files, key=sort_key)


def add_token(store: dict, lang: str, token: str, json_name: str, entry_index: int, field_type: str) -> None:
    if "#" in token:
        return
    key = (lang, token)
    record = store.get(key)
    if record is None:
        store[key] = {
            "语言": lang,
            "单词": token,
            "出现次数": 1,
            "首次关卡文件": json_name,
            "首次entry索引": entry_index,
            "来源类型": field_type,
        }
        return
    record["出现次数"] += 1


def main() -> int:
    args = parse_args()
    data_dir = pathlib.Path(args.data_dir)
    if not data_dir.exists() or not data_dir.is_dir():
        raise SystemExit(f"[ERR] data dir not found: {data_dir}")

    token_map = {}
    total_tokens = 0

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
                        add_token(token_map, lang, title, json_file.name, entry_index, "title")
                        total_tokens += 1
                    for content_item in key_item.get("content") or []:
                        if isinstance(content_item, str) and "#" not in content_item:
                            add_token(token_map, lang, content_item, json_file.name, entry_index, "content")
                            total_tokens += 1

    rows = sorted(
        token_map.values(),
        key=lambda row: (-int(row["出现次数"]), row["语言"], row["单词"]),
    )

    output_path = pathlib.Path(args.output)
    with output_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["语言", "单词", "出现次数", "首次关卡文件", "首次entry索引", "来源类型"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"[OK] total tokens: {total_tokens}")
    print(f"[OK] unique lang-token pairs: {len(rows)} -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
