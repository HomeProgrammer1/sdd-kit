---
name: handover
description: Push the feature branch and open a draft pull/merge request that links the spec, lists ACs with evidence, and asks for human review. Never merges. Use at the end of /sdd-kit:sdd at level push, or for /sdd-kit:handover.
disable-model-invocation: true
argument-hint: "<ID>"
---

1. Confirm `state.json.phase == verified`, the branch is not protected, and the working tree is clean.
2. `git push -u origin <branch>` (the permission prompt is expected; the hook blocks protected branches and force pushes).
3. Open a **draft** PR/MR with the VCS CLI (`gh pr create --draft`, `glab mr create --draft`) or the configured MCP connector. Body:
   - Before / After in plain language
   - Spec: link to `specs/<ID>/spec.md`; Plan: `plan.md`
   - AC table: AC → test(s) → verifier evidence
   - Concerns and decisions taken by default
   - How to test locally (from CLAUDE.md)
4. If a tracker connector is configured, comment the PR link on the ticket. Do not change ticket status unless the user asked.
5. Record the PR URL in `side_effects`, set `phase: handed-over`, tell the human: review, test, merge are theirs.
