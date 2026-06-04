# Scan Confidence Rules

## Confidence levels

- High: traceable implementation evidence in business code/config, including file path, line number, and a concrete anchor such as `key=...`, `symbol=...`, `class=...`, or `function=...`.
- Medium: traceable implementation evidence exists but still needs runtime validation.
- Low: keyword-only hits, weak/generic hits, generated-file hits, third-party/non-business paths, or insufficient evidence.

## Filtering

- Keyword-only hits must be written as `AI测试结果=不通过`.
- Never mark `通过` from `命中<path>:<keyword>/<keyword>` style reasons without line number and concrete anchor.
- Obsolete detail columns such as `AI置信等级`, `AI证据文件`, and `AI证据关键词` should not be published.

## Threshold guidance

- `--min-hits` can help find candidate files only. It is not sufficient proof.
- Runtime behavior remains unverified unless runtime execution was actually performed.
