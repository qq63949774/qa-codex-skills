# Tracking Case Writing Rules

## Required Coverage

1. Validate every event in the source CSV at least once.
2. Validate every property (`属性名`) under each event:
   - Presence
   - Data type alignment with `属性值类型`
   - Business meaning alignment with `属性说明`
3. Validate enum-like values from `备注1`/`属性说明` with value-focused cases.

## Operation Step Style

1. Derive operations from `点位触发说明`.
2. Keep steps action-oriented and reproducible.
3. Keep 数数 query wording generic (user handles actual query workflow).

## Expected Result Style

1. Write event success criteria.
2. Append an explicit checklist:
   - `属性名(类型)`
3. For enum-focused cases, call out the specific expected value.

## Suggested Output Columns

- 测试内容
- 测试目的
- 前置条件
- 操作步骤
- 期望结果
- 需求模块
- 事件名
- 重点校验属性
- 属性检查清单
