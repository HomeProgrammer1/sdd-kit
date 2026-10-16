#!/usr/bin/env python3
"""render_prototype: turn specs/<ID>/design/screens.json into a clickable HTML
prototype styled by the project's design-system tokens, and check it.

screens.json is the single source for the prototype and the Figma layout
(see references/screens-schema.md). The HTML written here is generated; edit
screens.json or the design system, never the HTML.

Usage:
  render_prototype.py check <screens.json> [--ds components.json] [--theme NAME] [--spec spec.md] [--neutral]
  render_prototype.py build <screens.json> [--ds components.json] [--theme NAME] [--spec spec.md] [--out DIR] [--neutral]

The design system is found from --ds, else from the line
"Design system: <path/to/components.json>" in the nearest CLAUDE.md above the
screens file. Without one the command stops (exit 2) unless --neutral is given,
which uses a plain grey placeholder theme for throwaway sketches.

The spec is --spec, else ../spec.md next to the design/ folder. Its sha1 is
compared with "spec_sha1" in screens.json, so a prototype built from an older
spec is reported.

Standard library only. No network.
"""
import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path

CORE_TYPES = {
    "Stack", "Grid", "Card", "Divider", "Spacer", "Text", "Button", "Link", "TextField", "Checkbox",
    "Toggle", "Select", "Alert", "Badge", "Image", "Avatar", "List", "NavBar", "TabBar", "Sidebar",
    "Table", "Modal", "Tabs", "Pagination", "Progress", "Chart",
}
NEUTRAL_TOKENS = {
    "color.background": "#f7f7f8", "color.surface": "#ffffff", "color.surface-2": "#eeeef0",
    "color.text": "#18181d", "color.text-muted": "#5b5b66", "color.border": "#dcdce0",
    "color.primary": "#3f3f46", "color.on-primary": "#ffffff", "color.primary-subtle": "#eeeef0",
    "color.danger": "#c62828", "color.danger-subtle": "#fdecec", "color.success": "#1b7a3a",
    "color.success-subtle": "#e8f5ec", "color.warning": "#8a5a00", "color.warning-subtle": "#fdf4e3",
    "color.info": "#1d5fbf", "color.info-subtle": "#e9f1fc", "color.overlay": "#18181d80",
    "radius.sm": 4, "radius.md": 8, "radius.lg": 16, "radius.full": 999,
    "font.family.sans": "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    "font.size.caption": 12, "font.size.label": 14, "font.size.body": 16, "font.size.heading": 20,
    "font.size.title": 28, "font.size.display": 40,
    "font.weight.regular": 400, "font.weight.medium": 500, "font.weight.bold": 700,
}
NEUTRAL_TOKENS.update({f"space.{n}": 4 * n for n in range(0, 13)})
OPTIONAL_TOKENS = {"color.overlay"}   # only Modal uses it; check warns when a Modal needs it
EXPECTED = [k for k in NEUTRAL_TOKENS if k not in OPTIONAL_TOKENS and (not k.startswith("space.") or k in ("space.1", "space.2", "space.4", "space.8"))]
VIEWPORTS = {"web": (1280, 800), "mobile": (390, 844)}
AC_RE = re.compile(r"\bAC-\d+\b")
SHA1_RE = re.compile(r"[0-9a-f]{40}")
CHART_KINDS = ["line", "bar", "pie"]
CHART_BARS = (45, 70, 55, 90, 65, 80)
BADGE_TONES = ["default", "primary", "danger", "success", "warning", "info"]


def esc(s):
    return html.escape(str(s), quote=True)


# --------------------------------------------------------------------- tokens


def flatten(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        if "$value" in obj or "value" in obj:
            out[prefix] = obj.get("$value", obj.get("value"))
            return out
        for k, v in obj.items():
            if not k.startswith("$"):
                out.update(flatten(v, f"{prefix}.{k}" if prefix else k))
    elif prefix:
        out[prefix] = obj
    return out


def resolve(flat, value, seen=()):
    if isinstance(value, str):
        m = re.fullmatch(r"\{([^}]+)\}", value.strip())
        if m:
            key = m.group(1)
            if key in seen or len(seen) > 10 or key not in flat:
                return None
            return resolve(flat, flat[key], seen + (key,))
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict) and "value" in value and "unit" in value:   # DTCG 2025 dimension
        return value["value"]
    return value


def find_design_system(start):
    for folder in [start] + list(start.parents):
        md = folder / "CLAUDE.md"
        if md.exists():
            m = re.search(r"^\s*[-*]?\s*Design system:\s*(\S+\.json)", md.read_text(encoding="utf-8"), re.M)
            if m:
                p = Path(m.group(1))
                return p if p.is_absolute() else (folder / p)
            return None
    return None


def load_design_system(ds_path, theme=None):
    ds = json.loads(Path(ds_path).read_text(encoding="utf-8"))
    files = ds.get("tokens") or []
    if theme and theme in (ds.get("themes") or {}):
        files = ds["themes"][theme]
    if isinstance(files, str):
        files = [files]
    flat = {}
    for f in files:
        flat.update(flatten(json.loads((Path(ds_path).parent / f).read_text(encoding="utf-8"))))
    tokens = {}
    for k, v in flat.items():
        r = resolve(flat, v)
        if r is not None:
            tokens[k] = r
    return ds, tokens


# --------------------------------------------------------------------- checks

CONTRAST_PAIRS = [
    ("color.text", "color.background"), ("color.text", "color.surface"), ("color.text-muted", "color.surface"),
    ("color.on-primary", "color.primary"), ("color.primary", "color.surface"), ("color.danger", "color.surface"),
    # Table header, selected rows, active tabs and sidebar items, muted text on the page
    ("color.text-muted", "color.surface-2"), ("color.text", "color.primary-subtle"),
    ("color.primary", "color.primary-subtle"), ("color.text-muted", "color.background"),
] + [(f"color.{t}", f"color.{t}-subtle") for t in ("danger", "success", "warning", "info")] \
  + [("color.text", f"color.{t}-subtle") for t in ("danger", "success", "warning", "info")]


