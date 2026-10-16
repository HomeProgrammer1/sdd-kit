---
name: worktree
description: Create or verify the isolated git worktree for one /sdd-kit:sdd run and prove a clean baseline before any code changes.
user-invocable: false
---

# Isolated workspace per feature

Each feature gets its own worktree so parallel features, a dirty main checkout, and the human's own edits never collide.

1. **Already isolated?** If `state.json.worktree` exists and `git -C <path> rev-parse --abbrev-ref HEAD` equals `state.json.branch`, reuse it and skip to step 4.
2. **Pick the location**: `.worktrees/<ID>-<slug>` inside the repo. Check `git check-ignore -q .worktrees/` — if it is not ignored, add `.worktrees/` to `.gitignore` and commit that one line first (never commit worktree contents).
3. **Create**: `git worktree add .worktrees/<ID>-<slug> -b feat/<ID>-<slug> <default-branch>`. Never create the feature branch from another feature branch unless the plan says so.
4. **Baseline**: inside the worktree run install and the unit test command from CLAUDE.md.
   - Green → record `worktree`, `base_sha` (`git rev-parse HEAD`) and the baseline numbers in `state.json`.
   - Red → pause: the failures are not ours. Report them; do not start tasks on a red baseline unless the human says to.
5. Every later dispatch names the worktree path as the working directory.

Cleanup is the human's call after merge: `git worktree remove .worktrees/<ID>-<slug>`.

---
Adapted from the `using-git-worktrees` skill of obra/superpowers (MIT, © Jesse Vincent). See THIRD_PARTY_NOTICES.md.
