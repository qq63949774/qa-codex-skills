---
name: qa-code-evidence-scan
description: Scan project code for testcase evidence and merge AI judgment columns back into the testcase CSV with confidence filtering.
---

# QA Code Evidence Scan

## Overview

This skill only handles code-evidence scanning. Testcase writing is out of scope.

## Preconditions

- Input testcase CSV already exists (typically produced by `qa-requirement-testcase-writer`).
- User provides project path, or the caller is `qa-requirement-testcase-writer` running its default post-generation scan.
- Scan runs when AI code evidence is requested explicitly or when invoked by the requirement testcase workflow.

## Workflow

1. Verify inputs
   - Confirm cases CSV path and project path.
   - Default scan root to business code (example: `Assets/Game`).
   - If the project root has no scannable business code/config files, or only contains generated testcase/report/output files, no case may be marked `通过`.

2. Run scan script
   - Use `scripts/ai_case_verifier.py` (stable entry).
   - Optional tuning:
     - `--min-hits` (default 2)
     - `--max-file-size`

3. Merge AI columns into testcase CSV
   - Maintain/add:
     - `AI测试结果`
     - `AI判定原因`
     - `AI测试用例通过率`
   - Remove obsolete detail columns from output:
     - `AI判定通过原因`
     - `AI证据文件`
     - `AI证据行号`
     - `AI证据关键词`
     - `AI置信度`
     - `AI置信等级`
   - Keep `测试结果` unchanged.

4. Confidence filter
   - `High`: traceable implementation evidence in business code/config, including file path, line number, and a concrete anchor such as `key=...`, `symbol=...`, `class=...`, or `function=...`.
   - `Medium`: traceable implementation evidence exists but still needs runtime validation.
   - `Low`: weak/generic keyword hits, third-party noise, generated files, or insufficient evidence.
   - `AI测试结果` must be explicit:
     - `通过`: Medium/High traceable business-code/config evidence found.
     - `不通过`: no sufficient evidence, evidence is Low confidence, or the finding is only semantic/keyword similarity.
   - Never mark `通过` only because requirement words overlap code words. A reason like `命中<path>:<keyword>/<keyword>` without line number and concrete anchor is not valid proof.
   - Evidence must not come from generated testcase CSVs, reports, `QAReports/`, `reports/`, `output/`, docs, package/vendor/plugin/third-party files, or skill scripts.

5. Report expectations
   - Provide AI pass count, AI pass rate, parameters, scan timestamp/timezone, and residual risks.

## Recommended command

```bash
python3 scripts/ai_case_verifier.py \
  --cases ./V1.0版本_测试用例_20260228.csv \
  --project /path/to/project \
  --min-hits 2
```

## Files to use

- `scripts/ai_case_verifier.py`
- `scripts/modules/code_scan.py`
- `references/scan-confidence.md`
