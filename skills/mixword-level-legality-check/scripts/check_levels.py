#!/usr/bin/env python3
"""Check Mixword level legality with static and runtime validations."""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


EPSILON = 1e-6


@dataclass
class RawKeyGroup:
    title: str
    is_image: bool
    content: List[str]


@dataclass
class RawStage:
    column: List[List[str]]
    stock: List[str]
    key: List[RawKeyGroup]
    class_name: List[Dict[str, str]]
    source_file_name: str
    source_item_index: int
    source_language: str
    mapped_level: Optional[int] = None


@dataclass
class LegacyBook:
    book_id: int
    name: str
    count: int
    words: List[str]
    image: bool
    resource_class_name: Optional[str]
    resource_keys: Optional[List[str]]


@dataclass
class LegacyLevel:
    founds: List[List[float]]
    columns: List[List[float]]
    stocks: List[float]
    word_books: List[int]
    books: List[LegacyBook]


@dataclass
class CheckMessage:
    severity: str
    code: str
    message: str


@dataclass
class LevelCheckResult:
    dataset: str
    language: str
    file_name: str
    item_index: int
    mapped_level: Optional[int]
    static_messages: List[CheckMessage]
    runtime_messages: List[CheckMessage]

    @property
    def ok(self) -> bool:
        return not any(msg.severity == "error" for msg in self.static_messages + self.runtime_messages)


@dataclass
class LayoutCheckResult:
    dataset: str
    level: int
    baseline_language: str
    mismatches: List[str]
    details: List[str]

    @property
    def ok(self) -> bool:
        return not self.mismatches


def is_type(card: float) -> bool:
    return abs(card - round(card)) < EPSILON


def card_type(card: float) -> int:
    return int(round(card)) if is_type(card) else int(math.floor(card + EPSILON))


def format_card(card: float) -> str:
    return str(int(round(card))) if is_type(card) else f"{card:.2f}"


def add_message(messages: List[CheckMessage], severity: str, code: str, message: str) -> None:
    messages.append(CheckMessage(severity=severity, code=code, message=message))


def severity_label(severity: str) -> str:
    return {
        "error": "错误",
        "warning": "警告",
        "info": "信息",
    }.get(severity, severity)


def load_stage_from_slot(dataset_root: Path, language: str, file_name: str, item_index: int) -> RawStage:
    file_path = dataset_root / language / file_name
    if not file_path.exists():
        raise FileNotFoundError(f"找不到关卡资源文件：{file_path}")

    data = json.loads(file_path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"关卡资源文件不是 JSON 数组：{file_path}")
    if item_index < 0 or item_index >= len(data):
        raise IndexError(f"槽位索引 {item_index} 超出 {file_path.name} 范围")

    token = data[item_index]
    if not isinstance(token, dict):
        raise ValueError(f"{file_path.name} 的槽位 {item_index} 不是 JSON 对象")

    key_groups = []
    for group in token.get("key", []) or []:
        key_groups.append(
            RawKeyGroup(
                title=group.get("title", ""),
                is_image=bool(group.get("isImage", False)),
                content=list(group.get("content") or []),
            )
        )

    return RawStage(
        column=[list(column or []) for column in token.get("column") or []],
        stock=list(token.get("stock") or []),
        key=key_groups,
        class_name=list(token.get("className") or []),
        source_file_name=file_path.name,
        source_item_index=item_index,
        source_language=language,
    )


