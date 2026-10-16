---
name: run-state
description: Schema and rules for specs/<ID>/state.json, the on-disk memory of an SDD run that survives session restarts and context compaction. Use whenever starting, resuming, pausing or advancing a run.
user-invocable: false
---

Only the orchestrator writes `state.json`. Write it **before** reporting to the human and **after** every side effect (branch, commit, push, PR, tracker update), so a crash never loses or duplicates work.

```json
{
  "id": "F-001",
  "slug": "password-reset",
  "profile": ["web", "backend"],
  "autonomy": "spec",
  "phase": "intake",
  "branch": "feat/F-001-password-reset",
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

- `phase`: `intake → spec-review → planning → plan-review → implementing → verifying → verified → handed-over → done` (or `abandoned`).
- `approvals.*`: `{ "by": "<name>", "at": "<ISO time>", "how": "/sdd-kit:sdd F-001 | message" }`.
- `pause`: `{ "reason": "...", "needs": "what the human must do", "at": "..." }`; cleared on resume.
- `autonomy` is set once from the user and never raised by the run.
- On resume: re-read, verify each side effect still exists (`git log`, `git branch`), then continue from `phase`.
