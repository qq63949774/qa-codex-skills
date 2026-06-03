---
name: multilang-scan-qa
description: Scan MixSota project multilingual JSON content for suspicious non-local language words and export a single CSV report. Use when the user asks to scan/check multi-language word lists, localization cleanliness, or suspected non-current language tokens in MixSota. 
---

# Multilang Scan QA

## Overview
Scan multilingual level JSONs in the current project for non-local script words (excluding image tokens with `#`) and export a single CSV report in Chinese.

## Workflow
1) Run the scan script from the project root (current directory). By default it scans `Mix多语言700关卡/`.
2) Review the generated CSV: `language_suspect_entries.csv` (fixed filename, written to current directory).

## How to run
- Default (current directory contains `Mix多语言700关卡/`):

```bash
python3 ~/.codex/skills/multilang-scan-qa/scripts/scan_multilang.py
```

- If the data folder name is different:

```bash
python3 ~/.codex/skills/multilang-scan-qa/scripts/scan_multilang.py --data-dir <folder>
```

## Rules enforced by the script
- `#` indicates an image token; those words are excluded from language checks.
- For `zh-Hans` / `zh-Hant`: words must contain at least one CJK character.
- For `ja`: words must contain Japanese scripts (Hiragana/Katakana/Kanji).
- For `ru`: words must contain Cyrillic.
- For other languages (`de/es/fr/it/pt/default`): words must NOT contain CJK, Japanese Kana, or Cyrillic.

## Output (CSV)
Fixed filename: `language_suspect_entries.csv`

Columns (Chinese):
- 语言
- 关卡文件
- entry索引
- 异常类型
- 异常词数量
- 总词数量
- 异常比例
- 异常示例

## Notes
- The scan checks `key.title` and `key.content` only.
- This is a heuristic for “non-current language words,” not a full translation quality audit.

## Resources
### scripts/
- `scan_multilang.py` (main scanner)
