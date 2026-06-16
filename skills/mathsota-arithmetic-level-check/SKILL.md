---
name: mathsota-arithmetic-level-check
description: Check Mathsota arithmetic level JSONs for numeric category and equation correctness. Use when the user asks to scan Mathsota level files, arithmetic cards, math expressions, formula correctness, tokens like "8:2x4", or whether LevelData/SpecialLevelData equations equal their target number; distinct from Mixword word/image legality checks.
---

# Mathsota Arithmetic Level Check

## Purpose

Use this skill for Mathsota arithmetic level validation. It is separate from `mixword-level-legality-check`:

- Mixword legality checks verify token mapping, duplicate/missing cards, cover build behavior, and runtime initial state.
- Mathsota arithmetic checks verify that every numeric target and arithmetic expression agree, for example `8:2x4` is valid because `2x4 = 8`.

This skill does not prove long-step solvability.

## Evidence To Read

When the project source is available, use these files as the rule source:

- `Assets/Game/Levels/Script/LevelLegacyAdapter.cs`
  - Raw tokens map as `{title}:{content}`.
  - Type-card tokens map as `{title}:{title}`.
  - Non-type cards must be declared in the matching `key[].content`.
- `Assets/Game/Game/Script/Card.cs`
  - `TryParseFormula` recognizes digits + one operator + digits.
  - Operators include `+`, `-`, `−`, `*`, `x`, `X`, `×`, `/`, `÷`.

## Workflow

1. Confirm the project root. For this repository, use the Unity root that contains `Assets/`, for example:
   `<MATHSOTA_UNITY_ROOT>`
2. Pick dataset:
   - `normal` scans `Assets/Game/Levels/Resources/LevelData/<language>`
   - `special` scans `Assets/Game/Levels/Resources/SpecialLevelData/<language>`
3. Pick scope:
   - `--all` for all stage items
   - `--level N` for mapped level number
   - `--file X.json --item-index I` for one resource slot
4. Run `scripts/check_arithmetic_levels.py`.
5. Report:
   - dataset, language, file, item index, mapped level
   - counts for JSON files, levels, `key.content`, board tokens, type tokens, equation tokens
   - each failure with token, computed value, expected target, and reason
   - state clearly that solvability still requires solver/runtime verification

## Commands

Full normal/en scan:

```bash
python3 $CODEX_HOME/skills/mathsota-arithmetic-level-check/scripts/check_arithmetic_levels.py \
  --project-root /absolute/project/root \
  --dataset normal \
  --language en \
  --all
```

Single mapped level:

```bash
python3 $CODEX_HOME/skills/mathsota-arithmetic-level-check/scripts/check_arithmetic_levels.py \
  --project-root /absolute/project/root \
  --dataset normal \
  --language en \
  --level 1
```

Single file slot:

```bash
python3 $CODEX_HOME/skills/mathsota-arithmetic-level-check/scripts/check_arithmetic_levels.py \
  --project-root /absolute/project/root \
  --dataset normal \
  --language en \
  --file 1.json \
  --item-index 0
```

Export CSV failures/details:

```bash
python3 $CODEX_HOME/skills/mathsota-arithmetic-level-check/scripts/check_arithmetic_levels.py \
  --project-root /absolute/project/root \
  --dataset normal \
  --language en \
  --all \
  --output-csv /tmp/mathsota_arithmetic_scan.csv
```

## Pass/Fail Rules

Fail the scan when any of these occur:

- `key[].title` is not a pure integer.
- `key[].isImage` is true for a Mathsota arithmetic stage.
- `key[].content` expression cannot be parsed or evaluated.
- A `column`/`stock` token lacks `:`.
- A token's left side is not a pure integer.
- The right-side expression result does not equal the left-side target.
- A non-type board token is not declared in the matching `key[].content`.
- Division by zero occurs.

Treat `{N}:{N}` as a type-card token, not as a missing `key.content` equation.
