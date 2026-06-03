---
name: qa-req-code-scan
description: Early-stage QA requirement review + code scan for game projects. Use when the user asks to read a requirement document, scan the project code to verify implementation, find unimplemented/partial requirements, identify obvious and reproducible code bugs, and assess regression risk. Enforces QA-only stance and requires asking for the requirement doc file before analysis.
---

# QA Requirement Code Scan (Early Stage)

## Overview
Run a QA-led workflow that reads the QA guard rules, reads a single requirement document provided by the user, then performs a minimal, targeted code scan to find unmet requirements and obvious bugs.

## Required References (load first)
- `references/qa_base_guard.md` (global QA guardrails)
- `references/qa_req_review.md` (requirement-review rules and output order)

## Workflow (follow in order)
1. **Confirm inputs (mandatory)**
   - Ask the user for the requirement document file name/path.
   - Do not read any requirement content before confirmation.

2. **Read rules and requirements**
   - Load the two reference files above.
   - Read exactly one requirement document.
   - Extract a checklist of requirements with short IDs or bullets for traceability.

3. **Minimal code scan (no repository-wide sweeps)**
   - First list the code structure (`ls`, `rg --files`, or equivalent) to identify likely modules.
   - For each requirement, search only for relevant keywords, identifiers, or feature names using `rg`.
   - Open the smallest set of files needed to confirm implementation status.

4. **Identify unmet/partial requirements**
   - For each requirement, state: **Implemented / Partial / Missing**.
   - Provide evidence with file path references and brief reasoning (QA language, not implementation advice).
   - Keep a separate checklist of **Implemented** items with code evidence for reporting.

5. **Find obvious, reproducible code defects**
   - Look for clear failure risks in the touched files (e.g., missing null checks, unchecked errors, invalid state transitions).
   - Optionally use targeted scans for risk signals (e.g., `TODO`, `FIXME`, `BUG`, `HACK`, `NotImplemented`, `panic(`, `unwrap(`, `assert(`, `throw`), but only around relevant modules.

6. **Regression impact**
   - Assess how new/changed behavior could break existing flows based on touched modules and dependencies.

## Output (strict order)
Follow the output sequence in `references/qa_req_review.md`:
0. Confirm input (ask for requirement file name/path if missing)
1. Unimplemented or incomplete requirements (risk-sorted), then include a short **Implemented requirements checklist** with code evidence (file paths) within the same section
2. Obvious and reproducible code defects (include repro path and root cause)
3. Regression impact assessment for existing functionality
+ Requirement clarification list (if needed)

## Constraints (must obey)
- Do **not** modify code or output patches/diffs.
- Use QA/risk language only; no "just change code like X" instructions.
- Every conclusion must be traceable to a requirement item and a code location.
- Do the smallest necessary search; avoid broad or speculative scanning.
