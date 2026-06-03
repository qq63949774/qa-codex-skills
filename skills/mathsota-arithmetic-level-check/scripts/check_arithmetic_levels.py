#!/usr/bin/env python3
"""Check Mathsota arithmetic level JSONs for formula-target correctness."""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable

NUMBER_RE = re.compile(r"^\d+$")
FORMULA_RE = re.compile(r"^(\d+)([+\-−*xX×/÷])(\d+)$")


@dataclass
class Issue:
    file: str
    item_index: int
    mapped_level: int
    location: str
    token: str
    expected: str
    actual: str
    reason: str


@dataclass
class Stats:
    files: int = 0
    levels: int = 0
    key_groups: int = 0
    key_content: int = 0
    board_tokens: int = 0
    type_tokens: int = 0
    equation_tokens: int = 0
    formula_entries: int = 0
    number_entries: int = 0
    unique_expressions: set[str] | None = None

    def __post_init__(self) -> None:
        if self.unique_expressions is None:
            self.unique_expressions = set()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Mathsota arithmetic level formulas."
    )
    parser.add_argument("--project-root", required=True, help="Unity project root containing Assets")
    parser.add_argument(
        "--dataset",
        choices=("normal", "special"),
        default="normal",
        help="normal=LevelData, special=SpecialLevelData",
    )
    parser.add_argument("--language", default="en", help="LevelData language folder")

    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--all", action="store_true", help="Scan all stages")
    scope.add_argument("--level", type=int, help="Mapped level number, 1-based")
    scope.add_argument("--file", help="Resource file name, e.g. 1.json")
    parser.add_argument("--item-index", type=int, help="0-based stage index within --file")

    parser.add_argument("--fail-only", action="store_true", help="Print only failing stages")
    parser.add_argument("--output-csv", help="Write per-issue CSV; writes a PASS row when clean")
    return parser.parse_args()


def dataset_dir(project_root: Path, dataset: str, language: str) -> Path:
    folder = "LevelData" if dataset == "normal" else "SpecialLevelData"
    return project_root / "Assets" / "Game" / "Levels" / "Resources" / folder / language


def mapped_level_for(file_name: str, item_index: int) -> int:
    stem = Path(file_name).stem
    if stem.isdigit():
        return (int(stem) - 1) * 10 + item_index + 1
    return item_index + 1


def eval_expr(expr: str) -> tuple[Fraction, str]:
    value = expr.strip()
    if NUMBER_RE.fullmatch(value):
        return Fraction(int(value), 1), "number"

    match = FORMULA_RE.fullmatch(value)
    if not match:
        raise ValueError("unsupported expression format")

    left = Fraction(int(match.group(1)), 1)
    right = Fraction(int(match.group(3)), 1)
    operator = match.group(2)

    if operator == "+":
        return left + right, "formula"
    if operator in ("-", "−"):
        return left - right, "formula"
    if operator in ("*", "x", "X", "×"):
        return left * right, "formula"
    if operator in ("/", "÷"):
        if right == 0:
            raise ZeroDivisionError("division by zero")
        return left / right, "formula"

    raise ValueError(f"unsupported operator {operator!r}")


def as_target(value: Any) -> tuple[Fraction | None, str | None]:
    text = str(value).strip()
    if not NUMBER_RE.fullmatch(text):
        return None, text
    return Fraction(int(text), 1), text


def add_issue(
    issues: list[Issue],
    file_name: str,
    item_index: int,
    mapped_level: int,
    location: str,
    token: str,
    expected: Any,
    actual: Any,
    reason: str,
) -> None:
    issues.append(
        Issue(
            file=file_name,
            item_index=item_index,
            mapped_level=mapped_level,
            location=location,
            token=str(token),
            expected=str(expected),
            actual=str(actual),
            reason=reason,
        )
    )


