---
name: feature-diagrams
description: Check and render the "How it works" Mermaid diagrams of an SDD feature (specs/<ID>/spec.md and plan.md) into editorial SVG, an optional multi-page .drawio and a review gallery. Use after a spec or plan with Mermaid blocks is written or changed, or when asked for a feature's diagrams. Not for free-form diagrams outside specs/.
argument-hint: "<feature ID | path to spec.md> [--drawio] [--check]"
allowed-tools: Bash(python3 *), Read, Glob
---

# Feature diagrams

Arguments: `$ARGUMENTS`

Mermaid inside `spec.md` / `plan.md` is the **single source of truth**. Everything this skill writes into `specs/<ID>/diagrams/` is generated, stamped with the source hash, and never edited by hand. Fix a diagram by editing its Mermaid block, then rebuild.

## Steps

1. **Find the files.** An ID → `specs/<ID>*/spec.md` and, if present, `plan.md` and `discovery.md`. A path → that file. No Mermaid blocks in the spec → stop and report `NO_DIAGRAMS`: the spec is incomplete (section 9 "How it works" is mandatory, see `sdd-kit:spec-format` when that plugin is installed).
2. **Check first** (writes nothing):
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/sdd_diagrams.py" check specs/<ID>/spec.md specs/<ID>/plan.md
   ```
   - `error` lines (parse failure, more than 12 nodes, a decision without all its exits, more than 2 focal nodes, overlapping nodes) → fix the Mermaid source and check again. If the spec is not yours to edit (a reviewer or a user owns it), report the errors instead.
   - `warn` lines (above the comfortable 9 nodes, unlabeled decision exits, a label on a connector) → fix when cheap; otherwise mention them in your report.
   - `SKIP` lines are Mermaid types outside the portable subset (erDiagram, classDiagram, gantt, …). They stay as Mermaid and render on GitHub/GitLab; nothing to do.
3. **Build** when there are no errors (`--check` given → stop after step 2):
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/sdd_diagrams.py" build specs/<ID>/spec.md specs/<ID>/plan.md [--drawio] [--tokens <design-tokens.json>]
   ```
   Pass `--drawio` when the user or the run options ask for draw.io (or for Figma, which imports the SVGs). Pass `--tokens` when the project's CLAUDE.md names a design-system tokens file, so diagrams use the brand colours; otherwise the neutral editorial palette is used.
4. **Look at the result.** Read at least the main flow SVG. If anything reads badly (a label far from its connector, a lopsided layout), simplify the Mermaid: fewer nodes, shorter labels, split an overview from the detail. Do not hand-edit SVG.
5. **Report** in this shape:
   ```
   DIAGRAMS: <n> rendered, <n> skipped
   FILES: specs/<ID>/diagrams/index.html, <svg list>, [<ID>.drawio]
   ISSUES: none | <warnings you left and why>
   ```

## Rules

- Read `${CLAUDE_SKILL_DIR}/references/style.md` before writing or reshaping a diagram. It holds the budgets, the node vocabulary and the taste checks the renderer enforces.
- One diagram, one idea: **Flow** (mandatory), **Sequence** (when two or more systems talk), **State** (when an entity has a lifecycle). A plan adds its own Sequence or ER diagrams.
- Node labels carry the AC IDs they prove (`AC-3`); the renderer shows them as mono tags, so reviewers can trace every acceptance criterion to the picture.
- The generated `diagrams/` folder is committed with the spec, so reviewers see pictures in the pull request without running anything.
- Other diagram tools can stay installed. This skill only owns `specs/*/diagrams/`. A free-form or marketing diagram is a job for whatever diagram skill the user prefers.
