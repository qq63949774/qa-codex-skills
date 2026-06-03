# Sotaten Level Rules

This reference captures the project-specific legality rules observed in the current Sotaten Unity codebase.

## Generated Ten Levels

- Loader path: `GamePanel.startGame()` creates `GeneratedLevelLoader`, converts the generated level with `GeneratedLevelLayoutData.TryCreate`, then starts `WordSotaGame`.
- Config provider: `LocalLevelConfigProvider` handles level 1 as a fixed tutorial, levels 2-30 from `GameConfig.startLevelConfig`, and level 31+ from cycle config.
- Cycle constants: `CycleConfigStartLevel = 31`, `CycleTemplateStartNumber = 9`, `CycleTemplateLoopStartNumber = 1`, and Easy cycle templates must have fewer than 20 covered cards.
- Default `tenConfig.cycleLevelDiff` is `[3, 4, 2, 0, 1]`, mapping to `SubExtraHard`, `Random`, `ExtraHard`, `Easy`, `Hard`.
- `startLevelConfig` difficulty strings accepted by code are `Hard`, `Extra_Hard`, `Extra Hard`, `ExtraHard`, `Sub_Extra_Hard`, `Sub Extra Hard`, `SubExtraHard`, and `Random`; anything else silently becomes Easy.
- `startLevelConfig.group` only distinguishes `[1, 9]` from every other value. `[1, 9]` means ranks 1-9; all other shapes become ranks 0-10.
- `extra` accepts only `Wild_Card`, `J`, `K`, and `Q`; unknown extras are ignored.
- Deck sizes are rank range times four suits plus non-duplicate extras. A layout requiring more cards than the deck is a runtime blocker.

## Board Templates

- Template resource path is `GeneratedBoardLayoutPresets`.
- Template ids must be contiguous from `t = 0`.
- Each card row must have at least six values: x, y, width, height, rotation, zIndex.
- Runtime sorts cards by zIndex, assigns slot ids from sorted order, and computes blockers from rotated AABB overlap.
- A higher-z card blocks a lower-z card when overlap ratio is greater than `0.08`.
- Duplicate zIndex values are risky because cards with equal zIndex do not block each other in the runtime blocker calculation.

## Match And Solver Rules

- Numbers match when ranks sum to 10; same-suit number matches are `Perfect`.
- J/Q/K match only same rank with another flower card.
- Wild cards match any non-wild target, but runtime restricts wild moves to a board target.
- Stock draw count is 3 and waste has 3 visible lanes.
- Guaranteed difficulties run up to 60 generation attempts. If no solvable deal is found, runtime falls back to a Random deal; report this as high risk, not as a guaranteed pass.

## Legacy Raw Levels

- `ResourcesLevelResourceProvider` reads `Resources/LevelData/<language>/<fileName>`.
- `SpecialLevelResourceProvider` reads `Resources/SpecialLevelData/<language>/<fileName>`.
- `LevelCatalog` sorts chunk files numerically, assumes ten slots per file, skips missing item indexes, and falls back to `en` when the requested language is unavailable.
- Raw stage schema includes `steps`, `column`, `stock`, `key`, and optional `className`.
- `LevelLegacyAdapter` maps text tokens as `title:content`; image tokens require a `className` mapping and image content shaped as `Class#Resource` or `prefix#Class#Resource`, then board tokens become `title:Class#Resource`.

## Evidence Standard

Report static script findings as evidence. For behavior depending on remote settings, downloaded level files, Unity serialization, first-open state, or ad/reward state, say `requires runtime verification` unless those artifacts are provided locally.
