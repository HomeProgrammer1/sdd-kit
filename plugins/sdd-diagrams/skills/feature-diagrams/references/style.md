# Diagram style for feature specs

A feature diagram exists so a reviewer can say "yes, that is how it should work" in under a minute. Every rule below serves that.

## 1. Delete before you draw

- Start from the acceptance criteria, not from the code. A node earns its place only if it changes what happens next or proves an AC.
- Merge steps that always happen together ("Validate and save").
- Prefer two small diagrams (overview + detail) to one dense one.

**Budgets the renderer enforces**

| | Comfortable | Hard limit |
|---|---|---|
| Nodes in a flow or state diagram | 9 | 12 (error above) |
| Connectors | 14 | warning above |
| Focal (accent) nodes | 1 | 2 (error above) |
| Sequence participants | 5 | 6 (warning above) |
| Sequence messages | 12 | 16 (warning above) |

## 2. Node vocabulary

Use Mermaid shapes; the renderer maps them to one quiet visual language.

| Mermaid | Meaning | Rendered as |
|---|---|---|
| `A([Start or end])` | entry/exit of the flow | ink-filled rounded box |
| `A[Step]` | something the system or user does | outlined box |
| `A{Question?}` | a decision; **every exit labelled** (`-->|yes|`) | tinted box with a diamond mark |
| `A[(Store)]` | a database, queue or file | tinted box with a lid line |
| `A((External))` | a system you do not own | dashed outline |
| `class A focal` | the one thing the reviewer must look at | accent outline and tint |
| `-.->` | optional, async or "returns later" path | dashed connector |
| `==>` | the happy path, when it helps | heavier connector |

Write decisions as questions, steps as verb phrases, at most about six words. Put AC IDs in the label (`{Token valid? AC-3}`); they render as small mono tags.

## 3. Layout the renderer does for you

- Top-to-bottom for flows (`flowchart TD`), left-to-right only for short pipelines (`LR`).
- Orthogonal connectors with 8 px rounded corners; fan-out points spread evenly along a side (k/(N+1)); one-to-one links are straightened.
- Connectors are drawn first and never run behind a box. Back edges ("try again") return on an outside lane.
- Labels sit **beside** a vertical segment or **above** a horizontal one with a small gap, never on the stroke. Decision labels stay close to their decision.
- Box sizes snap to a 4 px grid.

## 4. Colour and type

- Semantic roles only: `paper`, `paper2`, `ink`, `muted`, `soft`, `rule`, `accent`, `accentTint`, `link`. No ad-hoc hex values in Mermaid (`style`/`classDef` lines are ignored on purpose).
- With `--tokens <file>` the roles come from the project's design-system tokens (DTCG `$value` or plain JSON, aliases resolved). Keep the contract: `ink`, `muted` and `soft` on `paper` must reach WCAG AA (4.5:1) for text.
- Accent is a highlighter, not decoration: at most two focal elements.
- Sans for names, mono for IDs and eyebrows.

## 5. Accessibility and provenance

- Every SVG has `role="img"`, a `<title>` and a `<desc>` first.
- Every SVG carries `source-sha1` of its Mermaid block; `check` reports stale or missing renders.

## 6. Taste check before you hand it over

1. Can someone who has not read the spec explain the flow back from the picture alone?
2. Is there exactly one obvious entry and every path ends somewhere?
3. Does every decision show all its exits, labelled?
4. Is every AC that describes behaviour visible on at least one node?
5. Would removing any node lose information? If not, remove it.
6. Do labels read without crossing a line or touching a box?

Anti-patterns: a node per function call, a legend explaining colours, more than one accent, arrows labelled "then", diagrams that restate the code instead of the behaviour.

---
The layout and taste principles here are our own rework of ideas from [diagram-design](https://github.com/cathrynlavery/diagram-design) (MIT, © 2025 Cathryn Lavery). No code or text is copied; see `THIRD_PARTY_NOTICES.md` at the repository root.
