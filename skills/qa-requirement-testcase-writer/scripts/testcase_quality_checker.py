#!/usr/bin/env python3
"""Quality checker for testcase CSV before AI scan."""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

REQUIRED_COLUMNS = [
    "测试内容",
    "测试目的",
    "前置条件",
    "操作步骤",
    "期望结果",
    "需求模块",
    "测试结果",
]

FUZZY_PATTERNS = [r"正常", r"符合预期", r"合理", r"无异常"]
RISK_TAGS = ("[高风险]", "[关键模块]", "[异常]")
DEPENDENCY_PATTERNS = [
    r"上一条",
    r"上条",
    r"前一条",
    r"继续前面的",
    r"延续前置",
    r"基于前序",
    r"在前序用例基础上",
]
NORMAL_HINTS = ("正常", "主流程", "成功", "首次", "基础")
BOUNDARY_HINTS = ("边界", "最小", "最大", "上限", "下限", "临界")
EXCEPTION_HINTS = ("异常", "失败", "错误", "非法", "空值", "重试", "中断", "超时")
REQUIRED_REPORT_SECTIONS = [
    "需求文档名",
    "包含模块",
    "待确认模块",
    "覆盖清单",
    "新增后台参数覆盖",
    "配置读路径/生效范围",
    "需求原子项映射",
]

PARAMETER_HINTS = (
    "参数",
    "配置",
    "后台",
    "json",
    "开关",
    "概率",
    "阈值",
    "区间",
    "价格",
    "金币",
    "时间",
    "奖励",
    "解锁",
    "fixedlevels",
    "randomlevels",
)