def load_stage_from_level(dataset_root: Path, language: str, level: int) -> RawStage:
    language_root = dataset_root / language
    if not language_root.exists():
        fallback_root = dataset_root / "en"
        if language != "en" and fallback_root.exists():
            language = "en"
            language_root = fallback_root
        else:
            raise FileNotFoundError(f"找不到语言目录：{dataset_root / language}")

    file_names = sorted(
        [path.name for path in language_root.glob("*.json")],
        key=lambda name: (int(Path(name).stem) if Path(name).stem.isdigit() else 10**9, name),
    )
    if not file_names:
        raise FileNotFoundError(f"在 {language_root} 下找不到 JSON 文件")

    slot_count = len(file_names) * 10
    start_slot = (level - 1) % slot_count
    for offset in range(slot_count):
        slot = (start_slot + offset) % slot_count
        file_name = file_names[slot // 10]
        item_index = slot % 10
        try:
            stage = load_stage_from_slot(dataset_root, language, file_name, item_index)
        except IndexError:
            continue
        stage.mapped_level = level + offset
        return stage

    raise ValueError(f"在 {language_root} 中找不到可用的关卡 {level} 原始槽位")


def resolve_resource_class_name(class_names: Sequence[Dict[str, str]], title: str) -> str:
    for entry in class_names:
        if isinstance(entry, dict) and title in entry and entry[title]:
            return entry[title]
    raise ValueError(f"缺少 '{title}' 的 className 映射")


def normalize_image_content(title: str, raw_content: str, expected_class_name: str) -> Tuple[str, str]:
    parts = raw_content.split("#")
    if len(parts) == 3:
        class_name = parts[1]
        resource_key = parts[2]
    elif len(parts) == 2:
        class_name = parts[0]
        resource_key = parts[1]
    else:
        raise ValueError(f"'{title}' 的图片 token 格式不支持：'{raw_content}'")

    if not class_name or not resource_key:
        raise ValueError(f"'{title}' 的图片 token 非法：'{raw_content}'")
    if class_name != expected_class_name:
        raise ValueError(
            f"图片 className '{class_name}' 与期望值 '{expected_class_name}' 不一致"
        )
    return f"{class_name}#{resource_key}", resource_key


def adapt_stage(stage: RawStage) -> Tuple[LegacyLevel, Dict[str, float], List[CheckMessage]]:
    messages: List[CheckMessage] = []
    token_to_id: Dict[str, float] = {}
    books: List[LegacyBook] = []
    word_books: List[int] = []

    seen_titles = set()
    for key_index, key_group in enumerate(stage.key):
        if not key_group.title:
            add_message(messages, "error", "empty-title", f"第 {key_index} 个 key 分组 title 为空")
            continue
        if key_group.title in seen_titles:
            add_message(messages, "error", "duplicate-title", f"存在重复 key title：'{key_group.title}'")
            continue
        seen_titles.add(key_group.title)

        type_id = key_index + 1
        contents = key_group.content or []
        words: List[str] = []
        resource_keys: Optional[List[str]] = [] if key_group.is_image else None
        resource_class_name: Optional[str] = None

        if f"{key_group.title}:{key_group.title}" in token_to_id:
            add_message(messages, "error", "duplicate-token", f"类别 token 重复：'{key_group.title}:{key_group.title}'")
        token_to_id[f"{key_group.title}:{key_group.title}"] = float(type_id)

        if key_group.is_image:
            try:
                resource_class_name = resolve_resource_class_name(stage.class_name, key_group.title)
            except ValueError as exc:
                add_message(messages, "error", "missing-classname", str(exc))
                resource_class_name = None

        for content_index, raw_content in enumerate(contents):
            mapped_id = type_id + (content_index + 1) / 100.0
            if key_group.is_image:
                if not resource_class_name:
                    continue
                try:
                    board_token, resource_key = normalize_image_content(
                        key_group.title, raw_content, resource_class_name
                    )
                except ValueError as exc:
                    add_message(messages, "error", "bad-image-token", str(exc))
                    continue
                words.append(resource_key)
                assert resource_keys is not None
                resource_keys.append(resource_key)
                token_key = f"{key_group.title}:{board_token}"
            else:
                words.append(raw_content)
                token_key = f"{key_group.title}:{raw_content}"

            if token_key in token_to_id:
                add_message(messages, "error", "duplicate-token", f"存在重复 token：'{token_key}'")
            token_to_id[token_key] = float(mapped_id)

        books.append(
            LegacyBook(
                book_id=type_id,
                name=key_group.title,
                count=len(contents),
                words=words,
                image=key_group.is_image,
                resource_class_name=resource_class_name,
                resource_keys=resource_keys,
            )
        )
        word_books.append(type_id)

    founds = [[] for _ in stage.column]
    columns = [map_tokens(column, token_to_id, messages, stage, "column") for column in stage.column]
    stocks = map_tokens(stage.stock, token_to_id, messages, stage, "stock")

    return (
        LegacyLevel(
            founds=founds,
            columns=columns,
            stocks=stocks,
            word_books=word_books,
            books=books,
        ),
        token_to_id,
        messages,
    )


def map_tokens(
    tokens: Iterable[str],
    token_to_id: Dict[str, float],
    messages: List[CheckMessage],
    stage: RawStage,
    location: str,
) -> List[float]:
    mapped: List[float] = []
    for token in tokens:
        if token not in token_to_id:
            add_message(
                messages,
                "error",
                "unknown-token",
                f"未知 token：'{token}'，位置：{stage.source_file_name} 槽位 {stage.source_item_index} 的 {location}",
            )
            continue
        mapped.append(token_to_id[token])
    return mapped


def get_all_array(level: LegacyLevel) -> List[float]:
    all_cards: List[float] = []
    for book in level.books:
        all_cards.append(float(book.book_id))
        for index in range(1, book.count + 1):
            all_cards.append(book.book_id + index / 100.0)
    return all_cards


def build_cover(level: LegacyLevel) -> Tuple[List[float], List[float]]:
    all_cards = get_all_array(level)
    used_cards = []
    for column in level.founds:
        used_cards.extend(column)
    for column in level.columns:
        used_cards.extend(column)

    explicit_stocks = list(level.stocks)
    remaining = [card for card in all_cards if card not in used_cards and card not in explicit_stocks]
    shuffled = list(remaining)
    rng = random.Random(0)
    rng.shuffle(shuffled)
    return shuffled + explicit_stocks, remaining


def check_static(stage: RawStage, level: LegacyLevel, token_to_id: Dict[str, float]) -> List[CheckMessage]:
    messages: List[CheckMessage] = []

    raw_tokens: List[str] = []
    for column in stage.column:
        raw_tokens.extend(column)
    raw_tokens.extend(stage.stock)
    token_counts = Counter(raw_tokens)
    for token, count in sorted(token_counts.items()):
        if count > 1:
            add_message(messages, "error", "duplicate-raw-token", f"Raw token '{token}' 出现了 {count} 次")

    expected_cards = Counter(format_card(card) for card in get_all_array(level))
    referenced_cards = Counter(format_card(card) for card in level.stocks)
    for column in level.columns:
        referenced_cards.update(format_card(card) for card in column)

    extra_cards = referenced_cards - expected_cards
    if extra_cards:
        add_message(messages, "error", "extra-card", f"引用牌集合超出应有全集：{dict(extra_cards)}")

    missing_cards = expected_cards - referenced_cards
    if missing_cards:
        add_message(
            messages,
            "warning",
            "auto-fill-cover",
            f"Raw stock 缺少部分牌，运行时会自动补到 cover：{dict(missing_cards)}",
        )

    if len(level.founds) != len(level.columns):
        add_message(
            messages,
            "error",
            "founds-columns-mismatch",
            f"Adapter 产出的 founds 数量 {len(level.founds)} 与 columns 数量 {len(level.columns)} 不一致",
        )

    if not stage.key:
        add_message(messages, "error", "empty-key", "关卡没有任何 key 分组")

    for key_group in stage.key:
        if not key_group.content:
            add_message(messages, "warning", "empty-content", f"Key 分组 '{key_group.title}' 没有 content")

    return messages


def check_runtime(level: LegacyLevel) -> List[CheckMessage]:
    messages: List[CheckMessage] = []
    cover_cards, autofill_cards = build_cover(level)

    expected = Counter(format_card(card) for card in get_all_array(level))
    actual = Counter()

    for base_index, pile in enumerate(level.founds):
        actual.update(format_card(card) for card in pile)
        check_base_pile(messages, level, pile, base_index)

    for work_index, pile in enumerate(level.columns):
        actual.update(format_card(card) for card in pile)
        check_work_pile(messages, pile, work_index)

    actual.update(format_card(card) for card in cover_cards)

    missing = expected - actual
    extra = actual - expected
    if missing:
        add_message(messages, "error", "runtime-missing", f"运行时状态缺牌：{dict(missing)}")
    if extra:
        add_message(messages, "error", "runtime-extra", f"运行时状态多牌：{dict(extra)}")

    if not missing and not extra:
        explicit_missing_count = len(autofill_cards)
        if explicit_missing_count > 0:
            add_message(
                messages,
                "warning",
                "runtime-autofill",
                f"运行时在显式 stock 前自动补入了 {explicit_missing_count} 张遗漏牌到 cover",
            )

    initial_cover = list(cover_cards)
    decks: List[List[float]] = [[], []]
    if initial_cover:
        draw = initial_cover[-2:]
        for index, card in enumerate(draw):
            decks[index].append(card)

    if state_is_immediate_fail(level.founds, level.columns, decks, initial_cover[:-len(draw)] if initial_cover else initial_cover):
        add_message(messages, "error", "immediate-fail", "初始运行时状态已构成立即死局")
    elif not has_any_drag_move(level.founds, level.columns, decks) and cover_cards:
        add_message(
            messages,
            "warning",
            "no-immediate-drag",
            "初始状态没有立刻可拖动的操作，但 cover 仍有牌，关卡仍可继续",
        )

    return messages


def check_base_pile(messages: List[CheckMessage], level: LegacyLevel, pile: List[float], base_index: int) -> None:
    if not pile:
        return

    type_cards = [card for card in pile if is_type(card)]
    if len(type_cards) != 1:
        add_message(
            messages,
            "error",
            "base-type-count",
            f"Base 堆 {base_index} 必须且只能有 1 张类别牌，实际为 {len(type_cards)}",
        )
        return

    base_type = card_type(type_cards[0])
    if card_type(pile[0]) != base_type or not is_type(pile[0]):
        add_message(
            messages,
            "error",
            "base-first-card",
            f"Base 堆 {base_index} 的首张必须是对应类别牌",
        )

    for card in pile[1:]:
        if is_type(card):
            add_message(
                messages,
                "error",
                "base-extra-type",
                f"Base 堆 {base_index} 含有额外类别牌 {format_card(card)}",
            )
        elif card_type(card) != base_type:
            add_message(
                messages,
                "error",
                "base-mixed-type",
                f"Base 堆 {base_index} 混入了不同类别的牌：{format_card(card)}",
            )

    expected_count = next((book.count for book in level.books if book.book_id == base_type), None)
    if expected_count is None:
        add_message(messages, "error", "base-unknown-type", f"Base 堆 {base_index} 使用了未知类别 {base_type}")
    elif len(pile) > expected_count + 1:
        add_message(
            messages,
            "error",
            "base-overflow",
            f"Base 堆 {base_index} 超过最大长度 {expected_count + 1}",
        )


def check_work_pile(messages: List[CheckMessage], pile: List[float], work_index: int) -> None:
    if not pile:
        return

    # In raw-to-runtime initial state, only the top card becomes uncovered.
    # We validate the adapted pile shape, not mutable later save data.
    revealed_count = 1
    if len(pile) >= 2:
        # Future-proof warning only. The initial raw stage may still be legal even when
        # the uncovered tail would not chain after multiple moves, because only the top
        # card is initially revealed.
        pass

    if revealed_count > len(pile):
        add_message(messages, "error", "work-reveal", f"Work 堆 {work_index} 的翻开数量非法")


def has_any_drag_move(bases: List[List[float]], works: List[List[float]], decks: List[List[float]]) -> bool:
    empty_base_exists = any(not pile for pile in bases)
    base_types = [card_type(next(card for card in pile if is_type(card))) for pile in bases if pile]
    work_tops = [pile[-1] for pile in works if pile]

    if empty_base_exists:
        for card in work_tops:
            if is_type(card):
                return True
        for deck in decks:
            if deck and is_type(deck[-1]):
                return True

    for top in work_tops:
        if any(card_type(other) == card_type(top) and other != top for other in work_tops):
            return True
        if any(card_type(deck[-1]) == card_type(top) for deck in decks if deck):
            return True
        if card_type(top) in base_types:
            return True

    for deck in decks:
        if not deck:
            continue
        top = deck[-1]
        if any(card_type(other) == card_type(top) for other in work_tops):
            return True
        if card_type(top) in base_types:
            return True

    return False


def state_is_immediate_fail(
    bases: List[List[float]],
    works: List[List[float]],
    decks: List[List[float]],
    cover: List[float],
) -> bool:
    if cover:
        return False
    if any(not pile for pile in works):
        return False
    return not has_any_drag_move(bases, works, decks)


def render_result(result: LevelCheckResult, mode: str) -> str:
    lines = [
        f"[{'通过' if result.ok else '失败'}] dataset={result.dataset} lang={result.language} "
        f"file={result.file_name} item={result.item_index}"
        + (f" mapped_level={result.mapped_level}" if result.mapped_level is not None else ""),
    ]
    if mode in ("static", "all"):
        lines.append("  静态检查：")
        lines.extend(render_messages(result.static_messages))
    if mode in ("runtime", "all"):
        lines.append("  运行时检查：")
        lines.extend(render_messages(result.runtime_messages))
    return "\n".join(lines)


def render_layout_result(result: LayoutCheckResult) -> str:
    lines = [
        f"[{'通过' if result.ok else '失败'}] dataset={result.dataset} all_languages_layout level={result.level} baseline={result.baseline_language}"
    ]
    if result.details:
        lines.extend(f"  - {detail}" for detail in result.details)
    else:
        lines.append("  - 所有语言布局一致")
    return "\n".join(lines)


def render_messages(messages: List[CheckMessage]) -> List[str]:
    if not messages:
        return ["    - 通过"]
    return [f"    - {severity_label(msg.severity)} {msg.code}: {msg.message}" for msg in messages]


def check_one_stage(stage: RawStage, dataset: str, mode: str) -> LevelCheckResult:
    legacy, token_to_id, adapt_messages = adapt_stage(stage)
    static_messages = list(adapt_messages)
    runtime_messages: List[CheckMessage] = []

    if mode in ("static", "all"):
        static_messages.extend(check_static(stage, legacy, token_to_id))
    if mode in ("runtime", "all"):
        runtime_messages.extend(check_runtime(legacy))

    return LevelCheckResult(
        dataset=dataset,
        language=stage.source_language,
        file_name=stage.source_file_name,
        item_index=stage.source_item_index,
        mapped_level=stage.mapped_level,
        static_messages=static_messages,
        runtime_messages=runtime_messages,
    )


def iter_all_slots(dataset_root: Path, language: str) -> Iterable[RawStage]:
    language_root = dataset_root / language
    if not language_root.exists():
        raise FileNotFoundError(f"找不到语言目录：{language_root}")

    file_names = sorted(
        [path.name for path in language_root.glob("*.json")],
        key=lambda name: (int(Path(name).stem) if Path(name).stem.isdigit() else 10**9, name),
    )
    for file_name in file_names:
        file_path = language_root / file_name
        data = json.loads(file_path.read_text())
        if not isinstance(data, list):
            continue
        for item_index, token in enumerate(data):
            if isinstance(token, dict):
                yield load_stage_from_slot(dataset_root, language, file_name, item_index)


def list_languages(dataset_root: Path) -> List[str]:
    return sorted(path.name for path in dataset_root.iterdir() if path.is_dir())


def list_file_names(dataset_root: Path, language: str) -> List[str]:
    language_root = dataset_root / language
    if not language_root.exists():
        raise FileNotFoundError(f"找不到语言目录：{language_root}")
    return sorted(
        [path.name for path in language_root.glob("*.json")],
        key=lambda name: (int(Path(name).stem) if Path(name).stem.isdigit() else 10**9, name),
    )


def legacy_layout_signature(level: LegacyLevel) -> Tuple[Tuple[Tuple[float, ...], ...], Tuple[float, ...]]:
    columns = tuple(tuple(column) for column in level.columns)
    stocks = tuple(level.stocks)
    return columns, stocks


def format_stage_location(stage: RawStage, language: Optional[str] = None) -> str:
    prefix = f"{language or stage.source_language}: "
    return (
        f"{prefix}file={stage.source_file_name} item={stage.source_item_index}"
        + (f" mapped_level={stage.mapped_level}" if stage.mapped_level is not None else "")
    )


def check_level_layout_across_languages(
    dataset_root: Path,
    dataset: str,
    level: int,
    baseline_language: str,
) -> LayoutCheckResult:
    languages = list_languages(dataset_root)
    if baseline_language not in languages:
        raise FileNotFoundError(f"基准语言目录不存在：{baseline_language}")

    mismatches: List[str] = []
    details: List[str] = []

    try:
        baseline_stage = load_stage_from_level(dataset_root, baseline_language, level)
    except Exception as exc:
        return LayoutCheckResult(
            dataset=dataset,
            level=level,
            baseline_language=baseline_language,
            mismatches=[baseline_language],
            details=[f"{baseline_language}: 基准关卡加载失败：{exc}"],
        )

    baseline_location = format_stage_location(baseline_stage, baseline_language)
    details.append(f"基准布局 {baseline_location}")

    baseline_legacy, _, baseline_messages = adapt_stage(baseline_stage)
    if any(message.severity == "error" for message in baseline_messages):
        mismatches.append(baseline_language)
        details.extend(
            f"{baseline_language}: adapter 失败 {message.code}: {message.message}"
            for message in baseline_messages
            if message.severity == "error"
        )
        return LayoutCheckResult(
            dataset=dataset,
            level=level,
            baseline_language=baseline_language,
            mismatches=mismatches,
            details=details,
        )

    baseline_signature = legacy_layout_signature(baseline_legacy)

    for language in languages:
        try:
            stage = load_stage_from_level(dataset_root, language, level)
        except Exception as exc:
            mismatches.append(language)
            details.append(f"{language}: 关卡加载失败：{exc}")
            continue

        legacy, _, adapt_messages = adapt_stage(stage)
        if any(message.severity == "error" for message in adapt_messages):
            mismatches.append(language)
            details.append(f"{language}: adapter 失败 {format_stage_location(stage, language)}")
            details.extend(
                f"{language}: {message.code}: {message.message}"
                for message in adapt_messages
                if message.severity == "error"
            )
            continue

        signature = legacy_layout_signature(legacy)
        if signature != baseline_signature:
            mismatches.append(language)
            details.append(f"{language}: 布局不一致 {format_stage_location(stage, language)}")

    if not mismatches:
        details = [f"所有语言与 {baseline_location} 一致"]

    return LayoutCheckResult(
        dataset=dataset,
        level=level,
        baseline_language=baseline_language,
        mismatches=mismatches,
        details=details,
    )


def iter_layout_results_across_all_levels(
    dataset_root: Path,
    dataset: str,
    baseline_language: str,
) -> Iterable[LayoutCheckResult]:
    baseline_files = list_file_names(dataset_root, baseline_language)
    if not baseline_files:
        raise FileNotFoundError(f"基准语言 {baseline_language} 下找不到 JSON 文件")

    total_levels = len(baseline_files) * 10
    for level in range(1, total_levels + 1):
        yield check_level_layout_across_languages(
            dataset_root=dataset_root,
            dataset=dataset,
            level=level,
            baseline_language=baseline_language,
        )


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查 Mixword 关卡合法性")
    parser.add_argument("--project-root", required=True, help="项目根目录，内部应包含 Assets/Game/Levels/Resources")
    parser.add_argument("--dataset", choices=("normal", "special"), default="normal")
    parser.add_argument("--language", default="en")
    parser.add_argument("--level", type=int, help="游戏关卡号")
    parser.add_argument("--file", help="资源文件名，例如 1.json")
    parser.add_argument("--item-index", type=int, help="JSON 数组里的 0 基槽位索引")
    parser.add_argument("--all", action="store_true", help="扫描当前数据集/语言下的全部槽位")
    parser.add_argument("--mode", choices=("static", "runtime", "all"), default="all")
    parser.add_argument("--fail-only", action="store_true", help="只输出失败结果")
    parser.add_argument(
        "--all-languages-layout",
        action="store_true",
        help="按关卡号检查当前数据集下所有语言的布局是否一致（基准语言默认取 --language）",
    )
    return parser.parse_args(argv)


def resolve_dataset_root(project_root: Path, dataset: str) -> Path:
    base = project_root / "mixword" / "Assets" / "Game" / "Levels" / "Resources"
    if not base.exists():
        base = project_root / "Assets" / "Game" / "Levels" / "Resources"
    if not base.exists():
        raise FileNotFoundError("在项目根目录下找不到 Assets/Game/Levels/Resources")
    return base / ("LevelData" if dataset == "normal" else "SpecialLevelData")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    project_root = Path(args.project_root).resolve()
    dataset_root = resolve_dataset_root(project_root, args.dataset)

    modes_selected = sum(
        [
            1 if args.level is not None else 0,
            1 if args.file is not None or args.item_index is not None else 0,
            1 if args.all else 0,
        ]
    )
    if args.all_languages_layout:
        if modes_selected != 1 or (args.level is None and not args.all):
            print("--all-languages-layout 必须和 --level 或 --all 一起使用，且不能与 --file/--item-index 组合", file=sys.stderr)
            return 2
    elif modes_selected != 1:
        print("必须且只能选择一种范围：--level、--file/--item-index 或 --all", file=sys.stderr)
        return 2

    results: List[LevelCheckResult] = []
    try:
        if args.all_languages_layout:
            if args.level is not None:
                layout_results = [
                    check_level_layout_across_languages(
                        dataset_root=dataset_root,
                        dataset=args.dataset,
                        level=args.level,
                        baseline_language=args.language,
                    )
                ]
            else:
                layout_results = list(
                    iter_layout_results_across_all_levels(
                        dataset_root=dataset_root,
                        dataset=args.dataset,
                        baseline_language=args.language,
                    )
                )

            failed_results = 0
            total_languages = len(list_languages(dataset_root))
            for layout_result in layout_results:
                if args.fail_only and layout_result.ok:
                    continue
                print(render_layout_result(layout_result))
                if not layout_result.ok:
                    failed_results += 1

            print(
                f"汇总：共检查 {len(layout_results)} 个关卡，失败 {failed_results} 个，通过 {len(layout_results) - failed_results} 个"
            )
            if len(layout_results) == 1:
                single = layout_results[0]
                print(
                    f"语言汇总：共检查 {total_languages} 个语言，失败 {len(single.mismatches)} 个，通过 {total_languages - len(single.mismatches)} 个"
                )
            return 1 if failed_results else 0
        elif args.level is not None:
            stage = load_stage_from_level(dataset_root, args.language, args.level)
            results.append(check_one_stage(stage, args.dataset, args.mode))
        elif args.file is not None or args.item_index is not None:
            if args.file is None or args.item_index is None:
                print("--file 和 --item-index 必须一起使用", file=sys.stderr)
                return 2
            stage = load_stage_from_slot(dataset_root, args.language, args.file, args.item_index)
            results.append(check_one_stage(stage, args.dataset, args.mode))
        else:
            for stage in iter_all_slots(dataset_root, args.language):
                results.append(check_one_stage(stage, args.dataset, args.mode))
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    failure_count = 0
    for result in results:
        if args.fail_only and result.ok:
            continue
        print(render_result(result, args.mode))
        if not result.ok:
            failure_count += 1

    print(f"汇总：共检查 {len(results)} 个，失败 {failure_count} 个，通过 {len(results) - failure_count} 个")
    return 1 if failure_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
