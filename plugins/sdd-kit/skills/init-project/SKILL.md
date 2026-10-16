---
name: init-project
description: One-time setup of sdd-kit in a repository — copies the project template (CLAUDE.md, rules, settings, specs/), detects the stack, picks the stack profile, fills CLAUDE.md Commands and Layout, suggests MCP connectors. Use for /sdd-kit:init-project or "set up sdd-kit for this repo".
disable-model-invocation: true
---

Template files live in `${CLAUDE_SKILL_DIR}/template/`.

1. **Copy the template** into the project root without overwriting anything that exists:
   - `CLAUDE.md` — if one exists, merge the template's sections into it instead (keep the user's content, add Stack profile, Commands, How work flows, Definition of done).
   - `CLAUDE.local.md.example`, `.mcp.json` (only if absent), `.claude/settings.json` (only if absent; otherwise show the user the permission and statusLine blocks to merge), `.claude/rules/`, `.claude/statusline.sh`, `.claude/settings.local.json.example`, `specs/`, `docs/adr/`.
   - Append `gitignore.snippet` lines to `.gitignore` that are not already there.
   - Leave `mcp-connectors/` in the plugin; you read snippets from there in step 6.
2. **Detect the stack** from manifests: `package.json` (+ framework deps: next, react, vue, svelte, express, nest), `pubspec.yaml` (Flutter), `*.xcodeproj`/`Package.swift` (iOS), `build.gradle*` with `com.android.application` (Android), `app.json`/`expo` (React Native), `pyproject.toml`/`requirements.txt`, `go.mod`, `Cargo.toml`, `pom.xml`, `*.csproj`, `Gemfile`, `docker-compose.yml`.
3. **Pick the profile**: `web`, `mobile`, `backend`, or a combination. Empty repo → ask the human which, then propose a stack with one-line reasons and wait for approval before scaffolding anything.
4. **Find real commands**: read scripts (`package.json` scripts, Makefile, Gradle tasks, CI config). Run each candidate once; record only commands that ran. Mark missing ones `n/a` and say so.
5. **Fill CLAUDE.md**: Project, Stack profile, Commands, Layout. Stay under 150 lines. Delete `.claude/rules/*.md` that do not apply and adjust `paths:` globs to real folders.
6. **Connectors**: list which of `${CLAUDE_SKILL_DIR}/template/mcp-connectors/*.json` fit (tracker, VCS host, design, browser) and show the snippet to merge into `.mcp.json`. Tokens always come from environment variables, never from the file.
7. Report what was set, what is `n/a`, and the first command to try: `/sdd-kit:sdd "<small feature>" --level=spec`.
