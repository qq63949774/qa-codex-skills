---
name: mixword-version-config-diff
description: 保存 Mixword 或 gpMixWord 某个版本的关卡配置基线，并在后续版本间做配置比对。适用于“保存当前版本关卡文件”“给 1.0.6 建基线”“比对两个版本的 LevelData/SpecialLevelData/common 配置差异”“输出新增/删除/修改的关卡 json 清单”这类请求。只处理配置快照和差异报告，不修改项目代码。
---

# Mixword Version Config Diff

## 概述

这个 skill 用来做两件事：

1. 把当前项目中的关卡配置保存成某个版本号的基线
2. 把当前项目配置和某个已保存版本做 diff，输出新增、删除、修改文件清单

优先直接运行脚本，不要在对话里手工拼目录或手工逐个比文件。

## 工作流

1. 确认项目根目录。当前工作区里如果是 Mixword/gpMixWord 项目，默认用当前项目。
2. 只处理以下 4 组配置：
   `Assets/Game/Levels/Resources/LevelData`
   `Assets/Game/Levels/Resources/SpecialLevelData`
   `common/normal`
   `common/bonus`
3. 默认只保存和比对 `.json` 文件，忽略 `.meta`、`.DS_Store` 等非配置文件。
4. 如果用户要“保存当前版本为基线”，运行 `save-baseline`。
5. 如果用户要“比对当前版本和某个历史版本”，运行 `diff`。
6. 输出时按配置组分别汇总 changed / added / removed，并给出总数。

## 常用命令

把当前项目保存成 `1.0.6` 基线：

```bash
python3 ~/.codex/skills/mixword-version-config-diff/scripts/version_config_diff.py \
  save-baseline \
  --project-root /absolute/project/root \
  --version 1.0.6
```

指定基线目录：

```bash
python3 ~/.codex/skills/mixword-version-config-diff/scripts/version_config_diff.py \
  save-baseline \
  --project-root /absolute/project/root \
  --version 1.0.6 \
  --baseline-root /absolute/baseline/root
```

把当前项目和 `1.0.6` 做配置比对：

```bash
python3 ~/.codex/skills/mixword-version-config-diff/scripts/version_config_diff.py \
  diff \
  --project-root /absolute/project/root \
  --version 1.0.6
```

输出 JSON 报告到文件：

```bash
python3 ~/.codex/skills/mixword-version-config-diff/scripts/version_config_diff.py \
  diff \
  --project-root /absolute/project/root \
  --version 1.0.6 \
  --report-json /tmp/mixword_1.0.6_diff.json
```

## 输出要求

结果里要明确给出：

- 使用的 baseline version 和 baseline 路径
- 当前项目路径
- 4 个配置组各自的 added / removed / changed 数量
- 如有变更，列出相对路径
- 如用户只问“是否有差异”，也要给出总数，不要只回答有或没有

## 边界

- 这个 skill 只负责配置快照和文件级 diff，不解释玩法影响，也不验证关卡合法性。
- 如果用户要验证关卡本身是否合法，改用 `$mixword-level-legality-check`。
- 如果仓库里缺少其中某组目录，按缺失目录处理，并在输出里说明。

## 资源

- `scripts/version_config_diff.py`：保存基线和执行 diff 的主脚本
- [references/paths.md](references/paths.md)：项目目录约定和保存范围说明
