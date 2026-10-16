# screens.json — one source for the HTML prototype and the Figma layout

`specs/<ID>/design/screens.json` describes every screen of a feature as a tree of design-system components. `render_prototype.py` turns it into a clickable HTML prototype; the `sdd-figma` plugin turns the same file into auto-layout frames in Figma. Nobody draws the same screen twice.

## File

```json
{
  "$schema": "sdd-screens/1",
  "feature": "F-001",
  "title": "Password reset",
  "platform": "web",
  "viewport": { "width": 1280, "height": 800 },
  "spec_sha1": "3f786850e387550fdab836ed7e6dc881de23001b",
  "screens": [
    {
      "id": "enter-email",
      "title": "Enter email",
      "state": "default",
      "ac": ["AC-1", "AC-2"],
      "note": "Same message whether or not the email exists",
      "body": { "type": "Stack", "gap": "space.4", "padding": "space.8", "children": [] }
    }
  ],
  "flows": [
    { "from": "enter-email", "to": "check-inbox", "on": "Send link", "ac": "AC-1" }
  ]
}
```

| Field | Rule |
|---|---|
| `platform` | `web` or `mobile`. Default viewport: web 1280×800, mobile 390×844. |
| `spec_sha1` | Optional, but write it. The sha1 of the bytes of the `spec.md` this file was built from: 40 lower-case hex characters (`sha1sum spec.md`). `render_prototype.py check` prints it on an `info:` line while the field is missing. When `spec.md` changes later, `check` and `build_bundle.py` warn `screens.json was built from an older spec.md; re-run the prototype`. Update it each time you bring screens.json in line with the spec. |
| `screens[].id` | kebab-case, unique. One screen per meaningful **state**: default, empty, loading, error, success. |
| `screens[].ac` | The AC IDs this screen makes visible. Every UI-facing AC appears on at least one screen. |
| `screens[].body` | One root node, usually a `Stack`. |
| `flows` | Every navigation the prototype supports. `on` is the visible label of the control that triggers it. |

## Nodes

Every node has `type`. Values written as `"space.4"`, `"radius.md"`, `"color.surface"` are **token paths** into the design system; plain numbers are pixels.

| Type | Props |
|---|---|
| `Stack` | `direction` (`vertical`\|`horizontal`), `gap`, `padding`, `align` (`start`\|`center`\|`end`\|`stretch`), `justify` (`start`\|`center`\|`end`\|`between`), `fill` (`background`\|`surface`\|`none`), `width` (`fill`\|`hug`\|px), `children` |
| `Grid` | `columns`, `gap`, `children` |
| `Card` | `padding`, `gap`, `children` |
| `Text` | `text`, `variant` (`display`\|`title`\|`heading`\|`body`\|`caption`\|`label`), `tone` (`default`\|`muted`\|`primary`\|`danger`\|`success`) |
| `Button` | `label`, `variant` (`primary`\|`secondary`\|`ghost`\|`danger`), `link` (screen id), `full` (bool) |
| `Link` | `text`, `link` |
| `TextField` | `label`, `placeholder`, `value`, `inputType` (`text`\|`email`\|`password`), `hint`, `error` |
| `Checkbox` | `label`, `checked` |
| `Toggle` | `label`, `on` |
| `Select` | `label`, `value` |
| `Alert` | `tone` (`info`\|`success`\|`warning`\|`danger`), `title`, `text` |
| `Badge` | `text`, `tone` |
| `Image` | `alt`, `ratio` (`"16:9"`, `"1:1"`, …) |
| `Avatar` | `name` |
| `List` | `items` (strings) |
| `NavBar` | `title`, `back` (bool) |
| `TabBar` | `items`, `active` (index) |
| `Sidebar` | `items`, `active` (index) |
| `Divider`, `Spacer` | none |
| `Table` | `columns` (labels, or `{label, align}` with `align` `start`\|`end`), `rows` (one list per row, one cell per column), `selectable` (bool: a checkbox column), `selected` (row indexes; needs `selectable`), `sortable` (`true` for every column, or a list of column indexes) |
| `Modal` | `title`, `children` (the body), `actions` (`Button` or `Link` nodes, the main action last) |
| `Tabs` | `items` (labels, or `{label, link}`), `active` (index) |
| `Pagination` | `pages` (total, 1 or more), `page` (current, 1-based) |
| `Progress` | `value` (0–100), `label` |
| `Chart` | `kind` (`line`\|`bar`\|`pie`), `title` |

A design system may add types in its `components.json`; `render_prototype.py check` rejects any type or variant the design system does not declare.

### Data and overlay components

- **Table** cells are text, a number, or `{"text": "Paid", "tone": "success"}`, which draws a Badge. The tone must be a Badge variant of the design system. A table shows a handful of representative rows; pagination says how many more there are.
- **Modal** is drawn open: a scrim (`color.overlay`) over the whole screen with the dialog centred on it. Make it the last child of the screen's root, put the page it covers in the same screen, and give it its own screen per state (for example `invoices` and `confirm-delete`). One Modal per screen. Each action's `link` is the screen it leads to, so Cancel usually links back to the screen without the Modal.
- **Tabs** switch between screens: an inactive item with a `link` navigates there, and the item for the current screen is `active`. They are not a way to hide content inside one screen.
- **Chart** is a labelled placeholder, not a chart of real data. It shows the `kind` and the `title`, so the layout and the place of the chart can be reviewed before the real chart is designed. The kinds are `Chart.variants` in `components.json` (default `line`, `bar`, `pie`).
- **Progress** is a determinate bar: `value` is a percentage. Show indeterminate loading with a loading-state screen instead.

`references/example.dashboard.screens.json` uses all six.

## components.json (lives in the design-system repo)

```json
{
  "name": "acme-ds",
  "version": "1.4.0",
  "tokens": ["tokens/primitives.json", "tokens/themes/light.json"],
  "themes": {
    "light": ["tokens/primitives.json", "tokens/themes/light.json"],
    "dark": ["tokens/primitives.json", "tokens/themes/dark.json"]
  },
  "components": {
    "Button": { "variants": ["primary", "secondary", "ghost", "danger"],
                "figma": { "key": "<published component-set key>", "variantProperty": "Variant", "textProperty": "Label" } },
    "Text": { "variants": ["display", "title", "heading", "body", "caption", "label"] }
  }
}
```

`tokens` and each theme are token files merged in order (DTCG `$value`, `{alias}` references allowed). `figma.key` is optional. When present and the library is enabled in the target Figma file, the Figma export places real library instances; otherwise it draws the component from tokens.

## Semantic tokens the renderer expects

`color.background`, `color.surface`, `color.surface-2`, `color.text`, `color.text-muted`, `color.border`, `color.primary`, `color.on-primary`, `color.danger`, `color.success`, `color.warning`, `color.info`; `space.1` … `space.12`; `radius.sm`, `radius.md`, `radius.lg`; `font.family.sans`, `font.size.caption|body|heading|title|display`, `font.weight.regular|medium|bold`. Missing ones fall back to neutral defaults and are reported by `check`.

Optional: `color.overlay`, the Modal scrim, as a colour with alpha (`#18181d80`). `check` asks for it only when a screen uses a Modal. `color.surface-2` is used for table headers, progress tracks and chart plots, so it has to differ visibly from `color.surface` in every theme.
