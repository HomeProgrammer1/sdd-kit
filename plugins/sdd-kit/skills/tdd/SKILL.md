---
name: tdd
description: sdd-kit's test-first procedure for implementing a task from specs/<ID>/tasks.md — red, green, refactor, one behaviour at a time, plus the bug-fix variant. Loaded by sdd-kit agents during /sdd-kit:sdd runs.
user-invocable: false
---

## Cycle (one behaviour at a time)
1. **Red** — write one test for the next behaviour from an AC. Run just that test file. It must fail **for the right reason** (assertion, not import/compile error). Keep the failure message for your report.
2. **Green** — the smallest code that passes. Run the file again.
3. **Refactor** — clean up with tests green. No new behaviour.
4. Repeat. When the task's ACs are covered, run the full `verify` skill.

## Bug fix
Test that reproduces the bug → see it fail → fix the root cause → see it pass → temporarily revert the fix and confirm the test fails again → restore.

## Test quality
- Assert observable behaviour, not private calls. Name tests after the behaviour: `rejects_expired_reset_token`.
- One reason to fail per test. Deterministic: no real clock, network, randomness or order dependence; inject them.
- Use the lowest level that proves the AC: unit → integration → UI/e2e.
- A new query runs against a real (containerised or in-memory) store at least once; a mocked repository does not prove a query.

## Never
Skip/only/xfail to pass; loosen an assertion; snapshot-update without reading the diff; delete a failing test.
