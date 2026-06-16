---
name: wordtiles-level-scan
description: Use this for WordTiles level-file QA in `<WORDTILES_REPO>`, especially when the user asks to scan level JSON, check local level packages, verify multilingual level consistency, inspect image-word resources, or review level loading risk. Runs a project-specific checker against `WordTiles/Assets/Main/Resources/out/<lang>/diff*.json` using the current client loading rules from `GameLevel` and `TileGameData`.
---

# WordTiles Level Scan

Use this skill to inspect WordTiles level resources with code-backed QA evidence. The project must not be uploaded; work only with local files.

## Scope

Default local level path:

```text
<WORDTILES_REPO>/WordTiles/Assets/Main/Resources/out/<lang>/diff*.json
```

The checker is based on current client behavior:

- `GameLevel.GetNoramlLevelText(int level)` builds the local Resources path as `out/<lang>/diff1` for level 1, otherwise `diff{level / 100 * 100 + 2}_{(level / 100 + 1) * 100}`.
- `GameLevel.loadData()` parses that file as a JSON array and selects the object whose `level` equals `GameConfig.CurrentLevel`.
- `TileGameData.init(JObject level)` requires `books`, `baseCount`, and `wordBooks`.
- `TileGameData.queryWord()` uses each book `count` to index `words`.
- `TileGameData.queryImage()` expects image words to contain at least `Class#Resource` and loads `Origin/<Class>/<Class>#<Resource>@2x` through `Resources.Load<Sprite>()`.

## Required Command

Run the checker before making claims:

```bash
python3 $CODEX_HOME/skills/wordtiles-level-scan/scripts/check_wordtiles_levels.py \
  --project-root <WORDTILES_REPO>
```

For a single language:

```bash
python3 $CODEX_HOME/skills/wordtiles-level-scan/scripts/check_wordtiles_levels.py \
  --project-root <WORDTILES_REPO> \
  --language en
```

For one level across all languages:

```bash
python3 $CODEX_HOME/skills/wordtiles-level-scan/scripts/check_wordtiles_levels.py \
  --project-root <WORDTILES_REPO> \
  --level 101
```

JSON output for machine comparison:

```bash
python3 $CODEX_HOME/skills/wordtiles-level-scan/scripts/check_wordtiles_levels.py \
  --project-root <WORDTILES_REPO> \
  --json
```

Filter one issue type:

```bash
python3 $CODEX_HOME/skills/wordtiles-level-scan/scripts/check_wordtiles_levels.py \
  --project-root <WORDTILES_REPO> \
  --code runtime_file_mismatch
```

## What The Checker Verifies

Treat these as failures unless runtime evidence proves otherwise:

- malformed JSON or a level file whose root is not an array
- duplicate level IDs inside the same language
- gaps in level coverage within a language
- level objects missing `level`, `baseCount`, `wordBooks`, or `books`
- `baseCount` that cannot be converted to an integer or is less than 1
- `wordBooks` entries that are missing, duplicated, or not present in `books`
- duplicate `books[].id`
- book `count` that exceeds `words.length`, because `queryWord()` can index past the array
- image books whose words cannot satisfy `queryImage()` path parsing
- image paths that do not resolve to a local sprite under `Assets/Main/Resources/Origin`
- file placement that does not match the current `GameLevel.GetNoramlLevelText()` runtime path
- cross-language differences in level set, `baseCount`, `wordBooks`, book IDs, book `count`, book `image`, or `words.length`

Treat these as warnings by default:

- book records present in `books` but not referenced by `wordBooks`
- book `count` differs from `words.length` when enough words still exist
- duplicate displayed words inside one book
- `baseCount` greater than the number of `wordBooks`

This checker is structural and resource-focused. It does not prove full playthrough solvability or UI layout fit; those require runtime verification.

## Reporting Format

For important findings, include:

- item
- status
- file path
- function/class/config key
- short reasoning
- suggested validation

Use exact local paths and cite the code anchor that makes the issue risky. If a result depends only on static analysis, say that runtime verification is still required.

## Code Anchors

Refresh these files before explaining failures:

- `<WORDTILES_REPO>/WordTiles/Assets/Game/Script/GameLevel.cs`
- `<WORDTILES_REPO>/WordTiles/Assets/Game/Script/TileGameData.cs`
- `<WORDTILES_REPO>/WordTiles/Assets/Main/Base/UIExtension.cs`

## Output Guidance

Lead with pass/fail status and the highest-risk blockers. Group findings by:

- runtime load path
- JSON/schema
- level coverage
- word book structure
- image resource mapping
- multilingual consistency
- runtime-only risks

Do not mark a level pack safe if the checker reports failures. If the user asks whether a specific level is affected, rerun with `--level N` and report that exact level rather than relying on a range summary.
