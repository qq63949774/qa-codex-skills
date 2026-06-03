# Paths

默认按以下路径查找 Mixword/gpMixWord 配置：

- `mixword/mixword/Assets/Game/Levels/Resources/LevelData`
- `mixword/mixword/Assets/Game/Levels/Resources/SpecialLevelData`
- `common/normal`
- `common/bonus`

其中前两组是项目内关卡资源，后两组是版本公共配置。

脚本行为：

- 只收集 `.json` 文件
- 保存基线时把 4 组配置分别复制到：
  - `LevelData/`
  - `SpecialLevelData/`
  - `common_normal/`
  - `common_bonus/`
- 同时生成 `manifest.json`
- 默认基线目录为 `~/.qa-codex-skill-data/config-baselines/<project-name>/<version>`

如果项目目录结构以后变化，优先改脚本中的 `DATASET_SPECS`，不要在对话里临时拼路径。
