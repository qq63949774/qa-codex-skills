#!/usr/bin/env python3
import argparse
import csv
import json
import pathlib
import re
import sys
from typing import Dict, Iterable, List, Optional, Sequence

try:
    from wordfreq import zipf_frequency
except ImportError:  # pragma: no cover
    zipf_frequency = None

CSV_NAME = "language_suspect_entries.csv"
STRUCTURE_CSV_NAME = "language_structure_mismatch.csv"

RE_CJK = re.compile(r"[\u4e00-\u9fff]")
RE_KANA = re.compile(r"[\u3040-\u30ff]")
RE_JA = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
RE_CYRILLIC = re.compile(r"[\u0400-\u04ff]")
RE_LATIN = re.compile(r"[A-Za-z]")
RE_ALL_CAPS_EN_NUM = re.compile(r"^[A-Z0-9]+$")
RE_ANY_DIGIT = re.compile(r"\d")
RE_ALLOWED_SYMBOLS = re.compile(r"^[A-Za-z0-9 .,+/&'()\-:;!?_]+$")

LANGUAGE_ALIASES = {
    "zh-Hans": "zh",
    "zh-Hant": "zh",
    "ja": "ja",
    "ru": "ru",
    "de": "de",
    "es": "es",
    "fr": "fr",
    "it": "it",
    "pt": "pt",
    "default": "en",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan multilingual JSONs for suspect tokens with optional wordfreq filtering."
    )
    parser.add_argument(
        "--data-dir",
        default=".",
        help="Folder containing language subfolders (default: current directory).",
    )
    parser.add_argument(
        "--rules-file",
        default=None,
        help="Optional JSON rules file.",
    )
    parser.add_argument(
        "--check-structure",
        action="store_true",
        help="Check structure counts vs base language and export mismatch CSV.",
    )
    parser.add_argument(
        "--base-lang",
        default=None,
        help="Base language folder to compare structure against. Defaults to rules file or de.",
    )
    parser.add_argument(
        "--min-zipf",
        type=float,
        default=2.2,
        help="Treat common Latin words at or above this zipf threshold as likely valid. Default: 2.2",
    )
    return parser.parse_args()


def load_rules(path: Optional[str]) -> Dict:
    if not path:
        return {}
    rules_path = pathlib.Path(path)
    if not rules_path.exists():
        raise FileNotFoundError(f"rules file not found: {rules_path}")
    with rules_path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("rules file root must be a JSON object")
    return data


def iter_json_files(lang_dir: pathlib.Path) -> Sequence[pathlib.Path]:
    files = list(lang_dir.glob("*.json"))

    def sort_key(path: pathlib.Path):
        try:
            return (0, int(path.stem))
        except ValueError:
            return (1, path.stem)

    return sorted(files, key=sort_key)


def detect_language_dirs(data_dir: pathlib.Path) -> Sequence[pathlib.Path]:
    dirs = [path for path in data_dir.iterdir() if path.is_dir()]
    dirs = [path for path in dirs if list(path.glob("*.json"))]
    return sorted(dirs, key=lambda path: path.name)


def extract_words(entry: dict) -> List[str]:
    words = []
    for key_item in entry.get("key", []):
        if not isinstance(key_item, dict):
            continue
        title = key_item.get("title")
        if isinstance(title, str):
            words.append(title)
        for content_item in key_item.get("content") or []:
            if isinstance(content_item, str):
                words.append(content_item)
    return words


def is_image_word(word: str) -> bool:
    return "#" in word


