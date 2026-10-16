---
name: spec-format
description: The required structure and quality bar for specs/<ID>/spec.md — requirements, Given/When/Then acceptance criteria with IDs, NFRs, out of scope, open questions, self-check. Use whenever writing or reviewing a spec.
user-invocable: false
---

Copy `${CLAUDE_SKILL_DIR}/templates/spec.md` and fill every section. Delete hint comments.

## Rules
- **What and why, never how.** No class names, tables, endpoints or libraries.
- **Requirements** use EARS forms: "The system shall…", "When <trigger>, the system shall…", "While <state>, …", "If <unwanted condition>, then the system shall…".
- **Acceptance criteria**: `AC-n`, Given/When/Then, one behaviour each, observable from outside, with concrete values ("within 2 s", "max 50 items"), not "fast" or "many".
- Each functional requirement maps to ≥1 AC.
- **NFRs** only where they matter for this feature, each with a number: performance, accessibility (WCAG 2.2 AA for UI), security/privacy, offline behaviour (mobile), compatibility (browsers / OS versions).
- **Open questions** carry a recommended default so a human can answer "yes".

## Self-check (all must be true)
- [ ] A tester could write each AC's test without asking anything.
- [ ] No AC depends on an implementation detail.
- [ ] Every requirement maps to an AC; every AC maps to a requirement.
- [ ] Out of scope lists at least the obvious neighbours.
- [ ] No invented business rules: anything assumed is in Open questions.
