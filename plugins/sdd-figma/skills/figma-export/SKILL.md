---
name: figma-export
description: Lay out an SDD feature in Figma — its How-it-works diagrams and, when a prototype exists, every screen as auto-layout frames built from the design system with prototype links — through the Figma MCP connector if it is connected, otherwise through the bundled "SDD Kit Import" Figma plugin. Use for /sdd-figma:figma-export or when /sdd-kit:sdd runs with --figma.
argument-hint: "<feature ID> [--via mcp|plugin] [--theme NAME]"
allowed-tools: Bash(python3 *), Bash(mkdir *), Bash(cp *), Read, Glob
---

# Export a feature to Figma

Arguments: `$ARGUMENTS`

Figma is **downstream**. The spec's Mermaid and `design/screens.json` stay the source; Figma receives a fresh layout each time. Changes a designer makes in Figma come back by editing screens.json or the spec (read the frames with the Figma MCP if it is connected), never the other way round silently.

## 1. Make sure the inputs are current
- Diagrams: `specs/<ID>-*/diagrams/manifest.json` must exist and match the spec. If not, run `sdd-diagrams:feature-diagrams <ID>` first (when that plugin is installed). No diagrams and no screens → stop: nothing to export.
- Screens: `design/screens.json` if the feature has a prototype. If it was made with `--sketch`, export diagrams only and say why.

## 2. Build the bundle (both paths use it)
```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/build_bundle.py" specs/<ID>-<slug> [--theme <theme>]
```
It reads the design system from the `Design system:` line in CLAUDE.md (or `--ds`), resolves tokens, embeds the SVGs and screens, records `sources` (the sha1 of `spec.md`, `design/screens.json` and each diagram source), and writes `specs/<ID>-<slug>/figma/bundle.json`. Report its warnings. If one says `screens.json was built from an older spec.md`, the prototype is stale: offer to re-run `/sdd-design:prototype <ID>` before exporting.

## 3a. Path A — Figma MCP connector (when its tools are available and `--via plugin` was not given)
Writing to Figma changes a shared file, so first confirm the target file with the human (a figma.com/design URL they give you). Never create or edit a file they did not name.
1. Follow the connector's own instructions and skills for writing (load them before the first write).
2. Diagrams: on a page `<ID> · How it works`, import each SVG from the bundle as a frame named after the diagram, stacked vertically. For FigJam, the connector's diagram tool can take the Mermaid source in `diagrams/<name>.mmd` directly.
3. Screens: search the file's design system for each component type used in screens.json and use library instances where they exist; otherwise draw them from the bundle tokens. One auto-layout frame per screen on `<ID> · Screens`, named `<id> — <title>`, AC IDs in an annotation above, prototype links from `flows`.
4. Same rules as the plugin: put `Generated from spec <first 7 of sources.spec.sha1> · <date>` above each page's content. Never delete earlier layers; move them to `<ID> · Archive` under a section `Run <ISO date-time>`.
5. Record the file URL in `state.json` → `side_effects` (`kind: "figma"`).

## 3b. Path B — the bundled Figma plugin (no connector needed)
1. Copy the plugin into the project once: `mkdir -p .sdd && cp -R "${CLAUDE_SKILL_DIR}/../../figma-plugin" .sdd/figma-plugin` (skip if it is already there and unchanged). `.sdd/` is in the sdd-kit gitignore snippet.
2. Tell the human, in their language and in three short steps:
   1. Figma desktop app → Plugins → Development → Import plugin from manifest… → `.sdd/figma-plugin/manifest.json` (one time).
   2. Open the design file, run Plugins → Development → SDD Kit Import.
   3. Choose `specs/<ID>-<slug>/figma/bundle.json` and press Build. Re-running deletes nothing: it rebuilds the generated pages and moves the earlier generated layers, designer edits included, to the page `<ID> · Archive` under a section `Run <date-time>`. Layers they added themselves stay where they are.
   Each page gets the caption `Generated from spec <sha7> · <date>`. Its sources are also stored in the page's plugin data.

## 4. Report
```
FIGMA: <file URL> | bundle ready: specs/<ID>-<slug>/figma/bundle.json (run the plugin)
PAGES: <ID> · How it works (<n> diagrams), <ID> · Screens (<n> frames, <n> links)
COMPONENTS: library instances <list> | drawn from tokens <list>
SOURCES: spec <sha7> · screens <sha7> | ARCHIVE: <n> earlier layer(s) → <ID> · Archive › Run <time> (when re-run)
```
