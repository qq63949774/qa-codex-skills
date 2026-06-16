---
name: mixword-level-legality-check
description: 检查 Mixword 或 gpMixWord 的关卡文件合法性，适用于 `Assets/Game/Levels/Resources/LevelData` 和 `SpecialLevelData`。当用户要求“检查关卡文件”“扫描关卡是否合法”“检查 level json”“检查奖励关资源”“检查关卡 token/className 映射”“检查重复牌/缺牌”“验证运行时初始局面是否合法”时使用。Validate Mixword level resources, token/className mapping, duplicate or missing cards, build-cover behavior, and runtime legality for the initial base/work/deck/cover state.
---

# Mixword Level Legality Check

## 概述

用这个 skill 检查 Mixword 关卡是否合法，分两层：

1. 静态关卡文件合法性检查
2. 运行时合法性检查：把 raw stage 转成项目内部牌模型后，按真实规则校验初始局面

优先直接运行脚本，不要在对话里手工重写整套规则。

## 工作流

1. 确认项目根目录。当前工作区里如果有 `Assets/Game/Levels/Resources`，默认就用当前项目。
2. 选择数据集：
   `normal` 对应 `LevelData`
   `special` 对应 `SpecialLevelData`
3. 选择范围：
   `--level N`：按游戏关卡号检查
   `--file X.json --item-index I`：按资源文件里的槽位检查
   `--all`：批量扫描
4. 选择模式：
   `static`：只做静态文件检查
   `runtime`：只做运行时合法性检查
   `all`：两层都跑
   `--all-languages-layout`：按关卡号检查所有语言的布局是否一致
5. 运行脚本：

```bash
python3 $CODEX_HOME/skills/mixword-level-legality-check/scripts/check_levels.py \
  --project-root /absolute/project/root \
  --dataset normal \
  --language en \
  --level 1 \
  --mode all
```

6. 如果用户追问为什么失败，再读 [references/rules.md](references/rules.md)，按文件、槽位、token 和规则条件解释失败原因。

## 常用命令

按关卡号检查普通关：

```bash
python3 $CODEX_HOME/skills/mixword-level-legality-check/scripts/check_levels.py \
  --project-root /absolute/project/root \
  --dataset normal \
  --language en \
  --level 12 \
  --mode all
```

直接检查某个资源槽位：

```bash
python3 $CODEX_HOME/skills/mixword-level-legality-check/scripts/check_levels.py \
  --project-root /absolute/project/root \
  --dataset normal \
  --language en \
  --file 3.json \
  --item-index 2 \
  --mode all
```

批量扫描英文普通关：

```bash
python3 $CODEX_HOME/skills/mixword-level-legality-check/scripts/check_levels.py \
  --project-root /absolute/project/root \
  --dataset normal \
  --language en \
  --all \
  --fail-only \
  --mode all
```

批量扫描奖励关：

```bash
python3 $CODEX_HOME/skills/mixword-level-legality-check/scripts/check_levels.py \
  --project-root /absolute/project/root \
  --dataset special \
  --language en \
  --all \
  --fail-only \
  --mode all
```

检查首关所有语言布局是否一致：

```bash
python3 $CODEX_HOME/skills/mixword-level-legality-check/scripts/check_levels.py \
  --project-root /absolute/project/root \
  --dataset normal \
  --language en \
  --level 1 \
  --all-languages-layout
```

检查所有普通关的跨语言布局一致性：

```bash
python3 $CODEX_HOME/skills/mixword-level-legality-check/scripts/check_levels.py \
  --project-root /absolute/project/root \
  --dataset normal \
  --language en \
  --all \
  --all-languages-layout \
  --fail-only
```

## 输出要求

输出里要明确给出：

- dataset、language、file、slot，以及可用时的 mapped level
- `static` 和 `runtime` 两部分结果分别列出
- 当前关卡在所选模式下是否通过
- 是否存在“raw stock 缺牌，但运行时会自动补到 cover”的情况
- 如果使用 `--all-languages-layout`，要明确给出 baseline 语言，以及哪些语言布局不一致

以下情况按失败处理：

- 未知 token
- 图片 token 或 `className` 映射非法
- adapter 后出现重复牌
- build-cover 后仍然缺牌
- `base/work/deck/cover` 状态违反项目规则

以下情况默认按警告处理，除非用户明确要求严格模式：

- raw `stock` 没写全，但运行时会自动补到 `cover`
- 开局没有立刻可拖动的操作，但 `cover` 仍有牌，关卡仍可继续

## 边界

这个 skill 只检查合法性和规则一致性，不证明完整长步数可解性。只有用户明确要求时，才把脚本继续扩展成 solver。

## 资源

- [references/rules.md](references/rules.md)：仓库里的关卡加载、牌编码、cover 自动补齐、运行时移动规则摘要
- `scripts/check_levels.py`：可执行检测脚本，负责 `static` / `runtime` / `all`，并支持跨语言布局一致性检查
