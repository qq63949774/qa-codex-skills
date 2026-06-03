#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


LEVEL_FILE_RE = re.compile(r"^diff(?:(1)|(\d+)_(\d+))\.json$")
SPRITE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".psd", ".tga")


@dataclass
class Issue:
    severity: str
    code: str
    language: str
    file: str
    level: int | None
    item: str
    status: str
    function: str
    reasoning: str
    suggested_validation: str


@dataclass
class LevelLocation:
    language: str
    file_name: str
    file_path: str
    index: int
    level: int
    data: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan WordTiles local level JSONs against current runtime loading rules."
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Outer repo root or Unity project root. Defaults to current directory.",
    )
    parser.add_argument(
        "--resources-out",
        default=None,
        help="Override path to Assets/Main/Resources/out.",
    )
    parser.add_argument(
        "--language",
        action="append",
        default=[],
        help="Language folder to scan. Can be passed multiple times. Defaults to all languages.",
    )
    parser.add_argument("--level", type=int, default=None, help="Only report issues for this level.")
    parser.add_argument("--file", default=None, help="Only scan one diff*.json file name.")
    parser.add_argument("--json", action="store_true", help="Emit full JSON result.")
    parser.add_argument(
        "--code",
        action="append",
        default=[],
        help="Only report a specific issue code. Can be passed multiple times.",
    )
    parser.add_argument("--fail-only", action="store_true", help="Hide warnings in text output.")
    parser.add_argument("--max-issues", type=int, default=80, help="Max issues to print in text output.")
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Always exit 0 even when failures are found.",
    )
    return parser.parse_args()


def find_unity_project_root(project_root: Path) -> Path:
    candidates = [project_root, project_root / "WordTiles"]
    for candidate in candidates:
        if (candidate / "Assets" / "Main" / "Resources" / "out").is_dir():
            return candidate.resolve()
    raise SystemExit(
        "Unable to find WordTiles Unity root. Expected Assets/Main/Resources/out under "
        f"{project_root} or {project_root / 'WordTiles'}."
    )


def declared_range(file_name: str) -> tuple[int, int] | None:
    match = LEVEL_FILE_RE.match(file_name)
    if not match:
        return None
    if match.group(1):
        return (1, 1)
    return (int(match.group(2)), int(match.group(3)))


