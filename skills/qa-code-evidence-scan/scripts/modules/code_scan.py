#!/usr/bin/env python3
"""Code-evidence scan core for testcase CSV."""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_REASON_LEN = 50
DEFAULT_MAX_FILE_SIZE = 1_500_000
AI_OUTPUT_COLUMNS = [
    "AI测试结果",
    "AI判定原因",
    "AI测试用例通过率",
]
UNUSED_AI_COLUMNS = {
    "AI判定通过原因",
    "AI证据文件",
    "AI证据行号",
    "AI证据关键词",
    "AI置信度",
    "AI置信等级",
}

IGNORE_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "out",
    ".next",
    ".nuxt",
    ".idea",
    ".vscode",
    "__pycache__",
    "qareports",
    "reports",
    "report",
    "output",
    "outputs",
    "testcases",
    "testcase",
    "generated",
    "docs",
    "doc",
    "vendor",
    "vendors",
    "package",
    "packages",
    "plugin",
    "plugins",
    "third",
    "third_party",
    "third-party",
}

CODE_EXTS = {
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".py",
    ".java",
    ".kt",
    ".swift",
    ".m",
    ".mm",
    ".go",
    ".rs",
    ".cpp",
    ".cc",
    ".c",
    ".h",
    ".hpp",
    ".cs",
    ".php",
    ".rb",
    ".lua",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".xml",
    ".gradle",
    ".properties",
}

STOPWORDS = {
    "验证",
    "规则",
    "功能",
    "流程",
    "显示",
    "状态",
    "页面",
    "内容",
    "数据",
    "用户",
    "支持",
    "默认",
    "配置",
    "测试",
    "用例",
    "模块",
    "逻辑",
}

KEYWORD_EXPANSIONS = {
    "巅峰赛": ["pinnacle", "contest", "challenge"],
    "开放": ["open", "start", "end", "schedule"],
    "挑战": ["challenge", "contest"],
    "排行": ["rank", "ranking", "leaderboard"],
    "榜单": ["rank", "leaderboard"],
    "连胜": ["streak", "win_streak"],
    "道具": ["item", "prop", "booster", "tool"],
    "广告": ["ad", "reward", "incentive", "video"],
    "步数": ["step", "move"],
    "题库": ["level", "pool", "question", "pinnacle_level"],
    "去重": ["dedup", "unique", "duplicate"],
    "解锁": ["unlock", "unlock_level", "level_requirement"],
    "埋点": ["event", "track", "analytics", "log", "moveuse"],
    "金币": ["coin", "gold", "piggy"],
    "存钱罐": ["piggy", "bank", "coin"],
    "时间": ["time", "timer", "duration"],
    "小球": ["ball", "bubble", "item", "cell"],
    "合并": ["merge", "combine", "match"],
    "锁定": ["lock", "target", "select"],
    "重叠": ["overlap", "intersect", "collision"],
    "进度": ["progress", "finish"],
    "关卡": ["level", "stage"],
    "难度": ["difficulty", "diff"],
    "循环": ["loop", "repeat"],
    "放大镜": ["magnifier", "find", "finder", "hint"],
    "提示": ["hint", "tip", "guide"],
    "冰冻": ["freeze", "frozen"],
    "新手引导": ["guide", "tutorial", "hand"],
    "震动": ["vibrate", "vibration", "haptic"],
    "音效": ["audio", "sound", "sfx"],
    "动画": ["animation", "anim", "tween"],
}


@dataclass
class CodeFile:
    rel_path: str
    content: str
    content_lower: str


@dataclass
class Evidence:
    path: str
    keywords: list[str]
    line: int
    anchor_kind: str
    anchor_value: str


def truncate_chars(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len]


def should_scan_file(path: Path, max_size: int) -> bool:
    if path.suffix.lower() not in CODE_EXTS:
        return False
    try:
        if path.stat().st_size > max_size:
            return False
    except OSError:
        return False
    return True


def collect_code_files(project_root: Path, max_size: int) -> list[CodeFile]:
    files: list[CodeFile] = []
    for path in project_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if not should_scan_file(path, max_size):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not text or "\x00" in text:
            continue
        rel = str(path.relative_to(project_root))
        files.append(CodeFile(rel_path=rel, content=text, content_lower=text.lower()))
    return files


def extract_terms(text: str) -> list[str]:
    if not text:
        return []
    cn_terms = re.findall(r"[一-鿿]{2,}", text)
    en_terms = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text)
    raw = cn_terms + [term.lower() for term in en_terms]

    result: list[str] = []
    seen: set[str] = set()
    for token in raw:
        term = token.strip().lower()
        if not term or term in STOPWORDS:
            continue
        if term not in seen:
            seen.add(term)
            result.append(term)
    return result


def build_case_keywords(row: dict[str, str]) -> list[str]:
    source = " ".join(
        [
            row.get("测试内容", ""),
            row.get("测试目的", ""),
            row.get("前置条件", ""),
            row.get("操作步骤", ""),
            row.get("期望结果", ""),
            row.get("需求模块", ""),
        ]
    )
    base_terms = extract_terms(source)
    keywords: list[str] = []
    seen: set[str] = set()

    for term in base_terms:
        if term not in seen:
            seen.add(term)
            keywords.append(term)
        for expansion in KEYWORD_EXPANSIONS.get(term, []):
            key = expansion.lower()
            if key not in seen:
                seen.add(key)
                keywords.append(key)

    return keywords