def luminance(value):
    h = str(value).strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", h):
        return None
    ch = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    ch = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def contrast_warnings(tokens):
    t = dict(NEUTRAL_TOKENS)
    t.update(tokens)
    out = []
    for fg, bg in CONTRAST_PAIRS:
        a, b = luminance(t.get(fg)), luminance(t.get(bg))
        if a is None or b is None:
            continue
        ratio = (max(a, b) + 0.05) / (min(a, b) + 0.05)
        if ratio < 4.5:
            out.append(f"contrast: {fg} on {bg} is {ratio:.2f}:1, below WCAG AA 4.5:1")
    return out



def walk(node, path="body"):
    yield node, path
    for key in ("children", "actions"):
        for k, child in enumerate(node.get(key) or []):
            if not isinstance(child, dict):
                child = {"type": f"<{type(child).__name__}>"}
            yield from walk(child, f"{path}/{'' if key == 'children' else key + '/'}{child.get('type', '?')}[{k}]")


def variant_of(node):
    return node.get("variant") or node.get("tone")


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def item_label(item):
    return item.get("label", item.get("text")) if isinstance(item, dict) else item


def node_links(node):
    """Screen ids a node navigates to: its `link`, and the `link` of Tabs items."""
    out = [node["link"]] if node.get("link") else []
    if node.get("type") == "Tabs" and isinstance(node.get("items"), list):
        out += [i["link"] for i in node["items"] if isinstance(i, dict) and i.get("link")]
    return out


def prop_errors(node, inventory):
    """Shape of the props of Table, Modal, Tabs, Pagination, Progress and Chart (screens-schema.md)."""
    t, e = node.get("type"), []
    if t == "Table":
        cols, rows = node.get("columns"), node.get("rows")
        if not isinstance(cols, list) or not cols:
            e.append("Table needs `columns`: a non-empty list of labels or {label, align}")
            cols = []
        for k, c in enumerate(cols):
            if isinstance(c, dict):
                if not isinstance(c.get("label"), str):
                    e.append(f"Table column {k} needs a `label`")
                if c.get("align", "start") not in ("start", "end"):
                    e.append(f"Table column {k}: align `{c.get('align')}` is not start|end")
            elif not isinstance(c, str):
                e.append(f"Table column {k} must be a label or {{label, align}}")
        if not isinstance(rows, list):
            e.append("Table needs `rows`: a list of rows, each a list with one cell per column")
            rows = []
        tones = (inventory.get("Badge") or {}).get("variants") or BADGE_TONES
        for r, row in enumerate(rows):
            if not isinstance(row, list):
                e.append(f"Table row {r} must be a list of cells")
                continue
            if cols and len(row) != len(cols):
                e.append(f"Table row {r} has {len(row)} cell(s) for {len(cols)} column(s)")
            for c, cell in enumerate(row):
                if isinstance(cell, dict):
                    if not isinstance(cell.get("text"), str):
                        e.append(f"Table row {r} cell {c}: a badge cell needs `text`")
                    if cell.get("tone", "default") not in tones:
                        e.append(f"Table row {r} cell {c}: tone `{cell.get('tone')}` is not in the design system ({', '.join(tones)})")
                elif not (isinstance(cell, str) or is_num(cell)):
                    e.append(f"Table row {r} cell {c} must be text, a number or {{text, tone}}")
        if not isinstance(node.get("selectable", False), bool):
            e.append("Table `selectable` must be true or false")
        srt = node.get("sortable", False)
        if not isinstance(srt, bool) and not (isinstance(srt, list) and all(is_int(i) and 0 <= i < len(cols) for i in srt)):
            e.append(f"Table `sortable` must be true, false or a list of column indexes 0..{max(0, len(cols) - 1)}")
        sel = node.get("selected")
        if sel is not None:
            if node.get("selectable") is not True:
                e.append("Table `selected` needs `selectable: true`")
            if not (isinstance(sel, list) and all(is_int(i) and 0 <= i < len(rows) for i in sel)):
                e.append(f"Table `selected` must be a list of row indexes 0..{max(0, len(rows) - 1)}")
    elif t == "Modal":
        if not isinstance(node.get("title"), str) or not node["title"].strip():
            e.append("Modal needs a `title`")
        acts = node.get("actions", [])
        if not isinstance(acts, list) or not all(isinstance(a, dict) and a.get("type") in ("Button", "Link") for a in acts):
            e.append("Modal `actions` must be a list of Button or Link nodes")
    elif t == "Tabs":
        items = node.get("items")
        if not isinstance(items, list) or not items or not all(isinstance(item_label(i), str) and item_label(i) for i in items):
            e.append("Tabs needs `items`: a non-empty list of labels or {label, link}")
            items = []
        act = node.get("active", 0)
        if not is_int(act) or not 0 <= act < max(1, len(items)):
            e.append(f"Tabs `active` must be an index 0..{max(0, len(items) - 1)}")
    elif t == "Pagination":
        page, pages = node.get("page", 1), node.get("pages")
        if not is_int(pages) or pages < 1:
            e.append("Pagination needs `pages`: a whole number, 1 or more")
        elif not is_int(page) or not 1 <= page <= pages:
            e.append(f"Pagination `page` must be 1..{pages}")
    elif t == "Progress":
        v = node.get("value")
        if not is_num(v) or not 0 <= v <= 100:
            e.append(f"Progress `value` must be a number from 0 to 100 (got {json.dumps(v)})")
        if "label" in node and not isinstance(node["label"], str):
            e.append("Progress `label` must be text")
    elif t == "Chart":
        kinds = (inventory.get("Chart") or {}).get("variants") or CHART_KINDS
        if node.get("kind") not in kinds:
            e.append(f"Chart kind `{node.get('kind')}` is not in the design system ({', '.join(kinds)})")
        if not isinstance(node.get("title"), str) or not node["title"].strip():
            e.append("Chart needs a `title`")
    return e


