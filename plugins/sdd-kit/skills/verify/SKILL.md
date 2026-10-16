---
name: verify
description: Full local verification before claiming a task or feature is done — runs every build, lint, typecheck and test command from CLAUDE.md and reports real numbers. Use before any DONE, commit or handover.
user-invocable: false
---

1. Run, in order, every command in CLAUDE.md → Commands that is not `n/a`: install (only if lockfile changed) → build → lint → typecheck → unit tests → e2e/UI (if the task touches UI or the verifier asks).
2. Run them **after your last edit**. A ✅ from before an edit is not evidence.
3. Report per command: ✅/❌, counts (passed/failed/skipped), new lint warnings, coverage before → after if available.
4. A command that cannot run (missing tool, needs a secret) is reported as `⚠️ not run: <reason>`, never as ✅.
5. Any ❌ → `systematic-debugging`, not "probably flaky". Flaky claims need one re-run and the two outputs.
