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

A design system may add types in its `components.json`; `render_prototype.py check` rejects any type or variant the design system does not declare.

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
