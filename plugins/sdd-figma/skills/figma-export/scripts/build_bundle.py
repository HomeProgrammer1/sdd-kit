#!/usr/bin/env python3
"""Pack one feature's diagrams, screens and design tokens into figma/bundle.json
for the "SDD Kit Import" Figma plugin (plugins/sdd-figma/figma-plugin).

Usage:
  python3 build_bundle.py specs/<ID>-<slug> [--ds path/to/components.json]
                          [--theme light] [--out file] [--keep-markers]

Reads   <feature>/diagrams/manifest.json (+ the SVGs it lists)
        <feature>/design/screens.json (optional)
        the design system: --ds, else the "Design system: <components.json>" line
        of the nearest CLAUDE.md above the feature folder
Writes  <feature>/figma/bundle.json (or --out)

Exit 0 = written, 1 = nothing to export (no diagrams and no screens), 2 = usage error.
Standard library only.
"""
import argparse
import datetime
import json
import math
import re
import sys
from pathlib import Path

NEUTRAL = {
    "color.background": "#f7f7f8", "color.surface": "#ffffff", "color.surface-2": "#eeeef0",
    "color.text": "#18181d", "color.text-muted": "#5b5b66", "color.border": "#dcdce0",
    "color.primary": "#4338ca", "color.on-primary": "#ffffff", "color.primary-subtle": "#eef2ff",
    "color.danger": "#c62828", "color.danger-subtle": "#fdecec",
    "color.success": "#1b7a3a", "color.success-subtle": "#e8f5ec",
    "color.warning": "#8a5a00", "color.warning-subtle": "#fdf4e3",
    "color.info": "#1d5fbf", "color.info-subtle": "#e9f1fc",
    **{f"space.{n}": 4 * n for n in (1, 2, 3, 4, 5, 6, 8, 10, 12)},
    "radius.sm": 4, "radius.md": 8, "radius.lg": 16, "radius.full": 999,
    "font.family.sans": "Inter, system-ui, sans-serif",
    "font.size.caption": 12, "font.size.label": 14, "font.size.body": 16,
    "font.size.heading": 20, "font.size.title": 28, "font.size.display": 40,
    "font.weight.regular": 400, "font.weight.medium": 500, "font.weight.bold": 700,
}
EXPECTED = [k for k in NEUTRAL if not k.endswith("-subtle") and k not in ("radius.full", "font.size.label")]

# Built-in node types (screens-schema.md) and the prop that carries their variant.
BUILTIN = {"Stack", "Grid", "Card", "Text", "Button", "Link", "TextField", "Checkbox", "Toggle", "Select",
           "Alert", "Badge", "Image", "Avatar", "List", "NavBar", "TabBar", "Sidebar", "Divider", "Spacer"}
BUILTIN_VARIANTS = {
    "Text": ["display", "title", "heading", "body", "caption", "label"],
    "Button": ["primary", "secondary", "ghost", "danger"],
    "Alert": ["info", "success", "warning", "danger"],
}
VARIANT_PROP = {"Alert": "tone", "Badge": "tone"}
INPUT_TYPES = {"text", "email", "password"}


def load_json(path, warnings, what):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        warnings.append(f"{what}: cannot read {path} ({e})")
        return None


# ---------------------------------------------------------------- diagrams

ATTR_RE = re.compile(r'([\w:.-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')
NUM_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}


def attrs(s):
    return {m.group(1): m.group(2) if m.group(2) is not None else m.group(3) for m in ATTR_RE.finditer(s)}


