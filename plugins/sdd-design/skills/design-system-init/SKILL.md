---
name: design-system-init
description: Scaffold a new design-system repository from the sdd-design starter — DTCG tokens (primitives, light and dark themes), a components.json inventory with kits for SaaS, marketing sites and mobile apps, and a README on versioning and Figma. Use for /sdd-design:design-system-init, in an empty folder meant to become its own repository.
argument-hint: "[target folder, default: current]"
disable-model-invocation: true
allowed-tools: Bash(cp *), Bash(mkdir *), Bash(ls *), Bash(git status*), Read, Edit
---

# New design system

Arguments: `$ARGUMENTS`

A design system is a product of its own: it is versioned, reviewed and reused by several apps. It lives in **its own repository**, not inside a product repo and not inside this plugin.

1. Target = the argument, else the current directory. If it already contains `components.json` or `tokens/`, stop and ask before touching anything.
2. If the target is inside a product repository (it has `specs/` or an app's package manifest next to it), warn once that a design system belongs in its own repository and ask whether to continue.
3. Copy the starter: `cp -R "${CLAUDE_SKILL_DIR}/starter/." <target>/`.
4. Ask the human three things, one at a time, recommending a default each time:
   - the system's name (`name` in components.json),
   - the brand colour (replace `palette.brand.*`; derive 50/500/600/700 shades),
   - which kits they need first (saas-dashboard, marketing-site, mobile-app).
   Edit `components.json` and `tokens/primitives.json` accordingly. Keep the semantic token names: screens, code and Figma depend on them.
5. Check contrast with the sdd-design renderer against the bundled example:
   `python3 "${CLAUDE_SKILL_DIR}/../prototype/scripts/render_prototype.py" check "${CLAUDE_SKILL_DIR}/../prototype/references/example.screens.json" --ds <target>/components.json`
   and again with `--theme dark`. Fix every `contrast:` warning in the tokens before the first release.
6. Report what was created and the next steps from the starter README: first commit and tag `v0.1.0`, then in each product repo add the system (git submodule or package) and the CLAUDE.md lines:
   ```
   - Design system: design-system/components.json
   - Theme: light
   - Kit: saas-dashboard
   ```
Never push, publish or create remote repositories; the human does that.
