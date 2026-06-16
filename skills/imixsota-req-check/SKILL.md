---
name: imixsota-req-check
description: Use when the user asks to verify the current imixsota iOS project against a requirement document, acceptance criteria, or a versioned docx such as imixsota v1.x. Use this skill whenever the request is about requirement inspection, acceptance review, code evidence collection, section 8 test acceptance, implementation coverage, or "check the current project against the doc" for this repository.
---

# imixsota Requirement Check

This skill is for QA-style requirement inspection on the current project only:

- Project root: `<IMIXSOTA_REPO>`
- Main stance: QA / acceptance / evidence collection
- Not allowed: modifying product code, inventing runtime evidence, or declaring pass without traceable proof

Read `references/project-map.md` before starting if the request is about ads, lifecycle, config parsing, or acceptance section checks.

## When to use

Use this skill when the user asks things like:

- "According to this doc, check whether the project is implemented"
- "Verify section 8 acceptance criteria"
- "Help me finish acceptance for the current imixsota project"
- "Do requirement-to-code inspection for this repository"
- "Give evidence, do not guess"

Do not use this skill for generic coding, refactors, or cross-project QA work.

## Core rules

1. Stay in QA language. Report implementation status, evidence, defects, and regression risk.
2. Never claim runtime pass unless you actually ran the relevant check.
3. Every conclusion must map to both:
   - a requirement item
   - one or more code or test references
4. Prefer the smallest necessary code search. Do not sweep unrelated modules.
5. If dynamic validation is blocked by the environment, state the exact blocker and keep static evidence separate from runtime evidence.

## Workflow

### 1. Confirm the requirement input

Ask for exactly one requirement document path if the user has not already provided it.

If the user already named the document in the conversation, use that file and do not ask again.

### 2. Read the requirement doc

For `.docx`, prefer:

```bash
textutil -convert txt -stdout "<doc-path>"
```

Extract a traceable checklist first. When the doc has numbered acceptance sections, preserve that numbering in the checklist, for example:

- `8.1.a`
- `8.1.b`
- `8.2.a`

If the user asks to focus on a specific section such as `8. Test Acceptance`, narrow the checklist to that section but keep cross-references to earlier requirement sections when needed.

### 3. Build a targeted scan plan

List only the likely relevant code areas first. For this project, ad-related acceptance requests usually map to:

- `WordTop/Ad/V2/`
- `WordTop/Ad/AdAgent.swift`
- `WordTop/Report/SdkAgent.swift`
- `WordTop/SceneDelegate.swift`
- `WordTopTests/AdMax*.swift`
- `WordTopTests/SdkAgentAdMaxParsingTests.swift`

Search by requirement concepts, not by broad repository sweeps.

Examples:

```bash
rg -n "admax|warm_resume|rewarded|interstitial|urgent|_admax|sdk_admax_play" WordTop WordTopTests -S
```

### 4. Collect evidence in layers

Use this evidence priority:

1. Primary implementation evidence
2. Existing unit/UI test evidence
3. Dynamic execution evidence, only if actually executed

Treat these as distinct:

- `Implemented with code evidence`
- `Covered by existing tests`
- `Runtime-validated in this run`

Do not merge them into a single unsupported "passed" statement.

### 5. Evaluate each requirement item

For every checklist item, classify using one of:

- `Implemented`
- `Partial`
- `Missing`
- `Blocked for runtime verification`

Use `Blocked for runtime verification` only when static code exists but the user asked for full acceptance and runtime evidence could not be completed.

### 6. Look for obvious defects in touched modules

Only inspect the modules already opened for:

- requirement mismatch
- protocol/path mismatch
- off-by-one retry logic
- stale cache behavior
- lifecycle holes
- reward or callback semantic mismatch

Do not provide patch-style code fixes. Describe the defect, repro path, and impact.

### 7. Attempt runtime evidence when appropriate

If acceptance implies executable proof and the environment supports it, run the narrowest relevant validation.

For this project, before claiming runtime acceptance on iOS ad flows, verify the toolchain first:

- Xcode availability
- simulator availability
- CocoaPods support files existence under `Pods/Target Support Files`

If runtime execution fails, record the exact command failure and classify the relevant items as blocked for runtime verification rather than passed.

## Output order

Always use this order:

1. `Input confirmed`
2. `Unimplemented / partial / blocked items`, risk-sorted
3. `Implemented checklist with evidence`
4. `Obvious defects`
5. `Regression impact`
6. `Clarifications needed`
7. `Runtime verification status`

## Report style

For each finding or checklist item, include:

- requirement ID
- status
- conclusion
- evidence

Evidence should reference concrete files, for example:

- `<IMIXSOTA_REPO>/WordTop/Ad/V2/AdMaxV2Service.swift`
- `<IMIXSOTA_REPO>/WordTopTests/AdMaxV2ServiceTests.swift`

When discussing runtime blockers, include the exact failed precondition, such as:

- missing `Pods/Target Support Files`
- `xcodebuild` unavailable
- simulator service unavailable
- Ruby / CocoaPods dependency incompatibility

## Project-specific cautions

- The current project has requirement docs that may mention multiple `_admax` payload paths. Confirm whether the code matches the exact documented path before signing off.
- For ad acceptance, distinguish "code exists" from "fully accepted". Existing tests are strong evidence, but they are not the same as a successful local test run.
- If section `8` wording and code semantics differ, call out the exact wording mismatch instead of smoothing it over.

## Example triggers

Example 1:
Input: "According to imixsota v1.2.0.docx, help me finish acceptance for section 8 and show evidence."
Behavior: extract section 8 checklist, inspect only relevant ad modules, cite code and tests, separate static and runtime evidence.

Example 2:
Input: "Check whether the current project matches this requirement doc. Do not guess."
Behavior: confirm the doc path, build a traceable checklist, classify implemented/partial/missing, and surface blockers precisely.
