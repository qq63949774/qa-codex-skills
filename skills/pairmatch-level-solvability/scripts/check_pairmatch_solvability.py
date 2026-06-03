#!/usr/bin/env python3
import argparse
import json
import pathlib
import sys
from collections import Counter, defaultdict
from itertools import product


META_KEYS = {"theme", "difficulty", "time", "gridSize", "showRows", "data", "model"}
TABLE_KEYS = ("rowClass", "columnClass", "table", "queue1", "queue2")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Check PairMatch level JSON solvability invariants."
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--puzzle-dir",
        help="Directory containing puzzleData*.json files",
    )
    src.add_argument(
        "--json-file",
        help="Single JSON file containing one or more levels",
    )
    parser.add_argument(
        "--level",
        action="append",
        default=[],
        help="Only inspect named levels like level30; can be repeated",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )
    parser.add_argument(
        "--only-failed",
        action="store_true",
        help="Only print levels with issues in JSON mode or text mode details",
    )
    parser.add_argument(
        "--no-fail-on-issues",
        action="store_true",
        help="Always exit 0 even if suspicious levels are found",
    )
    return parser.parse_args()


def load_levels(args):
    levels = []
    wanted = set(args.level)

    if args.puzzle_dir:
        paths = sorted(pathlib.Path(args.puzzle_dir).glob("puzzleData*.json"))
    else:
        paths = [pathlib.Path(args.json_file)]

    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        for level_name, level_data in data.items():
            if wanted and level_name not in wanted:
                continue
            levels.append((path, level_name, level_data))
    return levels


def parse_grid_size(level):
    raw = str(level.get("gridSize", ""))
    parts = raw.split("x")
    if len(parts) != 2:
        return None, None, raw
    try:
        return int(parts[0]), int(parts[1]), raw
    except ValueError:
        return None, None, raw


def get_hidden_map(level):
    return {
        key: value
        for key, value in level.items()
        if key not in META_KEYS and isinstance(value, list)
    }


def last_link_target(cards):
    if not cards:
        return None
    return cards[-1].get("className")


def analyze_legacy_level(path, level_name, level, issues):
    target_class_count = int(str(level["gridSize"]).split("x")[0])
    initial_columns = level["data"]
    hidden_map = get_hidden_map(level)

    totals = Counter()
    mix_flags = defaultdict(set)
    reachable_classes = set()

    for col_idx, col in enumerate(initial_columns):
        if len(col) != 4:
            issues.append(
                {
                    "kind": "initial_column_len_not_4",
                    "column_index": col_idx,
                    "actual": len(col),
                }
            )
        for card in col:
            class_name = card["className"]
            totals[class_name] += 1
            mix_flags[class_name].add(bool(card.get("isMix")))
            reachable_classes.add(class_name)

    for hidden_key, cards in hidden_map.items():
        if len(cards) != 4:
            issues.append(
                {
                    "kind": "hidden_column_len_not_4",
                    "hidden_key": hidden_key,
                    "actual": len(cards),
                }
            )
        for card in cards:
            class_name = card["className"]
            totals[class_name] += 1
            mix_flags[class_name].add(bool(card.get("isMix")))

    if len(totals) != target_class_count:
        issues.append(
            {
                "kind": "class_kind_count_mismatch",
                "actual": len(totals),
                "expected": target_class_count,
            }
        )

    total_card_count = sum(totals.values())
    expected_total_cards = target_class_count * 4
    if total_card_count != expected_total_cards:
        issues.append(
            {
                "kind": "total_card_count_mismatch",
                "actual": total_card_count,
                "expected": expected_total_cards,
            }
        )

    wrong_totals = {key: totals[key] for key in sorted(totals) if totals[key] != 4}
    if wrong_totals:
        issues.append({"kind": "class_total_not_4", "details": wrong_totals})

    for hidden_key in sorted(hidden_map):
        if totals.get(hidden_key, 0) != 4:
            issues.append(
                {
                    "kind": "hidden_key_total_not_4",
                    "hidden_key": hidden_key,
                    "actual": totals.get(hidden_key, 0),
                }
            )
        if mix_flags.get(hidden_key) != {True}:
            issues.append(
                {
                    "kind": "hidden_key_not_all_mix",
                    "hidden_key": hidden_key,
                    "mix_flags": sorted(mix_flags.get(hidden_key, set())),
                }
            )

    changed = True
    while changed:
        changed = False
        for hidden_key, cards in hidden_map.items():
            if hidden_key in reachable_classes:
                new_classes = {card["className"] for card in cards}
                if not new_classes.issubset(reachable_classes):
                    reachable_classes.update(new_classes)
                    changed = True

    for hidden_key in sorted(hidden_map):
        if hidden_key not in reachable_classes:
            issues.append(
                {
                    "kind": "hidden_key_unreachable_from_initial_or_hidden_chain",
                    "hidden_key": hidden_key,
                }
            )

    for hidden_key in sorted(hidden_map):
        seen = []
        current = hidden_key
        while current in hidden_map:
            if current in seen:
                issues.append(
                    {"kind": "hidden_chain_cycle", "chain": seen + [current]}
                )
                break
            seen.append(current)
            current = last_link_target(hidden_map[current])

    return {
        "file": str(path),
        "level": level_name,
        "model": int(level.get("model", 0)),
        "target_class_count": target_class_count,
        "initial_column_count": len(initial_columns),
        "hidden_key_count": len(hidden_map),
        "issue_count": len(issues),
        "issues": issues,
    }


