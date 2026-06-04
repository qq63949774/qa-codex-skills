---
name: qa-requirement-testcase-writer
description: Generate black-box QA requirement/feature testcases (non-tracking analytics) from requirement documents, with governance gates, pending-case separation, quality validation, and default local AI code-evidence scan when a project path is available.
---

# QA Requirement Testcase Writer

## Overview

This skill handles requirement/function testcase authoring (non-tracking). For Feishu/Lark requirement links, the default full flow is: read Feishu requirements -> read local project code/config -> generate testcase CSVs -> run local AI code-evidence judgment -> publish the AI-checked testcase CSV and pending CSV back to the Feishu `测试用例` Base, unless the user explicitly says not to scan code or not to publish.

当前线程中用户明确给定的需求内容，是唯一需求来源。若用户给定飞书 Wiki/文档链接并明确要求读取，使用下方 `Feishu/Lark requirement intake` 只读流程读取到的文档内容也属于当前线程需求来源。

- 不得从 skill 本身、reference、历史常识或默认行业规则中补充额外业务需求。
- skill 只提供测试设计流程、表格结构、质量约束与校验方式。
- 若当前线程未写清某条需求，必须标记为`待确认`，不得自行扩写成新需求。

## 固化守则

- 保持现有输出格式、字段名、字段顺序、层级结构不变。
- 先拆需求，再写用例。必须先把当前线程给定的需求拆成最小可独立验证的`需求原子项`清单。
- 每个`需求原子项`至少落到以下二者之一：
  - 主 CSV 中至少 1 条可追溯测试用例
  - 待确认 CSV 中至少 1 条待确认项
- 不得把多个可独立验证的需求原子项揉成 1 条笼统用例；若确实无法分拆，必须在覆盖报告中说明不可分拆原因。
- 每条用例必须可独立执行，不依赖“上一条用例已通过”或其它用例产物；如确需数据准备，必须写入当前用例的`前置条件`。
- 用例设计必须覆盖正常流程、边界值、异常流程、状态流转、必要回归。
- 高风险模块、关键路径、异常场景优先生成；同类重复断言或仅文案改写的冗余场景应跳过。
- 若需求出现新增后台参数、服务端配置、运营配置、远程 JSON 参数、开关、概率、阈值、区间、价格、数量、解锁关卡等可配置项，必须生成可直接执行的参数验证用例，并在主 CSV 中增加`新增参数`列。
- 对新增/变更后台参数必须做`配置读路径与生效范围`检查：区分触发/选择类参数与效果类参数；若本地代码证据显示字段未被读取、读取的是普通/共用配置、或只在部分模式/model/stage 生效，主 CSV 必须生成对照验证用例或在待确认 CSV 记录缺口，不能只按 JSON 字段名生成正向用例。
- 不得把 skill 内置条目当作需求条目；所有业务规则必须来自当前线程给定的需求文档或用户补充说明。
- 若发现需求存在高风险但未形成可执行用例，必须输出遗漏/待确认提示。

## Workflow

1. Requirement entry gate
   - Record and print:
     - `需求文档名`
     - `需求版本`
     - `需求日期`
     - `适用包体/分支`
   - If missing, mark as `待确认` and continue with explicit assumptions.

### Feishu/Lark requirement intake

Use this only when the user explicitly provides a Feishu/Lark requirement link or asks to read requirements from Feishu.

- Read only. Never upload project code or local files to Feishu.
- Treat the Feishu document content read in the current turn as the requirement source; do not add business rules from memory, defaults, or the skill itself.
- For Wiki version pages, do not stop at the parent page body. Resolve the Wiki node first, list its child nodes, and read each child `docx` requirement page.
- Skip non-requirement child nodes such as `测试用例` bitable/sheet unless the user explicitly asks to use them as input.
- Preserve the original hierarchy in the requirement atom list: `版本父节点 -> 子需求文档标题 -> heading/list/table item`.
- If the CLI profile is in `strict-mode: bot` but the required scopes are user-identity scopes, ask/confirm before temporarily switching to `strict-mode user`; restore the original strict mode after reading.
- Minimum scopes:
  - `wiki:node:read` to resolve a Wiki node.
  - `wiki:node:retrieve` to list child nodes.
  - `docx:document:readonly` to read child requirement documents.
  - Optional `drive:drive.metadata:readonly` only for metadata/link enrichment.
- Prefer the helper script:
  - `scripts/feishu_wiki_requirements_reader.py --url <wiki_url> --version <version> --switch-user --output <json_path>`
- If the helper is unavailable, use equivalent `lark-cli` commands:
  1. `lark-cli wiki spaces get_node --params '{"token":"<wiki_token>","obj_type":"wiki"}' --as user`
  2. `lark-cli wiki nodes list --params '{"space_id":"<space_id>","parent_node_token":"<node_token>","page_size":50}' --as user --page-all`
  3. `lark-cli docs +fetch --api-version v2 --doc <obj_token> --as user --format json` for each child requirement `docx`.
