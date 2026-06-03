# Scan Confidence Rules

## Confidence levels

- High: >=3 meaningful keyword hits in business code.
- Medium: >=2 meaningful keyword hits in business code.
- Low: weak hits or paths likely from third-party/non-business code.

## Filtering

- For Low confidence, clear `AI测试结果` and keep evidence fields empty.
- Keep `AI置信等级` for manual review tracking.

## Threshold guidance

- Text/toast verification: prefer `--min-hits 3`.
- Flow/state verification: start with `--min-hits 2`, then manual review.