AI_RESULT_COLUMN = "AI测试结果"
AI_REASON_COLUMN = "AI判定原因"
AI_PASS_RATE_COLUMN = "AI测试用例通过率"
AI_VALID_RESULTS = {"通过", "不通过"}
AI_FORBIDDEN_EVIDENCE_PATH_PARTS = (
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
    "node_modules",
)
AI_EVIDENCE_PATH_RE = re.compile(
    r"(?P<path>[\w./\\ -]+\.(?:cs|js|jsx|ts|tsx|py|java|kt|swift|m|mm|go|rs|cpp|cc|c|h|hpp|lua|json|ya?ml|toml|ini|xml|gradle|properties)):(?P<line>\d+)"
)
AI_EVIDENCE_ANCHOR_RE = re.compile(
    r"(?i)\b(key|symbol|class|function|method|func|config|field|property)\s*="
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate testcase CSV quality before AI scan")
    parser.add_argument("--cases", required=True, help="Input testcase CSV path")
    parser.add_argument("--report", help="Optional plain-text coverage report path")
    return parser.parse_args()


def load_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise RuntimeError("CSV header is missing")
        rows = list(reader)
    return list(reader.fieldnames), rows


def check_required_columns(fieldnames: list[str]) -> list[str]:
    errors: list[str] = []
    for col in REQUIRED_COLUMNS:
        if col not in fieldnames:
            errors.append(f"缺少必需列: {col}")
    return errors


def check_required_values(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    required_no_empty = [col for col in REQUIRED_COLUMNS if col != "测试结果"]

    for idx, row in enumerate(rows, start=2):
        for col in required_no_empty:
            value = (row.get(col) or "").strip()
            if not value:
                errors.append(f"第{idx}行 {col} 为空")
    return errors


def check_duplicates(rows: list[dict[str, str]]) -> list[str]:
    bucket: dict[tuple[str, str], list[int]] = defaultdict(list)
    for idx, row in enumerate(rows, start=2):
        key = ((row.get("测试内容") or "").strip(), (row.get("期望结果") or "").strip())
        bucket[key].append(idx)

    errors: list[str] = []
    for (title, expect), lines in bucket.items():
        if title and expect and len(lines) > 1:
            errors.append(f"重复用例(测试内容+期望结果): 行{','.join(map(str, lines))}")
    return errors


def check_fuzzy_expected(rows: list[dict[str, str]]) -> list[str]:
    regex = re.compile("|".join(FUZZY_PATTERNS))
    errors: list[str] = []
    for idx, row in enumerate(rows, start=2):
        expected = (row.get("期望结果") or "").strip()
        if expected and regex.search(expected):
            errors.append(f"第{idx}行 期望结果含模糊词: {expected}")
    return errors


def row_text(row: dict[str, str]) -> str:
    return " ".join((row.get(col) or "").strip().lower() for col in REQUIRED_COLUMNS if col != "测试结果")


def has_any_keyword(text: str, keywords: tuple[str, ...] | list[str]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def detect_suite_coverage(rows: list[dict[str, str]]) -> dict[str, bool]:
    coverage = {
        "正常流程": False,
        "边界值": False,
        "异常场景": False,
        "高风险标记": False,
    }
    for row in rows:
        text = row_text(row)
        title = (row.get("测试内容") or "").strip()
        if has_any_keyword(text, NORMAL_HINTS):
            coverage["正常流程"] = True
        if has_any_keyword(text, BOUNDARY_HINTS):
            coverage["边界值"] = True
        if has_any_keyword(text, EXCEPTION_HINTS):
            coverage["异常场景"] = True
        if any(tag in title for tag in RISK_TAGS):
            coverage["高风险标记"] = True
    return coverage


def check_case_independence(rows: list[dict[str, str]]) -> list[str]:
    regex = re.compile("|".join(DEPENDENCY_PATTERNS))
    errors: list[str] = []
    for idx, row in enumerate(rows, start=2):
        for col in ("测试目的", "前置条件", "操作步骤", "期望结果"):
            value = (row.get(col) or "").strip()
            if value and regex.search(value):
                errors.append(f"第{idx}行 {col} 疑似依赖其它用例: {value}")
    return errors


def check_risk_tagging(rows: list[dict[str, str]]) -> list[str]:
    warnings: list[str] = []
    high_risk_keywords = ("异常", "失败", "错误", "中断", "超时", "边界", "上限", "下限", "优先级")
    for idx, row in enumerate(rows, start=2):
        text = row_text(row)
        title = (row.get("测试内容") or "").strip()
        if has_any_keyword(text, high_risk_keywords) and not any(tag in title for tag in RISK_TAGS):
            warnings.append(f"第{idx}行 疑似高风险/异常场景未标记: {title}")
    return warnings


def check_parameter_column(fieldnames: list[str], rows: list[dict[str, str]]) -> list[str]:
    if "新增参数" not in fieldnames:
        return []

    findings: list[str] = []
    for idx, row in enumerate(rows, start=2):
        text = row_text(row)
        parameter_value = (row.get("新增参数") or "").strip()
        if has_any_keyword(text, PARAMETER_HINTS) and not parameter_value:
            findings.append(f"第{idx}行 疑似参数/配置用例但`新增参数`为空")

    return findings


def reason_has_valid_ai_evidence(reason: str) -> tuple[bool, str]:
    if not reason:
        return False, "AI判定原因为空"

    if "仅命中" in reason or reason.startswith("命中"):
        return False, "AI判定原因只是关键词命中，不是可追溯实现证据"

    path_match = AI_EVIDENCE_PATH_RE.search(reason)
    if not path_match:
        return False, "AI判定原因缺少代码/配置路径和行号，例如 `Assets/.../Foo.cs:123`"

    evidence_path = path_match.group("path").replace("\\", "/").lower()
    path_parts = [part for part in evidence_path.split("/") if part]
    if any(part in AI_FORBIDDEN_EVIDENCE_PATH_PARTS for part in path_parts):
        return False, f"AI证据路径来自非业务代码/配置目录: {path_match.group('path')}"

    if not AI_EVIDENCE_ANCHOR_RE.search(reason):
        return False, "AI判定原因缺少具体实现锚点，例如 `key=...`、`class=...` 或 `function=...`"

    return True, ""


def check_ai_evidence_columns(fieldnames: list[str], rows: list[dict[str, str]]) -> list[str]:
    if AI_RESULT_COLUMN not in fieldnames:
        return []

    findings: list[str] = []
    if AI_REASON_COLUMN not in fieldnames:
        findings.append(f"存在`{AI_RESULT_COLUMN}`但缺少`{AI_REASON_COLUMN}`")
    if AI_PASS_RATE_COLUMN not in fieldnames:
        findings.append(f"存在`{AI_RESULT_COLUMN}`但缺少`{AI_PASS_RATE_COLUMN}`")

    for idx, row in enumerate(rows, start=2):
        result = (row.get(AI_RESULT_COLUMN) or "").strip()
        reason = (row.get(AI_REASON_COLUMN) or "").strip()

        if not result:
            findings.append(f"第{idx}行 {AI_RESULT_COLUMN} 为空")
            continue
        if result not in AI_VALID_RESULTS:
            findings.append(f"第{idx}行 {AI_RESULT_COLUMN} 非法值: {result}")
            continue

        if result == "通过":
            ok, message = reason_has_valid_ai_evidence(reason)
            if not ok:
                findings.append(f"第{idx}行 AI通过缺少实质证据: {message}")
        elif not reason:
            findings.append(f"第{idx}行 AI不通过但{AI_REASON_COLUMN}为空")

    return findings


def check_category_presence(rows: list[dict[str, str]]) -> list[str]:
    coverage = detect_suite_coverage(rows)
    findings: list[str] = []
    for name, covered in coverage.items():
        if not covered:
            findings.append(f"测试集可能缺少{name}覆盖")
    return findings


def print_summary(rows: list[dict[str, str]]) -> None:
    coverage = detect_suite_coverage(rows)
    modules = sorted({(row.get("需求模块") or "").strip() for row in rows if (row.get("需求模块") or "").strip()})
    print("Coverage summary:")
    for name, covered in coverage.items():
        print(f"- {name}: {'Y' if covered else 'N'}")
    if modules:
        print(f"- 已覆盖模块: {', '.join(modules)}")


def check_report_file(path: Path) -> list[str]:
    if not path.is_file():
        return [f"report file not found: {path}"]

    text = path.read_text(encoding="utf-8").strip()
    findings: list[str] = []

    if not text:
        return [f"report file is empty: {path}"]

    for section in REQUIRED_REPORT_SECTIONS:
        if section not in text:
            findings.append(f"覆盖报告缺少必需段落: {section}")

    if "需求原子项映射" in text:
        mapping_text = text.split("需求原子项映射", 1)[1]
        if "->" not in mapping_text and "对应" not in mapping_text:
            findings.append("覆盖报告存在`需求原子项映射`标题，但未发现映射内容")

    return findings


def main() -> int:
    args = parse_args()
    cases_path = Path(args.cases).expanduser().resolve()
    report_path = Path(args.report).expanduser().resolve() if args.report else None

    if not cases_path.is_file():
        raise FileNotFoundError(f"cases file not found: {cases_path}")

    fieldnames, rows = load_rows(cases_path)

    findings: list[str] = []
    findings.extend(check_required_columns(fieldnames))
    findings.extend(check_required_values(rows))
    findings.extend(check_duplicates(rows))
    findings.extend(check_fuzzy_expected(rows))
    findings.extend(check_case_independence(rows))
    findings.extend(check_parameter_column(fieldnames, rows))
    findings.extend(check_ai_evidence_columns(fieldnames, rows))
    findings.extend(check_category_presence(rows))
    if report_path:
        findings.extend(check_report_file(report_path))

    warnings = check_risk_tagging(rows)

    print(f"Cases file: {cases_path}")
    if report_path:
        print(f"Report file: {report_path}")
    print(f"Total cases: {len(rows)}")
    print(f"Findings: {len(findings)}")
    print_summary(rows)

    if findings:
        for issue in findings:
            print(f"- {issue}")
        if warnings:
            print(f"Warnings: {len(warnings)}")
            for issue in warnings:
                print(f"- {issue}")
        return 1

    if warnings:
        print(f"Warnings: {len(warnings)}")
        for issue in warnings:
            print(f"- {issue}")

    print("Quality check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
