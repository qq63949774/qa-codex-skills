# PairPop 崩溃测试配方

当用户问“怎么测试崩溃路径”时，优先按这些配方输出中文用例。每条用例都要结合当前代码证据调整；未实际执行前，状态写“需要运行时验证”。

## 通用执行环境

环境：

- Unity Editor Play Mode 或开发包。
- 如果可配置，打开完整异常堆栈。
- 观察 Unity Console、Android logcat 或 Xcode console。
- 记录本次测试属于新安装、老用户还是升级场景。

重置：

- 优先产品内路径：打开 GM 面板并使用清档。`GMNode.onBtnClearUser` 会调用 `PlayerPrefs.DeleteAll`、清 persistent data path，并在 Editor 中停止 Play Mode。
- 开发路径：删除 PlayerPrefs 键 `GameData`、`GameSetting`、`GameSettingMd5` 后重启。
- 项目标识来自 `ProjectSettings.asset`：company 为 `DefaultCompany`，product 为 `PairPop`。

写入 PlayerPrefs：

- 产品/QA 友好路径：优先使用已有 GM 控件，尤其是清档、普通关卡输入、挑战关卡输入、广告跳过、关卡跳转开关。
- Unity Editor 路径：临时加 Editor 菜单或 debug hook，在 Play Mode 前调用 `PlayerPrefs.SetString("GameData", "...")`、`PlayerPrefs.SetString("GameSetting", "...")`、`PlayerPrefs.Save()`。这个 helper 不要提交。
- 真机路径：只在测试设备上使用带临时 debug UI 的开发包，或平台特定 preference 写入方式。如果没有安全写入路径，记录为“造数受阻”，不要猜测运行结果。
- 测 `GameData` 老用户字段时，要保留有效且较新的 `updateTime`，因为 `DataSave.setGameData` 只有在保存的 `updateTime` 大于当前内存值时才替换 `GameInfo`。

需要记录的证据：

- 完整异常类型和堆栈。
- 当前 `currentRoundIndex`、`LoopStart`、`homeLevel`、model、challenge key，以及是否使用云端关卡/配置。
- 能证明操作路径的截图或视频。

## CRASH-DATA-001：本地 GameData 损坏后冷启动

目的： verify corrupted save data does not crash startup.

环境/数据准备：

- 使用开发包或 Unity Editor。
- 将 PlayerPrefs 键 `GameData` 写成非法 JSON，例如 `{bad-json`。
- 保持 `GameSetting` 为空或有效，避免混入配置解析问题。

操作步骤：

1. 冷启动 App。
2. 等待 Loading 流程结束。
3. 观察是否能进入首页或游戏界面。

预期结果：

- 期望 App 忽略或修复损坏本地存档。
- 失败信号：Loading/首页渲染前出现 `JsonReaderException` 或类似异常。

代码证据：

- `PairPop/Assets/Main/Script/DataSave.cs:174-186`
- `DataSave.load` reads `GameData`; `setGameData` directly calls `JsonConvert.DeserializeObject<InfoDef>(json)` without local try/catch.

清理：

- 使用 GM 清档，或删除 `GameData`。

## CRASH-CONFIG-001：已保存后台 GameSetting 非法 JSON 冷启动

目的： verify saved backend config cannot crash startup.

环境/数据准备：

- 将 PlayerPrefs 键 `GameSetting` 写成非法 JSON，例如 `{bad-json`。
- 可选：将 `GameSettingMd5` 写成任意非空值。

操作步骤：

1. 冷启动 App。
2. 观察 `DataSave.Awake` 阶段控制台日志。
3. 继续进入首页或第一局游戏。

预期结果：

- 期望只打印错误，并继续使用默认配置。
- 失败信号：未捕获 JSON 异常或启动流程中断。

代码证据：

- `PairPop/Assets/Main/Script/DataSave.cs:281-291`
- `DataSave.SetGameSetting` catches exceptions around `JObject.Parse` and `GameConfig.SetGameSetting`.

