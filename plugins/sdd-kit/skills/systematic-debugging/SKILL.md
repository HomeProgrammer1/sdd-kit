---
name: systematic-debugging
description: sdd-kit's root-cause-first debugging procedure — reproduce, isolate, one hypothesis at a time, regression test. Loaded by sdd-kit agents when something fails unexpectedly during a /sdd-kit:sdd run.
user-invocable: false
---

1. **Reproduce** with one exact command. Can't reproduce → gather more data (logs, versions, env), don't guess.
2. **Read the error fully**: first error, not the last; full stack; the line it names.
3. **Isolate**: smallest input, `git bisect` / `git stash` against a known-good state, comment out halves.
4. **Hypothesis**: write it down ("X is null because Y runs before Z"). Design a check that could prove it **wrong**. Run it.
5. **Fix the root cause**, not the symptom. No `try/catch` to silence, no sleeps for races, no retries for logic bugs.
6. **Regression test** that fails without the fix.

Stop after 3 disproven hypotheses or 3 failed fixes: report what you know (repro, hypotheses tried, evidence). That is a `BLOCKED`, not a failure of effort.
