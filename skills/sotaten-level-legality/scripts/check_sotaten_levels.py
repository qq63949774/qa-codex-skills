#!/usr/bin/env python3
"""Static Sotaten level legality checker.

The checks mirror the current Unity C# code closely enough to catch data and
configuration blockers without launching Unity.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SEVERITY_RANK = {"BLOCKER": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
VALID_DIFFICULTIES = {
    "Easy",
    "Hard",
    "Extra_Hard",
    "Extra Hard",
    "ExtraHard",
    "Sub_Extra_Hard",
    "Sub Extra Hard",
    "SubExtraHard",
    "Random",
}
VALID_EXTRAS = {"Wild_Card", "J", "Q", "K"}

DIFF_EASY = 0
DIFF_HARD = 1
DIFF_EXTRA_HARD = 2
DIFF_SUB_EXTRA_HARD = 3
DIFF_RANDOM = 4

RANGE_FIXED = 0
RANGE_ZERO_TO_TEN = 1
RANGE_ONE_TO_NINE = 2
RANGE_FULL = 3

SOLVABILITY_GUARANTEED = 0
SOLVABILITY_RANDOM = 1

STOCK_DEP_MEDIUM = 0
STOCK_DEP_HIGH = 1
STOCK_DEP_RANDOM = 2

PRESET_START = 100
BLOCK_OVERLAP_THRESHOLD = 0.08
GUARANTEED_ATTEMPTS = 60
STOCK_DEAL_COUNT = 3
STOCK_WASTE_SLOT_COUNT = 3
MAX_VISITED_STATES = 12000
MAX_BRANCHES_PER_STATE = 24

CYCLE_CONFIG_START_LEVEL = 31
CYCLE_TEMPLATE_START_NUMBER = 9
CYCLE_TEMPLATE_LOOP_START_NUMBER = 1
EASY_COVERED_CARD_SKIP_THRESHOLD = 20
WILD_CARD_SEED_OFFSET = 314159

DEFAULT_TEN_CONFIG = {
    "cycleLevelDiff": [3, 4, 2, 0, 1],
    "wildCardRatio": 0.33,
}


@dataclass
class Issue:
    severity: str
    item: str
    file_path: str
    symbol: str
    reasoning: str
    suggested_validation: str


@dataclass
class Slot:
    slot_id: int
    x: float
    y: float
    width: float
    height: float
    rotation: float
    render_order: int
    blocked_by: List[int] = field(default_factory=list)


@dataclass
class Template:
    template_id: int
    layout_id: int
    slots: List[Slot]


@dataclass(frozen=True)
class Card:
    card_id: int
    rank: int
    suit: int
    is_wild: bool = False


@dataclass
class BoardCard:
    slot_id: int
    card: Card
    face_up: bool


@dataclass
class DifficultyConfig:
    solvability_mode: int
    stock_cycle_count: int
    stock_dependency_mode: int
    internal_pair_target: int
    exposed_low_card_chance: float
    stock_assist_ratio: float
    chain_unlock_bias: float


@dataclass
class LevelConfig:
    level_id: int
    layout_id: int
    difficulty: int
    card_range: int
    seed: int
    fixed_deal: bool
    extras: List[int]
    source: str


@dataclass
class GeneratedLevel:
    level_id: int
    seed: int
    layout_id: int
    requested_difficulty: int
    difficulty: int
    used_fallback: bool
    solvability_mode: int
    stock_cycle_count: int
    move_limit: int
    board_cards: List[BoardCard]
    stock_cards: List[Card]
    solution_action_count: int


class Reporter:
    def __init__(self) -> None:
        self.issues: List[Issue] = []

    def add(
        self,
        severity: str,
        item: str,
        file_path: Path | str,
        symbol: str,
        reasoning: str,
        suggested_validation: str,
    ) -> None:
        self.issues.append(
            Issue(
                severity=severity,
                item=item,
                file_path=str(file_path),
                symbol=symbol,
                reasoning=reasoning,
                suggested_validation=suggested_validation,
            )
        )


class SeededLevelRandom:
    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFF
        if self.state == 0:
            self.state = 0x6D2B79F5

    def next_uint(self) -> int:
        self.state = (self.state ^ ((self.state << 13) & 0xFFFFFFFF)) & 0xFFFFFFFF
        self.state = (self.state ^ (self.state >> 17)) & 0xFFFFFFFF
        self.state = (self.state ^ ((self.state << 5) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return self.state

    def range(self, min_inclusive: int, max_exclusive: int) -> int:
        width = max_exclusive - min_inclusive
        if width <= 0:
            return min_inclusive
        return min_inclusive + int(self.next_uint() % width)

    def value(self) -> float:
        return (self.next_uint() & 0x00FFFFFF) / 16777216.0

    def shuffle(self, values: List[Any]) -> None:
        for i in range(len(values) - 1, 0, -1):
            j = self.range(0, i + 1)
            values[i], values[j] = values[j], values[i]


def read_json(path: Path, reporter: Reporter, item: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        reporter.add("BLOCKER", item, path, path.name, "Required JSON file is missing.", "Restore the Unity resource or confirm the resource path changed in code.")
    except json.JSONDecodeError as exc:
        reporter.add("BLOCKER", item, path, path.name, f"Invalid JSON: {exc}.", "Fix JSON syntax and rerun the checker.")
    return None


def resolve_unity_root(project: Path) -> Path:
    project = project.resolve()
    if (project / "Assets").is_dir():
        return project
    if (project / "sotaten" / "Assets").is_dir():
        return project / "sotaten"
    raise SystemExit(f"Could not find Unity Assets under {project} or {project / 'sotaten'}")


def is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def layout_id_for_template_number(template_number: int) -> int:
    return PRESET_START + template_number - 1


def template_number_for_layout_id(layout_id: int) -> int:
    return layout_id - PRESET_START + 1


def bounds(card: Slot) -> Tuple[float, float, float, float, float]:
    radians = card.rotation * math.pi / 180.0
    cos_v = abs(math.cos(radians))
    sin_v = abs(math.sin(radians))
    width = card.width * cos_v + card.height * sin_v
    height = card.width * sin_v + card.height * cos_v
    return (
        card.x - width * 0.5,
        card.x + width * 0.5,
        card.y - height * 0.5,
        card.y + height * 0.5,
        width * height,
    )


def overlap_ratio(a: Tuple[float, float, float, float, float], b: Tuple[float, float, float, float, float]) -> float:
    width = min(a[1], b[1]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[2], b[2])
    if width <= 0 or height <= 0 or a[4] <= 0:
        return 0.0
    return width * height / a[4]


def build_template(raw: Dict[str, Any], path: Path, reporter: Reporter) -> Optional[Template]:
    template_id = raw.get("t")
    cards = raw.get("c")
    if not isinstance(template_id, int) or isinstance(template_id, bool):
        reporter.add("BLOCKER", "Invalid generated board template id", path, "GeneratedBoardLayoutPresets.t", "Template id must be an integer.", "Fix the template id and rerun the checker.")
        return None
    if not isinstance(cards, list) or not cards:
        reporter.add("BLOCKER", f"Template {template_id} has no cards", path, "GeneratedBoardLayoutPresets.c", "Runtime throws when a generated board template has no cards.", "Restore card rows for this template.")
        return None

    slots: List[Slot] = []
    seen_z: Dict[int, int] = {}
    for index, row in enumerate(cards):
        if not isinstance(row, list) or len(row) < 6:
            reporter.add("BLOCKER", f"Template {template_id} card row is malformed", path, f"t={template_id}.c[{index}]", "Each card row must contain x, y, width, height, rotation, and zIndex.", "Regenerate the template export or fix the row.")
            continue
        if not all(is_finite_number(v) for v in row[:6]):
            reporter.add("BLOCKER", f"Template {template_id} card row has nonnumeric values", path, f"t={template_id}.c[{index}]", "Runtime casts these values to layout coordinates and zIndex.", "Replace nonnumeric values with finite numbers.")
            continue
        width = float(row[2])
        height = float(row[3])
        z_raw = float(row[5])
        z_index = int(z_raw)
        if width <= 0 or height <= 0:
            reporter.add("BLOCKER", f"Template {template_id} card has invalid size", path, f"t={template_id}.c[{index}]", "Width and height must be positive for overlap calculations.", "Fix exported card dimensions.")
        if z_raw != z_index:
            reporter.add("MEDIUM", f"Template {template_id} zIndex is fractional", path, f"t={template_id}.c[{index}][5]", "C# truncates zIndex with an int cast, which can change blocker ordering.", "Re-export zIndex values as integers.")
        if z_index in seen_z:
            reporter.add("MEDIUM", f"Template {template_id} has duplicate zIndex {z_index}", path, f"t={template_id}.c[{index}][5]", "Cards with equal zIndex do not block each other because runtime only checks strictly higher zIndex.", "Review this template visually or re-export unique render orders.")
        seen_z[z_index] = index
        slots.append(Slot(-1, float(row[0]), float(row[1]), width, height, float(row[4]), z_index))

    if not slots:
        return None

    slots.sort(key=lambda slot: slot.render_order)
    for slot_id, slot in enumerate(slots):
        slot.slot_id = slot_id

    all_bounds = [bounds(slot) for slot in slots]
    for i, slot in enumerate(slots):
        blockers: List[int] = []
        for j, other in enumerate(slots):
            if i == j or other.render_order <= slot.render_order:
                continue
            if overlap_ratio(all_bounds[i], all_bounds[j]) > BLOCK_OVERLAP_THRESHOLD:
                blockers.append(j)
        slot.blocked_by = blockers

    visible = [slot for slot in slots if not slot.blocked_by]
    if not visible:
        reporter.add("BLOCKER", f"Template {template_id} has no initially visible cards", path, f"t={template_id}", "The generated solver and runtime need visible cards to start play.", "Fix overlap or zIndex ordering.")
    elif len(visible) == 1:
        reporter.add("HIGH", f"Template {template_id} has only one initially visible card", path, f"t={template_id}", "A single visible card can deadlock unless stock immediately helps; this is high regression risk.", "Run runtime playthrough or adjust blockers.")

    return Template(template_id, PRESET_START + template_id, slots)


def load_templates(unity_root: Path, reporter: Reporter) -> Dict[int, Template]:
    path = unity_root / "Assets/Game/Levels/Resources/GeneratedBoardLayoutPresets.json"
    raw = read_json(path, reporter, "Generated board layout presets")
    templates: Dict[int, Template] = {}
    if raw is None:
        return templates
    if not isinstance(raw, list) or not raw:
        reporter.add("BLOCKER", "Generated board layout presets are empty", path, "GeneratedBoardLayoutPresets", "Runtime requires at least one generated board template.", "Restore the template export.")
        return templates

    sorted_raw = sorted([item for item in raw if isinstance(item, dict)], key=lambda item: item.get("t", 10**9))
    for expected, item in enumerate(sorted_raw):
        actual = item.get("t")
        if actual != expected:
            reporter.add("BLOCKER", "Generated board template ids are not contiguous", path, "GeneratedBoardLayoutPresetProvider.LoadTemplates", f"Expected template id {expected}, got {actual}. Runtime throws on this mismatch.", "Regenerate templates with contiguous ids starting at 0.")
    for item in sorted_raw:
        template = build_template(item, path, reporter)
        if template is not None:
            templates[template.layout_id] = template

    if len(templates) < CYCLE_TEMPLATE_START_NUMBER:
        reporter.add("BLOCKER", "Cycle template start is outside template count", path, "LocalLevelConfigProvider.GetCycleTemplateNumber", f"Cycle starts at template {CYCLE_TEMPLATE_START_NUMBER}, but only {len(templates)} templates are valid.", "Restore enough templates or update the cycle start constant.")

    easy_valid = [template for template in templates.values() if count_covered(template) < EASY_COVERED_CARD_SKIP_THRESHOLD]
    if not easy_valid:
        reporter.add("BLOCKER", "No Easy-valid cycle templates", path, "LocalLevelConfigProvider.SelectCycleLayoutId", "Cycle Easy levels require at least one template with fewer than 20 covered cards.", "Add an Easy-valid template or change the Easy skip threshold.")

    max_slots = max((len(template.slots) for template in templates.values()), default=0)
    if max_slots > 56:
        reporter.add("HIGH", "Template requires more cards than Full deck", path, "LevelDeckBuilder.Build", f"Largest template has {max_slots} slots; Full deck has 56 cards before optional wild.", "Reduce template slot count or add enough supported extra cards.")

    return templates


def count_covered(template: Template) -> int:
    return sum(1 for slot in template.slots if slot.blocked_by)


def parse_difficulty(value: Any, reporter: Reporter, path: Path, symbol: str) -> int:
    text = str(value or "").strip()
    if text not in VALID_DIFFICULTIES:
        reporter.add("MEDIUM", "Unknown difficulty falls back to Easy", path, symbol, f"Difficulty '{text}' is not handled by ParseDifficulty and will silently become Easy.", "Fix spelling or confirm Easy fallback is intended.")
    if text == "Hard":
        return DIFF_HARD
    if text in {"Extra_Hard", "Extra Hard", "ExtraHard"}:
        return DIFF_EXTRA_HARD
    if text in {"Sub_Extra_Hard", "Sub Extra Hard", "SubExtraHard"}:
        return DIFF_SUB_EXTRA_HARD
    if text == "Random":
        return DIFF_RANDOM
    return DIFF_EASY


def parse_card_range(group: Any, reporter: Reporter, path: Path, symbol: str) -> int:
    if not isinstance(group, list) or len(group) < 2:
        reporter.add("MEDIUM", "Card group falls back to 0-10", path, symbol, "ParseCardRange treats missing or short group as 0-10.", "Use [0, 10] or [1, 9] explicitly.")
        return RANGE_ZERO_TO_TEN
    if group[:2] == [1, 9]:
        return RANGE_ONE_TO_NINE
    if group[:2] != [0, 10]:
        reporter.add("MEDIUM", "Unsupported card group falls back to 0-10", path, symbol, f"Group {group} is not [1, 9]; runtime treats it as 0-10.", "Fix group values or confirm fallback is intended.")
    return RANGE_ZERO_TO_TEN


def parse_extras(values: Any, reporter: Reporter, path: Path, symbol: str) -> List[int]:
    if values is None:
        return []
    if not isinstance(values, list):
        reporter.add("MEDIUM", "Extras field is not an array", path, symbol, "ParseExtras expects an array; invalid values are effectively ignored.", "Use an array of Wild_Card, J, Q, and K.")
        return []
    result: List[int] = []
    for index, extra in enumerate(values):
        if extra not in VALID_EXTRAS:
            reporter.add("MEDIUM", "Unknown extra card is ignored", path, f"{symbol}[{index}]", f"Extra '{extra}' is not handled by ParseExtras.", "Fix spelling or remove the unsupported extra.")
            continue
        if extra == "Wild_Card":
            result.append(0)
        elif extra == "J":
            result.append(11)
        elif extra == "Q":
            result.append(12)
        elif extra == "K":
            result.append(13)
    return result


def load_start_configs(unity_root: Path, settings: Any, reporter: Reporter) -> Dict[int, Dict[str, Any]]:
    path = unity_root / "Assets/Game/Com/Resources/startLevelConfig.json"
    source = read_json(path, reporter, "startLevelConfig")
    source_path = path
    if isinstance(settings, list):
        source = settings
        source_path = Path("<settings>")
    elif isinstance(settings, dict) and "startLevelConfig" in settings:
        source = settings.get("startLevelConfig")
        source_path = Path("<settings>.startLevelConfig")

    configs: Dict[int, Dict[str, Any]] = {}
    if not isinstance(source, list):
        reporter.add("BLOCKER", "startLevelConfig is not an array", source_path, "GameConfig.LoadStartLevelConfig", "Runtime deserializes this value as a list of level configs.", "Provide an array of level config objects.")
        return configs

    for index, item in enumerate(source):
        if not isinstance(item, dict):
            reporter.add("BLOCKER", "startLevelConfig item is not an object", source_path, f"startLevelConfig[{index}]", "Runtime expects object fields level, layoutId, dif, group, and extra.", "Fix this entry.")
            continue
        level = item.get("level")
        if not isinstance(level, int) or isinstance(level, bool) or level <= 0:
            reporter.add("BLOCKER", "startLevelConfig level is invalid", source_path, f"startLevelConfig[{index}].level", "Level id must be a positive integer.", "Fix the level id.")
            continue
        if level in configs:
            reporter.add("HIGH", f"Duplicate start config for level {level}", source_path, f"startLevelConfig[{index}].level", "GameConfig keeps the last duplicate and silently overrides the earlier entry.", "Remove duplicates and confirm intended config.")
        configs[level] = item

    for missing in range(2, CYCLE_CONFIG_START_LEVEL):
        if missing not in configs:
            reporter.add("BLOCKER", f"Missing generated start config for level {missing}", source_path, "LocalLevelConfigProvider.TryGetConfig", "Levels 2-30 do not enter cycle config; missing entries make TryLoad fail.", "Add the missing level or lower the cycle start in code.")

    return configs


def load_ten_config(settings: Any, reporter: Reporter) -> Dict[str, Any]:
    config = dict(DEFAULT_TEN_CONFIG)
    if isinstance(settings, dict) and isinstance(settings.get("tenConfig"), dict):
        config.update(settings["tenConfig"])
    cycle = config.get("cycleLevelDiff")
    if not isinstance(cycle, list) or not cycle:
        reporter.add("BLOCKER", "cycleLevelDiff is empty", "<settings>.tenConfig", "LocalLevelConfigProvider.GetCycleDifficulty", "Cycle config requires at least one difficulty id.", "Provide a non-empty list of difficulty ids 0-4.")
        config["cycleLevelDiff"] = []
    else:
        for index, value in enumerate(cycle):
            if value not in [0, 1, 2, 3, 4]:
                reporter.add("BLOCKER", "cycleLevelDiff contains unsupported difficulty id", "<settings>.tenConfig", f"cycleLevelDiff[{index}]", f"Difficulty id {value} is not defined by LevelDifficultyId.", "Use only ids 0-4.")
    ratio = config.get("wildCardRatio", 0.0)
    if not isinstance(ratio, (int, float)) or isinstance(ratio, bool) or not math.isfinite(float(ratio)):
        reporter.add("MEDIUM", "wildCardRatio is invalid", "<settings>.tenConfig", "tenConfig.wildCardRatio", "Invalid ratio disables predictable cycle wild-card behavior.", "Use a finite number, usually between 0 and 1.")
        config["wildCardRatio"] = 0.0
    return config


def create_card(rank: int, suit: int) -> Card:
    return Card(rank * 10 + suit, rank, suit, False)


def create_wild() -> Card:
    return Card(999, 0, -1, True)


def build_deck(config: LevelConfig) -> List[Card]:
    cards: List[Card] = []
    seen: set[int] = set()

    def add(card: Card) -> None:
        if card.card_id not in seen:
            seen.add(card.card_id)
            cards.append(card)

    def add_rank(rank: int) -> None:
        for suit in range(4):
            add(create_card(rank, suit))

    if config.card_range == RANGE_ZERO_TO_TEN:
        for rank in range(0, 11):
            add_rank(rank)
    elif config.card_range == RANGE_ONE_TO_NINE:
        for rank in range(1, 10):
            add_rank(rank)
    elif config.card_range == RANGE_FULL:
        for rank in range(0, 14):
            add_rank(rank)

    for extra in config.extras:
        if extra == 0:
            add(create_wild())
        else:
            add_rank(extra)
    return cards


def is_number(card: Card) -> bool:
    return not card.is_wild and 0 <= card.rank <= 10


def is_flower(card: Card) -> bool:
    return not card.is_wild and 11 <= card.rank <= 13


def is_low_rank(card: Card) -> bool:
    return not card.is_wild and 0 <= card.rank <= 4


def are_match(first: Optional[Card], second: Optional[Card]) -> bool:
    if first is None or second is None:
        return False
    if first.is_wild or second.is_wild:
        return True
    if is_number(first) and is_number(second):
        return first.rank + second.rank == 10
    if is_flower(first) and is_flower(second):
        return first.rank == second.rank
    return False


def difficulty_config(difficulty: int, seed: int) -> DifficultyConfig:
    if difficulty == DIFF_HARD:
        cfg = DifficultyConfig(SOLVABILITY_GUARANTEED, -1, STOCK_DEP_MEDIUM, 0, 0.50, 0.85, 0.20)
    elif difficulty == DIFF_EXTRA_HARD:
        cfg = DifficultyConfig(SOLVABILITY_GUARANTEED, -1, STOCK_DEP_HIGH, 0, 0.60, 0.55, 0.45)
    elif difficulty == DIFF_SUB_EXTRA_HARD:
        cfg = DifficultyConfig(SOLVABILITY_GUARANTEED, -1, STOCK_DEP_HIGH, 0, 0.60, 0.55, 0.45)
    elif difficulty == DIFF_RANDOM:
        cfg = DifficultyConfig(SOLVABILITY_RANDOM, -1, STOCK_DEP_RANDOM, 0, 0.45, 0.25, 0.65)
    else:
        cfg = DifficultyConfig(SOLVABILITY_GUARANTEED, -1, STOCK_DEP_MEDIUM, 0, 0.55, 1.00, 0.10)
    cfg.internal_pair_target = resolve_internal_pair_target(difficulty, seed)
    return cfg


def resolve_internal_pair_target(difficulty: int, seed: int) -> int:
    if difficulty == DIFF_HARD:
        min_v, max_v = 5, 7
    elif difficulty == DIFF_EXTRA_HARD:
        min_v, max_v = 4, 4
    elif difficulty == DIFF_SUB_EXTRA_HARD:
        min_v, max_v = 4, 5
    elif difficulty == DIFF_RANDOM:
        min_v, max_v = 4, 4
    else:
        min_v, max_v = 7, 9
    if max_v <= min_v:
        return min_v
    return SeededLevelRandom(seed + ((difficulty + 1) * 1009)).range(min_v, max_v + 1)


def move_limit_offset(level_id: int, difficulty: int) -> int:
    if difficulty in (DIFF_SUB_EXTRA_HARD, DIFF_RANDOM):
        return 0
    if level_id <= 10:
        if difficulty == DIFF_HARD:
            return 2
        if difficulty == DIFF_EXTRA_HARD:
            return 1
        return 3
    if level_id <= 50:
        if difficulty == DIFF_HARD:
            return 0
        if difficulty == DIFF_EXTRA_HARD:
            return -1
        return 1
    if difficulty == DIFF_HARD:
        return -1
    if difficulty == DIFF_EXTRA_HARD:
        return -2
    return 0


def is_initially_visible(template: Template, slot_id: int) -> bool:
    return not template.slots[slot_id].blocked_by


def visible_board_indexes(template: Template, board_cards: List[BoardCard]) -> List[int]:
    return [i for i, board_card in enumerate(board_cards) if is_initially_visible(template, board_card.slot_id)]


def count_initial_visible_pairs(template: Template, board_cards: List[BoardCard]) -> int:
    indexes = visible_board_indexes(template, board_cards)
    count = 0
    for i in range(len(indexes)):
        for j in range(i + 1, len(indexes)):
            if are_match(board_cards[indexes[i]].card, board_cards[indexes[j]].card):
                count += 1
    return count


def count_blocked_slots(template: Template, blocker_slot_id: int) -> int:
    return sum(1 for slot in template.slots if blocker_slot_id in slot.blocked_by)


def select_visible_index(template: Template, board_cards: List[BoardCard], indexes: List[int], chain_unlock_bias: float, random: SeededLevelRandom) -> int:
    if random.value() > chain_unlock_bias:
        return indexes[random.range(0, len(indexes))]
    best = indexes[0]
    best_unlock = count_blocked_slots(template, board_cards[best].slot_id)
    for candidate in indexes[1:]:
        unlock = count_blocked_slots(template, board_cards[candidate].slot_id)
        if unlock > best_unlock:
            best = candidate
            best_unlock = unlock
    return best


def find_stock_index(stock_cards: List[Card], predicate: Any) -> int:
    for index, card in enumerate(stock_cards):
        if predicate(card):
            return index
    return -1


def build_candidate_deal(config: LevelConfig, template: Template, cfg: DifficultyConfig, random: SeededLevelRandom) -> Tuple[List[BoardCard], List[Card]]:
    deck = build_deck(config)
    if len(deck) < len(template.slots):
        raise ValueError(f"Deck has {len(deck)} cards but layout Preset{template_number_for_layout_id(config.layout_id):02d} needs {len(template.slots)}.")
    random.shuffle(deck)
    board_cards: List[BoardCard] = []
    stock_cards: List[Card] = []
    for index, card in enumerate(deck):
        if index < len(template.slots):
            slot = template.slots[index]
            board_cards.append(BoardCard(slot.slot_id, card, is_initially_visible(template, slot.slot_id)))
        else:
            stock_cards.append(card)

    for index, board_card in enumerate(board_cards):
        if not is_initially_visible(template, board_card.slot_id) or random.value() > cfg.exposed_low_card_chance:
            continue
        stock_index = find_stock_index(stock_cards, is_low_rank)
        if stock_index < 0:
            continue
        board_cards[index].card, stock_cards[stock_index] = stock_cards[stock_index], board_cards[index].card
    return board_cards, stock_cards


def improve_internal_pairs(template: Template, board_cards: List[BoardCard], stock_cards: List[Card], cfg: DifficultyConfig, random: SeededLevelRandom) -> None:
    safety = 0
    while count_initial_visible_pairs(template, board_cards) < cfg.internal_pair_target and safety < 80:
        safety += 1
        indexes = visible_board_indexes(template, board_cards)
        if len(indexes) < 2 or not stock_cards:
            return
        first_index = select_visible_index(template, board_cards, indexes, cfg.chain_unlock_bias, random)
        stock_index = find_stock_index(stock_cards, lambda card: are_match(board_cards[first_index].card, card))
        if stock_index < 0:
            continue
        second_index = indexes[random.range(0, len(indexes))]
        if second_index == first_index:
            continue
        board_cards[second_index].card, stock_cards[stock_index] = stock_cards[stock_index], board_cards[second_index].card


def arrange_solution_stock_assists(stock_cards: List[Card], solution: List[Tuple[int, int, Optional[Card]]], cfg: DifficultyConfig, random: SeededLevelRandom) -> None:
    if not stock_cards or not solution or cfg.stock_assist_ratio <= 0:
        return
    ordered_prefix: List[Card] = []
    for _, _, stock_card in solution:
        if stock_card is None or not stock_cards or random.value() > cfg.stock_assist_ratio:
            continue
        stock_index = next((i for i, card in enumerate(stock_cards) if card.card_id == stock_card.card_id), -1)
        if stock_index < 0:
            continue
        ordered_prefix.append(stock_cards.pop(stock_index))
    for card in reversed(ordered_prefix):
        stock_cards.insert(0, card)


class DealSolver:
    def __init__(self, template: Template, cfg: DifficultyConfig) -> None:
        self.template = template
        self.cfg = cfg
        self.stock_cycle_count = cfg.stock_cycle_count if cfg is not None else 0

    def try_solve(self, board_cards: List[BoardCard], stock_cards: List[Card]) -> Tuple[bool, List[Tuple[int, int, Optional[Card]]], int]:
        remaining = {card.slot_id: card.card for card in board_cards}
        stock = list(stock_cards)
        waste: List[Card] = []
        waste_slot_indices: List[int] = []
        path: List[Tuple[int, int, Optional[Card]]] = []
        visited: set[str] = set()
        return self._search(remaining, stock, waste, waste_slot_indices, path, visited, 0, 0)

    def _search(
        self,
        remaining: Dict[int, Card],
        stock: List[Card],
        waste: List[Card],
        waste_slot_indices: List[int],
        path: List[Tuple[int, int, Optional[Card]]],
        visited: set[str],
        action_count: int,
        stock_cycles_used: int,
    ) -> Tuple[bool, List[Tuple[int, int, Optional[Card]]], int]:
        if not remaining:
            return True, list(path), action_count
        if len(visited) >= MAX_VISITED_STATES:
            return False, [], 0
        key = self._state_key(remaining, stock, waste, waste_slot_indices, stock_cycles_used)
        if key in visited:
            return False, [], 0
        visited.add(key)

        visible_slots = self._visible_slots(remaining)
        branch_count = [0]
        prefer_stock = self.cfg is not None and self.cfg.stock_dependency_mode == STOCK_DEP_HIGH
        if prefer_stock:
            checks = [
                self._try_waste_branches,
                self._try_draw_branch,
                self._try_recycle_branch,
                self._try_board_pair_branches,
            ]
        else:
            checks = [
                self._try_board_pair_branches,
                self._try_waste_branches,
                self._try_draw_branch,
                self._try_recycle_branch,
            ]
        for check in checks:
            ok, solution, count = check(remaining, stock, waste, waste_slot_indices, path, visited, visible_slots, action_count, stock_cycles_used, branch_count)
            if ok:
                return ok, solution, count
        return False, [], 0

    def _try_board_pair_branches(self, remaining: Dict[int, Card], stock: List[Card], waste: List[Card], waste_slot_indices: List[int], path: List[Tuple[int, int, Optional[Card]]], visited: set[str], visible_slots: List[int], action_count: int, stock_cycles_used: int, branch_count: List[int]) -> Tuple[bool, List[Tuple[int, int, Optional[Card]]], int]:
        for i in range(len(visible_slots)):
            for j in range(i + 1, len(visible_slots)):
                first = visible_slots[i]
                second = visible_slots[j]
                if not are_match(remaining[first], remaining[second]):
                    continue
                first_card = remaining.pop(first)
                second_card = remaining.pop(second)
                path.append((first, second, None))
                ok, solution, count = self._search(remaining, stock, waste, waste_slot_indices, path, visited, action_count + 1, stock_cycles_used)
                if ok:
                    return ok, solution, count
                path.pop()
                remaining[first] = first_card
                remaining[second] = second_card
                branch_count[0] += 1
                if branch_count[0] >= MAX_BRANCHES_PER_STATE:
                    return False, [], 0
        return False, [], 0

    def _try_waste_branches(self, remaining: Dict[int, Card], stock: List[Card], waste: List[Card], waste_slot_indices: List[int], path: List[Tuple[int, int, Optional[Card]]], visited: set[str], visible_slots: List[int], action_count: int, stock_cycles_used: int, branch_count: List[int]) -> Tuple[bool, List[Tuple[int, int, Optional[Card]]], int]:
        if not waste:
            return False, [], 0
        for waste_index in self._visible_waste_indexes(waste_slot_indices):
            waste_card = waste[waste_index]
            waste_slot_index = waste_slot_indices[waste_index]
            for board_slot in visible_slots:
                if not are_match(remaining[board_slot], waste_card):
                    continue
                board_card = remaining.pop(board_slot)
                waste.pop(waste_index)
                waste_slot_indices.pop(waste_index)
                path.append((board_slot, -1, waste_card))
                ok, solution, count = self._search(remaining, stock, waste, waste_slot_indices, path, visited, action_count + 1, stock_cycles_used)
                if ok:
                    return ok, solution, count
                path.pop()
                waste.insert(waste_index, waste_card)
                waste_slot_indices.insert(waste_index, waste_slot_index)
                remaining[board_slot] = board_card
                branch_count[0] += 1
                if branch_count[0] >= MAX_BRANCHES_PER_STATE:
                    return False, [], 0
        return False, [], 0

    def _try_draw_branch(self, remaining: Dict[int, Card], stock: List[Card], waste: List[Card], waste_slot_indices: List[int], path: List[Tuple[int, int, Optional[Card]]], visited: set[str], visible_slots: List[int], action_count: int, stock_cycles_used: int, branch_count: List[int]) -> Tuple[bool, List[Tuple[int, int, Optional[Card]]], int]:
        if not stock:
            return False, [], 0
        draw_count = min(STOCK_DEAL_COUNT, len(stock))
        drawn: List[Card] = []
        for i in range(draw_count):
            card = stock.pop(0)
            waste.append(card)
            waste_slot_indices.append(i % STOCK_WASTE_SLOT_COUNT)
            drawn.append(card)
        ok, solution, count = self._search(remaining, stock, waste, waste_slot_indices, path, visited, action_count + 1, stock_cycles_used)
        if ok:
            return ok, solution, count
        for card in reversed(drawn):
            waste.pop()
            waste_slot_indices.pop()
            stock.insert(0, card)
        return False, [], 0

    def _try_recycle_branch(self, remaining: Dict[int, Card], stock: List[Card], waste: List[Card], waste_slot_indices: List[int], path: List[Tuple[int, int, Optional[Card]]], visited: set[str], visible_slots: List[int], action_count: int, stock_cycles_used: int, branch_count: List[int]) -> Tuple[bool, List[Tuple[int, int, Optional[Card]]], int]:
        if stock or not waste:
            return False, [], 0
        if not (self.stock_cycle_count < 0 or stock_cycles_used < self.stock_cycle_count):
            return False, [], 0
        recycled = list(waste)
        recycled_indices = list(waste_slot_indices)
        stock.extend(recycled)
        waste.clear()
        waste_slot_indices.clear()
        next_cycles = stock_cycles_used if self.stock_cycle_count < 0 else stock_cycles_used + 1
        ok, solution, count = self._search(remaining, stock, waste, waste_slot_indices, path, visited, action_count + 1, next_cycles)
        if ok:
            return ok, solution, count
        waste.extend(recycled)
        waste_slot_indices.extend(recycled_indices)
        del stock[-len(recycled):]
        return False, [], 0

    def _visible_slots(self, remaining: Dict[int, Card]) -> List[int]:
        result: List[int] = []
        for slot in self.template.slots:
            if slot.slot_id in remaining and all(blocker not in remaining for blocker in slot.blocked_by):
                result.append(slot.slot_id)
        return result

    @staticmethod
    def _visible_waste_indexes(waste_slot_indices: List[int]) -> List[int]:
        indexes: List[int] = []
        for slot_index in range(STOCK_WASTE_SLOT_COUNT):
            for waste_index in range(len(waste_slot_indices) - 1, -1, -1):
                if waste_slot_indices[waste_index] == slot_index:
                    indexes.append(waste_index)
                    break
        return sorted(indexes, reverse=True)

    @staticmethod
    def _state_key(remaining: Dict[int, Card], stock: List[Card], waste: List[Card], waste_slot_indices: List[int], stock_cycles_used: int) -> str:
        parts: List[str] = []
        for slot_id in sorted(remaining):
            parts.append(f"{slot_id}:{remaining[slot_id].card_id},")
        parts.append("|s:")
        parts.extend(f"{card.card_id}," for card in stock)
        parts.append("|w:")
        for index, card in enumerate(waste):
            parts.append(f"{waste_slot_indices[index]}:{card.card_id},")
        parts.append(f"|c:{stock_cycles_used}")
        return "".join(parts)


def fixed_deal(config: LevelConfig, template: Template) -> GeneratedLevel:
    cards_by_slot = {
        6: create_card(6, 2),
        7: create_card(5, 1),
        8: create_card(4, 0),
        0: create_card(5, 3),
        2: create_card(2, 2),
        5: create_card(7, 3),
        1: create_card(3, 2),
        4: create_card(9, 0),
        3: create_card(4, 1),
    }
    board_cards = [
        BoardCard(slot.slot_id, cards_by_slot[slot.slot_id], is_initially_visible(template, slot.slot_id))
        for slot in template.slots
        if slot.slot_id in cards_by_slot
    ]
    stock_cards = [create_card(8, 0), create_card(1, 1), create_card(6, 3)]
    return GeneratedLevel(config.level_id, config.seed, config.layout_id, config.difficulty, config.difficulty, False, SOLVABILITY_GUARANTEED, -1, 9, board_cards, stock_cards, 9)


def generate_level(config: LevelConfig, templates: Dict[int, Template]) -> GeneratedLevel:
    if config.layout_id not in templates:
        raise ValueError(f"Unsupported generated board layout id {config.layout_id}.")
    template = templates[config.layout_id]
    if config.fixed_deal:
        return fixed_deal(config, template)
    cfg = difficulty_config(config.difficulty, config.seed)
    if cfg.solvability_mode == SOLVABILITY_RANDOM:
        return build_random_deal(config, template, config.seed, config.difficulty, cfg)
    for attempt in range(GUARANTEED_ATTEMPTS):
        deal_seed = config.seed + attempt * 7919
        random = SeededLevelRandom(deal_seed)
        board_cards, stock_cards = build_candidate_deal(config, template, cfg, random)
        improve_internal_pairs(template, board_cards, stock_cards, cfg, random)
        solver = DealSolver(template, cfg)
        ok, solution, _ = solver.try_solve(board_cards, stock_cards)
        if not ok:
            continue
        arrange_solution_stock_assists(stock_cards, solution, cfg, random)
        ok, validated_solution, action_count = solver.try_solve(board_cards, stock_cards)
        if not ok:
            continue
        move_limit = max(1, action_count + move_limit_offset(config.level_id, config.difficulty))
        return GeneratedLevel(config.level_id, deal_seed, config.layout_id, config.difficulty, config.difficulty, False, cfg.solvability_mode, cfg.stock_cycle_count, move_limit, board_cards, stock_cards, action_count)
    fallback_seed = config.seed + 99991
    random_cfg = difficulty_config(DIFF_RANDOM, fallback_seed)
    return build_random_deal(config, template, fallback_seed, DIFF_RANDOM, random_cfg, used_fallback=True)


def build_random_deal(config: LevelConfig, template: Template, seed: int, output_difficulty: int, cfg: DifficultyConfig, used_fallback: bool = False) -> GeneratedLevel:
    random = SeededLevelRandom(seed)
    board_cards, stock_cards = build_candidate_deal(config, template, cfg, random)
    move_limit = random.range(20, 31)
    return GeneratedLevel(config.level_id, seed, config.layout_id, config.difficulty, output_difficulty, used_fallback, cfg.solvability_mode, cfg.stock_cycle_count, move_limit, board_cards, stock_cards, 0)


def config_for_level(level_id: int, start_configs: Dict[int, Dict[str, Any]], templates: Dict[int, Template], ten_config: Dict[str, Any], reporter: Reporter, source_path: Path) -> Optional[LevelConfig]:
    if level_id == 1:
        return LevelConfig(level_id, PRESET_START, DIFF_EASY, RANGE_FIXED, 100000 + level_id, True, [], "tutorial fixed")
    if level_id < 2:
        return None
    if level_id in start_configs:
        raw = start_configs[level_id]
        layout_number = raw.get("layoutId")
        symbol = f"startLevelConfig.level={level_id}"
        if not isinstance(layout_number, int) or isinstance(layout_number, bool):
            reporter.add("BLOCKER", f"Level {level_id} layoutId is invalid", source_path, f"{symbol}.layoutId", "layoutId must be an integer template number.", "Fix layoutId.")
            return None
        if layout_number < 1 or layout_number > len(templates):
            reporter.add("BLOCKER", f"Level {level_id} layoutId is out of range", source_path, f"{symbol}.layoutId", f"Template number {layout_number} is outside available range 1-{len(templates)}.", "Use a valid template number.")
            return None
        difficulty = parse_difficulty(raw.get("dif"), reporter, source_path, f"{symbol}.dif")
        card_range = parse_card_range(raw.get("group"), reporter, source_path, f"{symbol}.group")
        extras = parse_extras(raw.get("extra", []), reporter, source_path, f"{symbol}.extra")
        return LevelConfig(level_id, layout_id_for_template_number(layout_number), difficulty, card_range, 100000 + level_id, False, extras, "startLevelConfig")
    if level_id < CYCLE_CONFIG_START_LEVEL:
        return None
    cycle = ten_config.get("cycleLevelDiff") or []
    if not cycle:
        return None
    index = max(0, level_id - CYCLE_CONFIG_START_LEVEL) % len(cycle)
    difficulty = int(cycle[index])
    template_count = len(templates)
    template_number = cycle_template_number(level_id, template_count)
    for _ in range(template_count):
        layout_id = layout_id_for_template_number(template_number)
        template = templates.get(layout_id)
        if difficulty != DIFF_EASY or (template is not None and count_covered(template) < EASY_COVERED_CARD_SKIP_THRESHOLD):
            extras = cycle_extras(level_id, difficulty, ten_config)
            return LevelConfig(level_id, layout_id, difficulty, RANGE_FULL, 100000 + level_id, False, extras, "cycle")
        template_number = 1 if template_number >= template_count else template_number + 1
    reporter.add("BLOCKER", f"Level {level_id} cannot select an Easy cycle template", "GeneratedBoardLayoutPresets.json", "LocalLevelConfigProvider.SelectCycleLayoutId", "All templates are too covered for Easy cycle levels.", "Add an Easy-valid template or change cycle difficulty.")
    return None


def cycle_template_number(level_id: int, template_count: int) -> int:
    loop_size = template_count - CYCLE_TEMPLATE_LOOP_START_NUMBER + 1
    if loop_size <= 0:
        return CYCLE_TEMPLATE_LOOP_START_NUMBER
    offset = max(0, level_id - CYCLE_CONFIG_START_LEVEL)
    zero_based = (CYCLE_TEMPLATE_START_NUMBER - CYCLE_TEMPLATE_LOOP_START_NUMBER + offset) % loop_size
    return CYCLE_TEMPLATE_LOOP_START_NUMBER + zero_based


def cycle_extras(level_id: int, difficulty: int, ten_config: Dict[str, Any]) -> List[int]:
    if difficulty != DIFF_EXTRA_HARD:
        return []
    ratio = float(ten_config.get("wildCardRatio", 0.0) or 0.0)
    if ratio <= 0:
        return []
    if ratio >= 1:
        return [0]
    return [0] if SeededLevelRandom(100000 + level_id + WILD_CARD_SEED_OFFSET).value() < ratio else []


def check_generated_levels(unity_root: Path, templates: Dict[int, Template], start_configs: Dict[int, Dict[str, Any]], ten_config: Dict[str, Any], max_level: int, reporter: Reporter) -> None:
    source_path = unity_root / "Assets/Game/Com/Resources/startLevelConfig.json"
    for level_id in range(1, max_level + 1):
        config = config_for_level(level_id, start_configs, templates, ten_config, reporter, source_path)
        if config is None:
            reporter.add("BLOCKER", f"Generated level {level_id} has no config", source_path, "GeneratedLevelLoader.TryLoad", "TryLoad returns false and GamePanel clears generated data.", "Add a config or confirm this level is unreachable.")
            continue
        template = templates.get(config.layout_id)
        if template is None:
            continue
        deck_size = len(build_deck(config))
        if not config.fixed_deal and deck_size < len(template.slots):
            reporter.add("BLOCKER", f"Level {level_id} deck is smaller than template", source_path, config.source, f"Deck has {deck_size} cards but template has {len(template.slots)} slots.", "Use a smaller layout or broader card range/extras.")
            continue
        try:
            level = generate_level(config, templates)
        except Exception as exc:
            reporter.add("BLOCKER", f"Generated level {level_id} throws during static generation", source_path, "LevelGenerator.Generate", str(exc), "Inspect config/template and run a runtime load after fixing.")
            continue
        if config.fixed_deal and len(template.slots) != 9:
            reporter.add("HIGH", "Tutorial fixed deal template slot count changed", unity_root / "Assets/Game/Levels/Resources/GeneratedBoardLayoutPresets.json", "LevelGenerator.BuildFixedDeal", f"Tutorial maps 9 explicit slots, but Preset01 has {len(template.slots)} slots.", "Confirm empty slots are intended or update fixed tutorial mapping.")
        if level.used_fallback:
            reporter.add("HIGH", f"Generated level {level_id} used Random fallback", source_path, "LevelGenerator.Generate", "Guaranteed generation failed all 60 solver attempts and fell back to a Random deal.", "Review template/card pool or run runtime playthrough for this level.")
        if level.solvability_mode == SOLVABILITY_GUARANTEED and level.solution_action_count <= 0 and not config.fixed_deal:
            reporter.add("HIGH", f"Generated level {level_id} has no recorded solution", source_path, "LevelDealSolver.TrySolve", "Guaranteed level did not expose a validated solution action count.", "Requires runtime verification.")
        if level.move_limit <= 0:
            reporter.add("BLOCKER", f"Generated level {level_id} has nonpositive move limit", source_path, "LevelGenerator.CalculateMoveLimit", f"Move limit is {level.move_limit}.", "Fix difficulty offsets or solver output.")


def validate_raw_stage(stage: Any, path: Path, stage_index: int, reporter: Reporter) -> None:
    symbol = f"{path.name}[{stage_index}]"
    if not isinstance(stage, dict):
        reporter.add("BLOCKER", "Raw level stage is not an object", path, symbol, "LevelCatalog only converts object tokens to LevelRawStage.", "Fix this stage object.")
        return
    key_groups = stage.get("key")
    if not isinstance(key_groups, list) or not key_groups:
        reporter.add("BLOCKER", "Raw level stage has no key groups", path, f"{symbol}.key", "LevelLegacyAdapter throws when raw.key is missing.", "Add valid key groups.")
        return
    class_names = stage.get("className")
    token_map: set[str] = set()
    titles_seen: set[str] = set()
    for key_index, group in enumerate(key_groups):
        group_symbol = f"{symbol}.key[{key_index}]"
        if not isinstance(group, dict):
            reporter.add("BLOCKER", "Raw key group is not an object", path, group_symbol, "Key groups must contain title, isImage, and content.", "Fix this key group.")
            continue
        title = group.get("title")
        if not isinstance(title, str) or not title.strip():
            reporter.add("BLOCKER", "Raw key group title is blank", path, f"{group_symbol}.title", "LevelLegacyAdapter throws on blank titles.", "Add a nonblank title.")
            continue
        if title in titles_seen:
            reporter.add("HIGH", "Duplicate raw key group title", path, f"{group_symbol}.title", "Duplicate titles collide in token mapping.", "Rename or merge duplicate key groups.")
        titles_seen.add(title)
        token_map.add(f"{title}:{title}")
        contents = group.get("content") or []
        if not isinstance(contents, list):
            reporter.add("BLOCKER", "Raw key group content is not an array", path, f"{group_symbol}.content", "Content must be an array of strings.", "Fix content format.")
            contents = []
        is_image = bool(group.get("isImage"))
        resource_class = None
        if is_image:
            resource_class = resolve_class_name(class_names, title)
            if not resource_class:
                reporter.add("BLOCKER", "Image key group is missing className mapping", path, f"{symbol}.className", f"Image group '{title}' requires a className entry.", "Add className mapping for this title.")
        for content_index, content in enumerate(contents):
            if not isinstance(content, str) or not content.strip():
                reporter.add("BLOCKER", "Raw key content is blank", path, f"{group_symbol}.content[{content_index}]", "Blank content cannot produce a stable token.", "Fix or remove this content.")
                continue
            if is_image:
                parsed = parse_image_content(content)
                if parsed is None:
                    reporter.add("BLOCKER", "Image raw content has unsupported shape", path, f"{group_symbol}.content[{content_index}]", "Image content must be Class#Resource or prefix#Class#Resource.", "Fix image content.")
                    continue
                class_name, resource_key = parsed
                if resource_class and class_name != resource_class:
                    reporter.add("BLOCKER", "Image className does not match mapping", path, f"{group_symbol}.content[{content_index}]", f"Content class '{class_name}' differs from expected '{resource_class}'.", "Fix content class or className mapping.")
                token_map.add(f"{title}:{class_name}#{resource_key}")
            else:
                token_map.add(f"{title}:{content}")

    for field_name in ("column", "stock"):
        value = stage.get(field_name)
        if field_name == "column":
            token_lists = value if isinstance(value, list) else []
            if not isinstance(value, list):
                reporter.add("BLOCKER", "Raw stage column is missing or invalid", path, f"{symbol}.column", "column must be an array of token arrays.", "Fix column format.")
            for col_index, column in enumerate(token_lists):
                if not isinstance(column, list):
                    reporter.add("BLOCKER", "Raw stage column entry is not an array", path, f"{symbol}.column[{col_index}]", "Each column must be an array of tokens.", "Fix column entry.")
                    continue
                validate_tokens(column, token_map, path, f"{symbol}.column[{col_index}]", reporter)
        else:
            if value is None:
                value = []
            if not isinstance(value, list):
                reporter.add("BLOCKER", "Raw stage stock is invalid", path, f"{symbol}.stock", "stock must be an array of tokens.", "Fix stock format.")
            else:
                validate_tokens(value, token_map, path, f"{symbol}.stock", reporter)


def resolve_class_name(class_names: Any, title: str) -> Optional[str]:
    if not isinstance(class_names, list):
        return None
    for entry in class_names:
        if isinstance(entry, dict):
            value = entry.get(title)
            if isinstance(value, str) and value.strip():
                return value
    return None


def parse_image_content(content: str) -> Optional[Tuple[str, str]]:
    parts = content.split("#")
    if len(parts) == 3:
        return parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1]
    return None


def validate_tokens(tokens: Iterable[Any], token_map: set[str], path: Path, symbol: str, reporter: Reporter) -> None:
    for index, token in enumerate(tokens):
        if not isinstance(token, str):
            reporter.add("BLOCKER", "Raw card token is not a string", path, f"{symbol}[{index}]", "LevelRawStage token arrays are string arrays.", "Fix token type.")
            continue
        if token not in token_map:
            reporter.add("BLOCKER", "Raw card token is not declared in key content", path, f"{symbol}[{index}]", f"Unknown token '{token}' would throw in LevelLegacyAdapter.MapTokens.", "Add the token to key content or fix the board token.")


def check_raw_level_tree(root: Path, kind: str, reporter: Reporter) -> None:
    if not root.is_dir():
        return
    language_dirs = [path for path in root.iterdir() if path.is_dir()]
    if not language_dirs:
        language_dirs = [root]
    for language_dir in language_dirs:
        files = [path for path in language_dir.iterdir() if path.is_file() and path.suffix != ".meta"]
        for path in sorted(files, key=lambda p: (int(p.stem) if p.stem.isdigit() else 10**9, p.name)):
            raw = read_json(path, reporter, f"{kind} raw stage chunk")
            if raw is None:
                continue
            if not isinstance(raw, list):
                reporter.add("BLOCKER", f"{kind} chunk is not an array", path, path.name, "LevelCatalog parses each chunk as a JArray.", "Convert this chunk to an array of stage objects.")
                continue
            if len(raw) != 10:
                reporter.add("MEDIUM", f"{kind} chunk does not contain 10 stages", path, path.name, "LevelCatalog reserves ten slots per chunk; short chunks can shift level mapping.", "Confirm this is the final chunk or pad/fix the chunk.")
            for index, stage in enumerate(raw):
                validate_raw_stage(stage, path, index, reporter)


def find_legacy_roots(unity_root: Path) -> List[Tuple[Path, str]]:
    roots: List[Tuple[Path, str]] = []
    assets = unity_root / "Assets"
    for path in assets.rglob("LevelData"):
        if path.is_dir() and "Resources" in path.parts:
            roots.append((path, "LevelData"))
    for path in assets.rglob("SpecialLevelData"):
        if path.is_dir() and "Resources" in path.parts:
            roots.append((path, "SpecialLevelData"))
    return roots


def check_diff0(unity_root: Path, reporter: Reporter) -> None:
    path = unity_root / "Assets/Game/Com/Resources/diff0.json"
    raw = read_json(path, reporter, "diff0 tutorial legacy level")
    if raw is None:
        return
    if not isinstance(raw, list) or not raw:
        reporter.add("BLOCKER", "diff0 is empty or not an array", path, "diff0", "Tutorial legacy data is packaged as a JSON array.", "Restore valid diff0 data or confirm it is obsolete.")
        return
    for index, level in enumerate(raw):
        if not isinstance(level, dict):
            reporter.add("BLOCKER", "diff0 level is not an object", path, f"diff0[{index}]", "Each diff0 entry must be a level object.", "Fix this entry.")
            continue
        books = level.get("books")
        if not isinstance(books, list) or not books:
            reporter.add("BLOCKER", "diff0 level has no books", path, f"diff0[{index}].books", "Card ids depend on book definitions.", "Restore book definitions.")
            continue
        valid_ids: set[int] = set()
        for book in books:
            if not isinstance(book, dict):
                continue
            book_id = book.get("id")
            words = book.get("words") or []
            if not isinstance(book_id, int) or isinstance(book_id, bool):
                reporter.add("BLOCKER", "diff0 book id is invalid", path, f"diff0[{index}].books", "Book id must be an integer.", "Fix book id.")
                continue
            valid_ids.add(book_id * 100)
            if isinstance(words, list):
                for word_index in range(len(words)):
                    valid_ids.add(round((book_id + (word_index + 1) / 100.0) * 100))
        for field_name in ("columns", "stocks", "founds"):
            value = level.get(field_name)
            lists = value if field_name != "stocks" else [value]
            if not isinstance(lists, list):
                reporter.add("BLOCKER", f"diff0 {field_name} is invalid", path, f"diff0[{index}].{field_name}", "Expected an array.", "Fix this field.")
                continue
            for list_index, values in enumerate(lists):
                if not isinstance(values, list):
                    continue
                for card_index, card_key in enumerate(values):
                    if not isinstance(card_key, (int, float)) or isinstance(card_key, bool):
                        reporter.add("BLOCKER", "diff0 card key is not numeric", path, f"diff0[{index}].{field_name}[{list_index}][{card_index}]", "Legacy CardData keys are numeric.", "Fix card key.")
                        continue
                    normalized = round(float(card_key) * 100)
                    if normalized not in valid_ids:
                        reporter.add("HIGH", "diff0 card key is not declared by books", path, f"diff0[{index}].{field_name}[{list_index}][{card_index}]", f"Card key {card_key} has no matching book/content id.", "Fix book definitions or card key.")


def load_settings(path: Optional[Path], reporter: Reporter) -> Any:
    if path is None:
        return None
    return read_json(path, reporter, "remote game settings")


def print_report(unity_root: Path, max_level: int, reporter: Reporter) -> None:
    issues = sorted(reporter.issues, key=lambda issue: (SEVERITY_RANK.get(issue.severity, 99), issue.file_path, issue.item))
    counts: Dict[str, int] = {}
    for issue in issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
    print("Sotaten Level Legality Report")
    print(f"project: {unity_root}")
    print(f"generated levels checked: 1-{max_level}")
    print("findings: " + (", ".join(f"{key}={counts[key]}" for key in sorted(counts, key=lambda k: SEVERITY_RANK.get(k, 99))) if counts else "none"))
    print()
    if not issues:
        print("No static level legality findings.")
        return
    for issue in issues:
        print(f"[{issue.severity}] {issue.item}")
        print(f"  status: {issue.severity}")
        print(f"  file path: {issue.file_path}")
        print(f"  function/class/config key: {issue.symbol}")
        print(f"  short reasoning: {issue.reasoning}")
        print(f"  suggested validation: {issue.suggested_validation}")
        print()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check Sotaten level legality without launching Unity.")
    parser.add_argument("--project", default=".", help="Repository root or Unity project root.")
    parser.add_argument("--levels", type=int, default=80, help="Highest generated level id to simulate.")
    parser.add_argument("--settings", type=Path, help="Optional remote game setting JSON with startLevelConfig/tenConfig.")
    parser.add_argument("--legacy-root", action="append", type=Path, default=[], help="Additional LevelData or SpecialLevelData root to scan.")
    parser.add_argument("--fail-on", choices=["BLOCKER", "HIGH", "MEDIUM", "LOW"], default="BLOCKER", help="Exit nonzero when this severity or worse is present.")
    args = parser.parse_args(argv)

    reporter = Reporter()
    unity_root = resolve_unity_root(Path(args.project))
    settings = load_settings(args.settings, reporter)
    templates = load_templates(unity_root, reporter)
    start_configs = load_start_configs(unity_root, settings, reporter)
    ten_config = load_ten_config(settings, reporter)

    check_diff0(unity_root, reporter)
    if templates:
        check_generated_levels(unity_root, templates, start_configs, ten_config, max(1, args.levels), reporter)

    legacy_roots = find_legacy_roots(unity_root)
    for root in args.legacy_root:
        legacy_roots.append((root, root.name))
    seen_roots: set[Path] = set()
    for root, kind in legacy_roots:
        resolved = root.resolve()
        if resolved in seen_roots:
            continue
        seen_roots.add(resolved)
        check_raw_level_tree(resolved, kind, reporter)

    if not legacy_roots:
        reporter.add("INFO", "No LevelData or SpecialLevelData resources found in source tree", unity_root / "Assets", "ResourcesLevelResourceProvider/SpecialLevelResourceProvider", "Current source tree has generated Ten resources but no raw LevelData folders.", "If release uses downloaded or built-in raw levels, provide those JSON files with --legacy-root.")

    print_report(unity_root, max(1, args.levels), reporter)
    fail_rank = SEVERITY_RANK[args.fail_on]
    return 1 if any(SEVERITY_RANK.get(issue.severity, 99) <= fail_rank for issue in reporter.issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