def check(doc, ds, tokens, spec_text=None, spec_sha1=None):
    errors, warnings = [], []
    screens = doc.get("screens") or []
    if doc.get("platform", "web") not in VIEWPORTS:
        errors.append(f"platform must be one of {sorted(VIEWPORTS)}")
    ids = [s.get("id") for s in screens]
    if not screens:
        errors.append("no screens")
    for i in {i for i in ids if ids.count(i) > 1}:
        errors.append(f"duplicate screen id `{i}`")
    known = set(ids)
    inventory = (ds or {}).get("components") or {}
    allowed = set(inventory) if inventory else CORE_TYPES
    shown_ac = set()
    modal = False
    for s in screens:
        sid = s.get("id", "?")
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", str(sid)):
            errors.append(f"screen id `{sid}` must be kebab-case")
        shown_ac.update(s.get("ac") or [])
        body = s.get("body")
        if not isinstance(body, dict) or "type" not in body:
            errors.append(f"{sid}: body must be one node with a type")
            continue
        modals = 0
        for node, path in walk(body):
            t = node.get("type")
            if t not in allowed:
                errors.append(f"{sid} {path}: component `{t}` is not in the design system")
                continue
            variants = (inventory.get(t) or {}).get("variants")
            v = variant_of(node)
            if variants and v and v not in variants and t not in ("Text",) and node.get("variant"):
                errors.append(f"{sid} {path}: {t} variant `{v}` is not in the design system ({', '.join(variants)})")
            if t == "Text" and node.get("variant") and variants and node["variant"] not in variants:
                errors.append(f"{sid} {path}: Text variant `{node['variant']}` is not in the design system")
            errors += [f"{sid} {path}: {e}" for e in prop_errors(node, inventory)]
            modals += t == "Modal"
            for link in node_links(node):
                if link not in known:
                    errors.append(f"{sid} {path}: link to unknown screen `{link}`")
            for key in ("gap", "padding"):
                val = node.get(key)
                if ds and isinstance(val, str) and val not in tokens:
                    warnings.append(f"{sid} {path}: token `{val}` is not defined; neutral value used")
        if modals > 1:
            warnings.append(f"{sid}: {modals} Modals on one screen; show one open dialog per screen state")
        modal = modal or modals > 0
    for f in doc.get("flows") or []:
        for end in ("from", "to"):
            if f.get(end) not in known:
                errors.append(f"flow {f.get('from')} → {f.get('to')}: unknown screen `{f.get(end)}`")
    linked = {link for s in screens if isinstance(s.get("body"), dict) for n, _ in walk(s["body"]) for link in node_links(n)}
    linked |= {f.get("to") for f in doc.get("flows") or []}
    for s in screens[1:]:
        if s.get("id") not in linked:
            warnings.append(f"screen `{s.get('id')}` cannot be reached by any link or flow")
    built_from = doc.get("spec_sha1")
    if built_from is not None and not (isinstance(built_from, str) and SHA1_RE.fullmatch(built_from)):
        warnings.append("spec_sha1 must be the 40-character lower-case sha1 of spec.md")
    elif built_from and spec_sha1 and built_from != spec_sha1:
        warnings.append(f"screens.json was built from an older spec.md; re-run the prototype "
                        f"(spec_sha1 {built_from[:7]}, spec.md is now {spec_sha1[:7]})")
    if spec_text:
        missing = sorted(set(AC_RE.findall(spec_text)) - shown_ac, key=lambda a: int(a.split("-")[1]))
        if missing:
            warnings.append(f"ACs not shown on any screen: {', '.join(missing)} (fine if they have no UI)")
    if ds:
        warnings += contrast_warnings(tokens)
        if modal and "color.overlay" not in tokens:
            warnings.append("Modal uses `color.overlay` (the scrim), which the design system does not define; neutral value used")
    gaps = [k for k in EXPECTED if k not in tokens]
    if ds and gaps:
        warnings.append(f"design system lacks {len(gaps)} expected token(s): {', '.join(gaps[:8])}{' …' if len(gaps) > 8 else ''}")
    return errors, warnings


# --------------------------------------------------------------------- render


