---
name: commit
description: Analyse the staged/unstaged diff and create one Conventional Commit for one task, referencing the task and AC IDs. Use for /sdd-kit:commit or when the orchestrator commits an approved task.
argument-hint: "[T-n]"
allowed-tools: Bash(git status *), Bash(git diff *), Bash(git add *), Bash(git commit *), Bash(git log *)
---

1. `git status` and `git diff` — confirm the diff matches one task; unrelated changes → stop and ask.
2. Never stage `.env*`, keys, build output, or files outside the task.
3. Message:
   ```
   <type>(<scope>): <imperative summary, ≤ 72 chars>

   <why, 1–3 lines>

   Refs: <ID> T-n (AC-1, AC-2)
   ```
   `type` ∈ feat, fix, refactor, test, docs, chore, perf, build, ci.
4. Commit without `--no-verify`. If a pre-commit hook fails, fix the cause and commit again (new commit, never `--amend` a pushed commit).
