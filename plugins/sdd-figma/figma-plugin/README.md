# SDD Kit Import (Figma plugin)

Turns one feature's `figma/bundle.json` into Figma pages, so diagrams and screens come from the spec instead of being drawn by hand.

## What it builds

In the open design file:

- **`<feature> · How it works`**: every diagram SVG from `/sdd-diagrams:feature-diagrams`, stacked top to bottom. Each one has a heading with its title, kind and `source sha1`.
- **`<feature> · Screens`**: one frame per screen in `design/screens.json`, laid out left to right. Each frame is built from auto layout, is `viewport.width` wide, has a minimum height of `viewport.height` and grows with its content. An annotation above each frame shows `id · state · AC-…` and the note, if there is one. Layers are named after components (`Card`, `Button / primary`, `TextField / Email`), so a developer can read the layer list as a component tree.
- **Prototype**: each `Button` and `Link` with a `link` (or a matching `flows` entry) gets *On click → Navigate to* its target screen. The first screen is the flow's starting point.
- **Variables**: a collection named `<design system> tokens` (or `SDD tokens`) holds COLOR variables for `color.*` and FLOAT variables for `space.*`, `radius.*` and `font.size.*`. Fills, strokes, gaps, padding, corner radii and font sizes are bound to these variables. Running the plugin again updates the values in place.
- **Library components**: when `components.json` gives a component a `figma.key` (with `variantProperty` and `textProperty`), the plugin places a real instance and sets its variant and label. If that fails, it draws the component from tokens. The log lists which components were instanced and which were drawn.

Running it again rebuilds only what the plugin made: pages and layers marked with plugin data `sdd = generated`. Anything you added yourself, including notes on a generated page, is left alone.

## Make the bundle

```bash
python3 plugins/sdd-figma/skills/figma-export/scripts/build_bundle.py specs/F-001-password-reset \
  [--ds path/to/components.json] [--theme light]
# writes specs/F-001-password-reset/figma/bundle.json
```

Without `--ds`, the script takes the design system from the `Design system: <path>/components.json` line in the project's `CLAUDE.md`. With no design system at all, screens are still exported using neutral tokens. Unknown component types or variants show up as warnings.

## Install and run (Figma desktop)

1. Open a Figma design file in the **desktop app**.
2. **Plugins → Development → Import plugin from manifest…** and choose `plugins/sdd-figma/figma-plugin/manifest.json`.
3. **Plugins → Development → SDD Kit Import**, choose `bundle.json` (or paste its contents), then click **Build in Figma**.
4. The panel stays open and shows the summary: pages, frames, diagrams, links, variables, instanced and drawn components, and warnings.

The plugin makes no network requests (`allowedDomains: ["none"]`) and only works with the file that is open.

## Limitations

- Development plugins run only in the Figma desktop app, and only for the person who imported them. Other people need to import the manifest themselves, or the plugin has to be published privately to your organisation.
- Diagrams are imported as vectors. They are not editable auto layout. To change one, edit the Mermaid in `spec.md` and rebuild. `build_bundle.py` turns SVG arrowhead markers into plain shapes, because Figma does not import `<marker>`.
- Text inside the SVGs uses whatever fonts Figma has. A missing font is substituted. The screens use Inter, fall back to Roboto, and then to the first font that is available.
- Library instancing only works when the library is enabled in this file (Assets → Libraries). A key that cannot be imported falls back to drawing the component.
- The screens are a faithful layout, not pixel-identical to the HTML prototype. Drawn components are simple frames, not library components.
- If the Variables API is not available, the plugin uses plain colours and sizes and says so in the log.

## Test

```bash
node scripts/test_figma_plugin.js
```

The test builds a bundle from the EXAMPLE-001 spec and runs `code.js` against a strict mock of the Plugin API. The mock rejects FILL/HUG outside auto layout and rejects text set before its font is loaded.
