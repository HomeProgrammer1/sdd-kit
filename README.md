# SDD Kit: a Claude Code plugin marketplace for spec-driven delivery

[Українською](README.uk.md) · Tested with Claude Code 2.1.301

Four plugins that work together or on their own. A feature goes from idea to a draft pull request: first a spec with a "How it works" diagram, then a plan and, if you want, a clickable prototype built on your own design system and laid out in Figma, then test-first code with review. A human approves the spec and the plan, and only a human merges.

| Plugin | What it does | Commands |
|---|---|---|
| **sdd-kit** | Orchestrator and agents: discovery, analyst, architect, implementer, reviewer, branch-reviewer, verifier, security-auditor, debugger | `/sdd-kit:sdd`, `/sdd-kit:sdd-status`, `/sdd-kit:init-project` |
| **sdd-diagrams** | Checks the Mermaid in a spec; renders editorial SVG, a multi-page `.drawio` and a review gallery | `/sdd-diagrams:feature-diagrams` |
| **sdd-design** | ux-designer agent, `screens.json`, clickable HTML prototype, starter design system | `/sdd-design:prototype`, `/sdd-design:design-system-init` |
| **sdd-figma** | Lays diagrams and screens out in Figma, through the Figma MCP connector or a local Figma plugin | `/sdd-figma:figma-export` |

## Install

```text
/plugin marketplace add HomeProgrammer1/sdd-kit
/plugin install sdd-kit@sdd-marketplace
/plugin install sdd-diagrams@sdd-marketplace     # recommended
/plugin install sdd-design@sdd-marketplace       # for prototypes
/plugin install sdd-figma@sdd-marketplace        # for Figma
```

From a terminal: `claude plugin marketplace add HomeProgrammer1/sdd-kit`, then `claude plugin install <name>@sdd-marketplace`. The plugins do not depend on each other; `sdd-kit` uses the others when they are installed.

After installing `sdd-kit`, Claude Code may say "userConfig options not yet set". That is expected: the defaults apply (`guard_mode = sdd`, `format_on_edit = true`). The environment variables `SDD_GUARD=strict|hard-only|off` and `SDD_FORMAT=off` override them.

Requirements: `bash` and Python 3.8+ (`python3`, `python` or the Windows `py` launcher). If no Python is found, the session starts with a warning that the guard is off, and `strict` mode refuses tool calls instead.

In your project:

```text
/sdd-kit:init-project                          # CLAUDE.md template, rules, settings, specs/
/sdd-kit:sdd "Password reset by email"         # stops after the spec (Gate 1)
/sdd-kit:sdd F-001 --level=plan --design --figma
/sdd-kit:sdd "Fix: reset link expires too early" --quick   # small fix, one gate
```

## How it works

```
/sdd-kit:sdd "request" [--level=spec|plan|implement|push] [--quick] [--design] [--figma]
   0. discovery         short interview, one question at a time → discovery.md
   1. analyst           spec.md: EARS requirements, AC-1..n (Given/When/Then), "How it works" in Mermaid
      sdd-diagrams      checks and renders the diagrams → specs/F-001/diagrams/
   ═══ GATE 1: a human approves the spec ═══
   2. architect         plan.md, tasks.md (tasks with steps), ADRs
      sdd-design        ux-designer → design/screens.json → clickable prototype   (--design)
      sdd-figma         diagrams and screens in Figma                            (--figma)
   ═══ GATE 2: a human approves the plan (and prototype) ═══
   3. worktree + green baseline, pre-flight scan of the tasks
   4. per task: implementer (TDD) → reviewer (SPEC: PASS|FAIL, QUALITY: APPROVE|REQUEST_CHANGES)
      → up to 5 fix rounds → commit
   5. branch-reviewer → verifier (end to end against the ACs) → security-auditor
   6. handover: push the branch and open a DRAFT PR
   ═══ GATE 3: review and merge are done by a human only ═══
```

Agents hand each other **files**, not conversation. Each returns a fixed block (`STATUS`, `SPEC`, `QUALITY`, `VERDICT`) that the orchestrator routes on. Run state lives in `specs/<ID>/state.json` and `ledger.md` (decisions as "Ruling: what, why, cost if wrong"), so a run resumes in a new session or after context compaction.

**Quick lane.** `--quick` is for a bug fix or a tweak that touches at most 3 files and adds no screen, API, schema or dependency and nothing in auth, payments, permissions or secrets. It skips discovery, the architect, branch review and (unless the diff touches those areas) the security audit, and asks for one approval instead of two. The run moves itself to the full lane the moment the change grows past those limits.

## What a run costs

