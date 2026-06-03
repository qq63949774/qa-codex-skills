#!/usr/bin/env python3
import argparse
import csv
import json
import pathlib
import sys
from collections import Counter, defaultdict


META_KEYS = {
    "theme",
    "difficulty",
    "time",
    "move",
    "gridSize",
    "showRows",
    "data",
    "model",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Check PairPop model=0 column and model=3 text-bubble level JSON legality invariants."
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--puzzle-dir", help="Directory containing puzzleData*.json files")
    src.add_argument("--json-file", help="Single JSON file containing one or more levels")
    parser.add_argument("--level", action="append", default=[], help="Only inspect named levels")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    parser.add_argument("--only-failed", action="store_true", help="Only print failed level details")
    parser.add_argument(
        "--project-root",
        default=None,
        help="Unity project root used to resolve Resources assets",
    )
    parser.add_argument(
        "--item-image-dir",
        help="Override item image resource directory; defaults to <project-root>/Assets/Resources/Texture/ItemImage",
    )
    parser.add_argument(
        "--puzzle-language-csv",
        help="Override puzzleLanguage.csv path used to resolve duplicate text words; defaults to <project-root>/Assets/Resources/puzzleLanguage.csv",
    )
    parser.add_argument(
        "--skip-image-assets",
        action="store_true",
        help="Skip type=1 Texture/ItemImage resource existence checks",
    )
    parser.add_argument(
        "--skip-duplicate-text-words",
        action="store_true",
        help="Skip the model=3 same-level duplicate text word check",
    )
    parser.add_argument(
        "--no-fail-on-issues",
        action="store_true",
        help="Always exit 0 even if suspicious levels are found",
    )
    return parser.parse_args()


def infer_project_root(args):
    if args.project_root:
        return pathlib.Path(args.project_root).expanduser().resolve()
    if not args.puzzle_dir:
        return None
    puzzle_dir = pathlib.Path(args.puzzle_dir).expanduser().resolve()
    suffix = pathlib.Path("Assets/Resources/PuzzleData")
    try:
        rel = puzzle_dir.relative_to(puzzle_dir.parents[2])
    except IndexError:
        return None
    return puzzle_dir.parents[2] if rel == suffix else None


def load_item_image_stems(args):
    if args.skip_image_assets:
        return None
    project_root = infer_project_root(args)
    if args.item_image_dir:
        image_dir = pathlib.Path(args.item_image_dir).expanduser().resolve()
    elif project_root:
        image_dir = project_root / "Assets/Resources/Texture/ItemImage"
    else:
        return None
    stems = set()
    if not image_dir.exists():
        return stems
    for path in image_dir.iterdir():
        if path.is_file() and path.suffix != ".meta":
            stems.add(path.stem)
    return stems


def load_language_words(args):
    if args.skip_duplicate_text_words:
        return {}
    project_root = infer_project_root(args)
    if args.puzzle_language_csv:
        language_path = pathlib.Path(args.puzzle_language_csv).expanduser().resolve()
    elif project_root:
        language_path = project_root / "Assets/Resources/puzzleLanguage.csv"
    else:
        return {}
    words = {}
    if not language_path.exists():
        return words
    locale_keys = (
        "en",
        "zh_hans",
        "zh_hant",
        "fr",
        "de",
        "it",
        "ja",
        "pt",
        "ru",
        "es",
    )
    with language_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) >= 3 and row[0]:
                words[row[0]] = {
                    locale_keys[idx] if idx < len(locale_keys) else f"locale_{idx}": value
                    for idx, value in enumerate(row[2:])
                    if value
                }
    return words


def normalize_display_word(value):
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.strip().split()).casefold()
    return normalized or None


def display_words_for_element(element_name, language_words):
    values = language_words.get(element_name)
    if isinstance(values, dict) and values:
        return values
    return {"raw": element_name}


