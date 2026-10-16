---
name: handover
description: Finish a verified feature branch — push it and open a draft pull/merge request that links the spec and diagrams, lists ACs with evidence and asks for human review; or keep it local, or discard it on explicit request. Never merges. Use at the end of /sdd-kit:sdd, or for /sdd-kit:handover.
disable-model-invocation: true
argument-hint: "<ID> [pr|keep|discard]"
---

1. **Check**: `state.json.phase == verified`, tests green in the worktree right now (`verify`), working tree clean, branch is not protected.
2. **Choose the ending.** Default: `pr` at level `push`, `keep` below it. Otherwise ask the human with these options:
   - `pr` — push and open a draft PR/MR (below).
   - `keep` — leave the branch and worktree as they are; report the path.
   - `discard` — delete the branch and worktree. Only after the human types `discard <ID>`; list the commits that will be lost first.
   There is no merge option. Merge is the human's, in the VCS UI.
3. **pr**: `git push -u origin <branch>`, then a **draft** PR/MR via `gh pr create --draft`, `glab mr create --draft` or a configured MCP connector. Body:
   - Before / After in plain language
   - Links: `spec.md`, `plan.md`, diagrams (embed the Mermaid block so it renders), prototype / Figma if they exist
   - AC table: AC → test(s) → verifier evidence
   - Rulings and parked findings from the ledger
   - How to test locally (from CLAUDE.md)
4. A configured tracker connector gets a comment with the PR link. Do not change ticket status unless asked.
5. Record the result in `side_effects` and `ledger.md`, set `phase: handed-over`, and tell the human: review, testing and merge are theirs.

---
The ending options follow `finishing-a-development-branch` from obra/superpowers (MIT, © Jesse Vincent), without its merge path.

---
The pr / keep / discard options are adapted from `finishing-a-development-branch` in obra/superpowers (MIT, © Jesse Vincent). See THIRD_PARTY_NOTICES.md.
