---
name: spec-format
description: Structure and quality bar for sdd-kit specs (specs/<ID>/spec.md) — EARS requirements, Given/When/Then ACs with IDs, NFRs, out of scope, open questions and How-it-works diagrams. Use when writing or reviewing an sdd-kit spec.
user-invocable: false
---

Copy `${CLAUDE_SKILL_DIR}/templates/spec.md` and fill every section. Delete hint comments.

## Rules
- **What and why, never how.** No class names, tables, endpoints or libraries.
- **Requirements** use EARS forms: "The system shall…", "When <trigger>, the system shall…", "While <state>, …", "If <unwanted condition>, then the system shall…".
- **Acceptance criteria**: `AC-n`, Given/When/Then, one behaviour each, observable from outside, with concrete values ("within 2 s", "max 50 items"), not "fast" or "many".
- Each functional requirement maps to ≥1 AC.
- **NFRs** only where they matter for this feature, each with a number: performance, accessibility (WCAG 2.2 AA for UI), security/privacy, offline behaviour (mobile), compatibility (browsers / OS versions).
- **Open questions** carry a recommended default so a human can answer "yes".

## Diagrams (section 9, "How it works")
Every spec shows how the feature works as **Mermaid** blocks inside spec.md. They are the canonical diagrams: GitHub renders them in PRs and they diff like text. Every other format (SVG, .drawio, Figma) is generated from them and never edited by hand.

| Diagram | When | Mermaid |
|---|---|---|
| **Flow** (mandatory) | always: the user's path through the feature, with decisions and error exits | `flowchart TD` |
| **Sequence** | two or more actors/systems exchange messages (UI → API → DB → email) | `sequenceDiagram` |
| **State** | an entity has a lifecycle (order, token, subscription) | `stateDiagram-v2` |

Rules:
- One idea per node; aim for ≤ 9 nodes, never more than 12. More than that is two diagrams (overview + detail).
- Label nodes in the users' language; put the AC ID on the node or edge it proves: `C{Link valid? AC-3}`.
- Every decision is a question and every exit is labelled (`-->|yes|`, `-->|no|`).
- Show error and empty paths, not only the happy path. Mark at most one focal node with `class X focal`.
- Stay in the portable subset so every exporter can render it: flowchart nodes `A[Box]`, `A(Rounded)`, `A{Decision}`, `A([Start/End])`, `A[(Store)]`, `A((External))`; edges `-->`, `-->|label|`, `-.->`, `==>`; sequence `participant`/`actor`, `->>`, `-->>`, `--x`, `Note over`, `alt/else/opt/loop/par … end`; state `[*]`, `-->`, `: label`. No `style`/`classDef` colours: colour comes from the theme.
- Each block is preceded by a `### <Title>` line; the exporter uses it as the file name.

## Self-check (all must be true)
- [ ] A tester could write each AC's test without asking anything.
- [ ] No AC depends on an implementation detail.
- [ ] Every requirement maps to an AC; every AC maps to a requirement.
- [ ] Out of scope lists at least the obvious neighbours.
- [ ] No invented business rules: anything assumed is in Open questions.
- [ ] Section 9 has at least the Flow diagram; every decision node has all its exits.
