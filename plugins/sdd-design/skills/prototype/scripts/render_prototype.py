#!/usr/bin/env python3
"""render_prototype: turn specs/<ID>/design/screens.json into a clickable HTML
prototype styled by the project's design-system tokens, and check it.

screens.json is the single source for the prototype and the Figma layout
(see references/screens-schema.md). The HTML written here is generated; edit
screens.json or the design system, never the HTML.

Usage:
  render_prototype.py check <screens.json> [--ds components.json] [--spec spec.md] [--neutral]
  render_prototype.py build <screens.json> [--ds components.json] [--theme NAME] [--spec spec.md] [--out DIR] [--neutral]

The design system is found from --ds, else from the line
"Design system: <path/to/components.json>" in the nearest CLAUDE.md above the
screens file. Without one the command stops (exit 2) unless --neutral is given,
which uses a plain grey placeholder theme for throwaway sketches.

Standard library only. No network.
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

CORE_TYPES = {
    "Stack", "Grid", "Card", "Divider", "Spacer", "Text", "Button", "Link", "TextField", "Checkbox",
    "Toggle", "Select", "Alert", "Badge", "Image", "Avatar", "List", "NavBar", "TabBar", "Sidebar",
}
NEUTRAL_TOKENS = {
    "color.background": "#f7f7f8", "color.surface": "#ffffff", "color.surface-2": "#eeeef0",
    "color.text": "#18181d", "color.text-muted": "#5b5b66", "color.border": "#dcdce0",
    "color.primary": "#3f3f46", "color.on-primary": "#ffffff", "color.primary-subtle": "#eeeef0",
    "color.danger": "#c62828", "color.danger-subtle": "#fdecec", "color.success": "#1b7a3a",
    "color.success-subtle": "#e8f5ec", "color.warning": "#8a5a00", "color.warning-subtle": "#fdf4e3",
    "color.info": "#1d5fbf", "color.info-subtle": "#e9f1fc",
    "radius.sm": 4, "radius.md": 8, "radius.lg": 16, "radius.full": 999,
    "font.family.sans": "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    "font.size.caption": 12, "font.size.label": 14, "font.size.body": 16, "font.size.heading": 20,
    "font.size.title": 28, "font.size.display": 40,
    "font.weight.regular": 400, "font.weight.medium": 500, "font.weight.bold": 700,
}
NEUTRAL_TOKENS.update({f"space.{n}": 4 * n for n in range(0, 13)})
EXPECTED = [k for k in NEUTRAL_TOKENS if not k.startswith("space.") or k in ("space.1", "space.2", "space.4", "space.8")]
VIEWPORTS = {"web": (1280, 800), "mobile": (390, 844)}
AC_RE = re.compile(r"\bAC-\d+\b")


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
    for k, child in enumerate(node.get("children") or []):
        yield from walk(child, f"{path}/{child.get('type', '?')}[{k}]")


def variant_of(node):
    return node.get("variant") or node.get("tone")


def check(doc, ds, tokens, spec_text=None):
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
    for s in screens:
        sid = s.get("id", "?")
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", str(sid)):
            errors.append(f"screen id `{sid}` must be kebab-case")
        shown_ac.update(s.get("ac") or [])
        body = s.get("body")
        if not isinstance(body, dict) or "type" not in body:
            errors.append(f"{sid}: body must be one node with a type")
            continue
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
            link = node.get("link")
            if link and link not in known:
                errors.append(f"{sid} {path}: link to unknown screen `{link}`")
            for key in ("gap", "padding"):
                val = node.get(key)
                if ds and isinstance(val, str) and val not in tokens:
                    warnings.append(f"{sid} {path}: token `{val}` is not defined; neutral value used")
    for f in doc.get("flows") or []:
        for end in ("from", "to"):
            if f.get(end) not in known:
                errors.append(f"flow {f.get('from')} → {f.get('to')}: unknown screen `{f.get(end)}`")
    linked = {n.get("link") for s in screens if isinstance(s.get("body"), dict) for n, _ in walk(s["body"]) if n.get("link")}
    linked |= {f.get("to") for f in doc.get("flows") or []}
    for s in screens[1:]:
        if s.get("id") not in linked:
            warnings.append(f"screen `{s.get('id')}` cannot be reached by any link or flow")
    if spec_text:
        missing = sorted(set(AC_RE.findall(spec_text)) - shown_ac, key=lambda a: int(a.split("-")[1]))
        if missing:
            warnings.append(f"ACs not shown on any screen: {', '.join(missing)} (fine if they have no UI)")
    if ds:
        warnings += contrast_warnings(tokens)
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
        return f'<div class="st" style="{self.box_style(n, direction)}">{self.kids(n)}</div>'

    def r_Card(self, n):
        return f'<div class="cd st" style="{self.box_style(n, "column", "space.4", "space.6")}">{self.kids(n)}</div>'

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

    def r_Divider(self, n):
        return '<hr class="dv">'

    def r_Spacer(self, n):
        return '<div class="sp"></div>'


COMPONENT_CSS = """
*{box-sizing:border-box}
.screen-root{font-family:var(--font-family-sans);color:var(--color-text);background:var(--color-background);font-size:var(--font-size-body);line-height:1.45;min-height:100%}
.st{display:flex}
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
.btn[data-link],.lnk[data-link]{outline:2px dashed transparent;outline-offset:3px}
body.hints .btn[data-link],body.hints .lnk[data-link]{outline-color:var(--color-info)}
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
.bdg{display:inline-block;padding:2px 8px;border-radius:999px;font-size:var(--font-size-caption);background:var(--color-surface-2)}
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
    spec_text = None
    if a.spec:
        spec_text = Path(a.spec).read_text(encoding="utf-8")
    else:
        guess = src.resolve().parent.parent / "spec.md"
        if guess.exists():
            spec_text = guess.read_text(encoding="utf-8")
    errors, warnings = check(doc, ds, tokens, spec_text)
    for e in errors:
        print(f"error: {e}")
    for w in warnings:
        print(f"warn:  {w}")
    if a.command == "build" and not errors:
        out = Path(a.out) if a.out else src.parent
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(render_html(doc, tokens, label), encoding="utf-8")
        print(f"prototype: {out / 'index.html'}")
    print(f"{len(doc.get('screens') or [])} screen(s), {len(errors)} error(s), {len(warnings)} warning(s) · {label}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