def entry_structure(entry: dict) -> Dict:
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
        local_name, english_name = next(iter(item.items()))
        if isinstance(local_name, str) and isinstance(english_name, str):
            class_map[local_name] = english_name

    errors = []
    class_counts = {}
    for index, key_item in enumerate(key_list):
        if not isinstance(key_item, dict):
            errors.append(f"key索引{index}非对象")
            continue
        title = key_item.get("title")
        if not isinstance(title, str):
            errors.append(f"key索引{index}缺少title")
            continue
        class_name = class_map.get(title)
        if not class_name:
            errors.append(f"key索引{index}缺少className映射:{title}")
            continue
        if class_name in class_counts:
            errors.append(f"className重复:{class_name}")
        content = key_item.get("content")
        if not isinstance(content, list):
            errors.append(f"key索引{index}content非数组")
            class_counts[class_name] = None
        else:
            class_counts[class_name] = len(content)

    return {
        "key_len": len(key_list),
        "class_len": len(class_map),
        "class_counts": class_counts,
        "errors": errors,
    }


def compile_patterns(items: Iterable[str]) -> List[re.Pattern]:
    patterns = []
    for item in items:
        try:
            patterns.append(re.compile(item))
        except re.error as exc:
            raise ValueError(f"invalid regex in rules: {item} ({exc})") from exc
    return patterns


def build_ignore_config(rules: Dict) -> Dict[str, Dict[str, object]]:
    config = {
        "_global": {
            "words": set(rules.get("ignore_words", []) or []),
            "patterns": compile_patterns(rules.get("ignore_regexes", []) or []),
        }
    }

    per_lang_words = rules.get("per_language_ignore_words", {}) or {}
    per_lang_regexes = rules.get("per_language_ignore_regexes", {}) or {}
    languages = set(per_lang_words) | set(per_lang_regexes)
    for lang in languages:
        config[lang] = {
            "words": set(per_lang_words.get(lang, []) or []),
            "patterns": compile_patterns(per_lang_regexes.get(lang, []) or []),
        }
    return config


def should_ignore_word(word: str, lang: str, ignore_config: Dict[str, Dict[str, object]]) -> bool:
    bucket = ignore_config.get("_global", {})
    if word in bucket.get("words", set()):
        return True
    if any(pattern.search(word) for pattern in bucket.get("patterns", [])):
        return True

    lang_bucket = ignore_config.get(lang, {})
    if word in lang_bucket.get("words", set()):
        return True
    if any(pattern.search(word) for pattern in lang_bucket.get("patterns", [])):
        return True
    return False


def normalized_token(word: str) -> str:
    token = word.strip()
    token = token.replace("’", "'")
    return token


def token_zipf(word: str, lang: str) -> float:
    if zipf_frequency is None:
        return 0.0
    code = LANGUAGE_ALIASES.get(lang, lang.split("-")[0])
    try:
        return float(zipf_frequency(word.lower(), code))
    except Exception:
        return 0.0


def is_common_latin_word(word: str, lang: str, min_zipf: float) -> bool:
    if not RE_LATIN.search(word):
        return False
    if zipf_frequency is None:
        return False

    pieces = re.split(r"[ /|,+()\-:;!?]+", word)
    pieces = [piece for piece in pieces if piece]
    if not pieces:
        return False
    scores = [token_zipf(piece, lang) for piece in pieces]
    return bool(scores) and min(scores) >= min_zipf


def should_skip_due_to_format(word: str) -> bool:
    token = normalized_token(word)
    if RE_ALL_CAPS_EN_NUM.fullmatch(token):
        return True
    if len(token) <= 1 and RE_ALLOWED_SYMBOLS.fullmatch(token):
        return True
    if RE_ANY_DIGIT.search(token) and RE_ALLOWED_SYMBOLS.fullmatch(token):
        return True
    return False


def is_suspicious(word: str, lang: str, min_zipf: float) -> bool:
    token = normalized_token(word)
    if should_skip_due_to_format(token):
        return False

    if lang.startswith("zh"):
        if RE_CJK.search(token):
            return False
        if is_common_latin_word(token, lang, min_zipf):
            return False
        return True

    if lang == "ja":
        if RE_JA.search(token):
            return False
        if is_common_latin_word(token, lang, min_zipf):
            return False
        return True

    if lang == "ru":
        if RE_CYRILLIC.search(token):
            return False
        if is_common_latin_word(token, lang, min_zipf):
            return False
        return True

    has_disallowed_script = RE_CJK.search(token) or RE_KANA.search(token) or RE_CYRILLIC.search(token)
    if has_disallowed_script:
        return True
    return False