def combo_key(row_class, column_class):
    return f"{row_class}|{column_class}"


def analyze_table_level(path, level_name, level, issues):
    column_count, row_count, raw_grid_size = parse_grid_size(level)
    if column_count is None or row_count is None:
        issues.append(
            {
                "kind": "invalid_grid_size",
                "actual": raw_grid_size,
                "expected": "<columnCount>x<rowCount>",
            }
        )
        return {
            "file": str(path),
            "level": level_name,
            "model": 2,
            "row_count": None,
            "column_count": None,
            "issue_count": len(issues),
            "issues": issues,
        }

    table_data = level.get("data")
    if not isinstance(table_data, dict):
        issues.append(
            {
                "kind": "table_data_not_object",
                "actual_type": type(table_data).__name__,
            }
        )
        return {
            "file": str(path),
            "level": level_name,
            "model": 2,
            "row_count": row_count,
            "column_count": column_count,
            "issue_count": len(issues),
            "issues": issues,
        }

    for key in TABLE_KEYS:
        if key not in table_data:
            issues.append({"kind": "missing_table_key", "key": key})

    row_classes = table_data.get("rowClass", [])
    column_classes = table_data.get("columnClass", [])
    table_cards = table_data.get("table", [])
    queue1_cards = table_data.get("queue1", [])
    queue2_cards = table_data.get("queue2", [])

    for key, value in (
        ("rowClass", row_classes),
        ("columnClass", column_classes),
        ("table", table_cards),
        ("queue1", queue1_cards),
        ("queue2", queue2_cards),
    ):
        if not isinstance(value, list):
            issues.append(
                {
                    "kind": "table_key_not_list",
                    "key": key,
                    "actual_type": type(value).__name__,
                }
            )

    if not all(isinstance(value, list) for value in (row_classes, column_classes, table_cards, queue1_cards, queue2_cards)):
        return {
            "file": str(path),
            "level": level_name,
            "model": 2,
            "row_count": row_count,
            "column_count": column_count,
            "issue_count": len(issues),
            "issues": issues,
        }

    if len(row_classes) != row_count:
        issues.append(
            {
                "kind": "row_class_count_mismatch",
                "actual": len(row_classes),
                "expected": row_count,
            }
        )
    if len(column_classes) != column_count:
        issues.append(
            {
                "kind": "column_class_count_mismatch",
                "actual": len(column_classes),
                "expected": column_count,
            }
        )

    duplicate_rows = sorted(key for key, count in Counter(row_classes).items() if count != 1)
    if duplicate_rows:
        issues.append({"kind": "row_class_not_unique", "details": duplicate_rows})

    duplicate_columns = sorted(key for key, count in Counter(column_classes).items() if count != 1)
    if duplicate_columns:
        issues.append({"kind": "column_class_not_unique", "details": duplicate_columns})

    row_set = set(row_classes)
    column_set = set(column_classes)
    combo_locations = defaultdict(list)
    bad_rows = []
    bad_columns = []
    item_shape_issues = []

    for section_name, cards in (
        ("table", table_cards),
        ("queue1", queue1_cards),
        ("queue2", queue2_cards),
    ):
        for index, item in enumerate(cards):
            if not isinstance(item, dict):
                item_shape_issues.append(
                    {
                        "section": section_name,
                        "index": index,
                        "actual_type": type(item).__name__,
                    }
                )
                continue

            row_class = item.get("rowClass")
            column_class = item.get("columnClass")
            image_name = item.get("imageName")
            if not isinstance(row_class, str) or not row_class:
                item_shape_issues.append(
                    {
                        "section": section_name,
                        "index": index,
                        "field": "rowClass",
                        "actual": row_class,
                    }
                )
                continue
            if not isinstance(column_class, str) or not column_class:
                item_shape_issues.append(
                    {
                        "section": section_name,
                        "index": index,
                        "field": "columnClass",
                        "actual": column_class,
                    }
                )
                continue
            if not isinstance(image_name, str) or not image_name:
                item_shape_issues.append(
                    {
                        "section": section_name,
                        "index": index,
                        "field": "imageName",
                        "actual": image_name,
                    }
                )

            if row_class not in row_set:
                bad_rows.append(
                    {
                        "section": section_name,
                        "index": index,
                        "rowClass": row_class,
                    }
                )
            if column_class not in column_set:
                bad_columns.append(
                    {
                        "section": section_name,
                        "index": index,
                        "columnClass": column_class,
                    }
                )

            if row_class in row_set and column_class in column_set:
                combo_locations[combo_key(row_class, column_class)].append(f"{section_name}[{index}]")

    if item_shape_issues:
        issues.append({"kind": "table_item_invalid", "details": item_shape_issues})
    if bad_rows:
        issues.append({"kind": "table_item_unknown_row_class", "details": bad_rows})
    if bad_columns:
        issues.append({"kind": "table_item_unknown_column_class", "details": bad_columns})

    expected_total_cards = len(row_classes) * len(column_classes)
    actual_total_cards = len(table_cards) + len(queue1_cards) + len(queue2_cards)
    if actual_total_cards != expected_total_cards:
        issues.append(
            {
                "kind": "table_total_card_count_mismatch",
                "actual": actual_total_cards,
                "expected": expected_total_cards,
            }
        )

    expected_combos = {
        combo_key(row_class, column_class)
        for row_class, column_class in product(row_classes, column_classes)
    }
    missing_combos = sorted(expected_combos - set(combo_locations))
    if missing_combos:
        issues.append(
            {
                "kind": "table_coordinate_combo_missing",
                "details": missing_combos,
            }
        )

    duplicated_combos = {
        combo: locations
        for combo, locations in sorted(combo_locations.items())
        if len(locations) != 1
    }
    if duplicated_combos:
        issues.append(
            {
                "kind": "table_coordinate_combo_not_exactly_once",
                "details": duplicated_combos,
            }
        )

    return {
        "file": str(path),
        "level": level_name,
        "model": 2,
        "row_count": row_count,
        "column_count": column_count,
        "target_class_count": row_count + column_count,
        "table_filled_count": len(table_cards),
        "queue1_count": len(queue1_cards),
        "queue2_count": len(queue2_cards),
        "issue_count": len(issues),
        "issues": issues,
    }


