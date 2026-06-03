---
name: pairmatch-level-solvability
description: Use when verifying or writing a solvability guarantee for this PairMatch/ipair project's level JSONs. Applies the current client rules from PuzzleDataManager, GameCtr, ColumnCtr, Card, and GameTableCtr, then runs the bundled checker against classic pairmatch data or model=2 table levels to validate structural legality and list suspicious levels.
---

# PairMatch Level Solvability

Use this skill when the task is to explain, review, or batch-check whether PairMatch level JSONs are solvable under the current client implementation.

## Scope

This skill is for the PairMatch-style rules used in this repository.

Supported level families:

- `model` omitted / `model=0` / `model=1`:
  - A column is complete only when its 4 cards have the same `className`.
  - Cards are solved by swapping positions; the client swap logic allows arbitrary transpositions over time, so any target partition of the current visible cards is reachable.
  - When a solved column is `isMix=true`, the client replaces that column with `levelData[className]`, using the solved class as the deterministic expansion key.
  - Hidden expansion may chain multiple times until a non-mix class is reached.
- `model=2`:
  - `PuzzleDataManager` parses `gridSize` as `columnCount x rowCount`.
  - `GameTableCtr` builds a fixed grid from `rowClass` and `columnClass`.
  - Each card belongs to exactly one `(rowClass, columnClass)` coordinate.
  - Structural legality means the union of `table + queue1 + queue2` covers the full row/column cartesian product exactly once.

This is an invariant-based guarantee, not an exhaustive state-space solver.

## Code Anchors

Refresh these files before making claims:

- `<pairmatch-unity-project-root>/Assets/Script/Card.cs`
- `<pairmatch-unity-project-root>/Assets/Script/ColumnCtr.cs`
- `<pairmatch-unity-project-root>/Assets/Script/GameCtr.cs`
- `<pairmatch-unity-project-root>/Assets/Script/Data/PuzzleDataManager.cs`
- `<pairmatch-unity-project-root>/Assets/Script/GameTableCtr.cs`

The important behaviors are:

- `Card.getTypeValue()` returns the stored `className`
- `ColumnCtr.isColumnSuccess()` checks whether all 4 cards in a column share the same type
- `GameCtr.createNewColumn()` expands mix columns via `puzzleData.levelData[classType]`
- `PuzzleDataManager` parses legacy columns or `model=2` table payloads from the level JSON
- `GameTableCtr.createGrideDefaultCards()` places pre-filled table cards by `rowClass + columnClass`
- `GameTableCtr.createCandidateCards()` loads remaining cards from `queue1` and `queue2`
- `GameTableCtr.checkRowOrColumnFinished()` treats table progress as completed rows plus completed columns

## Required Check

Run the bundled checker:

```bash
python3 scripts/check_pairmatch_solvability.py \
  --puzzle-dir <pairmatch-unity-project-root>/Assets/Resources/PuzzleData
```

Optional filters:

```bash
python3 scripts/check_pairmatch_solvability.py \
  --puzzle-dir <pairmatch-unity-project-root>/Assets/Resources/PuzzleData \
  --level level30
```

JSON output:

```bash
python3 scripts/check_pairmatch_solvability.py \
  --puzzle-dir <pairmatch-unity-project-root>/Assets/Resources/PuzzleData \
  --json
```

Cloud patch / merged level file:

```bash
python3 scripts/check_pairmatch_solvability.py \
  --json-file <pairmatch-repo-root>/levels_1_470.json \
  --level level5 \
  --level level25 \
  --json
```

## What The Checker Guarantees

Treat a legacy level (`model` omitted / `0` / `1`) as structurally solvable only if these invariants hold:

1. Every visible column in `data` has exactly 4 cards.
2. Every hidden expansion array also has exactly 4 cards.
3. `gridSize` first dimension equals the total number of final target classes.
4. Across initial cards plus all hidden expansions, total card count equals `targetClassCount * 4`.
5. Every `className` appears exactly 4 times across the whole level payload.
6. Every hidden key is itself a 4-card mix class.
7. Hidden expansion chains are acyclic.

Treat a table level (`model=2`) as structurally legal only if these invariants hold:

1. `gridSize` parses to `columnCount x rowCount`.
2. `data` is an object containing `rowClass`, `columnClass`, `table`, `queue1`, and `queue2`.
3. `rowClass` count equals `gridSize` second dimension; `columnClass` count equals first dimension.
4. `rowClass` values are unique; `columnClass` values are unique.
5. Every entry in `table`, `queue1`, and `queue2` has valid `rowClass`, `columnClass`, and `imageName`.
6. Across `table + queue1 + queue2`, every `(rowClass, columnClass)` coordinate appears exactly once.
7. Total card count equals `rowCount * columnCount`.

These checks match the current client logic well enough to support a production-facing legality note. If any invariant fails, do not claim guaranteed legality.

## Output Style

When reporting results:

- State that the guarantee is based on current client rules, not a brute-force solver.
- Quote the exact suspicious levels from the script output.
- Cite the code anchors above when explaining why the invariants are sufficient.
- If the script finds failures, separate them into:
  - data-count violations
  - hidden-chain violations
  - mix-flag violations
  - table-coordinate coverage violations

## Current Repo Note

When this skill was created, the staged checker found suspicious levels in the current repository. Re-run the script instead of assuming they are still the same.