def issue_type_for_lang(lang: str) -> str:
    if lang.startswith("zh"):
        return "未包含中文字符(排除图片#词)"
    if lang == "ja":
        return "未包含日文脚本(排除图片#词)"
    if lang == "ru":
        return "未包含西里尔字符(排除图片#词)"
    return "含非本语言脚本(中/日/俄)(排除图片#词)"


def add_structure_issue(structure_rows: List[Dict], lang: str, json_file: pathlib.Path, level_number, entry_index, category: str, issue_type: str, detail: str) -> None:
    structure_rows.append({
        "语言": lang,
        "关卡文件": json_file.name,
        "关卡数": level_number,
        "entry索引": entry_index,
        "分类": category,
        "异常类型": issue_type,
        "详情": detail,
    })


def main() -> int:
    args = parse_args()
    try:
        rules = load_rules(args.rules_file)
    except Exception as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        return 1

    check_structure = args.check_structure or bool(rules.get("check_structure", False))
    base_lang = args.base_lang or rules.get("base_lang", "de")
    ignore_config = build_ignore_config(rules)

    data_dir = pathlib.Path.cwd() / args.data_dir
    if not data_dir.exists() or not data_dir.is_dir():
        print(f"[ERR] data dir not found: {data_dir}", file=sys.stderr)
        return 1

    lang_dirs = detect_language_dirs(data_dir)
    if not lang_dirs:
        print(f"[ERR] no language folders with json files under: {data_dir}", file=sys.stderr)
        return 1

    rows: List[Dict] = []
    structure_rows: List[Dict] = []
    base_files: Dict[str, Dict] = {}
    base_lang_dir = data_dir / base_lang

    if check_structure:
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
                "entries": [entry_structure(entry) for entry in data],
            }

    for lang_dir in lang_dirs:
        lang = lang_dir.name
        for json_file in iter_json_files(lang_dir):
            try:
                level_base = int(json_file.stem)
            except ValueError:
                level_base = None

            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception as exc:
                if check_structure and lang != base_lang:
                    add_structure_issue(structure_rows, lang, json_file, "", "", "", "JSON读取失败", str(exc))
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
                if check_structure and lang != base_lang:
                    add_structure_issue(structure_rows, lang, json_file, "", "", "", "JSON根节点非数组", type(data).__name__)
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

            if check_structure and lang != base_lang:
                base_info = base_files.get(json_file.name)
                if base_info is None:
                    add_structure_issue(structure_rows, lang, json_file, "", "", "", "基准缺少文件", f"{base_lang}中不存在该文件")
                elif "_invalid" in base_info:
                    add_structure_issue(structure_rows, lang, json_file, "", "", "", "基准文件异常", base_info["_invalid"])
                else:
                    base_entry_count = base_info["entry_count"]
                    if len(data) != base_entry_count:
                        add_structure_issue(
                            structure_rows,
                            lang,
                            json_file,
                            "",
                            "",
                            "",
                            "entry数量不一致",
                            f"基准:{base_entry_count} 当前:{len(data)}",
                        )

            for entry_index, entry in enumerate(data):
                level_number = ""
                if level_base is not None:
                    level_number = (level_base - 1) * len(data) + (entry_index + 1)

                if not isinstance(entry, dict):
                    if check_structure and lang != base_lang:
                        add_structure_issue(structure_rows, lang, json_file, level_number, entry_index, "", "entry非对象", type(entry).__name__)
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

                words = [word for word in extract_words(entry) if isinstance(word, str)]
                words_considered = [
                    word for word in words
                    if not is_image_word(word) and not should_ignore_word(word, lang, ignore_config)
                ]
                if not words_considered:
                    continue

                suspicious = [
                    word for word in words_considered
                    if is_suspicious(word, lang, args.min_zipf)
                ]

                if check_structure and lang != base_lang:
                    base_info = base_files.get(json_file.name)
                    if base_info and "_invalid" not in base_info and entry_index < len(base_info["entries"]):
                        base_entry = base_info["entries"][entry_index]
                        cur_entry = entry_structure(entry)
                        if "_invalid" in cur_entry:
                            add_structure_issue(structure_rows, lang, json_file, level_number, entry_index, "", "结构异常", cur_entry["_invalid"])
                        else:
                            if base_entry.get("key_len") != cur_entry.get("key_len"):
                                add_structure_issue(
                                    structure_rows,
                                    lang,
                                    json_file,
                                    level_number,
                                    entry_index,
                                    "",
                                    "key数量不一致",
                                    f"基准:{base_entry.get('key_len')} 当前:{cur_entry.get('key_len')}",
                                )
                            if base_entry.get("class_len") != cur_entry.get("class_len"):
                                add_structure_issue(
                                    structure_rows,
                                    lang,
                                    json_file,
                                    level_number,
                                    entry_index,
                                    "",
                                    "分类数量不一致",
                                    f"基准:{base_entry.get('class_len')} 当前:{cur_entry.get('class_len')}",
                                )
                            if cur_entry.get("errors"):
                                add_structure_issue(
                                    structure_rows,
                                    lang,
                                    json_file,
                                    level_number,
                                    entry_index,
                                    "",
                                    "结构异常",
                                    "; ".join(cur_entry.get("errors", [])),
                                )

                            base_counts = base_entry.get("class_counts", {})
                            cur_counts = cur_entry.get("class_counts", {})
                            base_classes = set(base_counts.keys())
                            cur_classes = set(cur_counts.keys())
                            missing = base_classes - cur_classes
                            extra = cur_classes - base_classes
                            if missing:
                                add_structure_issue(
                                    structure_rows,
                                    lang,
                                    json_file,
                                    level_number,
                                    entry_index,
                                    "",
                                    "分类缺失",
                                    "缺少:" + ",".join(sorted(missing)),
                                )
                            if extra:
                                add_structure_issue(
                                    structure_rows,
                                    lang,
                                    json_file,
                                    level_number,
                                    entry_index,
                                    "",
                                    "多余分类",
                                    "多出:" + ",".join(sorted(extra)),
                                )
                            for class_name in sorted(base_classes & cur_classes):
                                if base_counts.get(class_name) != cur_counts.get(class_name):
                                    add_structure_issue(
                                        structure_rows,
                                        lang,
                                        json_file,
                                        level_number,
                                        entry_index,
                                        class_name,
                                        "content数量不一致",
                                        f"基准:{base_counts.get(class_name)} 当前:{cur_counts.get(class_name)}",
                                    )

                if suspicious:
                    uniq = []
                    seen = set()
                    for word in suspicious:
                        if word not in seen:
                            uniq.append(word)
                            seen.add(word)
                        if len(uniq) >= 6:
                            break

                    rows.append({
                        "语言": lang,
                        "关卡文件": json_file.name,
                        "关卡数": level_number,
                        "entry索引": entry_index,
                        "异常类型": issue_type_for_lang(lang),
                        "异常词数量": len(suspicious),
                        "总词数量": len(words_considered),
                        "异常比例": f"{len(suspicious) / len(words_considered):.2%}",
                        "异常示例": " | ".join(uniq),
                    })

    out_path = pathlib.Path.cwd() / CSV_NAME
    with out_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh,
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

    if check_structure:
        structure_out = pathlib.Path.cwd() / STRUCTURE_CSV_NAME
        with structure_out.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(
                fh,
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

    if zipf_frequency is None:
        print("[WARN] wordfreq not installed, using script heuristics only")
    else:
        print(f"[OK] wordfreq enabled, min_zipf={args.min_zipf}")
    print(f"[OK] rows: {len(rows)} -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
