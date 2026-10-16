---
name: plan-format
description: Structure for plan.md (technical design), tasks.md (ordered testable tasks mapped to ACs) and ADRs. Use whenever planning or reviewing a plan.
user-invocable: false
---

Templates: `${CLAUDE_SKILL_DIR}/templates/plan.md`, `tasks.md`, `adr.md`.

## plan.md rules
- Start from the existing architecture; name the analogous feature you follow.
- Every new dependency: why, licence, maintenance status, alternative rejected.
- Data changes: schema diff, migration + rollback, backfill, effect on existing rows.
- Interfaces: request/response or function signatures, error cases, versioning.
- Risks: top 3 with mitigation. Rollout: flag / staged / big bang, and how to roll back.

## tasks.md rules
- `- [ ] T-n [P?] <imperative title> — ACs: AC-1, AC-3 — files: <paths> — verify: <test or command>`
- One task = one commit, ideally < 300 changed lines, leaves the build green.
- Order: contracts/types → data → domain logic → API/UI → wiring → docs.
- `[P]` only when tasks share no files.
- Last task is always "Update docs/README/CHANGELOG as needed".

## ADR
One file per decision that is expensive to reverse. Status: Proposed → Accepted by the human at Gate 2.
