---
name: sdd-status
description: Show the state of every SDD run in specs/ — phase, autonomy level, pause reason, task progress, next action. Use for /sdd-kit:sdd-status or "where are we with the features".
disable-model-invocation: true
allowed-tools: Read, Glob, Bash(ls *), Bash(bash *)
---

For each `specs/*/state.json` (newest first) print one row:

`<ID> | <phase> | level=<autonomy> | tasks <done>/<total> | <PAUSED: reason | next: command>`

Task counts come from `tasks.md` checkboxes. Then, for any paused run, one line saying exactly what the human must do.

Last, run `bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" sdd_session.py --status --session "${CLAUDE_SESSION_ID}"` and print its lines under **Guard**. If it reports a run with no session recorded, add: "The merge/deploy rails apply to every session in this project until that run is resumed or closed." If it prints nothing, say the guard is not running because Python 3 was not found.

Read only; change nothing.