class Renderer:
    def __init__(self, tokens):
        self.t = dict(NEUTRAL_TOKENS)
        self.t.update(tokens)

    def css_var(self, ref, default_px=None):
        """A token path → var(--x, fallback); a number → px."""
        if ref is None:
            return None if default_px is None else f"{default_px}px"
        if isinstance(ref, (int, float)):
            return f"{ref}px"
        name = "--" + ref.replace(".", "-")
        val = self.t.get(ref)
        if isinstance(val, (int, float)):
            return f"var({name}, {val}px)"
        return f"var({name}{', ' + str(val) if val is not None else ''})"

    def tokens_css(self):
        lines = []
        for k, v in sorted(self.t.items()):
            if k.startswith(("palette.", "scale.")):
                continue
            if isinstance(v, (int, float)) and not k.startswith("font.weight"):
                v = f"{v}px"
            if isinstance(v, (str, int, float)) and re.fullmatch(r"[\w\s#%(),.'\"/-]+", str(v)):
                lines.append(f"  --{k.replace('.', '-')}: {v};")
        return ":root {\n" + "\n".join(lines) + "\n}\n"

    def node(self, n):
        t = n.get("type")
        fn = getattr(self, "r_" + str(t), None)
        if fn is None:
            return f'<div class="unknown">{esc(t)}</div>'
        return fn(n)

    def kids(self, n):
        return "".join(self.node(c) for c in n.get("children") or [])

    def link_attr(self, n):
        return f' data-link="{esc(n["link"])}"' if n.get("link") else ""

    def box_style(self, n, direction="column", gap=None, padding=None):
        st = [f"flex-direction:{direction}"]
        g = self.css_var(n.get("gap", gap))
        p = self.css_var(n.get("padding", padding))
        if g:
            st.append(f"gap:{g}")
        if p:
            st.append(f"padding:{p}")
        align = {"start": "flex-start", "center": "center", "end": "flex-end", "stretch": "stretch"}.get(n.get("align", "stretch"))
        justify = {"start": "flex-start", "center": "center", "end": "flex-end", "between": "space-between"}.get(n.get("justify", "start"))
        st += [f"align-items:{align}", f"justify-content:{justify}"]
        fill = n.get("fill")
        if fill in ("background", "surface"):
            st.append(f"background:var(--color-{fill})")
        w = n.get("width")
        if w == "fill":
            st.append("align-self:stretch")
        elif isinstance(w, (int, float)):
            st.append(f"width:{w}px;max-width:100%")
        return ";".join(st)

    def r_Stack(self, n):
        direction = "row" if n.get("direction") == "horizontal" else "column"
        cls = "st" + (" row" if direction == "row" else "") + (" fill" if n.get("width") == "fill" else "")
        return f'<div class="{cls}" style="{self.box_style(n, direction)}">{self.kids(n)}</div>'

    def r_Card(self, n):
        cls = "cd st" + (" fill" if n.get("width") == "fill" else "")
        return f'<div class="{cls}" style="{self.box_style(n, "column", "space.4", "space.6")}">{self.kids(n)}</div>'

    def r_Grid(self, n):
        cols = int(n.get("columns", 2))
        return (f'<div class="gr" style="grid-template-columns:repeat({cols},minmax(0,1fr));gap:{self.css_var(n.get("gap", "space.4"))}">'
                f'{self.kids(n)}</div>')

    def r_Text(self, n):
        v = n.get("variant", "body")
        tag = {"display": "h1", "title": "h1", "heading": "h2"}.get(v, "p")
        return f'<{tag} class="tx tx-{esc(v)} tone-{esc(n.get("tone", "default"))}">{esc(n.get("text", ""))}</{tag}>'

    def r_Button(self, n):
        full = " full" if n.get("full") else ""
        return f'<button type="button" class="btn btn-{esc(n.get("variant", "primary"))}{full}"{self.link_attr(n)}>{esc(n.get("label", "Button"))}</button>'

    def r_Link(self, n):
        return f'<a href="#" class="lnk"{self.link_attr(n)}>{esc(n.get("text", "Link"))}</a>'

    def field(self, n, control):
        err = n.get("error")
        out = f'<label class="fld{" fld-err" if err else ""}"><span class="fld-l">{esc(n.get("label", ""))}</span>{control}'
        if err:
            out += f'<span class="fld-h tone-danger">{esc(err)}</span>'
        elif n.get("hint"):
            out += f'<span class="fld-h">{esc(n["hint"])}</span>'
        return out + "</label>"

    def r_TextField(self, n):
        typ = n.get("inputType", "text")
        attrs = f' type="{esc(typ)}"'
        if n.get("placeholder"):
            attrs += f' placeholder="{esc(n["placeholder"])}"'
        if n.get("value"):
            attrs += f' value="{esc(n["value"])}"'
        if n.get("error"):
            attrs += ' aria-invalid="true"'
        return self.field(n, f'<input class="inp"{attrs}>')

    def r_Select(self, n):
        return self.field(n, f'<select class="inp"><option>{esc(n.get("value", "Choose…"))}</option></select>')

    def r_Checkbox(self, n):
        checked = " checked" if n.get("checked") else ""
        return f'<label class="chk"><input type="checkbox"{checked}><span>{esc(n.get("label", ""))}</span></label>'

    def r_Toggle(self, n):
        on = " checked" if n.get("on") else ""
        return f'<label class="chk tgl"><input type="checkbox" role="switch"{on}><span class="tgl-t"></span><span>{esc(n.get("label", ""))}</span></label>'

    def r_Alert(self, n):
        tone = n.get("tone", "info")
        title = f'<strong>{esc(n["title"])}</strong>' if n.get("title") else ""
        return f'<div class="al al-{esc(tone)}" role="status">{title}<p>{esc(n.get("text", ""))}</p></div>'

    def r_Badge(self, n):
        return f'<span class="bdg bdg-{esc(n.get("tone", "default"))}">{esc(n.get("text", ""))}</span>'

    def r_Image(self, n):
        ratio = str(n.get("ratio", "16:9")).replace(":", "/")
        return f'<div class="img" role="img" aria-label="{esc(n.get("alt", "image"))}" style="aspect-ratio:{esc(ratio)}"><span>{esc(n.get("alt", "image"))}</span></div>'

    def r_Avatar(self, n):
        initials = "".join(w[0] for w in str(n.get("name", "?")).split()[:2]).upper()
        return f'<span class="av" title="{esc(n.get("name", ""))}">{esc(initials)}</span>'

    def r_List(self, n):
        return '<ul class="ls">' + "".join(f"<li>{esc(i)}</li>" for i in n.get("items") or []) + "</ul>"

    def r_NavBar(self, n):
        back = '<span class="nb-back" aria-hidden="true">‹</span>' if n.get("back") else ""
        return f'<header class="nb">{back}<span class="tx tx-heading">{esc(n.get("title", ""))}</span></header>'

    def bar(self, n, cls):
        active = n.get("active", 0)
        items = "".join(f'<span class="{"on" if k == active else ""}">{esc(i)}</span>' for k, i in enumerate(n.get("items") or []))
        return f'<nav class="{cls}">{items}</nav>'

    def r_TabBar(self, n):
        return self.bar(n, "tb")

    def r_Sidebar(self, n):
        return self.bar(n, "sb")

    def r_Table(self, n):
        cols = n.get("columns") or []
        srt = n.get("sortable")
        sortable = set(range(len(cols))) if srt is True else set(srt if isinstance(srt, list) else [])
        sel, selected = n.get("selectable"), set(n.get("selected") or [])
        ends = [isinstance(c, dict) and c.get("align") == "end" for c in cols]
        mark, end, on = ' <span class="tbl-sort" aria-hidden="true">↕</span>', ' class="end"', ' class="on"'
        head = "".join(f'<th scope="col"{end if ends[k] else ""}>{esc(item_label(c))}{mark if k in sortable else ""}</th>'
                       for k, c in enumerate(cols))
        if sel:
            head = '<th class="tbl-sel"><input type="checkbox" aria-label="Select all rows"></th>' + head
        body = []
        for r, row in enumerate(n.get("rows") or []):
            cells = "".join(f'<td{end if k < len(ends) and ends[k] else ""}>{self.cell(v)}</td>' for k, v in enumerate(row))
            if sel:
                cells = f'<td class="tbl-sel"><input type="checkbox" aria-label="Select row {r + 1}"{" checked" if r in selected else ""}></td>' + cells
            body.append(f'<tr{on if r in selected else ""}>{cells}</tr>')
        return f'<div class="tbl-w"><table class="tbl"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'

    def cell(self, v):
        if isinstance(v, dict):
            return f'<span class="bdg bdg-{esc(v.get("tone", "default"))}">{esc(v.get("text", ""))}</span>'
        return esc(v)

    def r_Modal(self, n):
        title = n.get("title", "Dialog")
        w = n.get("width")
        style = f' style="width:{w}px"' if isinstance(w, (int, float)) else ""
        actions = "".join(self.node(a) for a in n.get("actions") or [])
        foot = f'<div class="mdl-act">{actions}</div>' if actions else ""
        return (f'<div class="mdl"><div class="mdl-d" role="dialog" aria-modal="true" aria-label="{esc(title)}"{style}>'
                f'<h2 class="tx tx-heading">{esc(title)}</h2>{self.kids(n)}{foot}</div></div>')

    def r_Tabs(self, n):
        active, out = n.get("active", 0), []
        for k, it in enumerate(n.get("items") or []):
            on = k == active
            link = f' data-link="{esc(it["link"])}"' if isinstance(it, dict) and it.get("link") else ""
            out.append(f'<button type="button" role="tab" aria-selected="{"true" if on else "false"}" class="tab{" on" if on else ""}"{link}>'
                       f'{esc(item_label(it))}</button>')
        return f'<div class="tabs" role="tablist">{"".join(out)}</div>'

    def r_Pagination(self, n):
        pages = max(1, int(n.get("pages", 1)))
        page = min(pages, max(1, int(n.get("page", 1))))
        current = ' class="on" aria-current="page"'
        items = [f'<span class="{"off" if page == 1 else ""}">‹ Previous</span>']
        for p in page_list(page, pages):
            items.append('<span class="gap">…</span>' if p is None else f'<span{current if p == page else ""}>{p}</span>')
        items.append(f'<span class="{"off" if page == pages else ""}">Next ›</span>')
        return f'<nav class="pg" aria-label="Pagination">{"".join(items)}</nav>'

    def r_Progress(self, n):
        v = max(0.0, min(100.0, float(n.get("value", 0))))
        label = n.get("label")
        name = f' aria-label="{esc(label)}"' if label else ""
        return (f'<div class="pr"><div class="pr-h"><span>{esc(label or "")}</span><span class="tone-muted">{v:g}%</span></div>'
                f'<div class="pr-t" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{v:g}"{name}>'
                f'<div class="pr-v" style="width:{v:g}%"></div></div></div>')

    def r_Chart(self, n):
        kind = n.get("kind") if n.get("kind") in CHART_KINDS else "bar"
        title = n.get("title", "Chart")
        if kind == "line":
            plot = ('<svg class="ch-svg" viewBox="0 0 300 100" preserveAspectRatio="none" aria-hidden="true">'
                    '<polyline points="0,90 60,60 120,72 180,30 240,44 300,10" vector-effect="non-scaling-stroke"/></svg>')
        elif kind == "pie":
            plot = '<div class="ch-donut" aria-hidden="true"></div>'
        else:
            plot = "".join(f'<span style="height:{h}%"></span>' for h in CHART_BARS)
        return (f'<figure class="ch ch-{kind}" role="img" aria-label="{esc(title)} ({kind} chart placeholder)">'
                f'<figcaption class="tx tx-label">{esc(title)}</figcaption><div class="ch-plot">{plot}</div>'
                f'<p class="tx tx-caption tone-muted">Placeholder: {kind} chart, not real data</p></figure>')

    def r_Divider(self, n):
        return '<hr class="dv">'

    def r_Spacer(self, n):
        return '<div class="sp"></div>'