def extract_structured_anchors(row: dict[str, str]) -> list[str]:
    source = " ".join(
        [
            row.get("新增参数", ""),
            row.get("测试内容", ""),
            row.get("测试目的", ""),
            row.get("需求模块", ""),
        ]
    )
    anchors: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", source):
        lower = token.lower()
        if lower in STOPWORDS:
            continue
        if lower not in seen:
            seen.add(lower)
            anchors.append(token)
    return anchors


def anchor_kind_for_file(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".json":
        return "key"
    if suffix in {".yaml", ".yml", ".toml", ".ini", ".xml", ".properties"}:
        return "config"
    return "symbol"


def find_line_for_terms(content: str, terms: list[str]) -> tuple[int, str]:
    lowered_terms = [term.lower() for term in terms if term]
    for line_no, line in enumerate(content.splitlines(), start=1):
        lower_line = line.lower()
        for term in lowered_terms:
            if term in lower_line:
                return line_no, term
    return 1, lowered_terms[0] if lowered_terms else "evidence"


def score_confidence(keyword_count: int, file_path: str) -> str:
    lower_path = file_path.lower()
    non_business_hints = ("package", "library", "vendor", "plugin", "third")
    if any(hint in lower_path for hint in non_business_hints):
        return "Low"
    if keyword_count >= 3:
        return "High"
    if keyword_count >= 2:
        return "Medium"
    return "Low"


def find_best_evidence(row: dict[str, str], files: list[CodeFile], min_hits: int) -> tuple[bool, Evidence | None]:
    keywords = build_case_keywords(row)
    anchors = extract_structured_anchors(row)
    if not keywords:
        return False, None

    best_path = ""
    best_hits: list[str] = []
    best_count = 0
    best_file: CodeFile | None = None

    for code_file in files:
        anchor_hits = [anchor for anchor in anchors if anchor.lower() in code_file.content_lower]
        keyword_hits = [kw for kw in keywords if kw in code_file.content_lower]
        hits = anchor_hits + [kw for kw in keyword_hits if kw not in anchor_hits]
        hit_count = len(hits)
        if hit_count > best_count:
            best_count = hit_count
            best_hits = hits
            best_path = code_file.rel_path
            best_file = code_file

    if best_count < min_hits or best_file is None:
        return False, None

    line, anchor = find_line_for_terms(best_file.content, best_hits)
    return True, Evidence(
        path=best_path,
        keywords=best_hits,
        line=line,
        anchor_kind=anchor_kind_for_file(best_path),
        anchor_value=anchor,
    )


def ensure_columns(fieldnames: list[str]) -> list[str]:
    columns = [col for col in fieldnames if col not in UNUSED_AI_COLUMNS]
    if "测试结果" not in columns:
        columns.append("测试结果")
    for col in AI_OUTPUT_COLUMNS:
        if col not in columns:
            columns.append(col)
    return columns


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI code evidence verifier for testcase CSV")
    parser.add_argument("--cases", required=True, help="Input testcase CSV path")
    parser.add_argument("--project", required=True, help="Project directory path")
    parser.add_argument("--output", help="Output CSV path (default: overwrite input)")
    parser.add_argument("--min-hits", type=int, default=2, help="Minimum keyword hits to mark pass")
    parser.add_argument(
        "--max-reason-len",
        type=int,
        default=DEFAULT_MAX_REASON_LEN,
        help="Max characters for AI reason",
    )
    parser.add_argument(
        "--max-file-size",
        type=int,
        default=DEFAULT_MAX_FILE_SIZE,
        help="Skip files larger than this size in bytes",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases_path = Path(args.cases).expanduser().resolve()
    project_root = Path(args.project).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve() if args.output else cases_path

    if not cases_path.is_file():
        raise FileNotFoundError(f"cases file not found: {cases_path}")
    if not project_root.is_dir():
        raise NotADirectoryError(f"project path not found: {project_root}")

    code_files = collect_code_files(project_root, args.max_file_size)

    with cases_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise RuntimeError("CSV header is missing")
        fieldnames = ensure_columns(reader.fieldnames)
        rows = list(reader)

    passed = 0
    for row in rows:
        ok, evidence = find_best_evidence(row, code_files, args.min_hits)
        if ok and evidence:
            top_hits = evidence.keywords[:3]
            reason = (
                f"{evidence.path}:{evidence.line} "
                f"{evidence.anchor_kind}={evidence.anchor_value}; "
                f"evidence_terms={','.join(top_hits)}; 仍需运行验证"
            )
            confidence = score_confidence(len(evidence.keywords), evidence.path)
            if confidence == "Low":
                row["AI测试结果"] = "不通过"
                row["AI判定原因"] = "仅命中低置信关键词，缺少可追溯实现锚点"
            else:
                passed += 1
                row["AI测试结果"] = "通过"
                row["AI判定原因"] = truncate_chars(reason, args.max_reason_len)
        else:
            row.setdefault("测试结果", row.get("测试结果", ""))
            row["AI测试结果"] = "不通过"
            row["AI判定原因"] = "未找到可追溯项目代码/配置证据"

    pass_rate = f"{passed}/{len(rows)} ({(passed / len(rows) * 100):.2f}%)" if rows else "0/0 (0.00%)"
    for row in rows:
        row["AI测试用例通过率"] = pass_rate

    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Scanned files: {len(code_files)}")
    if not code_files:
        print("Warning: no scannable code files found; no cases were auto-marked")
    print(f"Total cases: {len(rows)}")
    print(f"AI marked pass: {passed}")
    print(f"Output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
