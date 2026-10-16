---
name: run-state
description: Schema and rules for specs/<ID>/state.json and ledger.md, the on-disk memory of a /sdd-kit:sdd run that survives restarts and compaction. Use when starting, resuming, pausing or advancing an sdd-kit run.
user-invocable: false
---

Two files hold a run's memory: `state.json` (machine state) and `ledger.md` (human-readable history: pre-flight scan, rulings, task completions, parked findings). Only the orchestrator writes them.

The orchestrator writes `state.json` Write it **before** reporting to the human and **after** every side effect (branch, commit, push, PR, tracker update), so a crash never loses or duplicates work.

```json
{
  "id": "F-001",
  "slug": "password-reset",
  "profile": ["web", "backend"],
  "autonomy": "spec",
  "lane": "full",
  "phase": "discovery",
  "session": "<session id of the session running /sdd-kit:sdd>",
  "branch": "feat/F-001-password-reset",
  "worktree": ".worktrees/F-001-password-reset",
  "base_sha": "9f8e7d6",
  "options": { "design": false, "figma": false },
  "approvals": { "spec": null, "plan": null },
  "tasks": { "T-1": "done", "T-2": "in-progress" },
  "retries": { "T-2:review": 1 },
  "pause": null,
  "side_effects": [
    { "at": "2026-10-16T16:00:00Z", "kind": "branch", "ref": "feat/F-001-password-reset" },
    { "at": "2026-10-16T16:40:00Z", "kind": "commit", "ref": "a1b2c3d", "task": "T-1" }
  ],
  "updated_at": "2026-10-16T16:40:00Z"
}
```

- `phase`: `discovery → specifying → spec-review → planning → plan-review → implementing → reviewing → verifying → verified → handed-over → done` (or `abandoned`).
- `approvals.*`: `{ "by": "<name>", "at": "<ISO time>", "how": "/sdd-kit:sdd F-001 | message" }`.
- `pause`: `{ "reason": "...", "needs": "what the human must do", "at": "..." }`; cleared on resume.
- `autonomy` is set once from the user and never raised by the run.
- `lane`: `full` (default) or `quick` (`--quick`). A quick run may switch to `full`, never back.
- `session` is overwritten with the current session id on start and on every resume; the guard hook uses it to tell an SDD session from any other. A run in `done` or `abandoned` no longer counts. While an open run has no usable `session` (missing, or the `${CLAUDE_SESSION_ID}` placeholder written literally), the guard applies its rails to every session in the project, so close runs you stop working on (`phase: abandoned`).
- On resume: re-read, verify each side effect still exists (`git log`, `git branch`), then continue from `phase`.

## ledger.md
```markdown
# Ledger — F-001
## Pre-flight scan
| Tasks | Produces / consumes | Finding | Ruling |
|---|---|---|---|
## Rulings
- Ruling: <what> — <why> — <cost if wrong>
## Progress
- T-1: complete a1b2c3d
- T-2: fix round 2 (F1, F3 open)
## Parked findings
- T-2/F4 [MINOR] … — Ruling: accepted, revisit in branch review
```
Append only. One line per event. Resume reads the last line of each task.