- Record in the report whether child-node traversal succeeded. If child traversal fails, mark child requirements as `unable to confirm` rather than generating cases only from the parent page.

2. Scope confirmation
   - Print:
     - `包含模块`
     - `不包含模块`
     - `待确认模块`
   - Limit output to `包含模块`.

3. Rule coverage pre-check
   - Before generating cases, first build a `需求原子项`清单：
     - 按文档原层级逐条拆分到最小可独立验证粒度。
     - 默认以“一个可独立观察的条件 / 动作 / 结果 / 状态约束”为一个原子项。
     - 示例：若同一条需求写了“未开始不计时、设置页暂停、切后台暂停、用道具暂停、看广告暂停、动画暂停”，则必须拆成 6 个原子项，不得合并成 1 条笼统倒计时用例。
   - 同时识别`新增后台参数`清单：
     - 包括文档中明确写出的后台参数名、JSON key、默认值、概率、阈值、区间、开关、价格、数量、奖励值、解锁关卡、显示关卡、冷却时间、次数限制、商品 id 映射等。
     - 对每个新增参数记录：`参数名`、`默认值/示例值`、`可测取值集合`、`影响的功能入口`、`预期可观察结果`、`待确认点`。
     - 对每个新增参数记录`读路径/生效范围`：本地代码/配置中读取该 key 的文件、函数/类、读取的是专用配置还是普通/共用配置、作用模式/页面/model/stage、fallback/default 行为；未找到证据时标记`unable to confirm`，不得默认认为生效。
     - 对嵌套配置或模式专用配置，必须拆成可独立验证的参数原子项：`作用域选择参数`、`触发/概率/阈值参数`、`效果数值参数`、`fallback/default 参数`。例如某模式下“是否出现特殊元素”和“特殊元素持续时间/奖励/扣减比例”必须分别确认读取路径和可见结果。
     - 参数用例必须遍历该参数的正常值、边界值和异常/容错值；概率类必须覆盖 0、100、>100 或文档指定边界；区间类必须覆盖 min、max、min=max、反向区间、空/缺失等文档或实现可能接受的形态；开关类必须覆盖开/关。
     - 若参数行为依赖关卡、model、难度、步数、计时、计数器、队列、解锁条件、商品配置等项目配置，且当前工作区有本地项目，必须读取本地配置/代码证据来选择具体测试入口。例如关卡中存在多种 model 时，遍历所有实际存在的 model；每种 model 至少给出 1 条正常触发或正常不触发用例。
     - 若无法从文档或本地项目确认具体关卡/入口/触发步数，主用例中只能写可确认部分，并在待确认 CSV 中列出需要产品、客户端或配置负责人确认的字段。
   - Then build and print a compact checklist covering:
     - `正常流程`
     - `边界值`
     - `异常场景`
     - `状态流转`
     - `回归影响`
     - `高风险/关键模块`
     - `待确认/潜在遗漏`
     - `新增后台参数覆盖`
     - `配置读路径/生效范围覆盖`
   - 若当前线程需求明确写出专项规则，再把这些专项规则加入 checklist。
   - Any item without enough evidence must be marked `未覆盖` or `待确认` before testcase writing.

4. Coverage design
   - Follow `references/testcase-methodology.md`.
   - Cover equivalence, boundary, state flow, exception, and regression.
   - For新增后台参数:
     - 每条参数用例必须体现“配置 -> 入口 -> 预期”的结构，做到 QA 可以直接按行执行。
     - 每个参数至少落到 1 条`读路径验证`或`生效范围验证`：同一业务对象存在普通配置和模式专用配置时，必须设计对照值用例来判断实际读取哪一套配置；若代码证据显示专用字段未接入，期望结果必须写成“仍读取普通/共用配置值”，并把专用字段未生效列入高风险或待确认。
     - 对固定规则与随机规则同时存在的配置，必须覆盖优先级、关闭固定规则后的随机规则、概率 0、概率 100、以及非法/不兼容类型导致 fallback/default 的风险。
     - `新增参数`列只填写当前用例需要修改/验证的新增参数差异配置，例如 `{"adBallProb":0,"adBallLeftMovesGap":[10,10]}`；不要把整份后台配置重复放进每条 CSV，除非用户明确要求完整配置。
     - `操作步骤`必须写清进入哪个页面、弹窗、关卡、model、商品或流程测试；如果能从本地项目计算触发点，必须写清“第几关 / 第几次操作 / 操作前剩余值 / 操作后剩余值 / 触发点”。
     - `期望结果`必须写清具体可观察结果，例如“第35次耗步失败，29->28 时出现广告球”“第5关不出现”“商品1展示1200金币”“概率0时多次到达触发点均不出现”。
     - 参数组合应以单参数覆盖为主，必要时增加少量组合用例验证字段之间的依赖关系；避免无意义笛卡尔积，但不能漏掉文档明确要求的每一种情况。
   - Prioritize output in this order:
     1) 高风险/关键模块
     2) 核心主流程
     3) 边界与异常
     4) 回归/兼容
   - Skip duplicated scenarios when assertion target, precondition intent, and expected result are materially identical.