def page_list(page, pages):
    """1 … 4 5 6 … 12: first, last and the neighbours of the current page; None marks a gap."""
    out = []
    for p in range(1, pages + 1):
        if pages <= 7 or p in (1, pages) or abs(p - page) <= 1:
            out.append(p)
        elif out[-1] is not None:
            out.append(None)
    return out


COMPONENT_CSS = """
*{box-sizing:border-box}
.screen-root{font-family:var(--font-family-sans);color:var(--color-text);background:var(--color-background);font-size:var(--font-size-body);line-height:1.45;min-height:100%;position:relative}
.st{display:flex}
.row>.fill{flex:1 1 0;min-width:0}
.screen-root>.st,.screen-root>.cd{min-height:inherit}
.gr{display:grid}
.cd{background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-lg)}
.tx{margin:0}
.tx-display{font-size:var(--font-size-display);font-weight:var(--font-weight-bold);line-height:1.1}
.tx-title{font-size:var(--font-size-title);font-weight:var(--font-weight-bold);line-height:1.2}
.tx-heading{font-size:var(--font-size-heading);font-weight:var(--font-weight-bold)}
.tx-body{font-size:var(--font-size-body)}
.tx-caption{font-size:var(--font-size-caption)}
.tx-label{font-size:var(--font-size-label);font-weight:var(--font-weight-medium)}
.tone-muted{color:var(--color-text-muted)}.tone-primary{color:var(--color-primary)}
.tone-danger{color:var(--color-danger)}.tone-success{color:var(--color-success)}
.btn{font:inherit;font-weight:var(--font-weight-medium);border-radius:var(--radius-md);padding:12px 20px;border:1px solid transparent;cursor:pointer;line-height:1.2}
.btn.full{width:100%}
.btn-primary{background:var(--color-primary);color:var(--color-on-primary)}
.btn-secondary{background:var(--color-surface);color:var(--color-text);border-color:var(--color-border)}
.btn-ghost{background:transparent;color:var(--color-primary)}
.btn-danger{background:var(--color-danger);color:var(--color-on-primary)}
.btn[data-link],.lnk[data-link],.tab[data-link]{outline:2px dashed transparent;outline-offset:3px}
body.hints .btn[data-link],body.hints .lnk[data-link],body.hints .tab[data-link]{outline-color:var(--color-info)}
.lnk{color:var(--color-primary);text-decoration:underline;font-size:var(--font-size-label)}
.fld{display:flex;flex-direction:column;gap:6px}
.fld-l{font-size:var(--font-size-label);font-weight:var(--font-weight-medium)}
.fld-h{font-size:var(--font-size-caption);color:var(--color-text-muted)}
.inp{font:inherit;height:44px;padding:0 12px;border:1px solid var(--color-border);border-radius:var(--radius-md);background:var(--color-surface);color:var(--color-text);width:100%}
.fld-err .inp{border-color:var(--color-danger)}
.chk{display:flex;align-items:center;gap:10px;font-size:var(--font-size-label)}
.chk input{width:18px;height:18px;accent-color:var(--color-primary);margin:0}
.tgl input{position:absolute;opacity:0}
.tgl-t{width:36px;height:20px;border-radius:999px;background:var(--color-border);position:relative;flex:none}
.tgl-t::after{content:"";position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:var(--color-surface);transition:left .15s}
.tgl input:checked+.tgl-t{background:var(--color-primary)}
.tgl input:checked+.tgl-t::after{left:18px}
.al{border:1px solid;border-radius:var(--radius-md);padding:16px;display:flex;flex-direction:column;gap:4px}
.al p{margin:0}
.al-info{background:var(--color-info-subtle);border-color:var(--color-info)}
.al-success{background:var(--color-success-subtle);border-color:var(--color-success)}
.al-warning{background:var(--color-warning-subtle);border-color:var(--color-warning)}
.al-danger{background:var(--color-danger-subtle);border-color:var(--color-danger)}
.bdg{display:inline-block;align-self:flex-start;width:max-content;max-width:100%;padding:2px 8px;border-radius:999px;font-size:var(--font-size-caption);background:var(--color-surface-2)}
.bdg-primary{background:var(--color-primary-subtle);color:var(--color-primary)}
.bdg-danger{background:var(--color-danger-subtle);color:var(--color-danger)}
.bdg-success{background:var(--color-success-subtle);color:var(--color-success)}
.img{background:var(--color-surface-2);border-radius:var(--radius-md);display:flex;align-items:center;justify-content:center;color:var(--color-text-muted);font-size:var(--font-size-caption);width:100%}
.av{width:40px;height:40px;border-radius:50%;background:var(--color-primary-subtle);color:var(--color-primary);display:inline-flex;align-items:center;justify-content:center;font-weight:var(--font-weight-bold);font-size:var(--font-size-label)}
.ls{list-style:none;margin:0;padding:0}
.ls li{padding:12px 0;border-bottom:1px solid var(--color-border)}
.nb{display:flex;align-items:center;gap:12px;height:56px;padding:0 16px;background:var(--color-surface);border-bottom:1px solid var(--color-border)}
.nb-back{font-size:28px;line-height:1;color:var(--color-primary)}
.tb{display:flex;border-top:1px solid var(--color-border);background:var(--color-surface)}
.tb span{flex:1;text-align:center;padding:12px 4px;font-size:var(--font-size-caption);color:var(--color-text-muted)}
.tb span.on{color:var(--color-primary);font-weight:var(--font-weight-medium)}
.sb{display:flex;flex-direction:column;gap:4px;width:240px;padding:16px;background:var(--color-surface);border-right:1px solid var(--color-border)}
.sb span{padding:8px 12px;border-radius:var(--radius-md);font-size:var(--font-size-label)}
.sb span.on{background:var(--color-primary-subtle);color:var(--color-primary);font-weight:var(--font-weight-medium)}
.dv{border:0;border-top:1px solid var(--color-border);margin:0;width:100%}
.sp{flex:1}
.tbl-w{width:100%;overflow:auto;background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-md)}
.tbl{width:100%;border-collapse:collapse;font-size:var(--font-size-label)}
.tbl th{background:var(--color-surface-2);color:var(--color-text-muted);font-weight:var(--font-weight-medium);text-align:left;white-space:nowrap;padding:var(--space-3) var(--space-4)}
.tbl td{padding:var(--space-3) var(--space-4);border-top:1px solid var(--color-border)}
.tbl .end{text-align:right;font-variant-numeric:tabular-nums}
.tbl tr.on td{background:var(--color-primary-subtle)}
.tbl .tbl-sel{width:48px}
.tbl-sel input{width:18px;height:18px;margin:0;vertical-align:middle;accent-color:var(--color-primary)}
.tbl-sort{color:var(--color-text-muted)}
.mdl{position:absolute;inset:0;z-index:2;display:flex;align-items:center;justify-content:center;padding:var(--space-4);background:var(--color-overlay)}
.mdl-d{display:flex;flex-direction:column;gap:var(--space-4);width:480px;max-width:100%;padding:var(--space-6);background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-lg)}
.mdl-d p{margin:0}
.mdl-act{display:flex;justify-content:flex-end;gap:var(--space-3)}
.tabs{display:flex;gap:var(--space-1);border-bottom:1px solid var(--color-border)}
.tab{font:inherit;font-size:var(--font-size-label);font-weight:var(--font-weight-medium);color:var(--color-text-muted);background:none;border:0;border-bottom:2px solid transparent;margin-bottom:-1px;padding:var(--space-3) var(--space-4);cursor:pointer}
.tab.on{color:var(--color-primary);border-bottom-color:var(--color-primary)}
.pg{display:flex;align-items:center;gap:var(--space-1);font-size:var(--font-size-label)}
.pg span{min-width:36px;text-align:center;padding:var(--space-2) var(--space-3);border-radius:var(--radius-md)}
.pg .on{background:var(--color-primary);color:var(--color-on-primary);font-weight:var(--font-weight-medium)}
.pg .off,.pg .gap{color:var(--color-text-muted)}
.pr{display:flex;flex-direction:column;gap:var(--space-2);width:100%}
.pr-h{display:flex;justify-content:space-between;gap:var(--space-2);font-size:var(--font-size-label)}
.pr-t{height:8px;border-radius:var(--radius-full);background:var(--color-surface-2);overflow:hidden}
.pr-v{height:100%;border-radius:var(--radius-full);background:var(--color-primary)}
.ch{margin:0;display:flex;flex-direction:column;gap:var(--space-3);padding:var(--space-5);background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-lg)}
.ch-plot{height:160px;display:flex;align-items:flex-end;justify-content:center;gap:var(--space-2);padding:var(--space-3);background:var(--color-surface-2);border-radius:var(--radius-md)}
.ch-bar .ch-plot span{flex:1;background:var(--color-primary);border-radius:var(--radius-sm) var(--radius-sm) 0 0}
.ch-line .ch-plot,.ch-pie .ch-plot{align-items:center}
.ch-svg{width:100%;height:100%;overflow:visible}
.ch-svg polyline{fill:none;stroke:var(--color-primary);stroke-width:2;stroke-linejoin:round}
.ch-donut{position:relative;width:120px;height:120px;border-radius:50%;background:conic-gradient(var(--color-primary) 0 70%,var(--color-primary-subtle) 0)}
.ch-donut::after{content:"";position:absolute;inset:27px;border-radius:50%;background:var(--color-surface-2)}
.unknown{border:1px dashed var(--color-danger);color:var(--color-danger);padding:8px;font-size:12px}
"""

