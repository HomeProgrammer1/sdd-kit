---
paths:
  - "specs/**"
---
# Specs folder rules
- `spec.md` is approved by a human before `plan.md` is written; `plan.md` is approved before code.
- Never edit an approved spec silently: add a dated entry to its Decisions table and set Status back to Draft.
- Keep IDs stable: never renumber ACs or tasks; deprecate with ~~strikethrough~~.
- `state.json` is written only by the /sdd-kit:sdd orchestrator.