清理：

- 删除 `GameSetting` 和 `GameSettingMd5`。

## CRASH-CONFIG-002：后台配置缺少 ADSetting/BannerAD/GameSetting

目的： verify partial backend config uses defaults instead of crashing.

环境/数据准备：

- 将 `GameSetting` 写成合法但缺少一个或多个 key 的 JSON，例如 `{}` 或 `{"GameSetting":"{}"}`。

操作步骤：

1. 冷启动 App。
2. 进入普通关卡，并完成或重开一次。
3. 尽量触发插屏路径：开始、重开、退出或胜利。

预期结果：

- 期望使用默认值且不崩溃。
- 失败信号：NullReference、KeyNotFound 或配置解析错误。

代码证据：

- `PairPop/Assets/Main/Script/ADConfig.cs:14-24` guards `ContainsKey`.
- `PairPop/Assets/Main/Script/GameSetting.cs:16-21` guards `ContainsKey`.

清理：

- 删除 `GameSetting` 和 `GameSettingMd5`。

## CRASH-LEVEL-001：本地或云端关卡 JSON 异常

目的： verify level parser handles bad level payloads.

环境/数据准备：

- Local path: temporarily duplicate one `PuzzleData/puzzleData*.json`, then corrupt one required field in a controlled branch; do not commit.
- Cloud path: use the configured level download/update path if available and provide malformed level payload.
- Bad fields to try: missing `gridSize`, malformed `gridSize` such as `3`, missing `data`, non-numeric `difficulty`, missing `move` for model 3, missing `time` for model 0/1/2.

操作步骤：

1. 冷启动 App，确保 `PuzzleDataManager.initPuzzleData` 执行。
2. 进入被异常 payload 覆盖的关卡。
3. 观察首个棋盘渲染前是否报错。

预期结果：

- App should reject bad level data and fall back or show a non-crashing error.
- Failure signal: NullReferenceException, FormatException, or IndexOutOfRangeException during parse.

代码证据：

- `PairPop/Assets/Script/Data/PuzzleDataManager.cs:78-85`
- `PairPop/Assets/Script/Data/PuzzleDataManager.cs:164-198`
- `ParseToPuzzleList` assumes required keys and numeric formats.

清理：

- Restore original JSON or clear cloud update config.

## CRASH-OLD-LEVEL-001：老用户关卡数超过本地关卡且 LoopStart 异常

目的： verify old/returning users cannot crash after level-count or backend-loop changes.

环境/数据准备：

- Set `GameData.currentRoundIndex` greater than local `PuzzleData` count.
- Set backend `GameSetting.GameSetting.LoopStart` at or after local level count.
- If direct PlayerPrefs edit is not practical, use GM level input to jump beyond final level and backend/config tool to override LoopStart.

操作步骤：

1. 冷启动 App。
2. Enter normal game.
3. Observe whether first board renders.

预期结果：

- App should clamp or fall back to a valid level.
- Failure signal: DivideByZeroException, modulo failure, or invalid index in `getLevelData`.

代码证据：

- `PairPop/Assets/Script/Data/PuzzleDataManager.cs:274-297`
- Loop math uses `loopLength = allLevelDataArrayList.Count - loopStartIndex - 1` and modulo when `currentRoundIndex` exceeds local count.
- `GameSetting.ServerSetting.LoopStart` default is at `PairPop/Assets/Main/Script/GameSetting.cs:166`.

清理：

- Clear user or reset `GameData.currentRoundIndex` and `GameSetting`.

## CRASH-CHALLENGE-001：GM 强制不存在的挑战关卡

目的： verify challenge mode handles forced missing challenge level key.

环境/数据准备：

- Use GM challenge level input to set a level index that has no matching `ChallengeData` key.
- Start daily challenge. `GMChallengeIndex > 0` forces key data use.

操作步骤：