5. Generate main testcase CSV
   - One core assertion per case.
   - 主 CSV 中每条用例默认只对应 1 个需求原子项；除非这些原子项在黑盒视角下无法拆分，否则不得合并。
   - Expected result must be explicit and observable.
   - Keep each case independently executable.
   - Keep batch generation and multi-round request handling inside the same output structure.
   - For high-risk module or critical/exception scenario, mark it inline in existing text fields only, for example by prefixing `测试内容` with `[高风险]`, `[关键模块]`, or `[异常]`. Do not add new columns.
   - If no新增后台参数 are detected, keep column order:
     1) `测试内容`
     2) `测试目的`
     3) `前置条件`
     4) `操作步骤`
     5) `期望结果`
     6) `需求模块`
     7) `测试结果` (keep empty)
   - If新增后台参数 are detected, add `新增参数` after `前置条件` and keep column order:
     1) `测试内容`
     2) `测试目的`
     3) `前置条件`
     4) `新增参数`
     5) `操作步骤`
     6) `期望结果`
     7) `需求模块`
     8) `测试结果` (keep empty)
   - `新增参数`列填写当前用例要测试的参数差异配置或参数名；优先使用紧凑 JSON。非参数用例可留空，但参数相关用例不得为空。

6. Generate pending-case CSV
   - Keep ambiguous items outside main CSV.
   - Put uncovered, conflicting, or insufficiently specified high-risk scenarios here.
   - Columns: `测试内容, 待确认点, 风险, 建议确认人, 备注`

7. Run quality checker
   - Run `scripts/testcase_quality_checker.py`.
   - Must pass checks before any AI code scan or Feishu/Lark publishing.
   - Review checker summary for:
     - duplicates / independence issues
     - fuzzy expected results
     - missing normal/boundary/exception/risk tags
     - coverage report structural completeness when report path is provided

8. Default local AI code judgment
   - After generating and quality-checking the main testcase CSV, run local AI code judgment by default whenever a local project path is available or can be reasonably inferred from the current workspace.
   - Do not upload project code. Scan local files only.
   - If the user explicitly says not to scan code, skip this step and state that it was skipped by request.
   - If the project path cannot be inferred, ask for the local project path instead of silently skipping.
   - Prefer the stable verifier from `qa-code-evidence-scan`: `/Users/adin/.codex/skills/qa-code-evidence-scan/scripts/ai_case_verifier.py`.
   - Scan only local project code/config; never upload project code.
   - Default project scan root to the business-code root, not the report/output root. For Unity projects, prefer the Unity project folder such as `<repo>/PairPop` over the repository root when the repo also contains `QAReports/`, `reports/`, `output/`, generated scripts, or prior testcase CSVs.
   - If AI evidence reasons mention generated testcase files, report files, `QAReports/`, or the testcase generation script itself, treat the scan as polluted and rerun against the narrower business-code root before publishing.
   - AI code judgment is an evidence gate, not a semantic similarity score:
     - Never mark `AI测试结果=通过` from keyword overlap, requirement-text similarity, file-name similarity, or generated testcase/report artifacts.
     - `通过` requires direct local business-code/config evidence with a traceable path, line number, and concrete implementation anchor such as `key=...`, `symbol=...`, `class=...`, `function=...`, or an equivalent config key/function/class name.
     - Evidence must come from project code/config under the business-code root. Do not use generated testcase CSVs, reports, `QAReports/`, `reports/`, `output/`, docs, package/vendor/plugin/third-party files, or this skill's scripts as proof.
     - Empty projects, unrelated projects, missing scannable business files, or only generic keyword hits must produce `AI测试结果=不通过` with a reason such as `未找到可追溯项目代码/配置证据`.
     - If any `通过` row lacks path + line + concrete anchor, the AI-checked CSV is invalid; rerun with a narrower project root or downgrade the row to `不通过`.
   - Append/maintain these columns after the base testcase schema:
     - `AI测试结果`: must be `通过` or `不通过`
     - `AI判定原因`
     - `AI测试用例通过率`
   - Remove obsolete detail columns if they exist in the input/output:
     - `AI判定通过原因`
     - `AI证据文件`
     - `AI证据行号`
     - `AI证据关键词`
     - `AI置信度`
     - `AI置信等级`
   - Keep `测试结果` unchanged for human QA execution.
   - Treat AI scan as evidence assistance only:
     - `通过` means traceable local business-code/config evidence was found.
     - `不通过` means traceable evidence was not found, confidence is Low, or the finding is keyword-only/generic.
     - Do not claim runtime behavior is verified unless runtime execution was actually performed.
   - After AI code judgment, run `scripts/testcase_quality_checker.py` again against the AI-checked CSV. Do not publish if the checker reports an AI evidence finding.

