---
name: stack-web
description: Web front-end profile (React, Vue, Svelte, Angular, Next/Nuxt, plain HTML) — what to check when specifying, planning, implementing and verifying UI on the web. Load when CLAUDE.md Stack profile includes web.
user-invocable: false
---

## Spec additions
- Supported browsers and breakpoints (e.g. last 2 Chrome/Safari/Firefox/Edge; 360 / 768 / 1280 px).
- Accessibility: WCAG 2.2 AA — keyboard path, focus order, labels, contrast ≥ 4.5:1.
- States for every screen: loading, empty, error, success, no-permission.
- Performance budget: LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1 on a mid-range mobile profile.
- SEO / sharing meta only if the page is public.

## Plan additions
- Where state lives (server cache vs client store vs URL); data fetching pattern used in the repo.
- Design source (Figma link / design system components) and which existing components are reused.
- i18n keys, feature flag, analytics events (names + properties).

## Implementation
- Reuse design-system components; no inline colours/sizes that bypass tokens.
- Forms: client + server validation, accessible error messages.
- Never put secrets in client bundles; anything `NEXT_PUBLIC_`/`VITE_` is public.

## Verification
- Unit/component tests (Testing Library style: query by role/label).
- E2E with Playwright (CLI or Playwright MCP) for each AC's happy path + one unhappy path.
- Automated a11y scan (axe) on changed pages; zero serious/critical violations.
- Lighthouse on the changed page if a performance NFR exists.