def expected_runtime_file(level: int) -> str:
    if level == 1:
        return "diff1.json"
    begin = level // 100 * 100 + 2
    end = (level // 100 + 1) * 100
    return f"diff{begin}_{end}.json"


def is_int_like(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return value.is_integer()
    if isinstance(value, str):
        text = value.strip()
        return bool(re.fullmatch(r"-?\d+", text))
    return False


def to_int(value: Any) -> int | None:
    if not is_int_like(value):
        return None
    return int(value)


def normalize_unity_token(value: str) -> str:
    return value.replace(" ", "_")


def resource_exists(resources_root: Path, unity_resource_path: str) -> bool:
    base = resources_root / unity_resource_path
    return any((base.with_suffix(ext)).is_file() for ext in SPRITE_EXTENSIONS)


def compact_ranges(values: list[int]) -> str:
    if not values:
        return ""
    values = sorted(set(values))
    ranges: list[str] = []
    start = prev = values[0]
    for value in values[1:]:
        if value == prev + 1:
            prev = value
            continue
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
        start = prev = value
    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(ranges)


def add_issue(
    issues: list[Issue],
    *,
    severity: str,
    code: str,
    language: str,
    file: str,
    level: int | None,
    item: str,
    function: str,
    reasoning: str,
    suggested_validation: str,
) -> None:
    issues.append(
        Issue(
            severity=severity,
            code=code,
            language=language,
            file=file,
            level=level,
            item=item,
            status="FAIL" if severity == "failure" else "WARN",
            function=function,
            reasoning=reasoning,
            suggested_validation=suggested_validation,
        )
    )


def issue_applies_to_level(issue: Issue, selected_level: int | None) -> bool:
    return selected_level is None or issue.level in (None, selected_level)


def load_json_file(path: Path, language: str, issues: list[Issue]) -> list[Any] | None:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except Exception as exc:  # noqa: BLE001 - report parser detail to QA output
        add_issue(
            issues,
            severity="failure",
            code="json_parse_error",
            language=language,
            file=str(path),
            level=None,
            item=path.name,
            function="GameLevel.loadData / JArray.Parse",
            reasoning=f"JSON parser failed: {exc}",
            suggested_validation="Open the file in a JSON parser, fix syntax, then rerun this checker.",
        )
        return None
    if not isinstance(data, list):
        add_issue(
            issues,
            severity="failure",
            code="json_root_not_array",
            language=language,
            file=str(path),
            level=None,
            item=path.name,
            function="GameLevel.loadData / JArray.Parse",
            reasoning="Runtime parses the level file as a JArray, but this file root is not an array.",
            suggested_validation="Change the file root to an array of level objects and rerun.",
        )
        return None
    return data


def validate_book(
    *,
    book: Any,
    book_index: int,
    language: str,
    file_path: Path,
    level: int,
    resources_root: Path,
    issues: list[Issue],
) -> tuple[int | None, dict[str, Any] | None]:
    item = f"level {level} books[{book_index}]"
    if not isinstance(book, dict):
        add_issue(
            issues,
            severity="failure",
            code="book_not_object",
            language=language,
            file=str(file_path),
            level=level,
            item=item,
            function="TileGameData.init / JsonConvert.DeserializeObject<List<WordBook>>",
            reasoning="A books entry is not an object and cannot populate WordBook fields reliably.",
            suggested_validation="Make each books entry an object with id, name, image, count, and words.",
        )
        return None, None

    book_id = to_int(book.get("id"))
    name = book.get("name")
    count = to_int(book.get("count"))
    words = book.get("words")
    image = book.get("image")

    if book_id is None:
        add_issue(
            issues,
            severity="failure",
            code="book_id_invalid",
            language=language,
            file=str(file_path),
            level=level,
            item=item,
            function="TileGameData.getWordBook / WordBook.id",
            reasoning="Book id is missing or cannot be converted to an integer.",
            suggested_validation="Set books[].id to a unique integer and rerun.",
        )
    if not isinstance(name, str) or not name.strip():
        add_issue(
            issues,
            severity="failure",
            code="book_name_invalid",
            language=language,
            file=str(file_path),
            level=level,
            item=item,
            function="BaseItem.feshTypeCard / WordBook.name",
            reasoning="Book name is missing or empty; runtime uses it for category labels.",
            suggested_validation="Set books[].name to a non-empty string and verify the label in runtime.",
        )
    if count is None or count < 0:
        add_issue(
            issues,
            severity="failure",
            code="book_count_invalid",
            language=language,
            file=str(file_path),
            level=level,
            item=item,
            function="TileGameData.GetBookCount / WordBook.count",
            reasoning="Book count is missing, non-integer, or negative.",
            suggested_validation="Set books[].count to a non-negative integer and rerun.",
        )
    if not isinstance(words, list):
        add_issue(
            issues,
            severity="failure",
            code="book_words_invalid",
            language=language,
            file=str(file_path),
            level=level,
            item=item,
            function="TileGameData.queryWord / WordBook.words",
            reasoning="Book words is missing or not an array; runtime indexes this field for item cards.",
            suggested_validation="Set books[].words to an array of strings and rerun.",
        )
        words = []
    if not isinstance(image, bool):
        add_issue(
            issues,
            severity="failure",
            code="book_image_invalid",
            language=language,
            file=str(file_path),
            level=level,
            item=item,
            function="TileOne.init / WordBook.image",
            reasoning="Book image flag is missing or not boolean; runtime branches text/image rendering on it.",
            suggested_validation="Set books[].image to true or false and rerun.",
        )
        image = False

    string_words = [word for word in words if isinstance(word, str)]
    for word_index, word in enumerate(words):
        if not isinstance(word, str) or not word.strip():
            add_issue(
                issues,
                severity="failure",
                code="book_word_invalid",
                language=language,
                file=str(file_path),
                level=level,
                item=f"{item}.words[{word_index}]",
                function="TileGameData.queryWord / WordBook.words",
                reasoning="A word entry is missing, empty, or not a string.",
                suggested_validation="Replace the word with a non-empty string and verify the tile display.",
            )

    if count is not None and isinstance(words, list):
        if len(words) < count:
            add_issue(
                issues,
                severity="failure",
                code="book_count_exceeds_words",
                language=language,
                file=str(file_path),
                level=level,
                item=item,
                function="TileGameData.queryWord / book.words[index - 1]",
                reasoning=f"count={count}, but words.length={len(words)}; runtime can index past the words array.",
                suggested_validation="Add enough words or reduce count, then start this level in runtime.",
            )
        elif len(words) != count:
            add_issue(
                issues,
                severity="warning",
                code="book_count_words_length_mismatch",
                language=language,
                file=str(file_path),
                level=level,
                item=item,
                function="TileGameData.getAllArray / TileGameData.queryWord",
                reasoning=f"count={count}, but words.length={len(words)}; extra words are likely unused.",
                suggested_validation="Confirm whether extra words are intentional; otherwise align count and words length.",
            )

    seen_words: dict[str, int] = {}
    for word_index, word in enumerate(string_words):
        normalized = " ".join(word.strip().casefold().split())
        if normalized in seen_words:
            add_issue(
                issues,
                severity="warning",
                code="duplicate_word_in_book",
                language=language,
                file=str(file_path),
                level=level,
                item=f"{item}.words[{word_index}]",
                function="TileGameData.queryWord / WordBook.words",
                reasoning=(
                    f"Duplicate displayed word also appears at words[{seen_words[normalized]}]: {word!r}."
                ),
                suggested_validation="Confirm the duplicate is intentional; otherwise replace one entry.",
            )
        else:
            seen_words[normalized] = word_index

    if image is True and count is not None and isinstance(words, list):
        for word_index, word in enumerate(words[:count]):
            if not isinstance(word, str):
                continue
            parts = word.split("#")
            if len(parts) < 2:
                add_issue(
                    issues,
                    severity="failure",
                    code="image_word_missing_resource_parts",
                    language=language,
                    file=str(file_path),
                    level=level,
                    item=f"{item}.words[{word_index}]",
                    function="TileGameData.queryImage / word.Split('#')",
                    reasoning=(
                        "Image books render non-cover cards through queryImage(), which reads the last two "
                        "segments of word.Split('#'); this word has fewer than two segments."
                    ),
                    suggested_validation=(
                        "Use a runtime-compatible image token such as Class#Resource, or update client parsing "
                        "and verify the level in Unity."
                    ),
                )
                continue
            class_name = normalize_unity_token(parts[-2])
            resource_key = normalize_unity_token(parts[-1])
            unity_path = f"Origin/{class_name}/{class_name}#{resource_key}@2x"
            if not resource_exists(resources_root, unity_path):
                add_issue(
                    issues,
                    severity="failure",
                    code="image_resource_missing",
                    language=language,
                    file=str(file_path),
                    level=level,
                    item=f"{item}.words[{word_index}]",
                    function="TileGameData.queryImage / UIExtension.loadSprite",
                    reasoning=f"Expected sprite resource is missing: Assets/Main/Resources/{unity_path}.<image>",
                    suggested_validation="Add or rename the sprite asset, then verify Resources.Load<Sprite>() in runtime.",
                )

    signature = None
    if book_id is not None:
        signature = {
            "id": book_id,
            "count": count,
            "image": image if isinstance(image, bool) else None,
            "words_len": len(words) if isinstance(words, list) else None,
        }
    return book_id, signature


def validate_level(
    *,
    data: Any,
    index: int,
    language: str,
    file_path: Path,
    expected_range: tuple[int, int] | None,
    resources_root: Path,
    issues: list[Issue],
) -> tuple[int | None, dict[str, Any] | None]:
    file_item = f"{file_path.name}[{index}]"
    if not isinstance(data, dict):
        add_issue(
            issues,
            severity="failure",
            code="level_not_object",
            language=language,
            file=str(file_path),
            level=None,
            item=file_item,
            function="GameLevel.loadData / x[\"level\"].Value<int>()",
            reasoning="A level array entry is not an object.",
            suggested_validation="Make each level array entry an object and rerun.",
        )
        return None, None

    level = to_int(data.get("level"))
    if level is None:
        add_issue(
            issues,
            severity="failure",
            code="level_id_invalid",
            language=language,
            file=str(file_path),
            level=None,
            item=file_item,
            function="GameLevel.loadData / x[\"level\"].Value<int>()",
            reasoning="Level id is missing or cannot be converted to an integer.",
            suggested_validation="Set level to a positive integer and rerun.",
        )
        return None, None

    if level < 1:
        add_issue(
            issues,
            severity="failure",
            code="level_id_out_of_range",
            language=language,
            file=str(file_path),
            level=level,
            item=file_item,
            function="GameConfig.CurrentLevel / GameLevel.loadData",
            reasoning="Level id must be at least 1 for the normal-level flow.",
            suggested_validation="Use a positive level id and rerun.",
        )

    if expected_range is not None and not (expected_range[0] <= level <= expected_range[1]):
        add_issue(
            issues,
            severity="failure",
            code="level_outside_declared_file_range",
            language=language,
            file=str(file_path),
            level=level,
            item=file_item,
            function="GameLevel.GetNoramlLevelText / Resources.Load<TextAsset>",
            reasoning=(
                f"{file_path.name} declares levels {expected_range[0]}-{expected_range[1]}, "
                f"but contains level {level}."
            ),
            suggested_validation="Move the level to the matching diff file or rename the file consistently.",
        )

    runtime_file = expected_runtime_file(level)
    if file_path.name != runtime_file:
        add_issue(
            issues,
            severity="failure",
            code="runtime_file_mismatch",
            language=language,
            file=str(file_path),
            level=level,
            item=f"level {level}",
            function="GameLevel.GetNoramlLevelText",
            reasoning=(
                f"Current client will request {runtime_file} for level {level}, "
                f"but this level is stored in {file_path.name}."
            ),
            suggested_validation="Start this level in Unity or align filename/range logic with the packaged data.",
        )

    base_count = to_int(data.get("baseCount"))
    if base_count is None:
        add_issue(
            issues,
            severity="failure",
            code="base_count_invalid",
            language=language,
            file=str(file_path),
            level=level,
            item=f"level {level}.baseCount",
            function="TileGameData.init / Convert.ToInt32(level[\"baseCount\"])",
            reasoning="baseCount is missing or cannot be converted to an integer.",
            suggested_validation="Set baseCount to a positive integer and rerun.",
        )
    elif base_count < 1:
        add_issue(
            issues,
            severity="failure",
            code="base_count_too_low",
            language=language,
            file=str(file_path),
            level=level,
            item=f"level {level}.baseCount",
            function="TileGameData.init / baseDatas",
            reasoning="baseCount creates the number of base slots; values below 1 leave no valid target slots.",
            suggested_validation="Set baseCount to at least 1 and verify the level in runtime.",
        )

    raw_word_books = data.get("wordBooks")
    if not isinstance(raw_word_books, list):
        add_issue(
            issues,
            severity="failure",
            code="word_books_invalid",
            language=language,
            file=str(file_path),
            level=level,
            item=f"level {level}.wordBooks",
            function="TileGameData.init / JsonConvert.DeserializeObject<List<int>>",
            reasoning="wordBooks is missing or not an array.",
            suggested_validation="Set wordBooks to an array of book ids and rerun.",
        )
        word_books: list[int] = []
    else:
        word_books = []
        for word_book_index, value in enumerate(raw_word_books):
            parsed = to_int(value)
            if parsed is None:
                add_issue(
                    issues,
                    severity="failure",
                    code="word_book_id_invalid",
                    language=language,
                    file=str(file_path),
                    level=level,
                    item=f"level {level}.wordBooks[{word_book_index}]",
                    function="TileGameData.init / allTypes",
                    reasoning="wordBooks entry is not an integer book id.",
                    suggested_validation="Replace the entry with an integer id that exists in books.",
                )
            else:
                word_books.append(parsed)

    if len(word_books) != len(set(word_books)):
        add_issue(
            issues,
            severity="failure",
            code="duplicate_word_book_id",
            language=language,
            file=str(file_path),
            level=level,
            item=f"level {level}.wordBooks",
            function="TileGameData.finishTypes / TileGameData.isSucc",
            reasoning="wordBooks contains duplicate ids; finishTypes stores unique ids, so completion can be inconsistent.",
            suggested_validation="Remove duplicate ids and verify level completion in runtime.",
        )

    raw_books = data.get("books")
    if not isinstance(raw_books, list):
        add_issue(
            issues,
            severity="failure",
            code="books_invalid",
            language=language,
            file=str(file_path),
            level=level,
            item=f"level {level}.books",
            function="TileGameData.init / JsonConvert.DeserializeObject<List<WordBook>>",
            reasoning="books is missing or not an array.",
            suggested_validation="Set books to an array of book objects and rerun.",
        )
        raw_books = []

    book_ids: list[int] = []
    signatures: list[dict[str, Any]] = []
    for book_index, book in enumerate(raw_books):
        book_id, signature = validate_book(
            book=book,
            book_index=book_index,
            language=language,
            file_path=file_path,
            level=level,
            resources_root=resources_root,
            issues=issues,
        )
        if book_id is not None:
            if book_id in book_ids:
                add_issue(
                    issues,
                    severity="failure",
                    code="duplicate_book_id",
                    language=language,
                    file=str(file_path),
                    level=level,
                    item=f"level {level}.books[{book_index}]",
                    function="TileGameData.getWordBook",
                    reasoning=f"Duplicate book id {book_id}; getWordBook() returns the first matching book.",
                    suggested_validation="Make books[].id unique and verify tiles for this level.",
                )
            book_ids.append(book_id)
        if signature is not None:
            signatures.append(signature)

    book_id_set = set(book_ids)
    for word_book_id in word_books:
        if word_book_id not in book_id_set:
            add_issue(
                issues,
                severity="failure",
                code="word_book_missing_book",
                language=language,
                file=str(file_path),
                level=level,
                item=f"level {level}.wordBooks",
                function="TileGameData.getWordBook / TileGameData.GetBookCount",
                reasoning=f"wordBooks references id {word_book_id}, but books does not define that id.",
                suggested_validation="Add the missing book or remove the id from wordBooks, then rerun.",
            )

    unused_book_ids = sorted(book_id_set.difference(word_books))
    if unused_book_ids:
        add_issue(
            issues,
            severity="warning",
            code="unused_books",
            language=language,
            file=str(file_path),
            level=level,
            item=f"level {level}.books",
            function="TileGameData.getAllArray / wordBooks",
            reasoning=f"books contains ids not referenced by wordBooks: {unused_book_ids}.",
            suggested_validation="Confirm these books are intentionally unused; otherwise update wordBooks.",
        )

    if base_count is not None and word_books and base_count > len(word_books):
        add_issue(
            issues,
            severity="warning",
            code="base_count_exceeds_word_books",
            language=language,
            file=str(file_path),
            level=level,
            item=f"level {level}.baseCount",
            function="TileGameData.init / baseDatas",
            reasoning=f"baseCount={base_count}, but wordBooks has only {len(word_books)} categories.",
            suggested_validation="Verify the intended difficulty and empty-slot behavior in runtime.",
        )

    signature = {
        "baseCount": base_count,
        "wordBooks": word_books,
        "books": sorted(signatures, key=lambda value: value["id"]),
    }
    return level, signature


def scan_language(
    *,
    language_dir: Path,
    resources_root: Path,
    selected_file: str | None,
    issues: list[Issue],
) -> tuple[dict[int, LevelLocation], dict[int, dict[str, Any]], int]:
    language = language_dir.name
    levels: dict[int, LevelLocation] = {}
    signatures: dict[int, dict[str, Any]] = {}
    files_scanned = 0

    files = sorted(language_dir.glob("diff*.json"))
    if selected_file:
        files = [language_dir / selected_file]

    for path in files:
        if not path.exists():
            add_issue(
                issues,
                severity="failure",
                code="selected_file_missing",
                language=language,
                file=str(path),
                level=None,
                item=path.name,
                function="GameLevel.GetNoramlLevelText / Resources.Load<TextAsset>",
                reasoning="Selected diff file does not exist.",
                suggested_validation="Check the file name or restore the missing level package.",
            )
            continue

        expected_range = declared_range(path.name)
        if expected_range is None:
            add_issue(
                issues,
                severity="failure",
                code="unexpected_level_file_name",
                language=language,
                file=str(path),
                level=None,
                item=path.name,
                function="GameLevel.GetNoramlLevelText",
                reasoning="Level file name does not match diff1.json or diff<start>_<end>.json.",
                suggested_validation="Rename the file to match the runtime Resources path pattern.",
            )
        data = load_json_file(path, language, issues)
        if data is None:
            continue
        files_scanned += 1

        for index, entry in enumerate(data):
            level, signature = validate_level(
                data=entry,
                index=index,
                language=language,
                file_path=path,
                expected_range=expected_range,
                resources_root=resources_root,
                issues=issues,
            )
            if level is None:
                continue
            if level in levels:
                first = levels[level]
                add_issue(
                    issues,
                    severity="failure",
                    code="duplicate_level_id",
                    language=language,
                    file=str(path),
                    level=level,
                    item=f"level {level}",
                    function="GameLevel.loadData / FirstOrDefault",
                    reasoning=(
                        f"Duplicate level id {level}; first occurrence is "
                        f"{first.file_path}[{first.index}], current is {path}[{index}]."
                    ),
                    suggested_validation="Keep only one object per level id in each language.",
                )
            else:
                levels[level] = LevelLocation(
                    language=language,
                    file_name=path.name,
                    file_path=str(path),
                    index=index,
                    level=level,
                    data=entry,
                )
            if signature is not None:
                signatures[level] = signature

    if levels:
        all_levels = sorted(levels)
        missing = [value for value in range(all_levels[0], all_levels[-1] + 1) if value not in levels]
        if missing:
            add_issue(
                issues,
                severity="failure",
                code="missing_level_range",
                language=language,
                file=str(language_dir),
                level=None,
                item=f"{language} level coverage",
                function="GameConfig.CurrentLevel / GameLevel.loadData",
                reasoning=f"Missing levels inside {all_levels[0]}-{all_levels[-1]}: {compact_ranges(missing)}.",
                suggested_validation="Add the missing levels or confirm they are unreachable in progression.",
            )

    return levels, signatures, files_scanned


def compare_languages(
    *,
    all_levels: dict[str, dict[int, LevelLocation]],
    all_signatures: dict[str, dict[int, dict[str, Any]]],
    selected_level: int | None,
    issues: list[Issue],
) -> None:
    if len(all_levels) < 2:
        return
    baseline_language = "en" if "en" in all_levels else sorted(all_levels)[0]
    baseline_levels = set(all_levels[baseline_language])
    baseline_signatures = all_signatures[baseline_language]

    for language in sorted(all_levels):
        if language == baseline_language:
            continue
        current_levels = set(all_levels[language])
        missing = sorted(baseline_levels - current_levels)
        extra = sorted(current_levels - baseline_levels)
        if selected_level is not None:
            missing = [value for value in missing if value == selected_level]
            extra = [value for value in extra if value == selected_level]
        if missing:
            add_issue(
                issues,
                severity="failure",
                code="cross_language_missing_levels",
                language=language,
                file=str(Path(all_levels[baseline_language][next(iter(baseline_levels))].file_path).parent),
                level=None if selected_level is None else selected_level,
                item=f"{language} vs {baseline_language}",
                function="GameLevel.GetNoramlLevelText / Language.getCurrentLocaleCode",
                reasoning=(
                    f"{language} is missing levels present in {baseline_language}: {compact_ranges(missing)}."
                ),
                suggested_validation="Add matching localized level objects or confirm the language is not shipped.",
            )
        if extra:
            add_issue(
                issues,
                severity="failure",
                code="cross_language_extra_levels",
                language=language,
                file=str(Path(next(iter(all_levels[language].values())).file_path).parent),
                level=None if selected_level is None else selected_level,
                item=f"{language} vs {baseline_language}",
                function="GameLevel.GetNoramlLevelText / Language.getCurrentLocaleCode",
                reasoning=f"{language} has levels absent from {baseline_language}: {compact_ranges(extra)}.",
                suggested_validation="Confirm whether the baseline language is incomplete or remove unintended extras.",
            )

        shared = sorted(baseline_levels & current_levels)
        if selected_level is not None:
            shared = [value for value in shared if value == selected_level]
        for level in shared:
            baseline_signature = baseline_signatures.get(level)
            current_signature = all_signatures[language].get(level)
            if baseline_signature != current_signature:
                add_issue(
                    issues,
                    severity="failure",
                    code="cross_language_structure_mismatch",
                    language=language,
                    file=all_levels[language][level].file_path,
                    level=level,
                    item=f"level {level} structure",
                    function="TileGameData.init / localized level data",
                    reasoning=(
                        f"{language} level {level} structure differs from {baseline_language}; "
                        "baseCount, wordBooks, book ids, count, image flags, or words length do not match."
                    ),
                    suggested_validation=(
                        f"Compare {language} and {baseline_language} level {level}, then run this checker again."
                    ),
                )


def main() -> int:
    args = parse_args()
    project_root_arg = Path(args.project_root).expanduser().resolve()
    unity_root = find_unity_project_root(project_root_arg)
    resources_root = unity_root / "Assets" / "Main" / "Resources"
    resources_out = (
        Path(args.resources_out).expanduser().resolve()
        if args.resources_out
        else resources_root / "out"
    )
    if not resources_out.is_dir():
        raise SystemExit(f"Resources out directory not found: {resources_out}")

    languages = sorted(path.name for path in resources_out.iterdir() if path.is_dir())
    if args.language:
        wanted = set(args.language)
        missing_languages = sorted(wanted.difference(languages))
        if missing_languages:
            raise SystemExit(f"Language folder(s) not found under {resources_out}: {missing_languages}")
        languages = [language for language in languages if language in wanted]
    if not languages:
        raise SystemExit(f"No language folders found under {resources_out}")

    issues: list[Issue] = []
    all_levels: dict[str, dict[int, LevelLocation]] = {}
    all_signatures: dict[str, dict[int, dict[str, Any]]] = {}
    files_scanned = 0

    for language in languages:
        levels, signatures, count = scan_language(
            language_dir=resources_out / language,
            resources_root=resources_root,
            selected_file=args.file,
            issues=issues,
        )
        all_levels[language] = levels
        all_signatures[language] = signatures
        files_scanned += count

    compare_languages(
        all_levels=all_levels,
        all_signatures=all_signatures,
        selected_level=args.level,
        issues=issues,
    )

    filtered_issues = [issue for issue in issues if issue_applies_to_level(issue, args.level)]
    if args.code:
        wanted_codes = set(args.code)
        filtered_issues = [issue for issue in filtered_issues if issue.code in wanted_codes]
    if args.fail_only:
        filtered_issues = [issue for issue in filtered_issues if issue.severity == "failure"]

    failures = sum(1 for issue in filtered_issues if issue.severity == "failure")
    warnings = sum(1 for issue in filtered_issues if issue.severity == "warning")
    issue_counts_by_code = Counter(issue.code for issue in filtered_issues)
    failure_counts_by_code = Counter(
        issue.code for issue in filtered_issues if issue.severity == "failure"
    )
    warning_counts_by_code = Counter(
        issue.code for issue in filtered_issues if issue.severity == "warning"
    )
    level_counts = {language: len(levels) for language, levels in all_levels.items()}
    result = {
        "status": "FAIL" if failures else "PASS",
        "project_root": str(unity_root),
        "resources_out": str(resources_out),
        "languages": languages,
        "files_scanned": files_scanned,
        "level_counts": level_counts,
        "selected_level": args.level,
        "selected_codes": args.code,
        "failures": failures,
        "warnings": warnings,
        "issue_counts_by_code": dict(issue_counts_by_code.most_common()),
        "failure_counts_by_code": dict(failure_counts_by_code.most_common()),
        "warning_counts_by_code": dict(warning_counts_by_code.most_common()),
        "issues": [asdict(issue) for issue in filtered_issues],
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("WordTiles level scan")
        print(f"status: {result['status']}")
        print(f"project_root: {unity_root}")
        print(f"resources_out: {resources_out}")
        print(f"languages: {', '.join(languages)}")
        print(f"files_scanned: {files_scanned}")
        print(f"level_counts: {level_counts}")
        print(f"failures: {failures}")
        print(f"warnings: {warnings}")
        if issue_counts_by_code:
            print("issue_counts_by_code:")
            for code, count in issue_counts_by_code.most_common():
                print(f"  {code}: {count}")
        if filtered_issues:
            print("")
            print(f"issues (showing first {min(args.max_issues, len(filtered_issues))} of {len(filtered_issues)}):")
            for issue in filtered_issues[: args.max_issues]:
                level_text = "all" if issue.level is None else str(issue.level)
                print(
                    f"- [{issue.status}] {issue.code} | lang={issue.language} | "
                    f"level={level_text} | item={issue.item}"
                )
                print(f"  file: {issue.file}")
                print(f"  function: {issue.function}")
                print(f"  reasoning: {issue.reasoning}")
                print(f"  validation: {issue.suggested_validation}")
        else:
            print("issues: none")

    if failures and not args.no_fail:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
