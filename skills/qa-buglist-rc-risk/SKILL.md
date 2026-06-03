---
name: qa-buglist-rc-risk
description: QA buglist analysis for late-stage releases (RC/freeze). Use when the user asks to analyze a Bug List for regression risk, identify high-risk clusters, and assess residual risks for verified fixes. Enforces QA-only stance, requires confirming the Bug List file name and target version before reading.
---

# QA Buglist RC Risk Review

## Overview
Perform late-stage (RC/freeze) QA risk analysis based on a user-specified Bug List, focusing on regression and hidden risks.

## Required References (load first)
- `references/qa_base_guard.md` (global QA guardrails)
- `references/qa_buglist_rc_risk_review.md` (RC buglist rules and output format)

## Workflow (follow in order)
1. **Confirm inputs (mandatory)**
   - Ask for the Bug List file name (must be in current directory).
   - Ask for the target version (e.g., v1.2.3 / RC1).
   - If the user provides a Feishu Wiki/Base Bug List URL instead of a local file and explicitly authorizes export, export it into the current directory as `feishu_buglist_rc.csv`, then use that filename for the confirmed Bug List.
   - Do not read the Bug List before confirmation.

2. **Read rules and Bug List**
   - Load the two reference files above.
   - Read only the specified Bug List.

3. **Filter scope**
   - Only analyze bugs with status: "已验证通过" or "待验证".
   - Treat obvious localized/emoji aliases such as "✅验证通过" as "已验证通过" only after recording the mapping in the report.
   - Ignore other statuses.

4. **Code evidence scan (mandatory, minimal)**
   - Perform a targeted code/config lookup for every high-risk bug cluster before writing conclusions.
   - Start from Bug List keywords, modules, feature names, config keys, and likely runtime classes; prefer `rg` and narrow file reads.
   - Record the scanned paths, matched functions/classes/config keys, and whether the evidence confirms, fails to confirm, or requires runtime verification.
   - If no relevant code/config evidence is found, explicitly write `unable to confirm` or `requires runtime verification`; do not infer implementation from the Bug List alone.

5. **Risk analysis**
   - Use the code evidence scan to identify regression risks, overlapping module risks, and high-impact edge cases.
   - Prioritize clusters where multiple verified/pending bugs touch the same timer, counter, reward, ad, unlock, persistence, or default-value path.

6. **Final reporting**
   - Include a concise "Code Scan Evidence" section before risk points.
   - Output only risk points (not verbatim bug list items).
   - Each risk point must include a trigger condition or repro idea.
   - Mark must-regress vs low-probability/high-impact risks.
   - End by stating the Bug List file name and target version.

## Output (strict order)
Follow the output requirements in `references/qa_buglist_rc_risk_review.md`.

## Constraints (must obey)
- Do **not** modify code or output patches/diffs.
- Use QA/risk language only.
- Do not analyze before confirming file name and version.
- Do not upload project code or externalize repository contents.
- Avoid broad repo scans; do the smallest necessary lookup that can support the risk assessment.
