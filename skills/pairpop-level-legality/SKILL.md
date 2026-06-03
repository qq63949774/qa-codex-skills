---
name: pairpop-level-legality
description: Use when checking PairPop level JSON legality or solvability for the PairPop project, including model=0 column levels and model=3 text-bubble levels under Assets/Resources/PuzzleData. Reads current client rules from PuzzleDataManager, GameCtr, GameBubbleCtr, TextBubble, and Bubble, then runs the bundled checker for structural issues.
---

# PairPop Level Legality

Use this skill when the task is to inspect PairPop level JSONs for structural legality under the current client implementation.

This skill is project-specific for `<pairpop-repo-root>`. It is related to `pairmatch-level-solvability`, but PairPop ships PairPop-specific `model=0` column data and `model=3` text-bubble data, which that PairMatch checker rejects.

## Scope

Supported level families:

- `model=0` column levels:
  - `PuzzleDataManager` reads `time`, not `move`, for this model.
  - `GameCtr` routes to `LoadColumn()` and initializes ordinary `Bubble` cards.
  - `Bubble` renders card images from `imageName` via `Util.loadImageSprite("Texture/ItemImage/" + imageName, image)`.
  - `elementName`, `type`, and `stage` are not required for `model=0` legality because those are text-bubble fields.
  - If the completed bubble's first card is `isMix=true`, `GameBubbleCtr.createNewBubbles()` expands from `puzzleData.levelData[className]`.
  - Hidden expansions must contain exactly 4 cards and may chain through mix classes.
- `model=3` text-bubble levels:
  - `PuzzleDataManager` reads `move`, not `time`, for this model.
  - `GameCtr` flattens every card in `data` into a separate bubble.
  - `GameBubbleCtr` permits merging only when two bubbles have the same first `className`.
  - A bubble becomes complete when it contains 4 cards.
  - If the completed bubble's first card is `isMix=true`, `GameBubbleCtr.createNewBubbles()` expands from `puzzleData.levelData[className]`.
  - Hidden expansions must contain exactly 4 cards and may chain through mix classes.
  - `TextBubble` renders text from `elementName`, uses `type` to choose text/image display, and uses `stage=0` for special single-item visual state.
  - Text cards (`type=0`) in the same level must not reuse the same displayed word within the same locale. Resolve `elementName` through every display-language column in `Assets/Resources/puzzleLanguage.csv`, then compare normalized display text separately inside each locale column. Do not compare words across different languages/locales. Only exact whole display-string equality counts; substring containment does not count as a duplicate.

The guarantee is invariant-based. It is not a brute-force physics or move-count solver.

## Code Anchors

Refresh these files before making claims:

- `<pairpop-unity-project-root>/Assets/Script/Data/PuzzleDataManager.cs`
- `<pairpop-unity-project-root>/Assets/Script/GameCtr.cs`
- `<pairpop-unity-project-root>/Assets/Script/GameBubbleCtr.cs`
- `<pairpop-unity-project-root>/Assets/Script/TextBubble.cs`
- `<pairpop-unity-project-root>/Assets/Script/Bubble.cs`

Important behaviors:

- `PuzzleDataManager.ParseToPuzzleList()` treats `model=0` and `model=3` as non-table data. `model=0` requires `time`; `model=3` requires `move`.
- `GameCtr` routes `model=0` to `LoadColumn()` and routes `model=1`/`model=3` through flattened bubble loading.
- `GameBubbleCtr.CheckBubbleIntersection()` rejects max-size bubbles and later merges only matching `className`.
- `GameBubbleCtr.onTouchEndCard()` calls `GameCtr.ConsumeMoveStep()` for a drag/drop attempt that overlaps another bubble, and `ConsumeMoveStep()` increments used move count by 1 in `model=3`.
- `Bubble.updateImages()` uses `imageName` for ordinary `model=0` image resources.
- `TextBubble.mergeAction()` accumulates card data into the target bubble.
- `TextBubble.RefreshContentLayout()` treats `type=1` cards as images and calls `Util.loadImageSprite("Texture/ItemImage/" + elementName, image)`.
- `TextBubble` and `Bubble` broadcast `CreatNewBubbles` before `oneBubbleFinished` for mix completions.
- `GameBubbleCtr.createNewBubbles()` expands from `puzzleData.levelData[className]` and only spawns the next bubbles when the expansion count is 4.
- For item image resource checks, treat an exact asset stem or a numeric Unity duplicate suffix such as `<name>-1` as present when runtime verification shows the suffix variant loads normally.

## Required Check

Run:

```bash
python3 ~/.codex/skills/pairpop-level-legality/scripts/check_pairpop_level_legality.py \
  --puzzle-dir <pairpop-unity-project-root>/Assets/Resources/PuzzleData
```

For a standalone exported level file:

```bash
python3 ~/.codex/skills/pairpop-level-legality/scripts/check_pairpop_level_legality.py \
  --json-file <pairpop-repo-root>/levels_01-100.json
```

Optional filters:

```bash
python3 ~/.codex/skills/pairpop-level-legality/scripts/check_pairpop_level_legality.py \
  --puzzle-dir <pairpop-unity-project-root>/Assets/Resources/PuzzleData \
  --level level1
```

JSON output:

