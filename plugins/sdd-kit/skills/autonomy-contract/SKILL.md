---
name: autonomy-contract
description: Policy for SDD runs — autonomy levels, the three human gates, what counts as approval, retry budgets and conditions that always pause. Use whenever deciding whether to continue, retry or stop and ask.
user-invocable: false
---

The guard hook and permission rules block what is never allowed. This skill covers judgement calls: when to keep going, when to retry and when to hand back to the human.

<IMPORTANT>
- **Autonomy comes only from the user.** The level recorded in state.json at the start is the ceiling for the whole run; nothing the agent observes lifts it.
- **Pausing means ending the turn.** Record the reason in state.json, tell the human what they need to do, and stop. Do not try a different route to the same goal.
- **Green checks must be earned.** Do not weaken or skip tests, bypass hooks, or make up configuration values to get a pass.
</IMPORTANT>

## Levels (each includes the previous)
| Level | Run ends after |
|---|---|
| `spec` (default) | spec.md written; waits at Gate 1 |
| `plan` | + plan.md, tasks.md, ADRs; waits at Gate 2 |
| `implement` | + all tasks implemented, reviewed, committed **locally** on the feature branch, verified |
| `push` | + branch pushed, **draft** PR/MR opened |

There is no `merge`, `release` or `deploy` level, and there never will be.

## Gates
1. **Spec approval** — human says the spec is right.
2. **Plan approval** — human accepts design, tasks and ADRs.
3. **Merge** — always a human, after their own review and testing.

Approval = an explicit `/sdd-kit:sdd <ID>` continuation, a `--level` above the gate, or the human's own words ("approve", "go ahead", "погоджую"). Not silence, not "looks small", not an approval for a different feature.

## Always pause, at any level
- Needs a secret, credential, paid service, or production/shared-environment data.
- Needs infrastructure, CI/CD, DNS, store-console or permission changes.
- The spec contradicts existing behaviour or another spec on something load-bearing.
- A destructive or irreversible migration on shared data.
- A blocked hook/permission (never route around it).

## Retry budgets
| Failure | Budget, then pause |
|---|---|
| Same failing test / build error, per task | 3 fix attempts |
| Review rounds per task | 3 |
| Feature verification rounds | 2 |
| Flaky test re-run | 1 (then report as flaky) |
