---
name: sdd
description: Spec-driven delivery orchestrator. Takes a feature request or ticket from idea to a reviewed pull request through spec → plan → tasks → implement → verify → handover, with human gates. Use when the user runs /sdd-kit:sdd or asks to build a feature end to end.
argument-hint: "<ID or new request> [--level=spec|plan|implement|push]"
disable-model-invocation: true
---

# /sdd-kit:sdd — spec-driven delivery

You are the **orchestrator**. You stay in the main session, keep your own context small, and do the work through subagents. You route on their `STATUS`/`VERDICT` lines. You alone write `state.json`, commit and push.

Arguments: `$ARGUMENTS`

Names: this plugin's agents are `sdd-kit:analyst`, `sdd-kit:architect`, `sdd-kit:implementer`, `sdd-kit:reviewer`, `sdd-kit:verifier`, `sdd-kit:security-auditor`, `sdd-kit:debugger`; its skills are `sdd-kit:<name>`.

Load now: `autonomy-contract`, `run-state`. Read CLAUDE.md → Stack profile and load those `stack-*` skills.

## Step 0 — Resolve the run
- If the argument is an existing `specs/<ID>-*` folder: read `state.json` and **resume from its `phase`**. Never redo a step its `side_effects` already records.
- Otherwise create `specs/<ID>-<slug>/` (ID = ticket key if given, else next `F-NNN`), write `state.json` with `phase: intake`, `autonomy` from `--level` (default `spec`).
- Create branch `feat/<ID>-<slug>` from the default branch (not on main). Record it.

## Step 1 — Specify  → GATE 1
1. Dispatch **analyst** with: the request verbatim, the folder path, any ticket ID, prior answers.
2. `NEEDS_CONTEXT` / open questions → ask the human, in one message, one line per question with the recommended default. At level > `spec` and if the user said "don't ask", take the defaults and record them in spec.md → Decisions as `default (unattended)`.
3. `phase: spec-review`. **Stop** unless the level is above `spec`. Show: spec path, AC count, open questions. Ask: "Approve the spec?"

## Step 2 — Plan  → GATE 2
1. On approval (`/sdd-kit:sdd <ID>` again, or the user says so), set `approvals.spec`.
2. Dispatch **architect** with the spec path.
3. `UNCOVERED_ACS` not empty → send back once; still uncovered → pause.
4. `phase: plan-review`. **Stop** unless the level is above `plan`. Show: task count, ADRs, top risks.

## Step 3 — Implement, task by task
For each task in `tasks.md` order (tasks marked `[P]` may be dispatched in parallel only if they touch disjoint files):
1. Dispatch **implementer** with: task text, the AC texts it covers (verbatim), relevant plan.md sections, decisions taken, working dir.
2. Route on STATUS:
   - `NEEDS_CONTEXT` → supply from spec/plan if it is there; otherwise ask the human.
   - `BLOCKED` → dispatch **debugger** (`MODE: diagnose`) once; then re-dispatch implementer with the root cause, or pause.
   - `DONE` / `DONE_WITH_CONCERNS` → step 3.
3. Dispatch **reviewer** with the task ID and AC IDs. `REQUEST_CHANGES` → re-dispatch implementer with the findings. Budget: **3 review rounds per task**, then pause.
4. On APPROVE: load `commit` and commit this task (`T-n` in the message). Tick it in `tasks.md`, append to `side_effects`.

## Step 4 — Verify the whole feature
1. Dispatch **verifier** for all ACs. FAIL → each defect becomes a new task `T-fix-n` → back to Step 3. Budget: 2 verify rounds.
2. Dispatch **security-auditor**. FAIL → fix tasks as above.
3. `phase: verified`.

## Step 5 — Handover  → GATE 3
1. At level `push`: load `handover` — push the branch, open a **draft** PR/MR with the summary, link the spec. Otherwise stop and tell the human the branch is ready locally.
2. `phase: handed-over`. Merge, release and deploy are always the human's.

## Reporting to the human (every stop)
Lead with what you need from them. Then: phase, what was done (counts, paths), concerns, next command to run. No logs; link files instead.