def iter_board_tokens(stage: dict[str, Any]) -> Iterable[tuple[str, str]]:
    for column_index, column in enumerate(stage.get("column") or []):
        for token_index, token in enumerate(column or []):
            yield f"column[{column_index}][{token_index}]", str(token)
    for token_index, token in enumerate(stage.get("stock") or []):
        yield f"stock[{token_index}]", str(token)


def check_stage(
    stage: dict[str, Any],
    file_name: str,
    item_index: int,
    stats: Stats,
) -> list[Issue]:
    mapped_level = mapped_level_for(file_name, item_index)
    issues: list[Issue] = []
    declared: set[tuple[str, str]] = set()

    for key_index, group in enumerate(stage.get("key") or []):
        stats.key_groups += 1
        title = str((group or {}).get("title", "")).strip()
        target, title_text = as_target(title)
        if target is None:
            add_issue(
                issues,
                file_name,
                item_index,
                mapped_level,
                f"key[{key_index}].title",
                title,
                "integer target",
                title_text or "",
                "key title is not a pure integer",
            )
            continue

        if (group or {}).get("isImage") is not False:
            add_issue(
                issues,
                file_name,
                item_index,
                mapped_level,
                f"key[{key_index}].isImage",
                title,
                "false",
                (group or {}).get("isImage"),
                "Mathsota arithmetic key group should not be image-based",
            )

        for content_index, expr in enumerate((group or {}).get("content") or []):
            expr_text = str(expr).strip()
            stats.key_content += 1
            stats.unique_expressions.add(expr_text)
            declared.add((title, expr_text))
            location = f"key[{key_index}].content[{content_index}]"
            try:
                result, kind = eval_expr(expr_text)
                if kind == "number":
                    stats.number_entries += 1
                else:
                    stats.formula_entries += 1
                if result != target:
                    add_issue(
                        issues,
                        file_name,
                        item_index,
                        mapped_level,
                        location,
                        f"{title}:{expr_text}",
                        target,
                        result,
                        "key content expression result does not match title",
                    )
            except Exception as exc:  # noqa: BLE001 - report data issues, keep scanning
                add_issue(
                    issues,
                    file_name,
                    item_index,
                    mapped_level,
                    location,
                    f"{title}:{expr_text}",
                    target,
                    "",
                    f"expression cannot be evaluated: {exc}",
                )

    for location, token in iter_board_tokens(stage):
        stats.board_tokens += 1
        if ":" not in token:
            add_issue(
                issues,
                file_name,
                item_index,
                mapped_level,
                location,
                token,
                "target:expression",
                "",
                "board token is missing ':'",
            )
            continue

        title, expr = [part.strip() for part in token.split(":", 1)]
        target, title_text = as_target(title)
        stats.unique_expressions.add(expr)
        if target is None:
            add_issue(
                issues,
                file_name,
                item_index,
                mapped_level,
                location,
                token,
                "integer target",
                title_text or "",
                "token target is not a pure integer",
            )
            continue

        try:
            result, kind = eval_expr(expr)
            if kind == "number":
                stats.number_entries += 1
            else:
                stats.formula_entries += 1
            if result != target:
                add_issue(
                    issues,
                    file_name,
                    item_index,
                    mapped_level,
                    location,
                    token,
                    target,
                    result,
                    "board token expression result does not match target",
                )
            if kind == "number" and expr == title:
                stats.type_tokens += 1
            else:
                stats.equation_tokens += 1
                if (title, expr) not in declared:
                    add_issue(
                        issues,
                        file_name,
                        item_index,
                        mapped_level,
                        location,
                        token,
                        "declared key.content",
                        "",
                        "non-type board token is not declared in matching key.content",
                    )
        except Exception as exc:  # noqa: BLE001
            add_issue(
                issues,
                file_name,
                item_index,
                mapped_level,
                location,
                token,
                target,
                "",
                f"expression cannot be evaluated: {exc}",
            )

    return issues


