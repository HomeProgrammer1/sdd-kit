---
name: prototype
description: Build a clickable prototype for an SDD feature from its approved spec, using only the project's own design system — screens.json plus a generated HTML prototype, ready for Figma export. Use for /sdd-design:prototype, or when /sdd-kit:sdd runs with --design.
argument-hint: "<feature ID> [--platform web|mobile] [--theme NAME] [--sketch]"
allowed-tools: Bash(python3 *), Read, Glob, Grep
---

# Prototype from spec

Arguments: `$ARGUMENTS`

## 0. Design system first (hard requirement)
Read the project `CLAUDE.md`. Look for `Design system: <path/to/components.json>` (plus optional `Theme:` and `Kit:` lines).

- Line missing, says `none`, or the file does not exist → **stop** and tell the human, in their language:
  > Prototypes are built only from your own design system, so the screens match what you will actually ship. Create one first (`/sdd-design:design-system-init` in a separate repository, or point to an existing one), then add `Design system: <path>/components.json` to CLAUDE.md.
  Report `STATUS: BLOCKED` / `NEEDS_DESIGN_SYSTEM` to the orchestrator if one called you. Never invent a design system on the fly.
- Exception: `--sketch` → a throwaway grey wireframe with `--neutral`. Label it a sketch everywhere and never export it to Figma as a design.

## 1. Inputs
Feature folder `specs/<ID>-*/`. The spec must be approved (`state.json` → `approvals.spec`) unless the human runs this skill directly and accepts that it may change. Platform from `--platform`, else CLAUDE.md Stack profile (`mobile` if it includes mobile, otherwise `web`).

## 2. Design
Dispatch the `sdd-design:ux-designer` agent with: the feature folder, the design-system path, theme, kit, platform, and these paths verbatim:
- schema: `${CLAUDE_SKILL_DIR}/references/screens-schema.md`
- example: `${CLAUDE_SKILL_DIR}/references/example.screens.json`
- dashboard example (Table, Modal, Tabs, Pagination, Progress, Chart): `${CLAUDE_SKILL_DIR}/references/example.dashboard.screens.json`
- render script: `${CLAUDE_SKILL_DIR}/scripts/render_prototype.py`
 It writes `design/screens.json` and renders `design/index.html`, then returns `STATUS`, `SCREENS`, `AC_COVERAGE`, `CONCERNS`.
- `NEEDS_CONTEXT` → answer from the spec/plan or ask the human.
- `BLOCKED` → report it; do not draw screens yourself.

## 3. Check
```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/render_prototype.py" check specs/<ID>/design/screens.json --ds <components.json> [--theme <theme>] --spec specs/<ID>/spec.md
```
Errors must be zero. Contrast warnings are real defects of the design system: report them to the human, do not patch colours in screens.
`screens.json was built from an older spec.md` means the spec changed after the screens were made (its sha1 no longer matches `spec_sha1`). Dispatch the agent again to update the screens. An `info:` line asking you to record `spec_sha1` means the agent skipped that step; send it back.

## 4. Report
```
PROTOTYPE: specs/<ID>/design/index.html (<n> screens, <platform>, <design system name@version · theme>)
AC_COVERAGE: <from the agent>
NEXT: review the prototype; /sdd-figma:figma-export <ID> to lay it out in Figma
```
The human reviews the prototype together with the plan at Gate 2. screens.json is committed with the spec; index.html is generated and may be committed for reviewers.

References: `${CLAUDE_SKILL_DIR}/references/screens-schema.md` (format), `${CLAUDE_SKILL_DIR}/references/example.screens.json` (worked example), `${CLAUDE_SKILL_DIR}/references/example.dashboard.screens.json` (data and overlay components).