Estimate, not a measurement. Assumptions per agent run: 30 turns, 60k tokens of context on average, 90% of input read from cache, 20k output tokens; Opus 5.5 at $4 / $20 per million tokens (cache reads $0.20), Sonnet 5.5 at $2 / $10.

| | Agent runs | Estimate |
|---|---|---|
| Full lane, one fix round | 10 on Opus, 6 on Sonnet, orchestrator | ≈ $32 per feature |
| Quick lane | 3 on Sonnet, orchestrator | ≈ $4–6 per change |
| The same feature in one plain session | 1 | ≈ $5 |

The full lane buys independent review, verification and a security pass, and costs several times a plain session. Use `--quick` for small changes. On a subscription the difference shows up as usage limits rather than dollars.

## Diagrams: every feature gets a "How it works"

The analyst writes the diagrams in `spec.md` in **Mermaid**. A Flow is required. A Sequence is required when two or more systems interact, and a State diagram when an entity has a lifecycle. Mermaid stays the single source: GitHub renders it in the PR and the diff reads as text. You do not need this plugin to see the diagrams. It adds the checks and the exports:

- at most 12 nodes, comfortable up to 9;
- every decision has all of its exits labelled;
- at most two highlighted nodes;
- no overlaps and no labels sitting on lines.

Then it writes SVG in an editorial style (rounded orthogonal connectors, labels beside their segment, AC tags on nodes, accessible `<title>/<desc>`, a hash of the source), a `.drawio` with one page per diagram, and an `index.html` gallery for review. Colours come from your design-system tokens (`--tokens`) with a WCAG AA contrast check. The engine is plain Python with no dependencies and no network.

<p align="center"><img src="docs/img/example-flow.svg" alt="Flow diagram of the example password-reset feature" width="440"></p>

## Design: build your own design system first

> **Important.** To build designs and prototypes, first **create your own design system**. `sdd-design` does not invent components or colours. It builds screens only from what your system declares, so the prototype matches what you will actually ship. Without a design system the step stops and explains what to do. `--sketch` produces a grey throwaway sketch only.

**One repository or several?** Recommended: **one separate design-system repository** (a monorepo), apart from both your products and this plugin. It holds:
- shared semantic tokens (DTCG), the contract for code, prototypes and Figma;
- **themes** (brands, dark mode) that only re-point aliases;
- **kits** such as `saas-dashboard`, `marketing-site` and `mobile-app`: subsets of the components, not forks.

Split into several repositories only when a brand is run by another team with its own release cycle, and even then keep the semantic token names shared.

1. In a new empty folder: `/sdd-design:design-system-init`. It creates the tokens (primitives, light, dark), `components.json` with kits, a README and a CHANGELOG, and checks contrast.
2. Publish it as its own repository with version tags (`v0.1.0`).
3. Add it to the product (for example as a git submodule in `design-system/`) and point `CLAUDE.md` at it:
   ```
   - Design system: design-system/components.json
   - Theme: light
   - Kit: saas-dashboard
   ```
4. `/sdd-kit:sdd F-001 --design` or `/sdd-design:prototype F-001`.

The **ux-designer** agent writes `specs/<ID>/design/screens.json`: a screen per state (default, empty, loading, error, success), built from your system's components, each tagged with the AC IDs it shows, and stamped with the hash of the spec it was built from. The renderer turns it into a clickable `index.html`. The starter design system has 26 components, among them Table, Modal, Tabs, Pagination, Progress and a Chart placeholder, and its kits pick subsets of them; a dashboard example ships next to the password-reset one. The checks catch unknown components and variants, broken links, unreachable screens, ACs without a screen, token contrast below AA, and a `screens.json` built from an older spec.

<p align="center"><img src="docs/img/example-prototype.png" alt="Prototype board for the example feature" width="720"></p>
<p align="center"><img src="docs/img/example-dashboard.png" alt="Overview screen of the example billing dashboard prototype" width="720"></p>

## Figma

`screens.json` and the SVG diagrams go into one `figma/bundle.json`, together with the hashes of the files they came from. Two ways in, same result:
- a page `<ID> · How it works` with the diagrams;
- a page `<ID> · Screens`: every screen as an **auto layout** frame, layers named after components, colours and spacing bound to **Figma variables** made from your tokens, and prototype links between screens.

Each page carries a caption with the spec hash and date it was generated from.

| Way | When | How |
|---|---|---|
| **Figma MCP connector** | The connector is set up and you gave a file URL | The agent writes into your file and places instances from your library where it can |
| **SDD Kit Import plugin** | No connector, or offline | Figma desktop → Plugins → Development → Import plugin from manifest → `.sdd/figma-plugin/manifest.json`, then Build with `bundle.json` |