CHROME_CSS = """
html,body{margin:0;background:#e9e9ec;color:#1d1d22;font:14px/1.45 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}
.bar{position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;padding:10px 16px;background:#fff;border-bottom:1px solid #d6d6db}
.bar h1{font-size:15px;margin:0;font-weight:600}
.bar .meta{color:#5b5b66;font-size:12px}
.bar .sp{flex:1}
.bar button{font:inherit;padding:6px 10px;border:1px solid #c9c9cf;border-radius:6px;background:#fff;cursor:pointer}
.bar button[aria-pressed=true]{background:#1d1d22;color:#fff;border-color:#1d1d22}
main{padding:24px 16px}
.board{display:flex;flex-wrap:wrap;gap:24px}
.shot{cursor:pointer}.shot:focus-visible{outline:2px solid #1d5fbf;outline-offset:4px;border-radius:8px}
.shot .cap{display:flex;gap:8px;align-items:baseline;margin:0 0 6px;font-size:12px;color:#5b5b66}
.shot .cap b{color:#1d1d22;font-weight:600}
.thumb{overflow:hidden;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.12);background:#fff;position:relative}
.thumb .frame{transform-origin:0 0;pointer-events:none;position:absolute;top:0;left:0}
.state{display:inline-block;padding:0 6px;border-radius:999px;background:#eeeef0;font-size:11px}
.state-error{background:#fdecec;color:#a11}.state-success{background:#e8f5ec;color:#185}
.focus{display:none}
body.focus-mode .board{display:none}
body.focus-mode .focus{display:block}
.focus .note{max-width:var(--vw);margin:0 auto 10px;font-size:12px;color:#5b5b66}
.focus .frame{margin:0 auto;box-shadow:0 2px 10px rgba(0,0,0,.15);border-radius:8px;overflow:auto;max-width:100%}
.frame{background:var(--color-background)}
"""

