---
name: qa-bug-driven-smoke-testcase
description: Use this whenever the user asks to generate compact release-check, smoke, or上线前检查 test cases by combining requirements with a current-version Bug List, especially Feishu/Lark requirement pages, Feishu Base bug tables, PairMatch/ipair version QA, or requests like "光看需求没有意义", "结合当前版本bug", "用例控制好量", "冒烟新增模块". The skill produces a small risk-clustered testcase CSV with code/config evidence, pending confirmations, and optional Feishu publishing, without uploading project code.
---

# QA Bug-Driven Smoke Testcase

## Purpose

Generate a compact, evidence-first release-check testcase set by combining:

- requirement source: Feishu Wiki/docs or local requirement artifacts
- current-version Bug List: usually a Feishu Base view or local CSV
- local code/config evidence: targeted, read-only scans

This is not a full testcase writer. It is for late-stage QA when the user wants the smallest useful set of上线前检查/冒烟用例 that reflects real bug risk.

## Guardrails

- Never upload project code.
- Do not claim a bug is fixed from the Bug List alone. Use `requires runtime verification` when runtime behavior is needed.
- Do not expand every requirement or every bug into a testcase. Cluster risk and control quantity.
- Prefer 20-30 main cases unless the user gives another limit. If the user says "不能太多", default to 25 or fewer.
- Keep unresolved/ambiguous items in a pending CSV, not the main table.
- Published Feishu artifacts may include generated testcase/pending/report CSVs only.

## Input Handling

Confirm or infer these inputs before generating cases:

- target version, for example `1.5.0`
- requirement source, if available
- Bug List source: local CSV or Feishu Wiki/Base URL
- output target: local only or also publish back to Feishu

For Feishu Bug List links:

1. Ask for explicit confirmation before exporting records.
2. Export to the current working directory as `feishu_buglist_rc.csv`.
3. Use that local CSV as the Bug List source.

Use `scripts/export_feishu_base_view.py` for Feishu Base view export:

```bash
python $CODEX_HOME/skills/qa-bug-driven-smoke-testcase/scripts/export_feishu_base_view.py \
  --url '<feishu wiki/base url with table/view query>' \
  --output feishu_buglist_rc.csv
```

If `lark-cli` reports missing scopes, run the exact read-only login it suggests, wait on the same device-flow session, then retry. Do not restart device login repeatedly.

## Workflow

1. **Read sources**
   - Read requirement content using the existing `qa-requirement-testcase-writer` flow when a Feishu requirement link is given.
   - Read the Bug List CSV only after file/version confirmation.
   - Filter to the target version using `修复版本` and/or `提交版本`.
   - Analyze only statuses equivalent to:
     - `✅验证通过` -> 已验证通过
     - `⚠️待验证` -> 待验证
   - Count ignored statuses, especially `未解决` and `已拒绝`, and mention unresolved release risk in pending items.

2. **Cluster bug risk**
   Build clusters from bug titles, module names, priority, severity, recurrence, and code keywords. Prioritize clusters involving:
   - old/new user or upgrade differences
   - first-open, first-entry, strong-popup, guide flows
   - timers, counters, queues, date reset, stage state
   - unlock conditions and fallback/default values
   - rewards, coins, ads, reporting
   - persistence and weak-network/runtime verification risk
   - iPad/resolution/safe-area visual regressions

3. **Do targeted code/config evidence scan**
   Use `rg` first. Scan only the files needed for the bug clusters. Record:
   - file path
   - function/class/config key
   - matched risk area
   - evidence status: confirmed / unable to confirm / requires runtime verification

   For PairMatch/ipair daily challenge work, high-value paths usually include:
   - `Assets/Script/GameCtr.cs`
   - `Assets/Script/Page/Challenge/ChallengePage.cs`
   - `Assets/Script/Data/PuzzleDataManager.cs`
   - `Assets/Script/Page/SettingPage.cs`
   - `Assets/Script/Page/levelWinPage.cs`
   - `Assets/Script/Page/LevelFailedPage.cs`
   - `Assets/Script/Page/TimeOutPage.cs`
   - `Assets/Main/Script/ADConfig.cs`
   - `Assets/Main/Script/GameSetting.cs`
   - `Assets/Main/Script/DataSave.cs`
   - special-element managers/pages when bug clusters mention special elements

4. **Design the testcase set**
   Present a compact strategy before writing files when the user has not already approved one. Recommended default:
   - 20-25 main cases
   - 5-10 pending confirmations
   - group by bug clusters, not by every bug
   - one testcase may cover multiple bugs only when it verifies the same runtime risk

5. **Generate artifacts**
   Main CSV default columns:
   - `测试内容`
   - `测试目的`
   - `前置条件`
   - `新增参数`
   - `操作步骤`
   - `期望结果`
   - `需求模块`
   - `测试结果`
   - `风险来源`
   - `代码证据`

   Pending CSV columns:
   - `测试内容`
   - `待确认点`
   - `风险`
   - `建议确认人`
   - `备注`

   Coverage report should include:
   - source requirement/Bug List names
   - target version
   - included/excluded modules
   - status mappings and counts
   - code scan evidence summary
   - bug-cluster-to-case mapping
   - skipped duplicate scenario types
   - pending/uncovered risks

6. **Validate**
   Run the testcase quality checker from `qa-requirement-testcase-writer` when available:

```bash
python $CODEX_HOME/skills/qa-requirement-testcase-writer/scripts/testcase_quality_checker.py \
  --cases <main.csv> \
  --report <coverage.md>
```

Fix missing structure, fuzzy expectations, duplicate cases, and missing normal/boundary/exception/risk coverage before publishing.

7. **Publish when requested or approved**
   If publishing to a Feishu requirement page, use the existing `qa-requirement-testcase-writer` publisher and target the existing `测试用例` Base when possible. Use a table name that makes the scope clear, for example:

```text
<version>Bug驱动上线检查测试用例_<YYYYMMDD>
<version>Bug驱动上线检查待确认用例_<YYYYMMDD>
```

## Output Naming

Prefer:

- `<版本>版本需求_Bug驱动上线检查用例_<YYYYMMDD>.csv`
- `<版本>版本需求_Bug驱动上线待确认用例_<YYYYMMDD>.csv`
- `<版本>版本需求_Bug驱动上线覆盖报告_<YYYYMMDD>.md`

For Feishu Bug List exports, use exactly:

- `feishu_buglist_rc.csv`

## Reporting Style

Keep final responses short:

- main case count
- pending count
- quality check result
- Feishu table names/ids if published
- local file paths

Do not paste large tables into chat when files were created.
