# Project instructions

<!-- Loaded into every session and every subagent. Keep under ~150 lines.
     Procedures live in .claude/skills, file-type rules in .claude/rules. -->

## Project
- Name: <PROJECT_NAME>
- What it is: <one sentence: who uses it and for what>
- Stack profile: <web | mobile | backend | web+backend | mobile+backend>
  Load the matching `stack-*` skill(s) before planning, implementing or verifying.

## Commands
<!-- Filled by /init-project. Every agent uses exactly these. -->
- Install:   `<cmd>`
- Build:     `<cmd>`
- Lint:      `<cmd>`
- Typecheck: `<cmd or n/a>`
- Unit test: `<cmd>`   (single file: `<cmd> <path>`)
- E2E / UI:  `<cmd or n/a>`
- Run local: `<cmd>`

## Layout
- `specs/<ID>-<slug>/` — one folder per feature: spec.md, plan.md, tasks.md, state.json
- `docs/adr/` — architecture decision records
- `<src dir>` — <what lives where>

## How work flows (spec-driven development)
1. No production code without an approved `spec.md` and `plan.md` for it. Use `/sdd-kit:sdd`.
2. The spec is the source of truth. If code and spec disagree, stop and say so; do not silently "fix" either.
3. Every change traces to an acceptance criterion ID (`AC-3`) or a task ID (`T-4`).
4. Humans approve the spec, approve the plan, and merge. Agents never merge, deploy or release.

## Conventions
- Follow the existing pattern next to the code you change over personal preference.
- Small, reviewable diffs: one task = one commit.
- Tests come first for behaviour changes and bug fixes (see `tdd` skill).
- Never weaken, skip or delete a test to get green.
- No secrets in code, logs, specs or commit messages. Config via environment.

## Definition of done (every task)
- Acceptance criteria covered by tests that were seen failing first.
- Build, lint, typecheck and tests all pass, run after the last edit.
- Reviewer verdict APPROVE; no unresolved BLOCKER findings.
- `tasks.md` and `state.json` updated.
