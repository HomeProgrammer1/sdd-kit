# Design system

The single source of visual truth for every product built with this team: tokens, a component inventory, themes and kits. Product repositories consume it at a pinned version; prototypes, Figma layouts and code all read the same names.

## Layout

```
components.json            inventory: which components exist, their variants, kits, optional Figma keys
tokens/primitives.json     raw palette and scales (never used directly by products)
tokens/themes/light.json   semantic tokens: color.text, color.surface, space.4, radius.md …
tokens/themes/dark.json    same names, different aliases
CHANGELOG.md               every release, with breaking changes called out
```

Add code packages when you need them, for example `packages/web` (CSS variables + components), `packages/ios`, `packages/android`. Generate platform files from the tokens with a build tool such as Style Dictionary; never hand-copy values.

## Rules

- **Semantic names are the contract.** Products, prototypes and Figma use `color.primary`, never `palette.brand.600`. Renaming a semantic token is a breaking change.
- **Themes only re-point aliases.** A new brand or dark mode is a new file under `tokens/themes/`, not new names.
- **Kits are subsets, not forks.** `saas-dashboard`, `marketing-site` and `mobile-app` list which components each kind of product starts from; they all share one token set.
- **Contrast is checked, not eyeballed.** Text roles must reach WCAG AA (4.5:1) on every surface they sit on, in every theme.
- **Versioned with git tags** (`v1.4.0`). Products pin a version and upgrade on purpose.

## One repository or many?

Keep **one design-system repository** (this one) with themes and kits inside it, separate from every product repository and from the sdd-kit plugin. Split into several repositories only when a brand is owned by a different team with its own release cadence; even then, share the semantic token names so tooling keeps working.

## Using it from a product

1. Add it to the product, for example as a git submodule at `design-system/` pinned to a tag, or as a package.
2. In the product's `CLAUDE.md`:
   ```
   - Design system: design-system/components.json
   - Theme: light
   - Kit: saas-dashboard
   ```
3. `/sdd-kit:sdd <ID> --design` (or `/sdd-design:prototype <ID>`) now builds prototypes only from these components and tokens.

## Figma

- Create a Figma library file for the system and publish it to your team. Its variables mirror `tokens/` (one collection, one mode per theme).
- To let Figma exports place real library components instead of drawn stand-ins, add the published component key to `components.json`:
  ```json
  "Button": { "variants": ["primary", "secondary", "ghost", "danger"],
              "figma": { "key": "<component set key>", "variantProperty": "Variant", "textProperty": "Label" } }
  ```
  Publishing libraries requires a Figma plan that supports team libraries.
