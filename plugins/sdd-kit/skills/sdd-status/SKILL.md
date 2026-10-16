---
name: sdd-status
description: Show the state of every SDD run in specs/ — phase, autonomy level, pause reason, task progress, next action. Use for /sdd-kit:sdd-status or "where are we with the features".
disable-model-invocation: true
allowed-tools: Read, Glob, Bash(ls *)
---

For each `specs/*/state.json` (newest first) print one row:

`<ID> | <phase> | level=<autonomy> | tasks <done>/<total> | <PAUSED: reason | next: command>`

Task counts come from `tasks.md` checkboxes. Then, for any paused run, one line saying exactly what the human must do. Read only; change nothing.
