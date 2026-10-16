---
name: discovery
description: The short interview that opens a /sdd-kit:sdd run for a new feature — what the human wants and why, one question at a time — producing specs/<ID>/discovery.md for the analyst.
user-invocable: false
---

# Discovery

Agents build what they believe the human wants, and that belief is usually thinner than it feels. This step finds out what they want and why, so the hundred small decisions in the spec get made the way they would make them.

Runs in the **main session** (the orchestrator), because it is a conversation.

## 1. Decide whether to ask at all
- Everything that matters is in the request (who, what, why, done-when): skip the interview, write `discovery.md` from the request, say so in one line.
- Something non-trivial is missing: interview.

## 2. First message
Two things, in this order:
1. One line: "If you'd rather skip the questions, say so and I'll go with sensible defaults."
2. One open question about a concrete moment: "Tell me about the last time someone needed this. What were they trying to do?"

## 3. The conversation
- **One question per message.** A single sentence, no list of example answers hanging off it.
- Use the human's vocabulary. Ask about real situations, not abstractions.
- Chase the **why** behind each want; the why decides edge cases later.
- Cover, in whatever order the conversation allows: who uses it; the main scenario; what "done" looks like for them; what must not happen; what is explicitly out of scope; constraints (deadline, platform, compliance).
- Stop when you could explain the feature to a stranger and predict how the human would answer the next three questions. Usually 4–8 questions.
- "Skip" or "just start" at any point: stop, take defaults, list them in `discovery.md` as `assumed`.

## 4. Output
Write `specs/<ID>-<slug>/discovery.md`:

```markdown
# <ID> discovery
## The why
## Who and when (the concrete moments)
## Must happen
## Must not happen
## Out of scope
## Constraints
## Assumed (not confirmed by the human)
## Quotes worth keeping
```

Keep the human's own words where they carry meaning. Then hand `discovery.md` to the analyst.

---
Adapted from the `brainstorming` skill of obra/superpowers (MIT, © Jesse Vincent). See THIRD_PARTY_NOTICES.md.