def path_points(d):
    """Absolute points of a path in drawing order (control points included), enough for end tangents."""
    toks, i, cmd, cur, start, out = NUM_TOKEN.findall(d), 0, None, (0.0, 0.0), (0.0, 0.0), []
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd, i = t, i + 1
            if cmd in "Zz":
                cur = start
                out.append(cur)
            continue
        if cmd is None or cmd in "Zz":
            raise ValueError("bad path data")
        up, rel, n = cmd.upper(), cmd.islower(), ARGS[cmd.upper()]
        a = [float(x) for x in toks[i:i + n]]
        if len(a) < n:
            break
        i += n

        def p(x, y):
            return (cur[0] + x, cur[1] + y) if rel else (x, y)
        if up == "M":
            cur = start = p(a[0], a[1])
            out.append(cur)
            cmd = "l" if rel else "L"
        elif up in ("L", "T"):
            cur = p(a[0], a[1]); out.append(cur)
        elif up == "H":
            cur = (cur[0] + a[0] if rel else a[0], cur[1]); out.append(cur)
        elif up == "V":
            cur = (cur[0], cur[1] + a[0] if rel else a[0]); out.append(cur)
        elif up == "C":
            pts = [p(a[0], a[1]), p(a[2], a[3]), p(a[4], a[5])]; out += pts; cur = pts[-1]
        elif up in ("S", "Q"):
            pts = [p(a[0], a[1]), p(a[2], a[3])]; out += pts; cur = pts[-1]
        elif up == "A":
            cur = p(a[5], a[6]); out.append(cur)
    return out