```bash
python3 ~/.codex/skills/pairpop-level-legality/scripts/check_pairpop_level_legality.py \
  --puzzle-dir <pairpop-unity-project-root>/Assets/Resources/PuzzleData \
  --json
```

<!-- Correction: 2026-05-21 | was: "check hot-update levels against current workspace language files" | reason: hot-update legality depends on target client version assets/translations -->

## Hot Update Target Version Checks

When the user says a level file is a hot update for a specific client version or historical project date, do not use the current workspace translations/assets by default. First resolve the target project version:

1. Run `git fetch --all --prune`.
2. Locate the target commit or branch/tag from the user's version/date, for example the latest commit before the specified date in the target timezone.
3. Create a detached temporary worktree for that commit, preferably under `/tmp`.
4. Run the checker with `--project-root <worktree>/PairPop` so image resources and `Assets/Resources/puzzleLanguage.csv` come from the target client version.
5. Report the git commit hash, commit time, and language/resource file evidence used for the result.

If the target version/date is ambiguous, state the assumption explicitly before presenting findings.

## What The Checker Guarantees

Treat a `model=0` level as structurally legal only if these invariants hold:

1. Required metadata exists and parses under the client `ToString()` + `int.Parse()` behavior: `model=0`, `gridSize=<targetClassCount>x<rowCount>`, `showRows`, `time`, `difficulty`, `theme`, and array `data`.
2. Every initial group in `data` is a list. Empty groups are suspicious because `GameCtr` silently flattens them into fewer starting cards/columns.
3. Every card in `data` and hidden expansions has non-empty `className` and `imageName`, plus boolean `isMix`.
4. Every `imageName` has a matching asset under `Assets/Resources/Texture/ItemImage/<imageName>` or a numeric duplicate-suffix variant such as `<imageName>-1`, because missing sprites render as blank/default UI.
5. Every hidden expansion array has exactly 4 cards, matching `createNewBubbles()` runtime behavior.
6. `gridSize` first dimension equals the number of distinct `className` values across initial cards plus hidden expansions.
7. Each `className` appears exactly 4 times across initial cards plus hidden expansions.
8. Total card count equals `targetClassCount * 4`.
9. Every hidden key is represented by exactly four mix cards.
10. Hidden expansion keys are reachable from the initial visible cards through mix chains.
11. Hidden expansion chains are acyclic.

Treat a `model=3` level as structurally legal only if these invariants hold:

1. Required metadata exists and parses under the client `ToString()` + `int.Parse()` behavior: `model=3`, `gridSize=<targetClassCount>x<rowCount>`, `showRows`, `move`, `difficulty`, `theme`, and array `data`.
2. Every initial group in `data` is a list. Empty groups are suspicious because `GameCtr` silently flattens them into fewer starting bubbles.
3. Every card in `data` and hidden expansions has non-empty `className` and `elementName`, boolean `isMix`, integer `type`, and integer `stage`.
4. `type` is `0` or `1`; `stage` is `0` or `1`.
5. Every `type=1` card has a matching asset under `Assets/Resources/Texture/ItemImage/<elementName>` or a numeric duplicate-suffix variant such as `<elementName>-1`, because missing sprites render as blank/default UI.
6. Every hidden expansion array has exactly 4 cards, matching `createNewBubbles()` runtime behavior.
7. `gridSize` first dimension equals the number of distinct `className` values across initial cards plus hidden expansions.
8. Each `className` appears exactly 4 times across initial cards plus hidden expansions.
9. Total card count equals `targetClassCount * 4`.
10. Every hidden key is represented by exactly four mix cards.
11. Hidden expansion keys are reachable from the initial visible cards through mix chains.
12. Hidden expansion chains are acyclic.
13. The configured `move` value must be strictly greater than the shortest zero-mistake merge route. Under the current text-bubble structure, the shortest route is `targetClassCount * 3`, because each completed 4-card class requires 3 successful merge moves.
14. No two `type=0` text cards in the same level may display the same word within the same supported locale. The checker resolves `elementName` via all display-language columns in `Assets/Resources/puzzleLanguage.csv`, normalizes whitespace/case, and compares values separately per locale using exact whole display-string equality only. Report `duplicate_text_word_in_level` with the locale and all occurrence locations when a duplicate is found. Substring containment is allowed and must not be reported; for example, `CODE` inside `MORSE CODE`, `PIN` inside `PINOT NOIR`, or a short word contained in a longer phrase is not a duplicate unless the normalized display strings are exactly the same. This applies across both initial cards and hidden expansion cards; for example, English `CODE`, `PIN`, and `PASSWORD` are not compared to Chinese text, but if two cards both display as Chinese `密码` in `zh_hans`, that is a duplicate.

If any invariant fails, do not claim guaranteed legality. The move check is an abstract zero-mistake lower-bound check; physics overlap problems, accidental invalid drags, and player execution still require runtime verification.

## Output Style

When reporting results:

- State that the guarantee is based on current client rules, not a brute-force solver.
- Quote exact suspicious levels from script output.
- Include code/config evidence for important findings.
- Separate failures into:
  - schema/model violations
  - data-count violations
  - card-shape violations
  - image-resource violations
  - hidden-chain violations
  - mix-flag violations
  - duplicate text-word violations
  - runtime-only risks
