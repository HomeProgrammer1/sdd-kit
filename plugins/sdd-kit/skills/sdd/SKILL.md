---
name: sdd
description: Spec-driven delivery orchestrator. Takes a feature request or ticket from idea to a reviewed pull request through discovery → spec (+ diagrams) → plan (+ optional design) → tasks → implement → review → verify → handover, with human gates, or a quick lane for small fixes. Use when the user runs /sdd-kit:sdd or asks to build a feature end to end.
argument-hint: "<ID or new request> [--level=spec|plan|implement|push] [--quick] [--design] [--figma]"
disable-model-invocation: true
---

# /sdd-kit:sdd — spec-driven delivery

You are the **orchestrator**. You stay in the main session, keep your own context small, and do the work through subagents. You route on their `STATUS` / `SPEC` / `QUALITY` / `VERDICT` lines. You alone write `state.json` and `ledger.md`, commit and push.

Arguments: `$ARGUMENTS`

Names: this plugin's agents are `sdd-kit:analyst`, `sdd-kit:architect`, `sdd-kit:implementer`, `sdd-kit:reviewer`, `sdd-kit:branch-reviewer`, `sdd-kit:verifier`, `sdd-kit:security-auditor`, `sdd-kit:debugger`; its skills are `sdd-kit:<name>`. Optional companion plugins: `sdd-diagrams` (renders and exports diagrams), `sdd-design` (prototypes), `sdd-figma` (Figma export). Use them only when installed.

Load now: `sdd-kit:autonomy-contract`, `sdd-kit:run-state`. Read CLAUDE.md → Stack profile and load those `sdd-kit:stack-*` skills.

**Other plugins.** Other workflow plugins (for example a general TDD, brainstorming or planning collection) may stay installed. For the duration of this run, the steps below and the `sdd-kit:` skills take precedence; outside the run, theirs apply as usual. Do not disable or edit another plugin.

## Working rules
- **Artifacts travel as files, not as pasted text.** Briefs, reports and diffs go under `specs/<ID>/work/` (gitignored); dispatches name the paths. Everything you paste stays in your context for the rest of the run.
- **The ledger is your memory.** After compaction trust `ledger.md`, `state.json` and `git log` over your recollection. Never re-dispatch a task the ledger marks complete.
- **Rulings, not stalls (after Gate 2 only).** During implementation, decide ambiguities the spec and plan leave open and log each as `Ruling: <what> — <why> — <cost if wrong>` in the ledger. Stop only for what `sdd-kit:autonomy-contract` lists as always-pause.
- **Pick the model per dispatch** (pass it explicitly; an omitted model inherits the most expensive one):
  | Work | Model |
  |---|---|
  | Task whose brief contains the complete code / single-file mechanical fix | haiku |
  | Typical task, task review, scoped re-review | sonnet |
  | Multi-file integration, debugging, fix rounds 4–5 | the session model or opus |
  | Analyst, architect, branch review, security audit | opus |
- **Batch small same-shape tasks** (the same tiny edit across files) into one dispatch and one review.

## Step 0 — Resolve the run
- Existing `specs/<ID>-*` → read `state.json` + `ledger.md` and **resume from `phase`**. Never redo what `side_effects` records.
- New → create `specs/<ID>-<slug>/` (ID = ticket key, else next `F-NNN`), `state.json` (`phase: discovery`, `autonomy` from `--level`, default `spec`; `lane: quick` with `--quick`, else `full`; `options.design` / `options.figma` from flags), `ledger.md` with first line `# Ledger — <ID>`.
- Either way set `state.json` → `"session": "${CLAUDE_SESSION_ID}"` before any other step. The guard applies sdd-kit's merge/deploy/secret rails to the session recorded there (and to sdd-kit agents), and leaves every other session alone.
- Then confirm the guard sees it: `bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" sdd_session.py --status --session "${CLAUDE_SESSION_ID}"`. Expected: `<ID>: rails on for this session (…)`. Any other output (no session recorded, placeholder not substituted, Python not found) → tell the human in one line what it says, then continue. While a run has no usable session the guard applies its rails to every session in this project, so nothing runs unprotected.
- `lane: quick` → follow **Quick lane** below instead of Steps 1–6.

## Quick lane (`--quick`)
For a small change only: a bug fix or tweak touching at most 3 files, with no new screen, public API, schema or dependency, and nothing in auth, payments, permissions or secrets. About 3 subagent runs instead of 16 or more.
1. Write `spec.md` yourself: Goal, the ACs and, for a bug, the reproduction. No discovery; no diagram unless the change alters a flow the existing diagram shows. One task in `tasks.md`.
2. One gate: show the ACs and the task in one message and ask "Approve?". `--level` still caps how far the run goes.
3. Load `sdd-kit:worktree` as in Step 4.1.
4. One **implementer** (sonnet), one **reviewer** (sonnet), at most 2 fix rounds, then commit as in Step 5.5.
5. **verifier** (sonnet) for the ACs. **security-auditor** only if the diff touches anything the first paragraph excludes.
6. Step 7 as usual.
The moment the change grows past these limits, log `Ruling: leaving the quick lane — <why>` in the ledger, set `lane: full` and continue at Step 2.