def element_points(tag, a):
    if tag == "path":
        return path_points(a.get("d", ""))
    if tag == "line":
        return [(float(a.get("x1", 0)), float(a.get("y1", 0))), (float(a.get("x2", 0)), float(a.get("y2", 0)))]
    nums = [float(x) for x in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", a.get("points", ""))]
    return list(zip(nums[0::2], nums[1::2]))


def vertex(pts, at_end):
    seq = list(reversed(pts)) if at_end else pts
    v = seq[0]
    for q in seq[1:]:
        if abs(q[0] - v[0]) + abs(q[1] - v[1]) > 1e-6:
            ang = math.degrees(math.atan2(v[1] - q[1], v[0] - q[0]) if at_end else math.atan2(q[1] - v[1], q[0] - v[0]))
            return v, ang
    return v, 0.0


def inline_markers(svg):
    """Replace marker-start/marker-end references by explicit, transformed copies of the
    marker content. Figma's SVG import does not draw <marker>, so arrowheads would vanish."""
    markers = {}
    for m in re.finditer(r"<marker\b([^>]*)>(.*?)</marker>", svg, re.S):
        a = attrs(m.group(1))
        if a.get("id"):
            markers[a["id"]] = (a, m.group(2))
    if not markers:
        return svg, 0
    count = 0

    def repl(m):
        nonlocal count
        tag, attr_text, tail = m.group(1), m.group(2), m.group(3)
        a = attrs(attr_text)
        refs = [(k, re.match(r"url\(#([^)]+)\)", a.get(k, "").strip())) for k in ("marker-start", "marker-end")]
        refs = [(k, r.group(1)) for k, r in refs if r and r.group(1) in markers]
        if not refs:
            return m.group(0)
        pts = element_points(tag, a)
        if len(pts) < 2:
            return m.group(0)
        sw = float(re.sub(r"[^\d.]", "", a.get("stroke-width", "1")) or 1)
        extra = []
        for key, mid in refs:
            ma, content = markers[mid]
            vb = [float(x) for x in re.split(r"[\s,]+", ma.get("viewBox", "").strip()) if x] or None
            mw, mh = float(ma.get("markerWidth", 3)), float(ma.get("markerHeight", 3))
            k = sw if ma.get("markerUnits", "strokeWidth") == "strokeWidth" else 1.0
            s = min(mw * k / vb[2], mh * k / vb[3]) if vb and vb[2] and vb[3] else k
            v, ang = vertex(pts, key == "marker-end")
            orient = ma.get("orient", "0")
            if orient == "auto-start-reverse" and key == "marker-start":
                ang += 180.0
            elif orient not in ("auto", "auto-start-reverse"):
                ang = float(re.sub(r"[^\d.+-]", "", orient) or 0)
            body = content.replace("context-stroke", a.get("stroke", "#000")).replace("context-fill", a.get("fill", "#000"))
            extra.append(f'<g transform="translate({v[0]:.2f},{v[1]:.2f}) rotate({ang:.2f}) scale({s:.4f}) '
                         f'translate({-float(ma.get("refX", 0)):g},{-float(ma.get("refY", 0)):g})">{body}</g>')
            count += 1
        cleaned = re.sub(r'\s+marker-(?:start|end)\s*=\s*("[^"]*"|\'[^\']*\')', "", attr_text)
        return f"<{tag}{cleaned}{tail}" + "".join(extra)

    out = re.sub(r"<(path|line|polyline)\b([^>]*?)(/>|>.*?</\1>)", repl, svg, flags=re.S)
    return out, count


def clean_svg(text):
    text = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", text)
    text = re.sub(r"<!DOCTYPE[^>]*>\s*", "", text, flags=re.I)
    return text.strip()


def read_diagrams(feature_dir, warnings, keep_markers):
    mpath = feature_dir / "diagrams" / "manifest.json"
    manifest = load_json(mpath, warnings, "diagrams")
    if manifest is None:
        warnings.append("no diagrams/manifest.json: run /sdd-diagrams:feature-diagrams first")
        return None, []
    out = []
    for d in manifest.get("diagrams") or []:
        raw = d.get("svg") or f"{d.get('name', '')}.svg"
        cands = [Path(raw)] if Path(raw).is_absolute() else []
        cands += [mpath.parent / raw, mpath.parent / Path(raw).name]
        if d.get("name"):
            cands.append(mpath.parent / f"{d['name']}.svg")
        src = next((c for c in cands if c.is_file()), None)
        if src is None:
            warnings.append(f"diagram '{d.get('title') or d.get('name')}': SVG {raw} not found "
                            "(run /sdd-diagrams:feature-diagrams first)")
            continue
        svg = clean_svg(src.read_text(encoding="utf-8"))
        if not keep_markers:
            try:
                svg, _ = inline_markers(svg)
            except (ValueError, IndexError, KeyError) as e:
                warnings.append(f"diagram '{d.get('title')}': arrowheads left as <marker> ({e})")
        out.append({"title": d.get("title") or d.get("name") or src.stem, "kind": d.get("kind") or "diagram",
                    "name": d.get("name") or src.stem, "sha1": d.get("sha1") or "", "svg": svg})
    for s in manifest.get("skipped") or []:
        warnings.append(f"diagram skipped by sdd-diagrams: {s if isinstance(s, str) else json.dumps(s)}")
    return manifest, out


# ---------------------------------------------------------------- design system

def find_ds_in_claude_md(start):
    for folder in [start, *start.parents]:
        md = folder / "CLAUDE.md"
        if not md.is_file():
            continue
        for line in md.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.search(r"Design system:\s*(.*)", line)
            if not m:
                continue
            for tok in m.group(1).split():
                tok = tok.strip("`'\"<>()[],;")
                if tok.endswith(".json"):
                    p = Path(tok).expanduser()
                    return (p if p.is_absolute() else folder / p).resolve(), md
    return None, None


def deep_merge(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and "$value" not in v and isinstance(base.get(k), dict) and "$value" not in base[k]:
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def flatten(tree, prefix="", out=None):
    out = {} if out is None else out
    for k, v in tree.items():
        if k.startswith("$") or not isinstance(v, dict):
            continue
        path = f"{prefix}{k}"
        if "$value" in v:
            out[path] = {"value": v["$value"], "type": v.get("$type")}
        else:
            flatten(v, path + ".", out)
    return out


ALIAS = re.compile(r"\{([^{}]+)\}")


def resolve_all(raw, warnings):
    cache = {}

    def res(path, depth, seen):
        if path in cache:
            return cache[path]
        if path not in raw:
            raise KeyError(path)
        if depth > 10 or path in seen:
            raise RecursionError(path)
        val = sub(raw[path]["value"], depth + 1, seen | {path})
        cache[path] = val
        return val

    def sub(v, depth, seen):
        if isinstance(v, str):
            whole = ALIAS.fullmatch(v.strip())
            if whole:
                return res(whole.group(1), depth, seen)
            return ALIAS.sub(lambda m: str(res(m.group(1), depth, seen)), v)
        if isinstance(v, list):
            return [sub(x, depth, seen) for x in v]
        if isinstance(v, dict):
            return {k: sub(x, depth, seen) for k, x in v.items()}
        return v

    flat = {}
    for path, tok in raw.items():
        try:
            flat[path] = normalize(res(path, 0, frozenset()), tok.get("type"))
        except KeyError as e:
            warnings.append(f"token {path}: alias to unknown token {e.args[0]}")
        except RecursionError as e:
            warnings.append(f"token {path}: alias cycle or chain deeper than 10 at {e.args[0]}")
    return flat


def normalize(v, typ):
    if isinstance(v, list) and all(isinstance(x, (str, int, float)) for x in v):
        return ", ".join(str(x) for x in v)
    if isinstance(v, dict):
        if "hex" in v:
            return v["hex"]
        if "value" in v and "unit" in v and isinstance(v["value"], (int, float)):
            return num(v["value"] * (16 if v["unit"] == "rem" else 1))
    if isinstance(v, str) and typ not in ("fontFamily", "color"):
        m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*(px|rem)?\s*", v)
        if m:
            return num(float(m.group(1)) * (16 if m.group(2) == "rem" else 1))
    if isinstance(v, float):
        return num(v)
    return v


def num(x):
    return int(x) if float(x).is_integer() else round(float(x), 4)


def load_design_system(ds_path, theme, warnings):
    ds = load_json(ds_path, warnings, "design system")
    if not isinstance(ds, dict):
        warnings.append(f"design system {ds_path} is not readable JSON; using neutral fallback tokens")
        return None, dict(NEUTRAL), None
    files, used_theme = ds.get("tokens") or [], None
    if theme:
        if theme in (ds.get("themes") or {}):
            files, used_theme = ds["themes"][theme], theme
        else:
            warnings.append(f"theme '{theme}' not in {ds_path.name}; using its default 'tokens' list")
    tree = {}
    for rel in files:
        t = load_json(ds_path.parent / rel, warnings, "tokens")
        if t is None:
            warnings.append(f"token file {rel} (from {ds_path.name}) not found")
        elif isinstance(t, dict):
            deep_merge(tree, t)
    tokens = resolve_all(flatten(tree), warnings)
    missing = [k for k in EXPECTED if k not in tokens]
    if missing:
        warnings.append(f"design system lacks {len(missing)} semantic token(s) ({', '.join(missing[:8])}"
                        f"{', …' if len(missing) > 8 else ''}); the plugin uses neutral defaults for them")
    meta = {"name": ds.get("name") or ds_path.parent.name, "version": ds.get("version"), "theme": used_theme}
    comps = ds.get("components") if isinstance(ds.get("components"), dict) else None
    return meta, tokens, comps


# ---------------------------------------------------------------- screens

def validate_screens(screens, comps, warnings):
    known = set(comps) if comps else BUILTIN
    where = "design system" if comps else "built-in node types"
    items = screens.get("screens") if isinstance(screens, dict) else None
    if not isinstance(items, list):
        warnings.append("screens.json has no 'screens' list")
        return
    ids = [s.get("id") for s in items if isinstance(s, dict)]
    for dup in sorted({i for i in ids if ids.count(i) > 1 and i}):
        warnings.append(f"screens.json: duplicate screen id '{dup}'")
    idset = set(ids)

    def walk(node, sid):
        if not isinstance(node, dict):
            warnings.append(f"screen {sid}: node is not an object")
            return
        t = node.get("type")
        if t not in known:
            warnings.append(f"screen {sid}: unknown component type '{t}' (not in the {where})")
        else:
            spec = (comps or {}).get(t) or {}
            variants = spec.get("variants") if comps else BUILTIN_VARIANTS.get(t)
            value = node.get(VARIANT_PROP.get(t, "variant"))
            if variants and value is not None and value not in variants:
                warnings.append(f"screen {sid}: {t} variant '{value}' not in {variants}")
        if t == "TextField" and node.get("inputType", "text") not in INPUT_TYPES:
            warnings.append(f"screen {sid}: TextField inputType '{node.get('inputType')}' is not text|email|password")
        if node.get("link") and node["link"] not in idset:
            warnings.append(f"screen {sid}: {t} links to unknown screen '{node['link']}'")
        for c in node.get("children") or []:
            walk(c, sid)

    for s in items:
        if isinstance(s, dict):
            walk(s.get("body"), s.get("id"))
    for f in screens.get("flows") or []:
        for end in ("from", "to"):
            if isinstance(f, dict) and f.get(end) not in idset:
                warnings.append(f"flow {f.get('from')} → {f.get('to')}: unknown screen '{f.get(end)}'")


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description="Build figma/bundle.json for the SDD Kit Import Figma plugin.")
    ap.add_argument("feature", help="feature folder, e.g. specs/F-001-password-reset")
    ap.add_argument("--ds", help="design system components.json (default: 'Design system:' line in CLAUDE.md)")
    ap.add_argument("--theme", help="theme name from components.json 'themes' (default: its 'tokens' list)")
    ap.add_argument("--out", help="output file (default: <feature>/figma/bundle.json)")
    ap.add_argument("--keep-markers", action="store_true", help="leave SVG <marker> arrowheads as they are")
    args = ap.parse_args(argv)

    feature_dir = Path(args.feature).expanduser().resolve()
    if not feature_dir.is_dir():
        print(f"[ERROR] feature folder not found: {feature_dir}", file=sys.stderr)
        return 2
    warnings = []

    manifest, diagrams = read_diagrams(feature_dir, warnings, args.keep_markers)
    screens = None
    spath = feature_dir / "design" / "screens.json"
    if spath.is_file():
        screens = load_json(spath, warnings, "screens")
        if screens is not None and not isinstance(screens, dict):
            warnings.append("design/screens.json is not an object; screens skipped")
            screens = None

    if args.ds:
        ds_path = Path(args.ds).expanduser().resolve()
        if not ds_path.is_file():
            print(f"[ERROR] --ds file not found: {ds_path}", file=sys.stderr)
            return 2
    else:
        ds_path, md = find_ds_in_claude_md(feature_dir)
        if ds_path is not None and not ds_path.is_file():
            warnings.append(f"{md}: design system {ds_path} not found")
            ds_path = None
    if ds_path is not None:
        ds_meta, tokens, comps = load_design_system(ds_path, args.theme, warnings)
    else:
        ds_meta, tokens, comps = None, dict(NEUTRAL), None
        if screens is not None:
            warnings.append("no design system (pass --ds or add 'Design system: <components.json>' to CLAUDE.md); "
                            "screens use neutral fallback tokens")
    if screens is not None:
        validate_screens(screens, comps, warnings)

    n_screens = len(screens.get("screens") or []) if screens else 0
    if not diagrams and not n_screens:
        for w in warnings:
            print(f"[WARN] {w}")
        print(f"[ERROR] nothing to export from {feature_dir}: no diagrams and no screens")
        return 1

    feature = (screens or {}).get("feature") or (manifest or {}).get("feature") or feature_dir.name
    title = (screens or {}).get("title")
    if not title and (feature_dir / "spec.md").is_file():
        m = re.search(r"^#\s+(.+)$", (feature_dir / "spec.md").read_text(encoding="utf-8"), re.M)
        title = m.group(1).strip() if m else None
    bundle = {
        "version": 1,
        "feature": feature,
        "title": title or feature,
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "designSystem": ds_meta,
        "tokens": tokens,
        "diagrams": diagrams,
        "screens": screens,
        "components": comps,
        "warnings": warnings,
    }
    out = Path(args.out).expanduser().resolve() if args.out else feature_dir / "figma" / "bundle.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for w in warnings:
        print(f"[WARN] {w}")
    ds_txt = f"{ds_meta['name']} {ds_meta.get('version') or ''}".strip() if ds_meta else "neutral fallback"
    print(f"[OK] {feature}: {len(diagrams)} diagram(s), {n_screens} screen(s), {len(tokens)} token(s) "
          f"({ds_txt}), {len(warnings)} warning(s) → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
