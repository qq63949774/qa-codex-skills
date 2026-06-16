---
name: pairpop-backend-param-diff-testcase
description: Use when comparing PairPop backend/server-delivered configuration parameters from a user-provided previous-version date/time to today's/current git version, then combining the user's backend config to produce a complete copyable backend configuration table and the exact expected behavior under that config. Also use for newly added GameSetting, ADSetting, DailyTask, GameConfig, hot-update, daily challenge/task/rank, reward, ad, unlock, timer, counter, and fallback parameters.
---

# PairPop Backend Param Diff Testcase

Use this skill for PairPop QA tasks that ask to compare backend parameters across versions, especially when the user gives an old-version date/time and a backend config, then wants copyable backend settings plus expected behavior.

## Boundaries

- Never upload project code. Read only local files in the executor's Codex environment.
- Treat "online version" as a git ref only when there is a tag/branch/commit proving it. If no release ref exists, use the latest commit at or before the requested old-version date/time as an assumption and state `unable to confirm true online build`.
- Evidence-first: do not mark a parameter as backend-controllable unless code parses it from server-delivered settings or a downloaded config path.
- If a parameter is declared but no runtime read/use is found, mark it `unable to confirm`.
- Runtime behavior such as ad display, daily reset, cloud download success, reward granting, and UI pop timing is `requires runtime verification` unless an executed run log exists.
- The user's backend config is execution input. Preserve supplied values exactly in copyable outputs; do not silently replace them with "better" values.

## Core Sources

Read these first when present:

- `PairPop/Assets/Main/Base/net/NetHelper.cs`: server login setting download and MD5 handling.
- `PairPop/Assets/Main/Script/GameConfig.cs`: top-level setting dispatcher.
- `PairPop/Assets/Main/Script/GameSetting.cs`: `GameSetting`, `DailyTaskSetting`, and server setting schema.
- `PairPop/Assets/Main/Script/ADConfig.cs`: `ADSetting` and ad weights.
- `PairPop/Assets/Script/Util/DownloadPuzzleData.cs`: normal/challenge cloud level update maps.
- Use `git grep` for each new key to find runtime consumers.

## Workflow

1. Input gate:
   - Required inputs:
     - `旧版本日期时间`: exact date and time for the previous version baseline, including timezone if available.
     - `目标版本`: default to fetched `origin/master` for "today/current" unless the user gives a branch/tag/commit.
     - `后台配置`: the user's actual backend config JSON/table/text to use for copyable config and expected-behavior output.
   - If `旧版本日期时间` is missing, do not guess silently. Ask for it.
   - If `后台配置` is missing and the user asks for copyable config/expected behavior, ask for the config or ask whether to use client default values as a temporary assumption.
   - If timezone is missing, state the assumed repo timezone and ask for confirmation before treating a boundary time as authoritative.
   - Before doing the final diff, restate the planned method in one short paragraph and ask for confirmation when any required input is incomplete or ambiguous. Example:
     - `我会用 <datetime> 当天该时间点之前最新 git commit 作为旧版本基线，用 fetch 后的 origin/master 作为当前版本，然后只对新增后台参数合并你给的后台配置输出配置表和预期。这个做法是否对？`
2. Fetch and identify refs:
   - Run `git fetch --all --prune`.
   - Prefer an explicit user-provided commit/tag.
   - If a date+time is provided, use the latest commit at or before that exact timestamp in the repo timezone.
   - If only a date is provided, ask whether to use the end of that day. If the user confirms, use the latest commit before the date end in the repo timezone and state the assumption.
   - For "today/current", prefer `origin/master` after fetch unless the user explicitly wants local `HEAD`.
   - Always record:
     - old baseline commit hash, commit time, subject.
     - target commit hash, commit time, subject.
     - `unable to confirm true online build` unless the old baseline is an explicit release tag/commit supplied by the user.
3. Run the bundled extractor for a raw diff:
   ```bash
   python3 $CODEX_HOME/skills/pairpop-backend-param-diff-testcase/scripts/diff_backend_params.py \
     --repo <PAIRPOP_REPO> \
     --base <base-ref> \
     --head <head-ref> \
     --out /tmp/pairpop_backend_param_diff.md
   ```
4. For every added key, run `git grep -n "<key>" <head-ref> -- PairPop/Assets/Main PairPop/Assets/Script`.
5. Parse the user's backend config:
   - Treat the user's config as the source of execution values.
   - Preserve every supplied value exactly when producing copyable output.
   - If the user's config omits a newly added parameter, fill the row value from the client default only when code evidence proves a default exists; mark `值来源=客户端默认值` and do not present it as production backend value.
   - If the user's config has a key that was not newly added, keep it in the complete config table only when it is inside the affected backend block needed for copy/paste context; mark `是否新增参数=否`.
   - For nested structures, flatten paths with dot/bracket notation such as `DailyTask.rewards[0].items[0].itemId`, while also preserving a compact JSON cell for copy/paste.
   - If config parsing is uncertain, put the raw snippet in the report and mark affected rows `unable to confirm`.
6. Group parameters by QA domain:
   - daily challenge: unlock, reward, victory multiplier, hot-update level map.
   - daily task: unlock, reward gap, reward items, daily reset.
   - daily rank: unlock, robot generation/progress, user score, reward config, display switch.
   - ads: challenge victory/failure/quit and normal game quit interstitial weights.
   - fallback/defaults: missing keys, null arrays, short arrays, malformed nested objects.