def load_levels(args):
    wanted = set(args.level)
    paths = sorted(pathlib.Path(args.puzzle_dir).glob("puzzleData*.json")) if args.puzzle_dir else [pathlib.Path(args.json_file)]
    levels = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            iterator = ((f"level{i + 1}", item) for i, item in enumerate(data))
        elif isinstance(data, dict):
            iterator = data.items()
        else:
            raise ValueError(f"{path}: root must be object or array")
        for level_name, level_data in iterator:
            if wanted and level_name not in wanted:
                continue
            levels.append((path, level_name, level_data))
    return levels


def parse_grid_size(raw):
    parts = str(raw).split("x")
    if len(parts) != 2:
        return None, None, str(raw)
    try:
        return int(parts[0]), int(parts[1]), str(raw)
    except ValueError:
        return None, None, str(raw)


def parse_int_like(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def get_hidden_map(level):
    return {
        key: value
        for key, value in level.items()
        if key not in META_KEYS and isinstance(value, list)
    }


def last_link_target(cards):
    if not cards:
        return None
    last = cards[-1]
    return last.get("className") if isinstance(last, dict) else None


def add_issue(issues, kind, **kwargs):
    issue = {"kind": kind}
    issue.update(kwargs)
    issues.append(issue)


def image_resource_exists(item_image_stems, resource_name):
    if resource_name in item_image_stems:
        return True
    prefix = f"{resource_name}-"
    return any(
        stem.startswith(prefix) and stem[len(prefix):].isdigit()
        for stem in item_image_stems
    )


def card_class_name(card):
    return card.get("className") if isinstance(card, dict) and isinstance(card.get("className"), str) else None


def simulate_completion_chain(level, target_class_count):
    hidden_map = get_hidden_map(level)
    visible_counts = Counter()
    completed_order = []
    spawned_hidden_keys = []
    spawned_hidden_key_set = set()
    blocked_snapshot = {}

    initial_groups = level.get("data")
    if isinstance(initial_groups, list):
        for group in initial_groups:
            if not isinstance(group, list):
                continue
            for card in group:
                class_name = card_class_name(card)
                if class_name:
                    visible_counts[class_name] += 1

    def spawn_hidden_cards(class_name):
        if class_name not in hidden_map:
            return
        if class_name in spawned_hidden_key_set:
            return
        spawned_hidden_key_set.add(class_name)
        spawned_hidden_keys.append(class_name)
        for card in hidden_map[class_name]:
            spawned_class_name = card_class_name(card)
            if spawned_class_name:
                visible_counts[spawned_class_name] += 1

    while True:
        ready_classes = sorted(
            class_name for class_name, count in visible_counts.items() if count >= 4
        )
        if not ready_classes:
            blocked_snapshot = {
                class_name: count for class_name, count in sorted(visible_counts.items()) if count > 0
            }
            break

        for class_name in ready_classes:
            if visible_counts[class_name] < 4:
                continue
            visible_counts[class_name] -= 4
            if visible_counts[class_name] == 0:
                del visible_counts[class_name]
            completed_order.append(class_name)
            spawn_hidden_cards(class_name)

    remaining_visible = {
        class_name: count for class_name, count in sorted(visible_counts.items()) if count > 0
    }
    expected_completion_count = target_class_count if isinstance(target_class_count, int) else None
    completed_count = len(completed_order)
    is_solvable = not remaining_visible
    if expected_completion_count is not None and completed_count != expected_completion_count:
        is_solvable = False

    return {
        "solvable": is_solvable,
        "completed_count": completed_count,
        "expected_completion_count": expected_completion_count,
        "completion_order": completed_order,
        "spawned_hidden_keys": spawned_hidden_keys,
        "remaining_visible": remaining_visible,
        "blocked_snapshot": blocked_snapshot,
    }


def validate_model3_card(card, issues, location, image_refs):
    if not isinstance(card, dict):
        add_issue(issues, "card_not_object", location=location, actual_type=type(card).__name__)
        return None

    class_name = card.get("className")
    element_name = card.get("elementName")
    is_mix = card.get("isMix")
    type_value = card.get("type")
    stage = card.get("stage")

    if not isinstance(class_name, str) or not class_name:
        add_issue(issues, "card_invalid_class_name", location=location, actual=class_name)
    if not isinstance(element_name, str) or not element_name:
        add_issue(issues, "card_invalid_element_name", location=location, actual=element_name)
    if not isinstance(is_mix, bool):
        add_issue(issues, "card_invalid_is_mix", location=location, actual=is_mix)
    if not isinstance(type_value, int) or type_value not in (0, 1):
        add_issue(issues, "card_invalid_type", location=location, actual=type_value, expected="0 or 1")
    if not isinstance(stage, int) or stage not in (0, 1):
        add_issue(issues, "card_invalid_stage", location=location, actual=stage, expected="0 or 1")

    if type_value == 1 and isinstance(element_name, str) and element_name:
        image_refs.append(
            {
                "location": location,
                "className": class_name,
                "elementName": element_name,
            }
        )

    return card if isinstance(class_name, str) and class_name else None


def validate_model0_card(card, issues, location, image_refs):
    if not isinstance(card, dict):
        add_issue(issues, "card_not_object", location=location, actual_type=type(card).__name__)
        return None

    class_name = card.get("className")
    image_name = card.get("imageName")
    is_mix = card.get("isMix")

    if not isinstance(class_name, str) or not class_name:
        add_issue(issues, "card_invalid_class_name", location=location, actual=class_name)
    if not isinstance(image_name, str) or not image_name:
        add_issue(issues, "card_invalid_image_name", location=location, actual=image_name)
    if not isinstance(is_mix, bool):
        add_issue(issues, "card_invalid_is_mix", location=location, actual=is_mix)

    if isinstance(image_name, str) and image_name:
        image_refs.append(
            {
                "location": location,
                "className": class_name,
                "imageName": image_name,
            }
        )

    return card if isinstance(class_name, str) and class_name else None


def analyze_common_counts_and_hidden(
    level,
    issues,
    target_class_count,
    item_image_stems,
    language_words,
    validate_card_func,
    image_ref_key,
    missing_image_kind,
    expected_image_path,
):
    initial_groups = level.get("data")
    if not isinstance(initial_groups, list):
        add_issue(issues, "data_not_list", actual_type=type(initial_groups).__name__)
        initial_groups = []

    hidden_map = get_hidden_map(level)
    totals = Counter()
    mix_flags = defaultdict(set)
    reachable_classes = set()
    initial_card_count = 0
    image_refs = []
    word_refs = []

    def collect_word_ref(card, location):
        if card.get("type") != 0:
            return
        element_name = card.get("elementName")
        display_words = display_words_for_element(element_name, language_words)
        for locale, display_word in display_words.items():
            normalized_word = normalize_display_word(display_word)
            if not normalized_word:
                continue
            word_refs.append(
                {
                    "location": location,
                    "className": card.get("className"),
                    "elementName": element_name,
                    "locale": locale,
                    "displayWord": display_word,
                    "normalizedWord": normalized_word,
                }
            )

    for group_idx, group in enumerate(initial_groups):
        if not isinstance(group, list):
            add_issue(issues, "initial_group_not_list", group_index=group_idx, actual_type=type(group).__name__)
            continue
        if len(group) == 0:
            add_issue(issues, "initial_group_empty", group_index=group_idx)
        for card_idx, card in enumerate(group):
            valid_card = validate_card_func(card, issues, f"data[{group_idx}][{card_idx}]", image_refs)
            if valid_card is None:
                continue
            collect_word_ref(valid_card, f"data[{group_idx}][{card_idx}]")
            class_name = valid_card["className"]
            totals[class_name] += 1
            mix_flags[class_name].add(valid_card.get("isMix"))
            reachable_classes.add(class_name)
            initial_card_count += 1

    for hidden_key, cards in hidden_map.items():
        if not isinstance(hidden_key, str) or not hidden_key:
            add_issue(issues, "hidden_key_invalid", hidden_key=hidden_key)
        if len(cards) != 4:
            add_issue(issues, "hidden_expansion_len_not_4", hidden_key=hidden_key, actual=len(cards))
        for card_idx, card in enumerate(cards):
            valid_card = validate_card_func(card, issues, f"{hidden_key}[{card_idx}]", image_refs)
            if valid_card is None:
                continue
            collect_word_ref(valid_card, f"{hidden_key}[{card_idx}]")
            class_name = valid_card["className"]
            totals[class_name] += 1
            mix_flags[class_name].add(valid_card.get("isMix"))

    duplicate_words = []
    word_refs_by_normalized = defaultdict(list)
    for ref in word_refs:
        word_refs_by_normalized[(ref["locale"], ref["normalizedWord"])].append(ref)
    for locale, normalized_word in sorted(word_refs_by_normalized):
        refs = word_refs_by_normalized[(locale, normalized_word)]
        if len(refs) > 1:
            duplicate_words.append(
                {
                    "locale": locale,
                    "display_word": refs[0]["displayWord"],
                    "normalized_word": normalized_word,
                    "count": len(refs),
                    "occurrences": [
                        {
                            "location": ref["location"],
                            "className": ref["className"],
                            "elementName": ref["elementName"],
                        }
                        for ref in refs
                    ],
                }
            )
    if duplicate_words:
        add_issue(
            issues,
            "duplicate_text_word_in_level",
            count=len(duplicate_words),
            details=duplicate_words,
        )

    if target_class_count is not None and len(totals) != target_class_count:
        add_issue(issues, "class_kind_count_mismatch", actual=len(totals), expected=target_class_count)

    if target_class_count is not None:
        expected_total_cards = target_class_count * 4
        actual_total_cards = sum(totals.values())
        if actual_total_cards != expected_total_cards:
            add_issue(issues, "total_card_count_mismatch", actual=actual_total_cards, expected=expected_total_cards)

    wrong_totals = {key: totals[key] for key in sorted(totals) if totals[key] != 4}
    if wrong_totals:
        add_issue(issues, "class_total_not_4", details=wrong_totals)

    for hidden_key in sorted(hidden_map):
        if totals.get(hidden_key, 0) != 4:
            add_issue(issues, "hidden_key_total_not_4", hidden_key=hidden_key, actual=totals.get(hidden_key, 0))
        if mix_flags.get(hidden_key) != {True}:
            add_issue(
                issues,
                "hidden_key_not_all_mix",
                hidden_key=hidden_key,
                mix_flags=sorted(str(flag) for flag in mix_flags.get(hidden_key, set())),
            )

    changed = True
    while changed:
        changed = False
        for hidden_key, cards in hidden_map.items():
            if hidden_key in reachable_classes:
                new_classes = {
                    card.get("className")
                    for card in cards
                    if isinstance(card, dict) and isinstance(card.get("className"), str) and card.get("className")
                }
                if not new_classes.issubset(reachable_classes):
                    reachable_classes.update(new_classes)
                    changed = True

    for hidden_key in sorted(hidden_map):
        if hidden_key not in reachable_classes:
            add_issue(issues, "hidden_key_unreachable_from_initial_or_hidden_chain", hidden_key=hidden_key)

    for hidden_key in sorted(hidden_map):
        seen = []
        current = hidden_key
        while current in hidden_map:
            if current in seen:
                add_issue(issues, "hidden_chain_cycle", chain=seen + [current])
                break
            seen.append(current)
            current = last_link_target(hidden_map[current])

    if item_image_stems is not None:
        missing_images = [
            ref
            for ref in image_refs
            if not image_resource_exists(item_image_stems, ref[image_ref_key])
        ]
        if missing_images:
            add_issue(
                issues,
                missing_image_kind,
                count=len(missing_images),
                expected_path=expected_image_path,
                details=missing_images,
            )

    completion = simulate_completion_chain(level, target_class_count)

    return {
        "initial_groups": initial_groups,
        "hidden_map": hidden_map,
        "image_refs": image_refs,
        "word_ref_count": len(word_refs),
        "initial_card_count": initial_card_count,
        "completion": completion,
    }


def analyze_model0_level(path, level_name, level, issues, item_image_stems, language_words):
    model = parse_int_like(level.get("model", 0))
    required_keys = ("theme", "difficulty", "gridSize", "showRows", "time", "data")
    for key in required_keys:
        if key not in level:
            add_issue(issues, "missing_required_key", key=key)

    target_class_count, row_count, raw_grid_size = parse_grid_size(level.get("gridSize", ""))
    if target_class_count is None or row_count is None:
        add_issue(issues, "invalid_grid_size", actual=raw_grid_size, expected="<targetClassCount>x<rowCount>")

    for key in ("difficulty", "showRows", "time"):
        if key in level and parse_int_like(level.get(key)) is None:
            add_issue(issues, "metadata_not_parseable_int", key=key, actual=level.get(key))

    if "theme" in level and not isinstance(level.get("theme"), str):
        add_issue(issues, "metadata_not_string", key="theme", actual=level.get("theme"))

    common = analyze_common_counts_and_hidden(
        level,
        issues,
        target_class_count,
        item_image_stems,
        language_words,
        validate_model0_card,
        "imageName",
        "missing_item_image_resources",
        "Assets/Resources/Texture/ItemImage/<imageName>",
    )

    completion = common["completion"]
    if not completion["solvable"]:
        add_issue(
            issues,
            "completion_chain_not_solvable",
            completed_count=completion["completed_count"],
            expected_completion_count=completion["expected_completion_count"],
            remaining_visible=completion["remaining_visible"],
            blocked_snapshot=completion["blocked_snapshot"],
        )

    return {
        "file": str(path),
        "level": level_name,
        "model": model,
        "target_class_count": target_class_count,
        "row_count": row_count,
        "initial_group_count": len(common["initial_groups"]),
        "initial_card_count": common["initial_card_count"],
        "hidden_key_count": len(common["hidden_map"]),
        "image_ref_count": len(common["image_refs"]),
        "solvable": completion["solvable"],
        "completion_count": completion["completed_count"],
        "time_budget": parse_int_like(level.get("time")),
        "issue_count": len(issues),
        "issues": issues,
    }


def analyze_model3_level(path, level_name, level, issues, item_image_stems, language_words):
    model = parse_int_like(level.get("model", 0))
    required_keys = ("theme", "difficulty", "gridSize", "showRows", "move", "data")
    for key in required_keys:
        if key not in level:
            add_issue(issues, "missing_required_key", key=key)

    target_class_count, row_count, raw_grid_size = parse_grid_size(level.get("gridSize", ""))
    if target_class_count is None or row_count is None:
        add_issue(issues, "invalid_grid_size", actual=raw_grid_size, expected="<targetClassCount>x<rowCount>")

    for key in ("difficulty", "showRows", "move"):
        if key in level and parse_int_like(level.get(key)) is None:
            add_issue(issues, "metadata_not_parseable_int", key=key, actual=level.get(key))

    if "theme" in level and not isinstance(level.get("theme"), str):
        add_issue(issues, "metadata_not_string", key="theme", actual=level.get("theme"))

    common = analyze_common_counts_and_hidden(
        level,
        issues,
        target_class_count,
        item_image_stems,
        language_words,
        validate_model3_card,
        "elementName",
        "missing_item_image_resources",
        "Assets/Resources/Texture/ItemImage/<elementName>",
    )

    completion = common["completion"]
    if not completion["solvable"]:
        add_issue(
            issues,
            "completion_chain_not_solvable",
            completed_count=completion["completed_count"],
            expected_completion_count=completion["expected_completion_count"],
            remaining_visible=completion["remaining_visible"],
            blocked_snapshot=completion["blocked_snapshot"],
        )

    move_budget = parse_int_like(level.get("move"))
    shortest_route_moves = target_class_count * 3 if isinstance(target_class_count, int) else None
    if (
        isinstance(move_budget, int)
        and isinstance(shortest_route_moves, int)
        and move_budget <= shortest_route_moves
    ):
        add_issue(
            issues,
            "move_budget_not_greater_than_shortest_route",
            actual=move_budget,
            expected_greater_than=shortest_route_moves,
            reasoning="A zero-mistake model=3 route needs 3 successful merge moves for each completed 4-card class.",
        )

    return {
        "file": str(path),
        "level": level_name,
        "model": model,
        "target_class_count": target_class_count,
        "row_count": row_count,
        "initial_group_count": len(common["initial_groups"]),
        "initial_card_count": common["initial_card_count"],
        "hidden_key_count": len(common["hidden_map"]),
        "type1_image_ref_count": len(common["image_refs"]),
        "text_word_ref_count": common["word_ref_count"],
        "solvable": completion["solvable"],
        "completion_count": completion["completed_count"],
        "shortest_route_moves": shortest_route_moves,
        "min_required_moves": shortest_route_moves,
        "move_budget": move_budget,
        "issue_count": len(issues),
        "issues": issues,
    }


def base_result(path, level_name, level, issues):
    return {
        "file": str(path),
        "level": level_name,
        "model": level.get("model") if isinstance(level, dict) else None,
        "issue_count": len(issues),
        "issues": issues,
    }


def check_level(path, level_name, level, item_image_stems, language_words):
    issues = []
    if not isinstance(level, dict):
        add_issue(issues, "level_not_object", actual_type=type(level).__name__)
        return base_result(path, level_name, level, issues)

    model = parse_int_like(level.get("model", 0))
    if model == 0:
        return analyze_model0_level(path, level_name, level, issues, item_image_stems, language_words)
    if model == 3:
        return analyze_model3_level(path, level_name, level, issues, item_image_stems, language_words)

    add_issue(issues, "invalid_model_value", actual=model, expected="0 or 3")
    return base_result(path, level_name, level, issues)


def summarize_results(results):
    checked = len(results)
    failed = sum(1 for result in results if result["issue_count"] > 0)
    return {
        "checked": checked,
        "passed": checked - failed,
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
    detail_results = [result for result in results if result["issue_count"] > 0] if only_failed else results
    if any(result["issue_count"] > 0 for result in detail_results):
        lines.append("")
        lines.append("Suspicious levels:")
        for result in detail_results:
            if result["issue_count"] == 0:
                continue
            lines.append(f"- {result['level']} ({pathlib.Path(result['file']).name}): {result['issue_count']} issue(s)")
            for issue in result["issues"]:
                lines.append(f"  - {issue['kind']}: {json.dumps(issue, ensure_ascii=False)}")
    return "\n".join(lines)


def main():
    args = parse_args()
    levels = load_levels(args)
    if not levels:
        print("No matching levels found.", file=sys.stderr)
        return 2

    item_image_stems = load_item_image_stems(args)
    language_words = load_language_words(args)
    results = [check_level(path, level_name, level, item_image_stems, language_words) for path, level_name, level in levels]
    rendered_results = [result for result in results if result["issue_count"] > 0] if args.only_failed else results

    if args.json:
        payload = {"summary": summarize_results(results), "results": rendered_results}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(format_text(results, only_failed=args.only_failed))

    has_issues = any(result["issue_count"] for result in results)
    return 1 if has_issues and not args.no_fail_on_issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