SCRIPT = """
(function(){
  var screens = JSON.parse(document.getElementById('screens-data').textContent);
  var order = screens.map(function(s){return s.id});
  var body = document.body, focus = document.getElementById('focus');
  function show(id){
    var s = null; screens.forEach(function(x){ if (x.id === id) s = x; });
    if (!s) { body.classList.remove('focus-mode'); document.getElementById('mode').setAttribute('aria-pressed','false'); return; }
    var tpl = document.getElementById('tpl-' + id);
    focus.innerHTML = '<p class="note"></p>';
    focus.querySelector('.note').textContent = s.title + ' · ' + s.state + (s.ac.length ? ' · ' + s.ac.join(', ') : '') + (s.note ? ' · ' + s.note : '');
    focus.appendChild(tpl.content.cloneNode(true));
    body.classList.add('focus-mode');
    document.getElementById('mode').setAttribute('aria-pressed','true');
    window.scrollTo(0,0);
  }
  function route(){ show(decodeURIComponent(location.hash.slice(1))); }
  document.addEventListener('click', function(e){
    var el = e.target.closest('[data-link]');
    if (el && focus.contains(el)) { e.preventDefault(); location.hash = el.getAttribute('data-link'); return; }
    var shot = e.target.closest('.shot');
    if (shot) { location.hash = shot.getAttribute('data-id'); }
  });
  document.addEventListener('keydown', function(e){
    var shot = e.target.closest && e.target.closest('.shot');
    if (shot && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); location.hash = shot.getAttribute('data-id'); }
  });
  document.getElementById('mode').addEventListener('click', function(){
    if (body.classList.contains('focus-mode')) { location.hash = ''; } else { location.hash = order[0]; }
  });
  document.getElementById('hints').addEventListener('click', function(){
    var on = body.classList.toggle('hints'); this.setAttribute('aria-pressed', String(on));
  });
  document.addEventListener('keydown', function(e){
    if (!body.classList.contains('focus-mode')) return;
    var i = order.indexOf(decodeURIComponent(location.hash.slice(1)));
    if (e.key === 'ArrowRight' && i < order.length - 1) location.hash = order[i + 1];
    if (e.key === 'ArrowLeft' && i > 0) location.hash = order[i - 1];
    if (e.key === 'Escape') location.hash = '';
  });
  window.addEventListener('hashchange', route);
  route();
})();
"""


