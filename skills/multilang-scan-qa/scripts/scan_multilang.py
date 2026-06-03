#!/usr/bin/env python3
import argparse
import csv
import json
import pathlib
import re
import sys

RE_CJK = re.compile(r"[\u4e00-\u9fff]")
RE_KANA = re.compile(r"[\u3040-\u30ff]")
RE_JA = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
RE_CYRILLIC = re.compile(r"[\u0400-\u04ff]")
RE_ALL_CAPS_EN_NUM = re.compile(r"^[A-Z0-9]+$")

CSV_NAME = "language_suspect_entries.csv"
STRUCTURE_CSV_NAME = "language_structure_mismatch.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan multilingual JSONs for non-local language words (exclude # image tokens)."
    )
    parser.add_argument(
        "--data-dir",
        default="Mix多语言700关卡",
        help="Folder containing language subfolders (default: Mix多语言700关卡)",
    )
    parser.add_argument(
        "--check-structure",
        action="store_true",
        help="Check structure counts vs base language and export mismatch CSV",
    )
    parser.add_argument(
        "--base-lang",
        default="de",
        help="Base language folder to compare structure against (default: de)",
    )
    return parser.parse_args()


def iter_json_files(lang_dir: pathlib.Path):
    files = list(lang_dir.glob("*.json"))
    def sort_key(p: pathlib.Path):
        try:
            return int(p.stem)
        except ValueError:
            return p.stem
    return sorted(files, key=sort_key)


def extract_words(entry: dict):
    words = []
    for k in entry.get("key", []):
        if not isinstance(k, dict):
            continue
        title = k.get("title")
        if isinstance(title, str):
            words.append(title)
        for c in k.get("content") or []:
            if isinstance(c, str):
                words.append(c)
    return words


def is_image_word(word: str) -> bool:
    return "#" in word


def entry_structure(entry: dict):
    if not isinstance(entry, dict):
        return {"_invalid": f"entry非对象:{type(entry).__name__}"}
    key_list = entry.get("key")
    if not isinstance(key_list, list):
        return {"_invalid": "key非数组"}
    class_list = entry.get("className")
    if not isinstance(class_list, list):
        return {"_invalid": "className非数组"}

    class_map = {}
    for item in class_list:
        if not isinstance(item, dict) or len(item) != 1:
            continue
        local, en = next(iter(item.items()))
        if isinstance(local, str) and isinstance(en, str):
            class_map[local] = en

    errors = []
    class_counts = {}
    for idx, k in enumerate(key_list):
        if not isinstance(k, dict):
            errors.append(f"key索引{idx}非对象")
            continue
        title = k.get("title")
        if not isinstance(title, str):
            errors.append(f"key索引{idx}缺少title")
            continue
        class_name = class_map.get(title)
        if not class_name:
            errors.append(f"key索引{idx}缺少className映射:{title}")
            continue
        if class_name in class_counts:
            errors.append(f"className重复:{class_name}")
        content = k.get("content")
        if not isinstance(content, list):
            errors.append(f"key索引{idx}content非数组")
            class_counts[class_name] = None
        else:
            class_counts[class_name] = len(content)

    return {
        "key_len": len(key_list),
        "class_len": len(class_map),
        "class_counts": class_counts,
        "errors": errors,
    }


