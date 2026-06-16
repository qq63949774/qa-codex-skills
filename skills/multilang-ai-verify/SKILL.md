---
name: multilang-ai-verify
description: Scan Mixfun/MixSota multilingual level JSONs for suspect words (using wordfreq), then optionally verify suspect terms with MiniMax, DeepSeek, or another compatible chat-completions endpoint and output CSVs. Use when asked to run multilingual scans, check localization cleanliness, review suspect words, or produce AI-verified CSV reports from a folder that contains language subfolders.
---

# Multilang AI Verify

## Quick Start
This skill is self-contained. Its scripts live under `scripts/` inside the skill directory and can be used from any project.

### 1. Run the scan
Run from the multilingual data folder itself, or pass `--data-dir <folder>` from the project root.

If `./multilang_scan_rules.json` exists:

```bash
python3 $CODEX_HOME/skills/multilang-ai-verify/scripts/scan_multilang_project.py \
  --rules-file ./multilang_scan_rules.json \
  --data-dir .
```

If no rules file:

```bash
python3 $CODEX_HOME/skills/multilang-ai-verify/scripts/scan_multilang_project.py \
  --data-dir .
```

Outputs (written to the current working directory):
- `language_suspect_entries.csv`
- `language_structure_mismatch.csv` (only when structure checking is enabled)

### 2. Ask whether to run AI verification
Only run this step if the user wants AI filtering/refinement on top of the scan output.

Recommended: put provider settings in a config file in the current directory. The script will auto-detect:
- `ai_verify_config.json`
- `ai_verify_config.md`
- `.ai_verify_config.json`
- `.ai_verify_config.md`
- `multilang_ai_verify_config.json`
- `multilang_ai_verify_config.md`

Standard run:

```bash
python3 $CODEX_HOME/skills/multilang-ai-verify/scripts/deepseek_verify_suspects.py \
  --input ./language_suspect_entries.csv \
  --output ./language_suspect_entries_ai.csv \
  --batch-size 50
```

### 3. Optional: run AI directly on all entries
Use this when the user explicitly wants full AI scanning of every entry instead of "heuristic scan first, AI review second".

```bash
python3 $CODEX_HOME/skills/multilang-ai-verify/scripts/ai_scan_all_entries.py \
  --data-dir ./all_languages_batch_export_1773891385967 \
  --batch-size 10
```

Outputs:
- `language_ai_full_scan_issues.csv`: only entries judged as issues

If you also want every scanned entry, explicitly add:

```bash
--output-all ./language_ai_full_scan_results.csv
```

Check whether the config was loaded correctly before making requests:

```bash
python3 $CODEX_HOME/skills/multilang-ai-verify/scripts/deepseek_verify_suspects.py \
  --input ./language_suspect_entries.csv \
  --output ./language_suspect_entries_ai.csv \
  --check-config
```

MiniMax JSON config example:

```json
{
  "provider": "minimax",
  "api_key": "your-api-key",
  "base_url": "https://api.minimax.io/v1",
  "model": "MiniMax-M2.5",
  "temperature": 0.1
}
```

MiniMax Markdown config example:

```md
# AI Verify Config
provider: minimax
api_key: your-api-key
base_url: https://api.minimax.io/v1
model: MiniMax-M2.5
temperature: 0.1
```

MiniMax example:
```bash
export AI_VERIFY_PROVIDER="minimax"
export MINIMAX_API_KEY="..."
export MINIMAX_BASE_URL="https://api.minimax.io/v1"
export MINIMAX_MODEL="MiniMax-M2.5"

python3 $CODEX_HOME/skills/multilang-ai-verify/scripts/deepseek_verify_suspects.py \
  --provider minimax \
  --input ./language_suspect_entries.csv \
  --output ./language_suspect_entries_ai.csv \
  --batch-size 50
```

Optional:
- `--limit N`
- `--model <custom-model>`
- `--temperature 0.1`
- `--no-progress-bar`
- `--config ./ai_verify_config.json`

DeepSeek example:

```bash
export AI_VERIFY_PROVIDER="deepseek"
export DEEPSEEK_API_KEY="..."
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
export DEEPSEEK_MODEL="deepseek-chat"

python3 $CODEX_HOME/skills/multilang-ai-verify/scripts/deepseek_verify_suspects.py \
  --provider deepseek \
  --input ./language_suspect_entries.csv \
  --output ./language_suspect_entries_ai.csv \
  --batch-size 50
```

MiniMax base URL notes:
- 国际站常用：`https://api.minimax.io/v1`
- 国内站如账号在中国区，按控制台实际地址设置 `MINIMAX_BASE_URL`，常见形态是 `https://api.minimaxi.com/v1`

## Bundled Scripts
- `scripts/scan_multilang_project.py`
  - Main multilingual scanner.
  - Uses `wordfreq` automatically when it is installed.
  - Falls back to script-based heuristics if `wordfreq` is unavailable.
  - Supports optional rules from `multilang_scan_rules.json`.
- `scripts/deepseek_verify_suspects.py`
  - Reads `language_suspect_entries.csv`.
  - Reads provider settings from current-directory JSON/Markdown config files or from environment variables.
  - Sends suspect rows to MiniMax, DeepSeek, or another兼容 `chat/completions` 的接口。
  - Keeps only rows judged as true issues and adds `AI原因`.
- `scripts/ai_scan_all_entries.py`
  - Runs AI directly on every entry in a multilingual data folder.
  - Outputs both all-results and issues-only CSVs.
- `scripts/extract_unique_tokens.py`
  - Extracts non-`#` tokens as unique `语言 + 单词` rows.
  - Useful for trying word-level dedupe before AI analysis.
- `scripts/ai_scan_unique_tokens.py`
  - Sends deduplicated `语言 + 单词` rows to AI.
  - Expands flagged words back to `关卡文件 + entry索引`.
- `examples/multilang_scan_rules.example.json`
  - Example rules file for structure check and ignore lists.
- `examples/ai_verify_config.example.json`
  - Example JSON config for AI verification.
- `examples/ai_verify_config.example.md`
  - Example Markdown config for AI verification.

## Rules File
`multilang_scan_rules.json` is optional. Supported keys:
- `check_structure`: `true` / `false`
- `base_lang`: baseline language folder for structure comparison, default `de`
- `ignore_words`: exact words to ignore globally
- `ignore_regexes`: regex patterns to ignore globally
- `per_language_ignore_words`: map of language to exact words to ignore
- `per_language_ignore_regexes`: map of language to regex patterns to ignore

## Notes
- The scanner checks `key.title` and `key.content`.
- `#` inside a token means image content and is excluded from checks.
- The AI script supports `MiniMax` and `DeepSeek`.
- Provider selection order: `--provider` > config file > `AI_VERIFY_PROVIDER` > default `deepseek`.
- Config file selection order: `--config` > `AI_VERIFY_CONFIG` > auto-detected file in current directory.
- For MiniMax, configure `MINIMAX_API_KEY`, and optionally `MINIMAX_BASE_URL` / `MINIMAX_MODEL`.
- For DeepSeek, configure `DEEPSEEK_API_KEY`, and optionally `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`.
- The AI script adds `AI原因` and removes rows marked OK by the model.
