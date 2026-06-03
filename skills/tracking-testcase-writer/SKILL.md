---
name: tracking-testcase-writer
description: Generate analytics event reporting test cases from tracking CSV tables (for example fields like 事件标签/事件名/点位触发说明/属性名/属性说明/备注1). Use when Codex needs to create or update 数数埋点测试用例, guarantee every event property is checked, and derive operation steps from trigger descriptions.
---

# Tracking Testcase Writer

## Workflow

1. Read the source tracking CSV and parse event blocks with carry-forward semantics:
   - Start a new event when `事件名` is non-empty.
   - Carry `事件标签` and `点位触发说明` to subsequent property rows.
   - Treat rows with non-empty `属性名` as properties under the current event.
2. Generate test cases that guarantee property coverage:
   - Create one base case per event.
   - For events with properties, include all properties in the expected check list.
   - Parse enum-like options from `备注1` and `属性说明`; create value-focused cases for each option.
3. Derive operation steps from `点位触发说明`:
   - Write concise business actions that can trigger the event.
   - Keep 数数查询描述 lightweight; assume the user handles detailed query operations.
4. Export CSV output for direct QA usage.

## Commands

Generate a draft test case CSV:

```bash
python3 scripts/generate_tracking_testcases.py \
  --input "/path/to/mixword埋点 - #事件数据.csv" \
  --output "/path/to/mixword埋点-事件数据_测试用例_测试版.csv" \
  --code-root "/path/to/project-code-root"
```

If `--output` is omitted, the script writes a dated file next to the input file.
Use `--disable-ai-analysis` to skip code scan and keep AI columns empty.

## Output Rules

- Keep one row per executable QA case.
- Use trigger-driven operations instead of implementation details.
- Always include an explicit property checklist in the expected result when the event has properties.
- When enum values exist, add dedicated rows to validate each value.
- Keep the case language concise and deterministic.
- Include AI scan columns:
  - `测试结果` (empty for manual fill)
  - `AI测试结果`
  - `ai判定通过原因`
  - `AI置信度`

See detailed writing constraints in [references/case-writing-rules.md](references/case-writing-rules.md).