def load_stages(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise RuntimeError(f"{path.name} must contain a JSON array")
    return data


def select_files(data_dir: Path, args: argparse.Namespace) -> list[Path]:
    if args.file:
        if args.item_index is None:
            raise RuntimeError("--item-index is required with --file")
        return [data_dir / args.file]
    if args.level is not None:
        if args.level < 1:
            raise RuntimeError("--level must be >= 1")
        file_no = (args.level - 1) // 10 + 1
        return [data_dir / f"{file_no}.json"]
    return sorted(data_dir.glob("*.json"), key=lambda path: int(path.stem) if path.stem.isdigit() else path.stem)


def select_indices(file_path: Path, stages: list[dict[str, Any]], args: argparse.Namespace) -> list[int]:
    if args.file:
        assert args.item_index is not None
        return [args.item_index]
    if args.level is not None:
        return [(args.level - 1) % 10]
    return list(range(len(stages)))


def write_csv(path: Path, issues: list[Issue], stats: Stats) -> None:
    fields = ["file", "item_index", "mapped_level", "location", "token", "expected", "actual", "reason"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        if issues:
            for issue in issues:
                writer.writerow(issue.__dict__)
        else:
            writer.writerow(
                {
                    "file": "ALL",
                    "item_index": "",
                    "mapped_level": "",
                    "location": "",
                    "token": "",
                    "expected": "0 issues",
                    "actual": f"{stats.levels} levels scanned",
                    "reason": "PASS",
                }
            )


def print_summary(args: argparse.Namespace, data_dir: Path, stats: Stats, issues: list[Issue]) -> None:
    print(f"dataset={args.dataset} language={args.language}")
    print(f"directory={data_dir}")
    print(f"json_files={stats.files}")
    print(f"levels={stats.levels}")
    print(f"key_groups={stats.key_groups}")
    print(f"key_content={stats.key_content}")
    print(f"board_tokens={stats.board_tokens}")
    print(f"type_tokens={stats.type_tokens}")
    print(f"equation_tokens={stats.equation_tokens}")
    print(f"formula_entries={stats.formula_entries}")
    print(f"number_entries={stats.number_entries}")
    print(f"unique_expressions={len(stats.unique_expressions)}")
    print(f"issues={len(issues)}")

    if issues:
        for issue in issues:
            print(
                f"[FAIL] file={issue.file} item={issue.item_index} "
                f"mapped_level={issue.mapped_level} location={issue.location} "
                f"token={issue.token} expected={issue.expected} actual={issue.actual} "
                f"reason={issue.reason}"
            )
    else:
        print("[PASS] all arithmetic targets match their expressions")


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    data_dir = dataset_dir(project_root, args.dataset, args.language)
    if not data_dir.is_dir():
        raise NotADirectoryError(f"level data directory not found: {data_dir}")

    stats = Stats()
    issues: list[Issue] = []

    for file_path in select_files(data_dir, args):
        if not file_path.is_file():
            raise FileNotFoundError(f"level file not found: {file_path}")
        stages = load_stages(file_path)
        stats.files += 1
        for item_index in select_indices(file_path, stages, args):
            if item_index < 0 or item_index >= len(stages):
                raise IndexError(f"{file_path.name} item index out of range: {item_index}")
            stats.levels += 1
            stage_issues = check_stage(stages[item_index], file_path.name, item_index, stats)
            issues.extend(stage_issues)
            if not args.fail_only or stage_issues:
                mapped_level = mapped_level_for(file_path.name, item_index)
                status = "FAIL" if stage_issues else "PASS"
                print(
                    f"[{status}] dataset={args.dataset} lang={args.language} "
                    f"file={file_path.name} item={item_index} mapped_level={mapped_level} "
                    f"issues={len(stage_issues)}"
                )

    print_summary(args, data_dir, stats, issues)

    if args.output_csv:
        output = Path(args.output_csv).expanduser().resolve()
        write_csv(output, issues, stats)
        print(f"csv={output}")

    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