def render_html(doc, tokens, ds_label):
    r = Renderer(tokens)
    platform = doc.get("platform", "web")
    vw, vh = VIEWPORTS.get(platform, VIEWPORTS["web"])
    vp = doc.get("viewport") or {}
    vw, vh = int(vp.get("width", vw)), int(vp.get("height", vh))
    scale = 0.25 if vw > 600 else 0.5
    screens = doc.get("screens") or []
    meta = [{"id": s.get("id"), "title": s.get("title", s.get("id")), "state": s.get("state", "default"),
             "ac": s.get("ac") or [], "note": s.get("note", "")} for s in screens]
    title = f'{doc.get("feature", "")} · {doc.get("title", "Prototype")}'.strip(" ·")
    parts = [
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
        f"<title>{esc(title)}</title>",
        "<!-- generated by sdd-design from screens.json; do not edit by hand -->",
        f"<style>{r.tokens_css()}{COMPONENT_CSS}{CHROME_CSS}:root{{--vw:{vw}px}}</style></head><body>",
        f'<div class="bar"><h1>{esc(title)}</h1><span class="meta">{len(screens)} screens · {esc(platform)} {vw}×{vh} · {esc(ds_label)}</span>'
        '<span class="sp"></span><button id="hints" aria-pressed="false">Show links</button>'
        '<button id="mode" aria-pressed="false">Click through</button></div><main><div class="board">',
    ]
    for s, m in zip(screens, meta):
        body = r.node(s["body"]) if isinstance(s.get("body"), dict) else ""
        frame = f'<div class="frame screen-root" style="width:{vw}px;min-height:{vh}px">{body}</div>'
        st = esc(m["state"])
        parts.append(
            f'<div class="shot" role="link" tabindex="0" data-id="{esc(m["id"])}" aria-label="Open {esc(m["title"])}">'
            f'<p class="cap"><b>{esc(m["title"])}</b><span class="state state-{st}">{st}</span><span>{esc(", ".join(m["ac"]))}</span></p>'
            f'<div class="thumb" style="width:{vw * scale:.0f}px;height:{vh * scale:.0f}px">'
            f'<div class="frame screen-root" style="width:{vw}px;min-height:{vh}px;transform:scale({scale})" aria-hidden="true" inert>{body}</div></div></div>'
            f'<template id="tpl-{esc(m["id"])}">{frame}</template>')
    parts.append('</div><div class="focus" id="focus"></div></main>')
    parts.append(f'<script type="application/json" id="screens-data">{json.dumps(meta, ensure_ascii=False).replace("</", "<\\/")}</script>')
    parts.append(f"<script>{SCRIPT}</script></body></html>\n")
    return "".join(parts)


# --------------------------------------------------------------------- main


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["build", "check"])
    ap.add_argument("screens")
    ap.add_argument("--ds")
    ap.add_argument("--theme")
    ap.add_argument("--spec")
    ap.add_argument("--out")
    ap.add_argument("--neutral", action="store_true", help="no design system: grey placeholder theme for sketches")
    a = ap.parse_args(argv)

    src = Path(a.screens)
    doc = json.loads(src.read_text(encoding="utf-8"))
    ds_path = Path(a.ds) if a.ds else find_design_system(src.resolve().parent)
    ds, tokens, label = None, {}, "neutral sketch theme"
    if ds_path and ds_path.exists():
        ds, tokens = load_design_system(ds_path, a.theme)
        label = f'{ds.get("name", ds_path.stem)} {ds.get("version", "")}'.strip() + (f" · {a.theme}" if a.theme else "")
    elif not a.neutral:
        where = f" ({ds_path} does not exist)" if ds_path else ""
        print("NEEDS_DESIGN_SYSTEM: no design system configured" + where + ".\n"
              "Add 'Design system: <path/to/components.json>' to CLAUDE.md (see the sdd-design README),\n"
              "or pass --neutral for a throwaway grey sketch.")
        return 2
    spec_text = spec_sha1 = None
    spec = Path(a.spec) if a.spec else src.resolve().parent.parent / "spec.md"
    if a.spec or spec.exists():
        raw = spec.read_bytes()
        spec_text, spec_sha1 = raw.decode("utf-8"), hashlib.sha1(raw).hexdigest()
    errors, warnings = check(doc, ds, tokens, spec_text, spec_sha1)
    for e in errors:
        print(f"error: {e}")
    for w in warnings:
        print(f"warn:  {w}")
    if spec_sha1 and doc.get("spec_sha1") != spec_sha1:
        print(f'info:  {spec} has sha1 {spec_sha1}; record it as "spec_sha1" in screens.json')
    if a.command == "build" and not errors:
        out = Path(a.out) if a.out else src.parent
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(render_html(doc, tokens, label), encoding="utf-8")
        print(f"prototype: {out / 'index.html'}")
    print(f"{len(doc.get('screens') or [])} screen(s), {len(errors)} error(s), {len(warnings)} warning(s) · {label}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