## Step 1 — Discovery
Load `sdd-kit:discovery` and run it here, in the main session. Output: `discovery.md`.

## Step 2 — Specify (+ diagrams) → GATE 1
1. Dispatch **analyst** (opus) with: `discovery.md` path, the original request verbatim, the folder path, any ticket ID.
2. The spec must contain its **How it works** Mermaid diagrams (see `spec-format`). If `sdd-diagrams` is installed, load `sdd-diagrams:feature-diagrams` to validate and render them (SVG, optional `.drawio`).
3. Open questions → ask the human in one message, one line per question with the recommended default.
4. `phase: spec-review`. **Stop** unless the level is above `spec`. Show: spec path, AC count, diagrams, open questions. Ask: "Approve the spec?"

## Step 3 — Plan (+ design) → GATE 2
1. On approval set `approvals.spec`. Dispatch **architect** (opus) with the spec path.
2. `UNCOVERED_ACS` not empty → send back once; still uncovered → pause.
3. If `options.design` and `sdd-design` is installed: load `sdd-design:prototype` (it checks the design system first and pauses if there is none).
4. If `options.figma` and `sdd-figma` is installed: load `sdd-figma:figma-export` for diagrams (and screens if step 3 ran).
5. `phase: plan-review`. **Stop** unless the level is above `plan`. Show: task count, ADRs, top risks, prototype/Figma links.

## Step 4 — Prepare implementation
1. Set `approvals.plan`. Load `sdd-kit:worktree`: isolated worktree + green baseline, record `base_sha`.
2. **Pre-flight scan** of `tasks.md`, written to the ledger as a table, not a verdict: one row per pair of tasks sharing a file or interface (what one produces vs what the other consumes, finding); one row per task (do its own tests, files and steps agree?). Rule on every conflict against the spec before Task 1.

## Step 5 — Task loop
For each task in order (`[P]` tasks touching disjoint files may run in parallel):
1. Record `BASE = git rev-parse HEAD`. Write the task brief to `work/T-n.brief.md`: task text, the AC texts verbatim, relevant plan.md sections, decisions and rulings it depends on, exact values to use verbatim.
2. Dispatch **implementer** with the brief path, the worktree path and the report path `work/T-n.report.md`.
   - `NEEDS_CONTEXT` → answer from spec/plan/ledger, else ask the human.
   - `BLOCKED` → **debugger** (`MODE: diagnose`) once, then re-dispatch with the root cause, or pause.
3. Write the diff to `work/T-n.diff` (`git log --oneline BASE..HEAD; git diff --stat; git diff -U10`, or the working-tree diff). Dispatch **reviewer** with brief, report and diff paths.
4. `SPEC: PASS` and `QUALITY: APPROVE` → step 6. Otherwise a **fix round**:
   - Rounds 1–3: same implementer brief + findings file (`work/T-n.findings.R.md`); it follows `sdd-kit:receiving-review`. Re-review is **scoped** to the findings and the fix diff.
   - Rounds 4–5: a fresh implementer on a stronger model with the full history.
   - After round 5: adjudicate each open finding. Load-bearing (wrong behaviour, security, AC not met) → pause. Otherwise park it in the ledger with a ruling and continue.
5. Load `sdd-kit:commit` and commit the task (`T-n` in the message). Tick it in `tasks.md`; ledger line `T-n: complete <sha>`; `side_effects` entry.

## Step 6 — Branch review and verification
1. Dispatch **branch-reviewer** (opus) once. Findings → ONE fix dispatch, one scoped re-review, then adjudicate residuals as above.
2. Dispatch **verifier** for all ACs. FAIL → defects become `T-fix-n` → Step 5. Budget: 2 verify rounds.
3. Dispatch **security-auditor**. FAIL → fix tasks as above.
4. If `sdd-diagrams` is installed and the code changed what a diagram shows, regenerate the diagrams and note it.
5. `phase: verified`.

## Step 7 — Handover → GATE 3
Load `sdd-kit:handover`. At level `push` it pushes and opens a **draft** PR; otherwise it reports the branch ready locally. Merge, release and deploy are always the human's.

## Reporting to the human (every stop)
Lead with what you need from them. Then: phase, what was done (counts, paths), rulings taken, concerns, the next command. No logs; link files.

---
The task loop (ledger, pre-flight scan, two-verdict review, fix-round escalation, branch review, model selection) is adapted from `subagent-driven-development` in obra/superpowers (MIT, © Jesse Vincent). See THIRD_PARTY_NOTICES.md.