If `components.json` lists the keys of published library components, the plugin places **real instances**; otherwise it draws the component from tokens. Re-running never deletes anything: the previous generated layers move to a `<ID> · Archive` page, so edits a designer made in them are kept. Figma is downstream here: changes made in Figma come back through `screens.json` or the spec.

## Living next to other plugins

The kit does not take over the session or block other work. It can sit next to general skill collections (for example superpowers) or diagram plugins (for example diagram-design):

- **The guard has two tiers.** Hard stops apply everywhere: recursive deletes of root, home or the project directory (in any flag spelling, inside `bash -c`, or as a `shutil.rmtree('/')` one-liner), force pushes to or deletion of main/master, writes to `.git/`, `~/.ssh` and cloud credentials. Process rails (merges and approvals including through the API, deploys, publishing, tags, `.env`, force pushes, role limits) apply only to the kit's own work: `sdd-kit:*` and `sdd-design:*` agents and the session running `/sdd-kit:sdd`. Modes: `sdd` (default), `strict`, `hard-only`, `off`.
- **A run that lost track of its session stays protected.** If an open run has no session recorded, the rails apply to every session in that project until the run is resumed or closed, and the deny message says so. `/sdd-kit:sdd` checks this when it starts, and `/sdd-kit:sdd-status` shows it.
- **Formatting after edits** happens only in SDD runs.
- **No forced instructions at session start.** SessionStart only lists open runs, if there are any.
- **Narrow skill descriptions** ("in an sdd-kit run…") and `sdd-kit:` prefixes. If superpowers is installed too, its TDD, debugging and review skills keep working outside a run; inside a run, the kit's agents load the `sdd-kit:` ones because the orchestrator parses their report format.
- **No dependencies** on other plugins or marketplaces.

## Safety in three layers

| Layer | Mechanism | What it guarantees |
|---|---|---|
| 1. The tool is not there | `tools:` in agents, `permissions.deny`, allow/deny lists in the MCP snippets | The reviewer cannot edit files; no agent sees a merge tool |
| 2. Hook refusal | `hooks/guard.py` on every Bash/Write/Edit, two tiers | See above; analyst, architect and ux-designer write only to `specs/` and `docs/` |
| 3. Policy in text | `autonomy-contract` skill | Autonomy levels, retry budgets, conditions that always pause |

There is no `merge`, `release` or `deploy` level: those steps are always a human's.

## What is in the repository

```
.claude-plugin/marketplace.json      catalogue of the 4 plugins
plugins/sdd-kit/                     8 agents, 18 skills, hooks, project template, output style
plugins/sdd-diagrams/                feature-diagrams skill, sdd_diagrams.py engine, style.md
plugins/sdd-design/                  ux-designer agent, prototype and design-system-init skills (starter)
plugins/sdd-figma/                   figma-export skill, build_bundle.py, figma-plugin/ (manifest, code.js, ui.html)
scripts/validate.py                  JSON, frontmatter, guard cases, diagrams, prototypes, Figma plugin test
scripts/typecheck_figma.sh           type-checks the Figma plugin against Figma's official API typings
.github/workflows/validate.yml       runs all of the above and `claude plugin validate` on every push
THIRD_PARTY_NOTICES.md               where the ideas come from (MIT)
```

## Limitations

- A full `/sdd-kit:sdd` cycle has not yet been run on a real project. The manifests pass `claude plugin validate`, a test install and `scripts/validate.py`.
- The Figma plugin is tested against a strict mock of the Figma API and type-checked against Figma's official typings, not yet run inside Figma. The MCP path is documented but not tried on a real file.
- The diagram engine covers a portable subset: flowchart, stateDiagram-v2, sequenceDiagram. ER, class and gantt stay in Mermaid and render on GitHub.
- The guard reads commands as typed, including `bash -c` bodies, but not scripts a command runs or strings built at runtime (variables, base64, downloaded code). It also treats a quoted mention such as `echo "rm -rf /"` as the command. In `sdd` mode an error inside the guard lets the call through; `strict` blocks it.
- MCP server addresses and packages in the snippets can change; check them against the vendor's docs.

## Development

```bash
python3 scripts/validate.py
claude plugin validate .
for p in plugins/*; do claude plugin validate "$p"; done
npm install --no-save --ignore-scripts --prefix /tmp/figma-types typescript@6 @figma/plugin-typings
bash scripts/typecheck_figma.sh /tmp/figma-types/node_modules
```

When you change a plugin, bump `version` in its `plugin.json` and in `marketplace.json`, or users will not get the update.

## Credits and licence

Some procedures rework ideas from [obra/superpowers](https://github.com/obra/superpowers) (MIT, © Jesse Vincent) and [diagram-design](https://github.com/cathrynlavery/diagram-design) (MIT, © Cathryn Lavery). No code was copied; details in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

MIT © HomeProgrammer1
