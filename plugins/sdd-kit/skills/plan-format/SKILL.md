---
name: plan-format
description: Structure and quality bar for sdd-kit plans — specs/<ID>/plan.md, tasks.md with right-sized checkable steps mapped to ACs, and ADRs. Use when writing or reviewing an sdd-kit plan.
user-invocable: false
---

Templates: `${CLAUDE_SKILL_DIR}/templates/plan.md`, `tasks.md`, `adr.md`.

Write for an engineer who has never seen this codebase or this spec. They write idiomatic code once they know the exact interface and the exact test. What they cannot know is what *you* decided: which files, names and signatures, which values from the spec, which tests prove each task. Write those down. DRY, YAGNI, TDD, frequent commits.

## plan.md
- Start from the existing architecture; name the analogous feature you follow.
- **File map first**: every file created or modified and its single responsibility. Files that change together live together; split by responsibility, not by layer.
- Interfaces: signatures / request-response, error cases, versioning.
- Data: schema diff, migration + rollback, backfill.
- Diagrams: add a Mermaid `sequenceDiagram` for any flow crossing ≥2 components and an `erDiagram` for any data model change (rules in `spec-format` → Diagrams).
- Every new dependency: why, licence, maintenance, alternative rejected.
- Risks (top 3) and rollout/rollback.

## tasks.md
**Right-sizing.** A task is the smallest unit that carries its own test cycle and is worth a reviewer's gate. Fold setup, config and docs into the task whose deliverable needs them. Split only where a reviewer could reject one task while approving its neighbour. Each task ends in an independently testable deliverable, ideally < 300 changed lines.

**Steps.** Each step is one action with a checkable result, typically: write the failing test → run it, see it fail → implement the minimum → run, see it pass → commit. Put exact values (numbers, strings, names) in the step text so they are copied, not re-invented.

Format:
```
- [ ] T-n [P?] <imperative title> — ACs: AC-1, AC-3
  files: <create/modify paths>
  steps:
    1. Write test `<name>` in <file> asserting <exact behaviour/value>
    2. Run `<command>` → expect FAIL: <reason>
    3. Implement <what> in <file>
    4. Run `<command>` → expect PASS
    5. Commit "<type>(<scope>): <summary>"
```
- Order: contracts/types → data → domain logic → API/UI → wiring → docs.
- `[P]` only when tasks share no files.
- End with a traceability table AC → tasks; every AC appears.

## ADR
One file per decision that is expensive to reverse. Status: Proposed → Accepted by the human at Gate 2.

---
Right-sizing and step granularity are adapted from `writing-plans` in obra/superpowers (MIT, © Jesse Vincent). See THIRD_PARTY_NOTICES.md.
