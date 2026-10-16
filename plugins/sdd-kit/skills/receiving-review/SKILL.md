---
name: receiving-review
description: How sdd-kit's implementer handles reviewer findings in a /sdd-kit:sdd fix round — verify each finding against the code, fix one at a time with a test, and push back with evidence when a finding is wrong.
user-invocable: false
---

# Receiving review findings

Review findings are claims to verify, not orders to obey and not criticism to placate.

## For each finding
1. **Read** the whole list first. Findings are often related.
2. **Restate** the requirement in one technical sentence. If you cannot, it is unclear.
3. **Verify** it against the code: reproduce, read the call sites, run the focused test.
4. **Evaluate**: is it correct *for this codebase and this spec*?
5. **Act**:
   - Correct → fix it, add or adjust a test that would have caught it, run the test.
   - Wrong → do not change code. Reply in your report with the evidence (file:line, test output, spec AC) under `PUSHBACK`.
   - Unclear → do not implement any item yet; return `NEEDS_CONTEXT` listing which items are unclear and why.

## Rules
- No performative agreement ("Great point!", "You're absolutely right"). State the fix or the evidence.
- One finding at a time; run its test before the next.
- A finding that conflicts with the spec or plan text goes back to the orchestrator as `NEEDS_CONTEXT`; the orchestrator rules on it.
- Never "fix" a finding by weakening a test or widening scope.

Report additions:
```
FINDINGS_ADDRESSED
  F1: fixed — <file:line> — test <name>
  F2: pushback — <evidence>
```

---
Adapted from the `receiving-code-review` skill of obra/superpowers (MIT, © Jesse Vincent). See THIRD_PARTY_NOTICES.md.