def check_level(path, level_name, level):
    issues = []
    model_val = level.get("model", 0)
    if not isinstance(model_val, int) or model_val not in (0, 1, 2):
        issues.append(
            {
                "kind": "invalid_model_value",
                "actual": model_val,
                "expected": "0, 1, 2 (or omitted)",
            }
        )

    if model_val == 2:
        return analyze_table_level(path, level_name, level, issues)
    return analyze_legacy_level(path, level_name, level, issues)


def summarize_results(results):
    checked = len(results)
    failed = sum(1 for result in results if result["issue_count"] > 0)
    passed = checked - failed
    return {
        "checked": checked,
        "passed": passed,
        "failed": failed,
        "failed_levels": [result["level"] for result in results if result["issue_count"] > 0],
    }


def format_text(results, only_failed=False):
    summary = summarize_results(results)
    lines = [
        f"Checked {summary['checked']} levels",
        f"Passed: {summary['passed']}",
        f"Failed: {summary['failed']}",
    ]

    detail_results = results
    if only_failed:
        detail_results = [result for result in results if result["issue_count"] > 0]

    if any(result["issue_count"] > 0 for result in detail_results):
        lines.append("")
        lines.append("Suspicious levels:")
        for result in detail_results:
            if result["issue_count"] == 0:
                continue
            lines.append(
                f"- {result['level']} ({pathlib.Path(result['file']).name}): {result['issue_count']} issue(s)"
            )
            for issue in result["issues"]:
                lines.append(f"  - {issue['kind']}: {json.dumps(issue, ensure_ascii=False)}")
    return "\n".join(lines)


def main():
    args = parse_args()
    levels = load_levels(args)
    if not levels:
        print("No matching levels found.", file=sys.stderr)
        return 2

    results = [check_level(path, level_name, level) for path, level_name, level in levels]
    rendered_results = results
    if args.only_failed:
        rendered_results = [result for result in results if result["issue_count"] > 0]

    if args.json:
        payload = {
            "summary": summarize_results(results),
            "results": rendered_results,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(format_text(results, only_failed=args.only_failed))

    has_issues = any(result["issue_count"] for result in results)
    if has_issues and not args.no_fail_on_issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