7. Build a separate added-parameter inventory CSV. This is not the copyable config table.
   - Columns: `参数名, 参数层级, 默认值/示例值, 可测取值集合, 影响入口, 读路径/生效范围, 待确认点, 代码证据`
   - Include only parameters proven newly added by the git diff.
   - Keep nested fields readable, for example `DailyTask.rewards[].items[].itemId`.
8. Generate the primary copyable backend configuration artifact in the user's original format.
   - This is the main output when the user provides backend config.
   - If the input config is JSON, output a complete JSON file, not only per-field snippets.
   - Preserve the user's top-level blocks, field names, nesting shape, and existing values. For PairPop this usually means complete `GameSetting`, `ADSetting`, `BannerAD`, and `DailyTask` blocks.
   - Do not output a partial config that only contains changed/new keys as the main copyable artifact; partial snippets are hard to paste into the backend safely.
   - When a newly added parameter is missing from the user's backend config, add it to a separate complete "补齐新增字段" JSON using the client default only when code evidence proves that default. Mark the value source in the report.
   - If recommending test adjustments, output a second complete JSON file such as `完整后台配置_建议测试版.json`; do not overwrite the current-value complete JSON.
   - Also generate an auxiliary config index CSV after the full JSON.
   - Auxiliary CSV columns, in order:
     - `配置块`
     - `配置路径`
     - `是否新增参数`
     - `当前值`
     - `建议测试值`
     - `值来源`
     - `复制用JSON片段`
     - `影响入口`
     - `预期表现摘要`
     - `代码证据`
     - `待确认点`
   - `当前值` is the value from the user's backend config, not a made-up test value.
   - `建议测试值` should be a small, directly useful adjustment for QA to copy into backend when the current value does not exercise the edge or feature clearly.
   - `复制用JSON片段` is auxiliary only; the full JSON file is the copy/paste source of truth.
   - Include enough surrounding parent structure to make the path clear, for example `{"GameSetting":{"dcUnlockLevel":30}}` or `{"DailyTask":{"rewards":[...]}}`.
   - Mark `是否新增参数=是` only for parameters proven added by git diff.
   - Mark missing or inferred values as `unable to confirm` in `待确认点`.
9. Generate the expected-behavior CSV for the provided config.
   - Required columns, in order:
     - `配置场景`
     - `使用配置`
     - `进入条件`
     - `操作入口`
     - `应该出现的正确预期`
     - `不应该出现`
     - `适用范围`
     - `证据状态`
     - `代码证据`
     - `requires runtime verification`
   - The expected behavior must be written for the exact user-provided config values. If a value is missing and defaulted, say so in `使用配置`.
   - Use player/client-observable results: page lock/unlock, reward amount, ad request/skip, rank score change, challenge data source, reset/persistence behavior.
   - Do not write generic expectations like `正常` or `符合预期`.
   - `证据状态` can be `code-confirmed`, `unable to confirm`, or `requires runtime verification`.
10. Generate optional QA testcase CSV only if the user explicitly asks for test cases or Feishu upload.
   - Required columns, in order: `测试内容, 测试目的, 前置条件, 新增参数, 操作步骤, 期望结果, 需求模块, 测试结果`
   - `新增参数` is required for every parameter/config case and should contain only the compact config delta for that case, preferably JSON.
   - `操作步骤` must be executable by QA and written from the player/client perspective: configure backend, cold start/login, enter page/level/flow, perform the action, observe the result.
   - `期望结果` must be specific and observable. Avoid `正常`, `符合预期`, `合理`, `无异常`, and implementation-only wording.
   - Put evidence paths, classes, functions, and code reasoning in the summary report or parameter inventory, not in the testcase row.
11. Generate a pending/unconfirmed CSV for unclear or runtime-only behavior.
   - Columns: `测试内容, 待确认点, 风险, 建议确认人, 备注`
   - Use this for true online build ref uncertainty, production payload values, backend validity limits, duplicate/negative/malformed value expectations, CDN availability, ad no-fill, daily reset, persistence, and any behavior with no executed runtime log.
12. Generate a compact evidence summary Markdown.
   - Include the base/head refs, `unable to confirm true online build` if applicable, raw added-key groups, code evidence anchors, and a note that project code was read only locally.
   - Keep separate sections for `unable to confirm` and `requires runtime verification`.

## Output Guidance

- For arrays and matrices, include boundary cases: null, empty, length too short, negative values, reversed ranges, overlapping ranges, extreme values.
- For unlock-level params, explain below threshold, exactly threshold, and above threshold expectations.
- For counters/rewards, explain first claim, duplicate claim prevention, next-day reset, and server-save persistence when code supports them.
- For ads, explain weight `0`, positive weight, ad-free user, and no-fill callback expectations; runtime ad behavior remains `requires runtime verification` without logs.
- For hot-update maps, explain no current-version key, empty filename, successful zip load, failed download, failed unzip, and fallback to built-in resource.
- Do not infer outputs from unrelated checklist items.
- Prefer a small number of readable config/expectation rows per parameter group over one row per code line. Split rows when the observable expectation is different: unlock gates, reward grant, display switch, fallback/default, malformed config tolerance, and persistence are separate assertions.
- If a behavior needs code evidence for scope, mention the scope in plain QA language, such as `仅挑战模式生效，普通关仍使用原 time_coin_add`, and put the path/function proof in the evidence columns or summary report.
- For copyable backend config outputs, prioritize a complete backend config in the user's original format over row-level snippets. The user should be able to copy the whole JSON/config block into the backend, then read the matching expected-behavior row to know what should happen.
- If the user's config value conflicts with code evidence, do not "fix" it silently. Preserve the user's value, explain the conflict, and add a suggested test value in `建议测试值`.
