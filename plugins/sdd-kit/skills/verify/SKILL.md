---
name: verify
description: sdd-kit's evidence gate — every build, lint, typecheck and test command from CLAUDE.md, run after the last edit, with real numbers — before an sdd-kit agent reports a task done, commits or opens a PR.
user-invocable: false
---

## The rule
**No completion claim without fresh evidence.** If the command that proves it did not run after your last edit, you cannot claim it.

## Gate (before any status or success statement)
1. **Identify** the command that proves the claim.
2. **Run** it in full, now.
3. **Read** the whole output: exit code, failure count, warnings.
4. **Compare**: does the output prove the claim? If not, state the actual status with the output.

| Claim | Needs | Not enough |
|---|---|---|
| Tests pass | test command output, 0 failures | an earlier run, "should pass" |
| Lint clean | linter output, 0 errors | a partial check |
| Build works | build exit 0 | lint passing |
| Bug fixed | the original symptom's test passes | code changed |
| Regression test works | seen red, then green | passes once |
| Subagent finished | the diff shows the change | its report says so |
| Requirements met | AC-by-AC checklist | tests green |

Red flags in your own text: "should", "probably", "seems to", celebrating before output, trusting a report.

## Procedure
1. Run, in order, every command in CLAUDE.md → Commands that is not `n/a`: install (only if the lockfile changed) → build → lint → typecheck → unit tests → e2e/UI (when the work touches UI or the verifier asks).
2. Report per command: ✅/❌, counts (passed/failed/skipped), new warnings, coverage before → after if available.
3. A command that cannot run (missing tool, needs a secret) is `⚠️ not run: <reason>`, never ✅.
4. Any ❌ → `systematic-debugging`. "Flaky" needs one re-run and both outputs.

---
The evidence table and gate are adapted from `verification-before-completion` in obra/superpowers (MIT, © Jesse Vincent). See THIRD_PARTY_NOTICES.md.
