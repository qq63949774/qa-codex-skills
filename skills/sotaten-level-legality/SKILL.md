---
name: sotaten-level-legality
description: Check Sotaten Unity project level legality for generated Ten card levels, generated board layout presets, startLevelConfig, optional remote game settings, and legacy LevelData/SpecialLevelData JSON. Use when asked to scan Sotaten levels, validate generated level configs/templates, inspect release risk from level data, or confirm whether current Sotaten level resources can load and solve without runtime blockers.
---

# Sotaten Level Legality

## Workflow

1. Work from the repository root that contains `sotaten/Assets`, or from the Unity project root `sotaten`.
2. Read `references/project-rules.md` before making judgments that go beyond the script output.
3. Run the checker:

```bash
python3 ~/.codex/skills/sotaten-level-legality/scripts/check_sotaten_levels.py --project .
```

Use `--levels N` for a wider generated-level sweep. Use `--settings path/to/game-setting.json` when a remote game setting payload may override `startLevelConfig` or `tenConfig`.

## What To Check

Focus on evidence from these sources:

- `sotaten/Assets/Game/Com/Resources/startLevelConfig.json`
- `sotaten/Assets/Game/Levels/Resources/GeneratedBoardLayoutPresets.json`
- `sotaten/Assets/Game/Com/Script/GameConfig.cs`
- `sotaten/Assets/Game/Levels/Generation/*.cs`
- Optional `Resources/LevelData/<lang>/<chunk>` and `Resources/SpecialLevelData/<lang>/<chunk>` files when present.

Treat generated-level fallbacks from guaranteed difficulties as high risk: runtime can still create a level, but the intended guarantee failed and requires design review or runtime verification.

## Reporting

For each important finding include:

- item
- status
- file path
- function/class/config key
- short reasoning
- suggested validation

Use `unable to confirm` or `requires runtime verification` when the evidence is not enough. Do not mark level solvability as guaranteed unless the checker or code evidence proves it.

## Boundaries

Do not upload project code. Do not launch Unity for this skill unless the user explicitly asks. This skill is designed for static QA inspection and deterministic local scripts.
