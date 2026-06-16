---
name: pairpop-crash-path-audit
description: 为 PairPop Unity 项目排查潜在崩溃路径，并输出中文 QA 崩溃测试用例，包含环境/数据准备、操作步骤、预期结果/失败信号、日志关键词、清理方式和代码/配置证据。Use when the user asks to排查崩溃路径, 崩溃用例, 中文用例, find possible crashes, inspect NullReference/IndexOutOfRange/JSON/config/resource/runtime callback risks, generate crash repro steps, or review PairPop release crash risk from code/config evidence.
---

# PairPop Crash Path Audit

## 目标

排查 PairPop 中可能导致崩溃的路径，并转成中文 QA 可执行测试用例。默认交付物是“怎么测”，不是原始风险列表。静态代码信号只能作为线索，不能当作已复现崩溃；未执行的用例标记为“需要运行时验证”。

## 必须输出

必须先输出中文测试矩阵。每条重要崩溃路径包含：

- 用例 ID
- 风险点
- 状态：`候选风险`、`运行时已确认`、`无法确认`、`需要运行时验证`
- 优先级
- 环境/数据准备
- 操作步骤
- 预期结果/失败信号
- 日志关键词
- 代码证据
- 函数/类/配置键
- 代码推理
- 清理/重置

优先写具体用户路径，不要只写异常类型。例如“老用户 currentRoundIndex 超过本地关卡数后冷启动”比“取模为 0 风险”更有测试价值。

## 快速流程

1. 确认范围：PairPop 项目根目录通常是 `<PAIRPOP_REPO>`，Unity 工程在内层 `PairPop/Assets`。
2. 先读 `references/test-recipes.md`，用里面的配方生成中文可执行用例。
3. 再读 `references/pairpop-map.md`，确认当前项目入口和高风险模块。
4. 生成第一版中文崩溃测试清单：

```bash
python3 $CODEX_HOME/skills/pairpop-crash-path-audit/scripts/scan_crash_risks.py <PAIRPOP_REPO> --testcases --top 12
```

5. 如果需要更深的代码线索，再跑原始扫描：

```bash
python3 $CODEX_HOME/skills/pairpop-crash-path-audit/scripts/scan_crash_risks.py <PAIRPOP_REPO> --top 80
```

6. 最终输出前，打开引用文件和上下文，确认用例的触发链。
7. 每条用例必须连接到玩家路径：
   - 首次打开 / 老用户升级 / 重装后服务端存档覆盖
   - 普通关 / 挑战 / 首页入口
   - model 0 column / model 1 bubble / model 2 table / model 3 text bubble
   - 激励广告 / 插屏回调 / IAP 回调
   - 计时器、步数、延迟 tween、协程、队列回调
   - 云端关卡/配置下载、异常 JSON、资源缺失、弱网
8. 按崩溃可能性和发布覆盖面定优先级。没有代码/配置证据时，不要声称已实现或已修复。

## 测试准备说明

PairPop 关键测试数据使用 PlayerPrefs：

- `GameData`：序列化后的 `DataSave.InfoDef`，包含 `currentRoundIndex`。
- `GameSetting`：后台配置 JSON，由 `DataSave.Client.GetGameSetting` 读取。
- `GameSettingMd5`：已保存后台配置对应的 MD5 字符串。

GM 面板中已有辅助能力：

- 清档：`GMNode.onBtnClearUser`。
- 设置普通关卡：`GMNode.setLevelIndex`。
- 设置挑战关卡：`GMNode.setChallengeLevelIndex`。
- 开关广告跳过：`GMNode.onBtnJumpAllAD`。
- 开关关卡跳转：`GMNode.onBtnShowGameJump`。

当用例依赖写 PlayerPrefs 或后台配置时，优先给产品内路径；没有产品内路径时给开发包/Editor 路径；两者都无法确认时，标记为“需要运行时验证”。

## 证据规则

- 尽量引用精确文件路径、函数/类和行号。
- 写清空引用、数组越界、解析失败、资源缺失等依赖，以及能到达该代码的调用链。
- 如果路径依赖 Unity Inspector 绑定、prefab 内容、后台 payload、广告 SDK 或设备状态，必须写“需要运行时验证”。
- 如果代码已有保护，必须说明保护点，并降低风险置信度，除非后续仍有绕过保护的直接访问。
- 永远不要上传项目代码。

## 中文用例模板

输出时使用这个结构：

```text
用例 ID: CRASH-OLD-LEVEL-001
风险点: 老用户 currentRoundIndex 超过本地关卡总数，且 LoopStart 异常时可能崩溃。
状态: 候选风险；需要运行时验证
优先级: P1
环境/数据准备:
- 使用 Unity Editor 或开发包。
- 将 PlayerPrefs 的 GameData.currentRoundIndex 设置为大于本地 PuzzleData 总数的值。
- 将已保存的 GameSetting 中 ServerSetting.LoopStart 设置为等于或大于本地关卡总数。
操作步骤:
1. 冷启动 App。
2. 从首页或启动流程进入普通关卡。
3. 观察首个棋盘是否能正常渲染。
预期结果/失败信号: 期望不崩溃并回退到有效关卡；失败信号是棋盘渲染前出现 DivideByZeroException 或 ArgumentOutOfRangeException。
日志关键词: PuzzleDataManager, getLevelData, LoopStart, DivideByZeroException, ArgumentOutOfRangeException
代码证据: PairPop/Assets/Script/Data/PuzzleDataManager.cs:274
函数/类/配置键: PuzzleDataManager.getLevelData / GameSetting.settingData.LoopStart
代码推理: currentRoundIndex 超过本地关卡数时，会计算 loopLength = allLevelDataArrayList.Count - loopStartIndex - 1；异常 LoopStart 可能导致取模或索引非法。
清理/重置: 使用 GM 清档，或删除/重置 PlayerPrefs 的 GameData、GameSetting、GameSettingMd5 后重启。
```

## 支持资源

- `references/test-recipes.md`：中文 PairPop 崩溃测试配方和造数据方式。
- `references/pairpop-map.md`：当前 PairPop 代码地图和优先检查入口。
- `scripts/scan_crash_risks.py`：加 `--testcases` 输出中文崩溃测试用例；不加时输出原始代码线索。