9. Default publish testcase CSV to Feishu/Lark for Feishu requirements
   - When the requirement source is a Feishu/Lark Wiki or doc link, publish generated cases back to the version page's `测试用例` Base by default after quality check and local AI code judgment, unless the user explicitly says not to publish.
   - If an AI-checked CSV exists, publish that AI-checked CSV rather than the base main CSV. The published testcase table must preserve the CSV columns in order, including:
     - `测试内容`
     - `测试目的`
     - `前置条件`
     - `新增参数` when present in the CSV
     - `操作步骤`
     - `期望结果`
     - `需求模块`
     - `测试结果`
     - `AI测试结果`
     - `AI判定原因`
     - `AI测试用例通过率`
   - Feishu field types must be:
     - `需求模块`: single-select field; options are the distinct module names from the testcase CSV.
     - `测试结果`: single-select field; options are exactly `通过` and `不通过`.
     - `AI测试结果`: single-select field with the same `通过` and `不通过` options when the AI-checked CSV is published.
     - `新增参数` and other testcase fields: text fields unless the user explicitly requests another field type.
   - If AI code judgment is skipped by explicit user request, publish the base main CSV with the 7 standard testcase columns.
   - Never upload project code, logs, or local source files. Publish only generated testcase/pending/report artifacts.
   - For a version Wiki page, first list child nodes under that version node:
     - If a child node named `测试用例` exists and its `obj_type` is `bitable`, use that Base.
     - If no `测试用例` child exists, create a Wiki child node titled `测试用例` with `obj_type=bitable`.
  - If a child named `测试用例` exists but is not `bitable`, do not overwrite it; create `测试用例-多维表格` or ask before changing depending on risk.
  - QA Proof Desk 网站默认遵循同一策略：优先接入版本 Wiki 下已有的 `测试用例` bitable；如果找不到现有 Base，则自动创建 Wiki 子 Base 后发布。只有当服务端显式开启 existing-only 策略时，网站调用发布脚本才附加 `--existing-only`。
   - In the target Base, name AI-checked tables like `<版本>测试用例_AI检查_<YYYYMMDD>` and base tables like `<版本>测试用例_<YYYYMMDD>`.
   - Pending cases should be published to a separate table such as `<版本>待确认用例_<YYYYMMDD>` when a pending CSV exists.
  - Use the helper script when possible:
    - `scripts/feishu_testcase_bitable_publisher.py --wiki-url <wiki_url> --version <version> --cases <ai_checked_or_main_csv> --pending <pending_csv> --switch-user`
    - For QA Proof Desk website integration, add `--existing-only` only when the service explicitly runs in existing-only mode.
   - If the CLI profile is in `strict-mode: bot` but publish requires user identity, ask/confirm before temporarily switching to `strict-mode user`; restore the original strict mode after publishing.
   - Publish mode is append/create-table only. Do not delete or overwrite existing Feishu records unless the user explicitly asks for replacement.

10. Post-generation brief report
   - After CSV generation, print a short coverage report only in plain text:
     - `需求文档名`
     - `需求版本`
     - `需求日期`
     - `适用包体/分支`
     - `包含模块`
     - `不包含模块`
     - `待确认模块`
     - `覆盖清单`
     - `已覆盖模块`
     - `高风险已覆盖点`
     - `新增后台参数覆盖`
     - `配置读路径/生效范围`
     - `未覆盖/待确认点`
     - `跳过的重复场景类型`
     - `需求原子项映射`
   - `需求原子项映射`必须逐条列出：
     - 原子需求文本
     - 对应主表用例标题，或
     - 对应待确认项标题
   - 若某原子项被判定为重复而跳过，必须在报告中说明其被哪条用例覆盖。
   - Do not change CSV schema for this report.

## Output naming

- `<需求名>_测试用例_<YYYYMMDD>.csv`
- `<需求名>_待确认用例_<YYYYMMDD>.csv`
- Write `<需求名>_测试用例_AI检查_<YYYYMMDD>.csv` when local AI code judgment runs; for Feishu requirements, this is the default publish target unless the user opts out.

## Files to use

- `references/testcase-methodology.md`
- `assets/testcase_template.csv`
- `scripts/testcase_quality_checker.py`
- `scripts/feishu_wiki_requirements_reader.py`
- `scripts/feishu_testcase_bitable_publisher.py`