1. Open app with GM/development access.
2. Set challenge level index to a very high value.
3. Enter daily challenge.
4. Observe before challenge board renders.

预期结果：

- App should fall back or show a non-crashing error.
- Failure signal: NullReferenceException when `GameCtr.startGame` dereferences `puzzleData.model`.

代码证据：

- `PairPop/Assets/Script/Data/PuzzleDataManager.cs:300-336`
- `forceUseKeyData` returns null when missing.
- `PairPop/Assets/Script/GameCtr.cs:847-864` uses `puzzleData.model` after challenge lookup.

清理：

- Reset `DataSave.GMChallengeIndex` or clear user.

## CRASH-MODEL-001：model=1/3 的 bubble 数据结构异常

目的： verify bubble/text-bubble levels do not crash on malformed nested `data`.

环境/数据准备：

- Use a controlled level payload where model is 1 or 3 and `data` contains an empty item, invalid card object, or missing `className`.

操作步骤：

1. Enter the target model 1/3 level.
2. Wait through board dealing.
3. Use hint/find if board renders.

预期结果：

- App should skip invalid cards or show a controlled failure.
- Failure signal: JSON parse, NullReference, or missing component during `GameBubbleCtr.LoadBubble`.

代码证据：

- `PairPop/Assets/Script/GameCtr.cs:977-1002`
- `PairPop/Assets/Script/GameBubbleCtr.cs:1323-1369`

清理：

- Restore level data.

## CRASH-MODEL-002：model=2 table 子节点/资源依赖异常

目的： verify table mode prefab/resources are complete.

环境/数据准备：

- Enter a known model 2 table level.
- If investigating a suspected asset regression, use a branch/build where `Texture/Table/accept` or `accept1` might be missing.

操作步骤：

1. Enter model 2 level.
2. Perform a table match/action that updates accept state.
3. Observe table cell visual update.

预期结果：

- App should not crash if resource is missing; UI may show fallback.
- Failure signal: NullReference from missing child `accept` or Image component.

代码证据：

- `PairPop/Assets/Script/GameCtr.cs:1021-1024`
- `PairPop/Assets/Script/GameTableCtr.cs` table accept update paths flagged by scanner.

清理：

- Restore table prefab/resources.

## CRASH-CALLBACK-001：重开/退出后的延迟回调

目的： verify delayed tweens/coroutines do not touch destroyed objects.

环境/数据准备：

- Use any level with long deal animation or visible delayed guide/hint animation.

操作步骤：

1. Start level.
2. Immediately open settings and restart or quit during board deal/guide animation.
3. Repeat for model 1 bubble, model 2 table, and model 3 text bubble.
4. Watch logs for 3-5 seconds after transition.

预期结果：

- No exception after old page/game object is closed.
- Failure signal: MissingReferenceException or NullReferenceException inside delayed callback.

代码证据：

- `PairPop/Assets/Script/GameCtr.cs:977-1061`
- `BasePanel.close` stops panel coroutines and destroys page objects, but DOTween delayed callbacks may still run unless explicitly killed.

清理：

- Relaunch if state is stuck.

## CRASH-AD-001：页面状态变化后的激励广告回调

目的： verify reward callbacks do not mutate closed pages or stale game state.

环境/数据准备：

- Development build with ad skip or controllable ad result.
- Ensure reward ad buttons are available: revive, get tool, double reward, ad bubble.

操作步骤：

1. Open a page with reward ad button.
2. Tap reward ad.
3. While ad is pending or immediately after callback, close/restart/transition if possible.
4. Repeat success and failure callback paths.

预期结果：

- Reward is applied once or safely ignored; no crash.
- Failure signal: NullReference/MissingReference in callback touching `Scene.Instance.gameCtr`, page components, or `DataSave.Instance`.

代码证据：

- `PairPop/Assets/Main/Script/ADConfig.cs:97-109`
- Reward callbacks call supplied page/game logic after SDK result.

清理：

- Clear user or reset tools/coins if rewards were applied.
