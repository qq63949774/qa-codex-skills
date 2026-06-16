# PairPop Crash Audit Map

Use this reference first when auditing `<PAIRPOP_REPO>`.

## Project Shape

- Unity project root inside repo: `PairPop/`
- C# scripts: `PairPop/Assets/Script`, `PairPop/Assets/Main/Script`, `PairPop/Assets/Main/Base`
- Local levels: `PairPop/Assets/Resources/PuzzleData/puzzleData*.json`
- Challenge levels: `PairPop/Assets/Resources/ChallengeData/challengeData*.json`
- Runtime prefabs/resources: `PairPop/Assets/Resources/Prefab`, `PairPop/Assets/Resources/Texture`, `PairPop/Assets/Resources/Font`

## Startup Path

- `PairPop/Assets/Main/Script/Scene.cs`
  - `Awake`: initializes `Config`, `BasePanel`, frame settings.
  - `Start`: runs `GameConfig.loadAllData`, opens loading page, instantiates home or `gamePre`, calls `gameCtr.startGame`, initializes ads, reads puzzle language.
- `PairPop/Assets/Main/Script/DataSave.cs`
  - `Awake`: loads local `GameData`, sets `Instance`, applies saved backend `GameSetting` if present.
  - `LoadFromServer`: merges server storage, calls `Language.ApplyCurrentLanguage`, invokes registered callbacks.

Crash leads:

- Corrupted `GameData` can throw in `DataSave.setGameData` because `JsonConvert.DeserializeObject<InfoDef>` is not guarded.
- Missing `DataSave.Instance` or `Scene.Instance` during delayed callbacks can crash if object lifecycle differs from expected scene order.
- Missing `puzzleLanguage` resource is logged and skipped, but downstream localized display may fall back to class/display names.

## Level Parse And Selection

- `PairPop/Assets/Script/Data/PuzzleDataManager.cs`
  - `initPuzzleData`: loads all `Resources/PuzzleData` and `ChallengeData`, deserializes each TextAsset into JObject, then calls `ParseToPuzzleList`.
  - `ParseToPuzzleList`: assumes level entries have `gridSize`, `data`, `difficulty`, `theme`, and either `move` for model 3 or `time` otherwise. It uses `int.Parse`, `gridSize.Split('x')`, and `ToString()` without full guards.
  - `getLevelData`: maps `currentRoundIndex` to local/cloud level and uses `GameSetting.settingData.LoopStart` for looping beyond local level count.
  - `getChallengeLevelData`: returns null if forced challenge key is missing; otherwise tries random challenge fallback.
  - `BuildCurrentPuzzleData`: builds `allClassNames` by recursing `levelData` and following className chains.

Crash leads:

- Malformed local/cloud level JSON can throw during parse before game starts.
- Missing required level fields can cause null dereference or parse errors.
- `LoopStart` values near or beyond local level count can produce invalid loop math for old users past the last local level.
- Challenge key fallback can return null; `GameCtr.startGame` dereferences `puzzleData.model` shortly after selection.

## Game Start And Model Branches

- `PairPop/Assets/Script/GameCtr.cs`
  - `startGame`: gets puzzle data, clears UI, switches by `puzzleData.model`, sets timers/moves, updates headers, then calls `dealCardBubbleAction`.
  - `dealCardBubbleAction`: delayed branch for model 0 column, model 1 bubble, model 2 table, model 3 text bubble.
  - Uses many public inspector fields: `blockView`, `normalClock`, `freezeClock`, `GameBubbleArea`, `toolBar`, `guideBg`, `GameTableCtr.Instance`, `GameBubbleCtr.Instance`.

Crash leads:

- If `puzzleData` is null, `startGame` dereferences `puzzleData.model`.
- Delayed `dealCardBubbleAction` can run after page/object state changes; verify target GameObjects still exist.
- `toolBar.transform.Find("base").gameObject`, `currentHeaderBae.transform.Find(...)`, guide child lookups require prefab child names.
- Model 2 depends on `GameTableCtr.Instance.LoadTableCell(puzzleData)`.
- Model 1/3 depend on nested level `data` shape and `CardJsonData` parse.

## Bubble And Text Bubble

- `PairPop/Assets/Script/GameBubbleCtr.cs`
  - Singleton `Instance`, public prefab references, many `GetComponent` and `transform.Find` calls.
  - `LoadBubble`: assumes `addStepLabel` and its `CanvasGroup` exist, then instantiates current bubble prefab for every card.
  - `GetBubblePrefabForCurrentMode`: uses `Scene.Instance.gameCtr.puzzleData.model`.
  - `BuildNextBubbleDataList`: reads `puzzleData.levelData[classType]`, parses next bubble data.
  - `showTips` path uses `tipsBg`, `toolParticle`, `transform.Find("title")`, `transform.Find("01")`.
- `PairPop/Assets/Script/TextBubble.cs`
  - Handles model 3 visual/content sizing and many delayed particle/completion effects.

Crash leads:

- Missing inspector references or child nodes produce NullReference on load or tool use.
- Bad text bubble data can produce invalid size/material/image lookup; resource misses may be non-crashing if helper handles null, but follow direct dereferences.
- Delayed merge/tween callbacks should be verified after restart, quit, page close, or rapid level transition.

## Ads, IAP, Network, Config

- `PairPop/Assets/Main/Script/ADConfig.cs`
  - `SetGameSetting`: parses `ADSetting` and `BannerAD`.
  - Reward/interstitial wrappers invoke callbacks from SDK paths.
  - `getNoAdsExtraConfig` and `getCoinProductConfig` read dictionaries on `GameSetting.settingData`.
- `PairPop/Assets/Main/Script/GameSetting.cs`
  - `SetGameSetting`: deserializes server config and custom converters for reward configs.
- `PairPop/Assets/Main/Script/DataSave.cs`
  - `Client.GetGameSetting`, `SetGameSetting`, server storage merge.

Crash leads:

- Backend config missing required keys can throw unless guarded.
- Ad reward callbacks may touch closed pages or destroyed game state.
- Purchase callbacks may assume `DataSave.Instance`, product config keys, and page prefab references.

## High-Value Repro Axes

- First-open fresh install with no local `GameData`.
- Old user upgrade with `currentRoundIndex` beyond local level count.
- Reinstall or weak network where server storage arrives after initial game/home render.
- Backend config variations: missing `ServerSetting`, malformed `LoopStart`, empty arrays, missing dictionaries.
- Cloud level replacement: empty payload, bad JSON, array root, missing required keys, model mismatch.
- Challenge entry by date with missing challenge key and `GMChallengeIndex`.
- Model-specific levels: model 0 normal, model 1 bubble, model 2 table, model 3 text bubble.
- Rapid flows: restart, quit, win, lose, watch ad, close page while delayed animations/tweens/coroutines are pending.