def main() -> int:
    args = parse_args()
    data_dir = pathlib.Path.cwd() / args.data_dir
    if not data_dir.exists() or not data_dir.is_dir():
        print(f"[ERR] data dir not found: {data_dir}", file=sys.stderr)
        return 1

    lang_dirs = sorted([p for p in data_dir.iterdir() if p.is_dir()])
    if not lang_dirs:
        print(f"[ERR] no language folders under: {data_dir}", file=sys.stderr)
        return 1

    rows = []
    structure_rows = []
    base_lang_dir = data_dir / args.base_lang
    base_files = {}
    if args.check_structure:
        if not base_lang_dir.exists() or not base_lang_dir.is_dir():
            print(f"[ERR] base lang dir not found: {base_lang_dir}", file=sys.stderr)
            return 1
        for json_file in iter_json_files(base_lang_dir):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception as exc:
                base_files[json_file.name] = {"_invalid": f"JSON读取失败:{exc}"}
                continue
            if not isinstance(data, list):
                base_files[json_file.name] = {"_invalid": "JSON根节点非数组"}
                continue
            base_files[json_file.name] = {
                "entry_count": len(data),
                "entries": [entry_structure(e) for e in data],
            }

    for lang_dir in lang_dirs:
        lang = lang_dir.name
        for json_file in iter_json_files(lang_dir):
            level_base = None
            try:
                level_base = int(json_file.stem)
            except ValueError:
                level_base = None
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception as exc:
                # Skip unreadable files but record an error row
                if args.check_structure and lang != args.base_lang:
                        structure_rows.append({
                            "语言": lang,
                            "关卡文件": json_file.name,
                            "关卡数": "",
                            "entry索引": "",
                            "分类": "",
                            "异常类型": "JSON读取失败",
                            "详情": str(exc),
                        })
                rows.append({
                    "语言": lang,
                    "关卡文件": json_file.name,
                    "关卡数": "",
                    "entry索引": "",
                    "异常类型": "JSON读取失败",
                    "异常词数量": "",
                    "总词数量": "",
                    "异常比例": "",
                    "异常示例": str(exc),
                })
                continue

            if not isinstance(data, list):
                if args.check_structure and lang != args.base_lang:
                    structure_rows.append({
                        "语言": lang,
                        "关卡文件": json_file.name,
                        "关卡数": "",
                        "entry索引": "",
                        "分类": "",
                        "异常类型": "JSON根节点非数组",
                        "详情": type(data).__name__,
                    })
                rows.append({
                    "语言": lang,
                    "关卡文件": json_file.name,
                    "关卡数": "",
                    "entry索引": "",
                    "异常类型": "JSON根节点非数组",
                    "异常词数量": "",
                    "总词数量": "",
                    "异常比例": "",
                    "异常示例": type(data).__name__,
                })
                continue

            if args.check_structure and lang != args.base_lang:
                base_info = base_files.get(json_file.name)
                if base_info is None:
                    structure_rows.append({
                        "语言": lang,
                        "关卡文件": json_file.name,
                        "关卡数": "",
                        "entry索引": "",
                        "分类": "",
                        "异常类型": "基准缺少文件",
                        "详情": f"{args.base_lang}中不存在该文件",
                    })
                elif "_invalid" in base_info:
                    structure_rows.append({
                        "语言": lang,
                        "关卡文件": json_file.name,
                        "关卡数": "",
                        "entry索引": "",
                        "分类": "",
                        "异常类型": "基准文件异常",
                        "详情": base_info["_invalid"],
                    })
                else:
                    base_entry_count = base_info["entry_count"]
                    if len(data) != base_entry_count:
                        structure_rows.append({
                            "语言": lang,
                            "关卡文件": json_file.name,
                            "关卡数": "",
                            "entry索引": "",
                            "分类": "",
                            "异常类型": "entry数量不一致",
                            "详情": f"基准:{base_entry_count} 当前:{len(data)}",
                        })

            for entry_index, entry in enumerate(data):
                level_number = ""
                if level_base is not None:
                    level_number = (level_base - 1) * len(data) + (entry_index + 1)

                if not isinstance(entry, dict):
                    if args.check_structure and lang != args.base_lang:
                        structure_rows.append({
                            "语言": lang,
                            "关卡文件": json_file.name,
                            "关卡数": level_number,
                            "entry索引": entry_index,
                            "分类": "",
                            "异常类型": "entry非对象",
                            "详情": type(entry).__name__,
                        })
                    rows.append({
                        "语言": lang,
                        "关卡文件": json_file.name,
                        "关卡数": level_number,
                        "entry索引": entry_index,
                        "异常类型": "entry非对象",
                        "异常词数量": "",
                        "总词数量": "",
                        "异常比例": "",
                        "异常示例": type(entry).__name__,
                    })
                    continue

                words = [w for w in extract_words(entry) if isinstance(w, str)]
                # exclude image words
                words_considered = [w for w in words if not is_image_word(w)]
                if not words_considered:
                    continue

                suspicious = []
                issue_type = None

                if lang.startswith("zh"):
                    for w in words_considered:
                        if RE_ALL_CAPS_EN_NUM.fullmatch(w):
                            continue
                        if not RE_CJK.search(w):
                            suspicious.append(w)
                    if suspicious:
                        issue_type = "未包含中文字符(排除图片#词)"
                elif lang == "ja":
                    for w in words_considered:
                        if RE_ALL_CAPS_EN_NUM.fullmatch(w):
                            continue
                        if not RE_JA.search(w):
                            suspicious.append(w)
                    if suspicious:
                        issue_type = "未包含日文脚本(排除图片#词)"
                elif lang == "ru":
                    for w in words_considered:
                        if RE_ALL_CAPS_EN_NUM.fullmatch(w):
                            continue
                        if not RE_CYRILLIC.search(w):
                            suspicious.append(w)
                    if suspicious:
                        issue_type = "未包含西里尔字符(排除图片#词)"
                else:
                    for w in words_considered:
                        if RE_ALL_CAPS_EN_NUM.fullmatch(w):
                            continue
                        if RE_CJK.search(w) or RE_KANA.search(w) or RE_CYRILLIC.search(w):
                            suspicious.append(w)
                    if suspicious:
                        issue_type = "含非本语言脚本(中/日/俄)(排除图片#词)"

                if args.check_structure and lang != args.base_lang:
                    base_info = base_files.get(json_file.name)
                    if base_info and "_invalid" not in base_info:
                        if entry_index < len(base_info["entries"]):
                            base_entry = base_info["entries"][entry_index]
                            cur_entry = entry_structure(entry)
                            if "_invalid" in cur_entry:
                                structure_rows.append({
                                    "语言": lang,
                                    "关卡文件": json_file.name,
                                    "关卡数": level_number,
                                    "entry索引": entry_index,
                                    "分类": "",
                                    "异常类型": "结构异常",
                                    "详情": cur_entry["_invalid"],
                                })
                            else:
                                if base_entry.get("key_len") != cur_entry.get("key_len"):
                                    structure_rows.append({
                                        "语言": lang,
                                        "关卡文件": json_file.name,
                                        "关卡数": level_number,
                                        "entry索引": entry_index,
                                        "分类": "",
                                        "异常类型": "key数量不一致",
                                        "详情": f"基准:{base_entry.get('key_len')} 当前:{cur_entry.get('key_len')}",
                                    })
                                if base_entry.get("class_len") != cur_entry.get("class_len"):
                                    structure_rows.append({
                                        "语言": lang,
                                        "关卡文件": json_file.name,
                                        "关卡数": level_number,
                                        "entry索引": entry_index,
                                        "分类": "",
                                        "异常类型": "分类数量不一致",
                                        "详情": f"基准:{base_entry.get('class_len')} 当前:{cur_entry.get('class_len')}",
                                    })
                                if cur_entry.get("errors"):
                                    structure_rows.append({
                                        "语言": lang,
                                        "关卡文件": json_file.name,
                                        "关卡数": level_number,
                                        "entry索引": entry_index,
                                        "分类": "",
                                        "异常类型": "结构异常",
                                        "详情": "; ".join(cur_entry.get("errors", [])),
                                    })

                                base_counts = base_entry.get("class_counts", {})
                                cur_counts = cur_entry.get("class_counts", {})
                                base_classes = set(base_counts.keys())
                                cur_classes = set(cur_counts.keys())
                                missing = base_classes - cur_classes
                                extra = cur_classes - base_classes
                                if missing:
                                    structure_rows.append({
                                        "语言": lang,
                                        "关卡文件": json_file.name,
                                        "关卡数": level_number,
                                        "entry索引": entry_index,
                                        "分类": "",
                                        "异常类型": "分类缺失",
                                        "详情": "缺少:" + ",".join(sorted(missing)),
                                    })
                                if extra:
                                    structure_rows.append({
                                        "语言": lang,
                                        "关卡文件": json_file.name,
                                        "关卡数": level_number,
                                        "entry索引": entry_index,
                                        "分类": "",
                                        "异常类型": "多余分类",
                                        "详情": "多出:" + ",".join(sorted(extra)),
                                    })
                                for class_name in sorted(base_classes & cur_classes):
                                    if base_counts.get(class_name) != cur_counts.get(class_name):
                                        structure_rows.append({
                                            "语言": lang,
                                            "关卡文件": json_file.name,
                                            "关卡数": level_number,
                                            "entry索引": entry_index,
                                            "分类": class_name,
                                            "异常类型": "content数量不一致",
                                            "详情": f"基准:{base_counts.get(class_name)} 当前:{cur_counts.get(class_name)}",
                                        })

                if suspicious:
                    uniq = []
                    seen = set()
                    for w in suspicious:
                        if w not in seen:
                            uniq.append(w)
                            seen.add(w)
                        if len(uniq) >= 6:
                            break

                    rows.append({
                        "语言": lang,
                        "关卡文件": json_file.name,
                        "关卡数": level_number,
                        "entry索引": entry_index,
                        "异常类型": issue_type,
                        "异常词数量": len(suspicious),
                        "总词数量": len(words_considered),
                        "异常比例": f"{len(suspicious) / len(words_considered):.2%}",
                        "异常示例": " | ".join(uniq),
                    })

    out_path = pathlib.Path.cwd() / CSV_NAME
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "语言",
                "关卡文件",
                "关卡数",
                "entry索引",
                "异常类型",
                "异常词数量",
                "总词数量",
                "异常比例",
                "异常示例",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    if args.check_structure:
        structure_out = pathlib.Path.cwd() / STRUCTURE_CSV_NAME
        with structure_out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "语言",
                    "关卡文件",
                    "关卡数",
                    "entry索引",
                    "分类",
                    "异常类型",
                    "详情",
                ],
            )
            writer.writeheader()
            writer.writerows(structure_rows)
        print(f"[OK] structure rows: {len(structure_rows)} -> {structure_out}")

    print(f"[OK] rows: {len(rows)} -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
