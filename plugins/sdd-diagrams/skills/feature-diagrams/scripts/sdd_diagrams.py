#!/usr/bin/env python3
"""sdd-diagrams: turn the Mermaid blocks in a spec or plan into editorial SVG,
a multi-page .drawio file and a review gallery, and check them.

Mermaid in the spec stays the single source of truth; everything written here
is generated, stamped with the source hash, and never edited by hand.

Supported (portable subset, see references/style.md):
  flowchart / graph  TD|TB|LR|RL|BT
  stateDiagram-v2
  sequenceDiagram
Other Mermaid types are listed as "skipped" so a human can render them elsewhere.

Usage:
  sdd_diagrams.py build <file.md|file.mmd>... [--out DIR] [--drawio] [--theme FILE] [--tokens FILE] [--id ID]
  sdd_diagrams.py check <file.md|file.mmd>... [--out DIR] [--strict]

check writes nothing; it reports parse errors, budget and layout problems, and
SVGs that are missing or older than their Mermaid source. Exit 1 on errors
(and on warnings with --strict).

Standard library only. No network.
"""
import argparse
import hashlib
import html
import json
import math
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------- theme

DEFAULT_THEME = {
    "paper": "#fafaf9",
    "paper2": "#f1f0ee",
    "ink": "#1f2430",
    "muted": "#4a5468",
    "soft": "#5f6b80",
    "rule": "#d6d3ce",
    "accent": "#b4400f",
    "accentTint": "#f6e7df",
    "link": "#1f4fb8",
    "font": "Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    "mono": "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
}

TOKEN_CANDIDATES = {
    "paper": ["diagram.paper", "color.background", "color.bg", "color.surface", "color.neutral.0", "color.white"],
    "paper2": ["diagram.paper2", "color.surface-2", "color.surface.subtle", "color.background-subtle", "color.neutral.50"],
    "ink": ["diagram.ink", "color.text", "color.text.primary", "color.foreground", "color.neutral.900"],
    "muted": ["diagram.muted", "color.text-muted", "color.text.secondary", "color.neutral.600"],
    "soft": ["diagram.soft", "color.text-subtle", "color.text.tertiary", "color.neutral.500"],
    "rule": ["diagram.rule", "color.border", "color.border.default", "color.neutral.200"],
    "accent": ["diagram.accent", "color.accent", "color.primary", "color.brand", "color.primary.600"],
    "accentTint": ["diagram.accentTint", "color.accent-subtle", "color.primary.50", "color.brand-subtle"],
    "link": ["diagram.link", "color.link", "color.info", "color.blue.600"],
    "font": ["diagram.font", "font.family.sans", "typography.fontFamily.sans", "font.sans"],
    "mono": ["diagram.mono", "font.family.mono", "typography.fontFamily.mono", "font.mono"],
}


def flatten_tokens(obj, prefix=""):
    """DTCG-style tokens ({"$value": ...}) or plain nested maps -> {dotted.path: value}."""
    out = {}
    if isinstance(obj, dict):
        if "$value" in obj or "value" in obj:
            out[prefix] = obj.get("$value", obj.get("value"))
            return out
        for k, v in obj.items():
            if k.startswith("$"):
                continue
            out.update(flatten_tokens(v, f"{prefix}.{k}" if prefix else k))
    else:
        out[prefix] = obj
    return out


def resolve_token(flat, value, depth=0):
    if isinstance(value, str):
        m = re.fullmatch(r"\{([^}]+)\}", value.strip())
        if m and depth < 10:
            return resolve_token(flat, flat.get(m.group(1)), depth + 1)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return value


def load_theme(theme_path=None, tokens_path=None):
    theme = dict(DEFAULT_THEME)
    if tokens_path:
        flat = flatten_tokens(json.loads(Path(tokens_path).read_text(encoding="utf-8")))
        for role, keys in TOKEN_CANDIDATES.items():
            for key in keys:
                val = resolve_token(flat, flat.get(key))
                if isinstance(val, str) and val:
                    theme[role] = val
                    break
    if theme_path:
        theme.update(json.loads(Path(theme_path).read_text(encoding="utf-8")))
    return theme


def _luminance(hex_colour):
    h = hex_colour.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h[:6]):
        return None
    chans = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        chans.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * chans[0] + 0.7152 * chans[1] + 0.0722 * chans[2]


def contrast_issues(theme):
    """Text roles must reach WCAG AA (4.5:1) on both paper colours."""
    issues = []
    for fg in ("ink", "muted", "soft"):
        for bg in ("paper", "paper2"):
            a, b = _luminance(theme[fg]), _luminance(theme[bg])
            if a is None or b is None:
                issues.append(f"theme: cannot read colours {fg}={theme[fg]} / {bg}={theme[bg]} (use hex)")
                continue
            ratio = (max(a, b) + 0.05) / (min(a, b) + 0.05)
            if ratio < 4.5:
                issues.append(f"theme: {fg} on {bg} is {ratio:.2f}:1, below WCAG AA 4.5:1")
    return issues


# --------------------------------------------------------------------- text metrics

NARROW = set("iljtfr.,:;|!'`()[] ")
WIDE = set("mwMWЖШЩЮФМ@%")


def text_width(text, size):
    w = 0.0
    for ch in text:
        if ch in NARROW:
            w += 0.32
        elif ch in WIDE:
            w += 0.86
        elif ch.isupper() or "Ѐ" <= ch <= "ӿ":
            w += 0.64
        else:
            w += 0.56
    return w * size


def wrap(text, size, max_w):
    words, lines, cur = text.split(), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if cur and text_width(trial, size) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [""]


def up4(v):
    return int(math.ceil(v / 4.0) * 4)


def esc(s):
    return html.escape(str(s), quote=True)


AC_RE = re.compile(r"\b(?:AC|FR|NFR)-\d+\b")

# --------------------------------------------------------------------- extraction


def extract_blocks(path):
    """Return [(title, source)] for every ```mermaid block; title = nearest preceding heading."""
    text = Path(path).read_text(encoding="utf-8")
    if Path(path).suffix == ".mmd":
        return [(Path(path).stem, text)]
    blocks, title, in_block, buf = [], None, False, []
    for line in text.splitlines():
        if not in_block:
            h = re.match(r"^#{2,6}\s+(.*)$", line)
            if h:
                title = h.group(1).strip()
            if re.match(r"^\s*```\s*mermaid\s*$", line):
                in_block, buf = True, []
        else:
            if re.match(r"^\s*```\s*$", line):
                blocks.append((title or f"Diagram {len(blocks) + 1}", "\n".join(buf)))
                in_block = False
            else:
                buf.append(line)
    return blocks


def diagram_kind(src):
    for line in src.splitlines():
        s = line.strip()
        if not s or s.startswith("%%"):
            continue
        head = s.split()[0]
        if head in ("flowchart", "graph"):
            return "flowchart"
        if head.startswith("stateDiagram"):
            return "state"
        if head == "sequenceDiagram":
            return "sequence"
        return head
    return "empty"


# --------------------------------------------------------------------- graph model


class Node:
    def __init__(self, nid, label=None, kind="step"):
        self.id, self.kind, self.cls = nid, kind, set()
        self.set_label(label if label is not None else nid)
        self.x = self.y = self.w = self.h = 0
        self.dummy = False

    def set_label(self, label):
        label = label.strip().strip('"').replace("<br>", " ").replace("<br/>", " ")
        self.tags = AC_RE.findall(label)
        name = AC_RE.sub("", label)
        name = re.sub(r"\s{2,}", " ", name).strip(" ,;·")
        self.label = name or label


class Edge:
    def __init__(self, src, dst, label="", dashed=False, thick=False, cross=False):
        self.src, self.dst, self.label = src, dst, label.strip().strip('"')
        self.dashed, self.thick, self.cross = dashed, thick, cross
        self.points, self.back = [], False


class Graph:
    def __init__(self, kind, direction="TD"):
        self.kind, self.direction = kind, direction
        self.nodes, self.order, self.edges = {}, [], []
        self.errors, self.warnings = [], []

    def node(self, nid, label=None, kind=None):
        n = self.nodes.get(nid)
        if n is None:
            n = Node(nid, label, kind or "step")
            self.nodes[nid] = n
            self.order.append(nid)
        else:
            if label is not None:
                n.set_label(label)
            if kind:
                n.kind = kind
        return n


SHAPES = [
    (r"\(\[(.*?)\]\)", "terminal"),
    (r"\[\((.*?)\)\]", "store"),
    (r"\(\((.*?)\)\)", "external"),
    (r"\[\[(.*?)\]\]", "step"),
    (r"\{\{(.*?)\}\}", "step"),
    (r"\[/(.*?)/\]", "step"),
    (r"\[(.*?)\]", "step"),
    (r"\((.*?)\)", "step"),
    (r"\{(.*?)\}", "decision"),
    (r">(.*?)\]", "step"),
]
NODE_RE = re.compile(r"\s*([A-Za-z0-9_]+)(" + "|".join(s for s, _ in SHAPES) + r")?(?::::([\w-]+))?\s*")
EDGE_RES = [
    (re.compile(r"\s*--\s+([^>|]+?)\s+-->\s*"), {}),
    (re.compile(r"\s*-\.\s+(.+?)\s+\.->\s*"), {"dashed": True}),
    (re.compile(r"\s*==\s+(.+?)\s+==>\s*"), {"thick": True}),
    (re.compile(r"\s*(-->|---|-\.->|-\.-|==>|===|--x|--o)\s*(?:\|([^|]*)\|)?\s*"), None),
]
IGNORED = ("%%", "classDef", "style ", "linkStyle", "click ", "subgraph", "end", "direction", "accTitle", "accDescr")


def parse_node_expr(g, text, pos):
    m = NODE_RE.match(text, pos)
    if not m or not m.group(1):
        return None, pos
    nid = m.group(1)
    label, kind = None, None
    shape_txt = m.group(2)
    if shape_txt:
        for pat, k in SHAPES:
            sm = re.fullmatch(pat, shape_txt)
            if sm:
                label, kind = sm.group(1), k
                break
    n = g.node(nid, label, kind)
    if m.group(m.lastindex) and m.lastindex >= 3 and text[m.start():m.end()].find(":::") >= 0:
        n.cls.add(m.group(m.lastindex))
    return n, m.end()


def parse_flowchart(src):
    lines = src.splitlines()
    g = Graph("flowchart")
    for i, raw in enumerate(lines, 1):
        for stmt in raw.split(";"):
            s = stmt.strip()
            if not s:
                continue
            head = s.split()[0]
            if head in ("flowchart", "graph"):
                parts = s.split()
                g.direction = parts[1].upper() if len(parts) > 1 else "TD"
                continue
            if s.startswith(IGNORED) and not re.match(r"^end\w", s):
                continue
            cm = re.match(r"^class\s+([\w,\s]+?)\s+([\w-]+)$", s)
            if cm:
                for nid in re.split(r"[,\s]+", cm.group(1)):
                    if nid:
                        g.node(nid).cls.add(cm.group(2))
                continue
            pos, prev_group, ok = 0, None, True
            n_order, n_edges = len(g.order), len(g.edges)
            while pos < len(s):
                group = []
                while True:
                    n, pos2 = parse_node_expr(g, s, pos)
                    if n is None:
                        ok = False
                        break
                    group.append(n)
                    pos = pos2
                    if s.startswith("&", pos):
                        pos += 1
                        continue
                    break
                if not ok:
                    break
                if prev_group is not None:
                    for a in prev_group[0]:
                        for b in group:
                            g.edges.append(Edge(a.id, b.id, prev_group[1].get("label", ""),
                                                prev_group[1].get("dashed", False), prev_group[1].get("thick", False),
                                                prev_group[1].get("cross", False)))
                if pos >= len(s):
                    break
                matched = None
                for rx, fixed in EDGE_RES:
                    em = rx.match(s, pos)
                    if em:
                        if fixed is None:
                            op = em.group(1)
                            matched = {"label": em.group(2) or "", "dashed": op.startswith("-."),
                                       "thick": op.startswith("=="), "cross": op.endswith("x")}
                        else:
                            matched = dict(fixed, label=em.group(1))
                        pos = em.end()
                        break
                if matched is None:
                    ok = False
                    break
                prev_group = (group, matched)
            if not ok:
                for nid in g.order[n_order:]:
                    del g.nodes[nid]
                del g.order[n_order:]
                del g.edges[n_edges:]
                g.errors.append(f"line {i}: cannot parse `{s}` (outside the portable subset)")
    return g


def parse_state(src):
    g = Graph("state")
    for i, raw in enumerate(src.splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("%%") or s.startswith("stateDiagram") or s in ("}",) or s.startswith(("direction", "note", "end note", "classDef", "class ")):
            continue
        m = re.match(r'^state\s+"([^"]+)"\s+as\s+(\w+)$', s)
        if m:
            g.node(m.group(2), m.group(1), "state")
            continue
        if re.match(r"^state\s+\w+\s*\{$", s):
            continue
        m = re.match(r"^(\[\*\]|\w+)\s*-->\s*(\[\*\]|\w+)\s*(?::\s*(.*))?$", s)
        if m:
            a, b, label = m.group(1), m.group(2), m.group(3) or ""
            a = "__start" if a == "[*]" else a
            b = "__end" if b == "[*]" else b
            for nid in (a, b):
                if nid == "__start":
                    g.node(nid, "", "start")
                elif nid == "__end":
                    g.node(nid, "", "end")
                elif nid not in g.nodes:
                    g.node(nid, nid, "state")
            g.edges.append(Edge(a, b, label))
            continue
        m = re.match(r"^(\w+)\s*:\s*(.+)$", s)
        if m:
            g.node(m.group(1), m.group(2), "state")
            continue
        g.errors.append(f"line {i}: cannot parse `{s}`")
    g.direction = "TD"
    return g


# --------------------------------------------------------------------- flow/state layout

NAME_SIZE, TAG_SIZE, EDGE_SIZE = 14, 10.5, 12
PAD_X, PAD_Y, LINE_H = 16, 12, 18
ORDER_GAP, MARGIN, HEADER_H = 48, 32, 56


def size_node(n):
    if n.kind in ("start", "end"):
        n.w = n.h = 20
        n.lines = []
        return
    max_text = 176 if n.kind != "decision" else 160
    n.lines = wrap(n.label, NAME_SIZE, max_text)
    tw = max(text_width(l, NAME_SIZE) for l in n.lines)
    tag_line = " · ".join(n.tags)
    tagw = text_width(tag_line, TAG_SIZE) if n.tags else 0
    extra = 18 if n.kind == "decision" else 0
    n.w = up4(max(104, max(tw, tagw) + 2 * PAD_X + extra))
    n.h = up4(max(44, len(n.lines) * LINE_H + (16 if n.tags else 0) + 2 * PAD_Y))


def layout_graph(g):
    for n in g.nodes.values():
        size_node(n)
    horizontal = g.direction in ("LR", "RL")
    so = (lambda n: n.h) if horizontal else (lambda n: n.w)   # size along the order axis
    sr = (lambda n: n.w) if horizontal else (lambda n: n.h)   # size along the rank axis

    ids = list(g.order)
    succ = {i: [] for i in ids}
    for e in g.edges:
        if e.src != e.dst:
            succ[e.src].append(e)
    # 1. break cycles with a DFS in definition order
    state, back = {}, set()

    def dfs(u):
        state[u] = 1
        for e in succ[u]:
            if state.get(e.dst) == 1:
                back.add(id(e))
            elif e.dst not in state:
                dfs(e.dst)
        state[u] = 2

    sys.setrecursionlimit(10000)
    for i in ids:
        if i not in state:
            dfs(i)
    for e in g.edges:
        e.back = id(e) in back
    dag = [(e.dst, e.src, e) if e.back else (e.src, e.dst, e) for e in g.edges if e.src != e.dst]

    # 2. longest-path ranks
    rank = {i: 0 for i in ids}
    for _ in range(len(ids) + 1):
        changed = False
        for a, b, _e in dag:
            if rank[b] < rank[a] + 1:
                rank[b] = rank[a] + 1
                changed = True
        if not changed:
            break

    # 3. dummy nodes for long forward edges; back edges get a side lane instead
    chains = {}
    nodes = dict(g.nodes)
    for a, b, e in dag:
        if e.back:
            continue
        chain = [a]
        for r in range(rank[a] + 1, rank[b]):
            d = Node(f"__d{len(nodes)}", "")
            d.dummy, d.w, d.h, d.lines = True, 16, 16, []
            nodes[d.id] = d
            rank[d.id] = r
            chain.append(d.id)
        chain.append(b)
        chains[id(e)] = chain
    layers = {}
    for nid in list(g.order) + [k for k in nodes if nodes[k].dummy]:
        layers.setdefault(rank[nid], []).append(nid)
    max_r = max(layers) if layers else 0
    up, down = {k: [] for k in nodes}, {k: [] for k in nodes}
    for chain in chains.values():
        for u, v in zip(chain, chain[1:]):
            down[u].append(v)
            up[v].append(u)

    # 4. ordering: barycentre sweeps, keeping the ordering with the fewest crossings;
    #    nodes on a back edge drift to the outer side, so the return lane needs no crossing
    bias = {}
    for e in g.edges:
        if e.back:
            bias[e.src] = bias.get(e.src, 0) + 0.6
            bias[e.dst] = bias.get(e.dst, 0) + 0.6
    pos = {}
    for r in range(max_r + 1):
        for k, nid in enumerate(layers.get(r, [])):
            pos[nid] = k

    def crossings():
        total = 0
        for nid in bias:   # back-edge ends away from the outer side cost a little
            total += 0.01 * (len(layers[rank[nid]]) - 1 - pos[nid])
        for r in range(max_r):
            pairs = [(pos[u], pos[v]) for u in layers.get(r, []) for v in down[u]]
            for i in range(len(pairs)):
                for j in range(i + 1, len(pairs)):
                    if (pairs[i][0] - pairs[j][0]) * (pairs[i][1] - pairs[j][1]) < 0:
                        total += 1
        return total

    best = (crossings(), {r: list(l) for r, l in layers.items()})
    for it in range(8):
        downward = it % 2 == 0
        links = up if downward else down
        for r in (range(1, max_r + 1) if downward else range(max_r - 1, -1, -1)):
            layer = layers.get(r, [])

            def bary(nid, links=links):
                ps = [pos[p] for p in links[nid]]
                return (sum(ps) / len(ps) if ps else pos[nid]) + bias.get(nid, 0)
            layer.sort(key=bary)
            for k, nid in enumerate(layer):
                pos[nid] = k
        c = crossings()
        if c < best[0]:
            best = (c, {r: list(l) for r, l in layers.items()})
    layers = best[1]
    for r, layer in layers.items():
        for k, nid in enumerate(layer):
            pos[nid] = k

    # 5. order-axis coordinates: each layer is pulled towards the median of its
    #    neighbours, with spacing kept by weighted isotonic regression (pool adjacent violators)
    def median(vals):
        vals = sorted(vals)
        m = len(vals) // 2
        return vals[m] if len(vals) % 2 else (vals[m - 1] + vals[m]) / 2

    def min_gap(a, b):
        if a.dummy and b.dummy:
            return 16
        return 24 if (a.dummy or b.dummy) else ORDER_GAP

    def pav(layer, desired, weight):
        offs, acc = [], 0.0
        for k, nid in enumerate(layer):
            if k:
                a, b = nodes[layer[k - 1]], nodes[nid]
                acc += so(a) / 2 + so(b) / 2 + min_gap(a, b)
            offs.append(acc)
        blocks = []
        for k, nid in enumerate(layer):
            w = weight[nid]
            blocks.append([w, w * (desired[nid] - offs[k]), 1])
            while len(blocks) > 1 and blocks[-2][1] / blocks[-2][0] > blocks[-1][1] / blocks[-1][0]:
                w2, s2, c2 = blocks.pop()
                blocks[-1][0] += w2
                blocks[-1][1] += s2
                blocks[-1][2] += c2
        out, k = {}, 0
        for w, s, c in blocks:
            for _ in range(c):
                out[layer[k]] = s / w + offs[k]
                k += 1
        return out

    centre = {}
    for r in range(max_r + 1):
        c = 0
        for nid in layers.get(r, []):
            s = so(nodes[nid])
            centre[nid] = c + s / 2
            c += s + ORDER_GAP
    schedule = ["down", "up"] * 5 + ["both-down", "both-up"]
    for mode in schedule:
        rng = range(0, max_r + 1) if mode.endswith("down") else range(max_r, -1, -1)
        for r in rng:
            layer = layers.get(r, [])
            if not layer:
                continue
            desired, weight = {}, {}
            for nid in layer:
                if mode == "down":
                    links = up[nid]
                elif mode == "up":
                    links = down[nid]
                else:
                    links = up[nid] + down[nid]
                ps = [centre[p] for p in links]
                desired[nid] = median(ps) if ps else centre[nid]
                weight[nid] = (4.0 if nodes[nid].dummy else 1.0) if ps else 0.2
            centre.update(pav(layer, desired, weight))
    # straighten one-to-one links (a single exit into a single entry) wherever the layer has room
    def fits(nid, c):
        layer = layers[rank[nid]]
        k = layer.index(nid)
        n = nodes[nid]
        if k > 0:
            m = nodes[layer[k - 1]]
            if centre[m.id] + so(m) / 2 + min_gap(m, n) > c - so(n) / 2 + 0.5:
                return False
        if k + 1 < len(layer):
            m = nodes[layer[k + 1]]
            if c + so(n) / 2 + min_gap(n, m) > centre[m.id] - so(m) / 2 + 0.5:
                return False
        return True

    for _ in range(2):
        for r in range(1, max_r + 1):
            for v in layers.get(r, []):
                if len(up[v]) == 1 and len(down[up[v][0]]) == 1:
                    u = up[v][0]
                    if abs(centre[u] - centre[v]) > 0.5:
                        if fits(v, centre[u]):
                            centre[v] = centre[u]
                        elif fits(u, centre[v]):
                            centre[u] = centre[v]
    min_left = min(centre[n] - so(nodes[n]) / 2 for n in centre) if centre else 0
    for n in centre:
        centre[n] = round(centre[n] - min_left + MARGIN)

    # 6. fan attach points along the order axis: k/(N+1) of the side; small circles take one point
    out_edges, in_edges = {}, {}
    for e in g.edges:
        if e.src == e.dst or e.back:
            continue
        ch = chains[id(e)]
        out_edges.setdefault(e.src, []).append((centre[ch[1]], e))
        in_edges.setdefault(e.dst, []).append((centre[ch[-2]], e))
    attach_out, attach_in = {}, {}
    for table, store in ((out_edges, attach_out), (in_edges, attach_in)):
        for nid, lst in table.items():
            lst.sort(key=lambda t: t[0])
            n, s = nodes[nid], so(nodes[nid])
            left = centre[nid] - s / 2
            single = len(lst) == 1 or n.kind in ("start", "end")
            for k, (_c, e) in enumerate(lst):
                store[id(e)] = centre[nid] if single else round(left + s * (k + 1) / (len(lst) + 1))

    # 7. rank-axis coordinates; a gap grows with the channels it carries and the labels it must hold
    channels = {r: [] for r in range(max_r + 1)}
    for e in g.edges:
        if e.src == e.dst or e.back:
            continue
        ch = chains[id(e)]
        for k, (u, v) in enumerate(zip(ch, ch[1:])):
            a = attach_out[id(e)] if k == 0 else centre[u]
            b = attach_in[id(e)] if k == len(ch) - 2 else centre[v]
            if abs(a - b) >= 6:
                channels[rank[u]].append((min(a, b), id(e), k))

    def outermost(nid):
        return all(centre[o] <= centre[nid] for o in layers[rank[nid]])

    top_pad = 0
    for e in g.edges:
        if not e.back:
            continue
        if not outermost(e.src):
            channels[rank[e.src]].append((-1e9, id(e), "bs"))
        if not outermost(e.dst):
            if rank[e.dst] > 0:
                channels[rank[e.dst] - 1].append((1e9, id(e), "bd"))
            else:
                top_pad = 20
    # a label band right after a rank keeps room beside the first segment of every labelled exit
    band = {}
    for e in g.edges:
        if e.label and not e.back and e.src != e.dst:
            need = 28 if not horizontal else text_width(e.label, EDGE_SIZE) + 28
            band[rank[e.src]] = max(band.get(rank[e.src], 0), need)
    rank_size = {r: max(sr(nodes[n]) for n in layers[r]) for r in layers}
    rank_start, cursor = {}, (HEADER_H if not horizontal else MARGIN) + top_pad
    for r in range(max_r + 1):
        rank_start[r] = cursor
        nch = len(channels.get(r, []))
        cursor += rank_size.get(r, 0) + max(56, 28 + 14 * nch) + band.get(r, 0)
    chan_pos = {}
    for r, lst in channels.items():
        lst.sort(key=lambda t: t[0])
        gap_start = rank_start[r] + rank_size.get(r, 0) + band.get(r, 0)
        gap_end = rank_start.get(r + 1, gap_start + 56)
        for k, (_x, eid, seg) in enumerate(lst):
            chan_pos[(eid, seg)] = round(gap_start + (gap_end - gap_start) * (k + 1) / (len(lst) + 1))

    def rpos(nid):  # rank-axis top of the node, centred in its band
        n = nodes[nid]
        return rank_start[rank[nid]] + (rank_size[rank[nid]] - sr(n)) / 2

    def to_xy(o, r):
        return (r, o) if horizontal else (o, r)

    for nid, n in nodes.items():
        n.x, n.y = to_xy(centre[nid] - so(n) / 2, rpos(nid))
        n.x, n.y = round(n.x), round(n.y)

    # 8. route edges
    side_lane = max((centre[n] + so(nodes[n]) / 2 for n in centre), default=0) + 32
    lane_k = 0
    for e in g.edges:
        a, b = nodes[e.src], nodes[e.dst]
        if e.src == e.dst:
            ar = rpos(e.src)
            o = centre[e.src] + so(a) / 2
            pts = [(o, ar + sr(a) * 0.3), (o + 24, ar + sr(a) * 0.3), (o + 24, ar + sr(a) * 0.7), (o, ar + sr(a) * 0.7)]
            e.points = [to_xy(*p) for p in pts]
            continue
        if e.back:
            lane = side_lane + 16 * lane_k
            lane_k += 1
            ma, mb = rpos(e.src) + sr(a) / 2, rpos(e.dst) + sr(b) / 2
            ea, eb = centre[e.src] + so(a) / 2, centre[e.dst] + so(b) / 2
            pts = [(ea, ma)]
            if (id(e), "bs") in chan_pos:
                cy = chan_pos[(id(e), "bs")]
                pts += [(ea + 16, ma), (ea + 16, cy), (lane, cy)]
            else:
                pts += [(lane, ma)]
            if (id(e), "bd") in chan_pos or not outermost(e.dst):
                cy = chan_pos.get((id(e), "bd"), rank_start[0] - 10)
                pts += [(lane, cy), (eb + 16, cy), (eb + 16, mb), (eb, mb)]
            else:
                pts += [(lane, mb), (eb, mb)]
            e.points = [to_xy(*p) for p in pts]
            continue
        ch = chains[id(e)]
        pts = []
        for k, (u, v) in enumerate(zip(ch, ch[1:])):
            ou = attach_out[id(e)] if k == 0 else centre[u]
            ov = attach_in[id(e)] if k == len(ch) - 2 else centre[v]
            ru = rpos(u) + sr(nodes[u]) if not nodes[u].dummy else rank_start[rank[u]] + rank_size[rank[u]]
            rv = rpos(v) if not nodes[v].dummy else rank_start[rank[v]]
            if k == 0 or nodes[u].dummy:
                pts.append((ou, ru))
            if abs(ou - ov) >= 6:
                cy = chan_pos.get((id(e), k), (ru + rv) / 2)
                pts += [(ou, cy), (ov, cy)]
            else:
                ov = ou
            pts.append((ov, rv))
        clean = []
        for p in pts:
            if not clean or (abs(p[0] - clean[-1][0]) > 0.5 or abs(p[1] - clean[-1][1]) > 0.5):
                clean.append(p)
        e.points = [to_xy(*p) for p in clean]

    real = [n for n in nodes.values() if not n.dummy]
    if horizontal:
        for n in real:
            n.y += HEADER_H - MARGIN
        for e in g.edges:
            e.points = [(x, y + HEADER_H - MARGIN) for x, y in e.points]
    place_labels(g, real)
    min_x = min([n.x for n in real] + [e.label_box[0] for e in g.edges if e.label_box])
    if min_x < MARGIN:   # a label may sit left of the leftmost node: move everything right
        dx = math.ceil(MARGIN - min_x)
        for n in real:
            n.x += dx
        for e in g.edges:
            e.points = [(x + dx, y) for x, y in e.points]
            if e.label_box:
                e.label_box = (e.label_box[0] + dx,) + tuple(e.label_box[1:])
    boxes = [e.label_box for e in g.edges if e.label_box]
    g.width = up4(max([n.x + n.w for n in real] + [p[0] for e in g.edges for p in e.points]
                      + [b[0] + b[2] for b in boxes] + [320]) + MARGIN)
    g.height = up4(max([n.y + n.h for n in real] + [p[1] for e in g.edges for p in e.points]
                       + [b[1] + b[3] for b in boxes]) + MARGIN + 8)
    return g


def rounded_path(pts, r=8):
    if not pts:
        return ""
    d = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
    for i in range(1, len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]
        l1, l2 = math.hypot(x1 - x0, y1 - y0), math.hypot(x2 - x1, y2 - y1)
        rr = min(r, l1 / 2, l2 / 2)
        if rr < 1:
            d.append(f"L{x1:.1f},{y1:.1f}")
            continue
        ax, ay = x1 - (x1 - x0) / l1 * rr, y1 - (y1 - y0) / l1 * rr
        bx, by = x1 + (x2 - x1) / l2 * rr, y1 + (y2 - y1) / l2 * rr
        d.append(f"L{ax:.1f},{ay:.1f}Q{x1:.1f},{y1:.1f} {bx:.1f},{by:.1f}")
    d.append(f"L{pts[-1][0]:.1f},{pts[-1][1]:.1f}")
    return "".join(d)


def seg_hits_box(p, q, box, pad=0):
    x, y, w, h = box[0] - pad, box[1] - pad, box[2] + 2 * pad, box[3] + 2 * pad
    (x0, y0), (x1, y1) = p, q
    if abs(x0 - x1) < 0.5:
        return x <= x0 <= x + w and min(y0, y1) < y + h and max(y0, y1) > y
    if abs(y0 - y1) < 0.5:
        return y <= y0 <= y + h and min(x0, x1) < x + w and max(x0, x1) > x
    return overlaps((min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)), (x, y, w, h))


def place_labels(g, real):
    """Beside a vertical segment or above/below a horizontal one, never on a stroke.

    Every candidate is scored: touching a node or another label is ruled out,
    crossing any connector is expensive, and decision exits stay near their decision.
    """
    nboxes = [(n.x, n.y, n.w, n.h) for n in real]
    placed = []
    for e in g.edges:
        e.label_box = None
    for e in sorted(g.edges, key=lambda e: 0 if g.nodes[e.src].kind == "decision" else 1):
        if not e.label or len(e.points) < 2:
            continue
        lw, lh = text_width(e.label, EDGE_SIZE) + 12, 18
        segs = list(zip(e.points, e.points[1:]))
        total = sum(abs(q[0] - p[0]) + abs(q[1] - p[1]) for p, q in segs) or 1
        near_src = g.nodes[e.src].kind == "decision"
        best, best_score, dist = None, None, 0.0
        for i, (p, q) in enumerate(segs):
            seg_len = abs(q[0] - p[0]) + abs(q[1] - p[1])
            cands = []
            if abs(p[0] - q[0]) < 0.5 and seg_len >= lh + 8:
                ts = [0.5, 0.3, 0.7]
                if seg_len >= 2 * (lh / 2 + 12):
                    ts.append((lh / 2 + 12) / seg_len)
                for t in ts:
                    cy = p[1] + (q[1] - p[1]) * t
                    cands += [((p[0] + 8, cy - lh / 2, lw, lh), dist + seg_len * t, 0),
                              ((p[0] - 8 - lw, cy - lh / 2, lw, lh), dist + seg_len * t, 1)]
            elif abs(p[1] - q[1]) < 0.5 and seg_len >= lw + 16:
                cx = (p[0] + q[0]) / 2
                cands += [((cx - lw / 2, p[1] - 6 - lh, lw, lh), dist + seg_len / 2, 0),
                          ((cx - lw / 2, p[1] + 6, lw, lh), dist + seg_len / 2, 1)]
            for box, d, side in cands:
                s = side * 2 + (d * 0.15 if near_src else abs(d - total / 2) * 0.05)
                if box[1] < HEADER_H - 4:   # the title block owns the top band
                    s += 400
                if any(overlaps(box, b, 4) for b in nboxes):
                    s += 1000
                if any(overlaps(box, b, 4) for b in placed):
                    s += 1000
                for e2 in g.edges:
                    for j, (a2, b2) in enumerate(zip(e2.points, e2.points[1:])):
                        if not (e2 is e and j == i) and seg_hits_box(a2, b2, box, 2):
                            s += 150
                if best_score is None or s < best_score:
                    best, best_score = box, s
            dist += seg_len
        if best is None:
            (x0, y0), (x1, y1) = segs[0]
            best = ((x0 + x1) / 2 + 8, (y0 + y1) / 2 - lh / 2, lw, lh)
        e.label_box = best
        placed.append(best)


# --------------------------------------------------------------------- sequence


def parse_sequence(src):
    seq = {"participants": [], "names": {}, "kinds": {}, "items": [], "errors": []}

    def ensure(pid, label=None, kind="participant"):
        if pid not in seq["names"]:
            seq["participants"].append(pid)
            seq["names"][pid] = label or pid
            seq["kinds"][pid] = kind
        elif label:
            seq["names"][pid] = label

    depth = 0
    for i, raw in enumerate(src.splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("%%") or s == "sequenceDiagram" or s.startswith(("autonumber", "activate", "deactivate", "title", "box", "create")):
            continue
        m = re.match(r"^(participant|actor)\s+(\w+)(?:\s+as\s+(.+))?$", s)
        if m:
            ensure(m.group(2), (m.group(3) or m.group(2)).strip(), m.group(1))
            continue
        m = re.match(r"^(\w+)\s*(-->>|->>|-->|->|--x|-x|--\)|-\))\s*[+-]?\s*(\w+)\s*:\s*(.*)$", s)
        if m:
            a, op, b, text = m.groups()
            ensure(a)
            ensure(b)
            seq["items"].append(("msg", a, b, text.strip(), op.startswith("--"), op.endswith("x")))
            continue
        m = re.match(r"^[Nn]ote\s+(over|left of|right of)\s+([\w\s,]+?)\s*:\s*(.*)$", s)
        if m:
            who = [w.strip() for w in m.group(2).split(",") if w.strip()]
            for w in who:
                ensure(w)
            seq["items"].append(("note", m.group(1), who, m.group(3).strip()))
            continue
        m = re.match(r"^(alt|opt|loop|par|critical|break|rect)\b\s*(.*)$", s)
        if m:
            depth += 1
            seq["items"].append(("open", m.group(1), m.group(2).strip()))
            continue
        m = re.match(r"^(else|and|option)\b\s*(.*)$", s)
        if m:
            seq["items"].append(("else", m.group(2).strip()))
            continue
        if s == "end":
            depth -= 1
            seq["items"].append(("close",))
            continue
        seq["errors"].append(f"line {i}: cannot parse `{s}`")
    if depth != 0:
        seq["errors"].append("unbalanced alt/opt/loop … end blocks")
    return seq


def layout_sequence(seq):
    parts = seq["participants"]
    box_w = {p: up4(max(104, text_width(seq["names"][p], NAME_SIZE) + 32)) for p in parts}
    x = {}
    cur = MARGIN
    for p in parts:
        x[p] = cur + box_w[p] / 2
        cur += box_w[p] + 40
    idx = {p: k for k, p in enumerate(parts)}
    for _ in range(len(parts) * 3):
        changed = False
        for it in seq["items"]:
            if it[0] != "msg" or it[1] == it[2]:
                continue
            a, b = sorted((it[1], it[2]), key=lambda p: idx[p])
            need = text_width(it[3], EDGE_SIZE) + 40
            gap = x[b] - x[a]
            if gap < need:
                d = need - gap
                for p in parts[idx[b]:]:
                    x[p] += d
                changed = True
        if not changed:
            break
    # y is the top of the next row; a message label sits 26px above its arrow
    y = HEADER_H + 4 + 40 + 16
    rows, frames, stack = [], [], []
    for it in seq["items"]:
        if it[0] == "msg":
            a, b, text = it[1], it[2], it[3]
            if a == b:
                rows.append(("self", a, text, it[4], y + 8))
                for f in stack:
                    f["xmax"] = max(f.get("xmax", 0), x[a] + 44 + text_width(text, EDGE_SIZE) + 24)
                y += 8 + 24 + 20
            else:
                rows.append(("msg", a, b, text, it[4], it[5], y + 26))
                y += 26 + 18
            for f in stack:
                f["who"].update({a, b})
        elif it[0] == "note":
            lines = wrap(it[3], 12.5, 220)
            h = len(lines) * 16 + 16
            ws = [x[p] for p in it[2]]
            nw = max(text_width(l, 12.5) for l in lines) + 24
            if it[1] == "over":
                nw = max(nw, max(ws) - min(ws) + 120)
                nx0 = (min(ws) + max(ws)) / 2 - nw / 2
            else:
                nx0 = ws[0] + 16 if it[1] == "right of" else ws[0] - 16 - nw
            rows.append(("note", it[1], it[2], lines, y + 6, h, nx0, nw))
            y += 6 + h + 14
            for f in stack:
                f["who"].update(it[2])
        elif it[0] == "open":
            f = {"kind": it[1], "label": it[2], "y0": y + 4, "elses": [], "who": set(), "depth": len(stack)}
            stack.append(f)
            y += 4 + 18 + 10
        elif it[0] == "else" and stack:
            stack[-1]["elses"].append((y + 6, it[1]))
            y += 6 + 22
        elif it[0] == "close" and stack:
            f = stack.pop()
            f["y1"] = y + 6
            frames.append(f)
            y += 6 + 14
    lefts = [x[p] - box_w[p] / 2 for p in parts] + [r[6] for r in rows if r[0] == "note"]
    rights = [x[p] + box_w[p] / 2 for p in parts] + [r[6] + r[7] for r in rows if r[0] == "note"]
    rights += [x[r[1]] + 44 + text_width(r[2], EDGE_SIZE) + 12 for r in rows if r[0] == "self"]
    dx = max(0, MARGIN - min(lefts)) if lefts else 0
    if dx:
        for f in frames:
            if "xmax" in f:
                f["xmax"] += dx
        for p in parts:
            x[p] += dx
        rows = [r[:6] + (r[6] + dx, r[7]) if r[0] == "note" else r for r in rows]
    width = (max(rights) + dx + MARGIN) if parts else 320
    return {"x": x, "box_w": box_w, "rows": rows, "frames": frames, "bottom": y, "width": up4(width + 24),
            "height": up4(y + 40)}


# --------------------------------------------------------------------- SVG output


def svg_open(w, h, uid, title, desc, theme, eyebrow):
    t = theme
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
        f'aria-labelledby="{uid}-title {uid}-desc">',
        f'<title id="{uid}-title">{esc(title)}</title>',
        f'<desc id="{uid}-desc">{esc(desc)}</desc>',
        "<defs>",
        f'<marker id="{uid}-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{t["muted"]}"/></marker>',
        f'<marker id="{uid}-arrow-accent" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{t["accent"]}"/></marker>',
        "</defs>",
        f'<rect width="{w}" height="{h}" fill="{t["paper"]}"/>',
        f'<text x="{MARGIN}" y="24" font-family="{esc(t["mono"])}" font-size="10.5" letter-spacing="0.08em" fill="{t["soft"]}">{esc(eyebrow.upper())}</text>',
        f'<text x="{MARGIN}" y="44" font-family="{esc(t["font"])}" font-size="17" font-weight="600" fill="{t["ink"]}">{esc(title)}</text>',
    ]


def render_node(n, t, out):
    if n.dummy:
        return
    focal = "focal" in n.cls
    stroke, fill, text = t["ink"], t["paper"], t["ink"]
    dash = ""
    if n.kind == "start":
        out.append(f'<circle cx="{n.x + 10}" cy="{n.y + 10}" r="8" fill="{t["ink"]}"/>')
        return
    if n.kind == "end":
        out.append(f'<circle cx="{n.x + 10}" cy="{n.y + 10}" r="9" fill="none" stroke="{t["ink"]}" stroke-width="1.5"/>'
                   f'<circle cx="{n.x + 10}" cy="{n.y + 10}" r="5" fill="{t["ink"]}"/>')
        return
    if n.kind == "terminal":
        fill, text, stroke = t["ink"], t["paper"], t["ink"]
    elif n.kind in ("decision", "store"):
        fill = t["paper2"]
    elif n.kind == "external":
        stroke, dash = t["muted"], ' stroke-dasharray="5,4"'
    if focal:
        stroke, fill = t["accent"], t["accentTint"] if n.kind != "terminal" else t["accent"]
    rx = 10 if n.kind == "state" else 6
    sw = 2 if focal else 1.25
    out.append(f'<rect x="{n.x}" y="{n.y}" width="{n.w}" height="{n.h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dash}/>')
    if n.kind == "store":
        out.append(f'<line x1="{n.x}" y1="{n.y + 6}" x2="{n.x + n.w}" y2="{n.y + 6}" stroke="{stroke}" stroke-width="1"/>')
    tx = n.x + n.w / 2
    if n.kind == "decision":
        cx, cy = n.x + 14, n.y + n.h / 2
        out.append(f'<path d="M{cx},{cy - 5} L{cx + 5},{cy} L{cx},{cy + 5} L{cx - 5},{cy} z" fill="{t["accent"] if focal else t["muted"]}"/>')
        tx += 7
    total = len(n.lines) * LINE_H + (16 if n.tags else 0)
    y0 = n.y + (n.h - total) / 2 + 13
    for k, line in enumerate(n.lines):
        out.append(f'<text x="{tx:.1f}" y="{y0 + k * LINE_H:.1f}" text-anchor="middle" font-family="{esc(t["font"])}" '
                   f'font-size="{NAME_SIZE}" font-weight="600" fill="{text}">{esc(line)}</text>')
    if n.tags:
        tag_fill = t["paper"] if n.kind == "terminal" else t["soft"]
        out.append(f'<text x="{tx:.1f}" y="{y0 + len(n.lines) * LINE_H + 1:.1f}" text-anchor="middle" font-family="{esc(t["mono"])}" '
                   f'font-size="{TAG_SIZE}" fill="{tag_fill}">{esc(" · ".join(n.tags))}</text>')


def render_graph_svg(g, title, theme, uid, eyebrow, src_hash):
    t = theme
    out = svg_open(g.width, g.height, uid, title,
                   f"{len([n for n in g.nodes.values()])} nodes, {len(g.edges)} connections. Source sha1 {src_hash}.", t, eyebrow)
    out.insert(1, f"<!-- generated by sdd-diagrams; source-sha1: {src_hash}; do not edit by hand -->")
    focal_ids = {n.id for n in g.nodes.values() if "focal" in n.cls}
    for e in g.edges:  # connectors first, so they sit behind nodes
        accent = e.src in focal_ids and e.dst in focal_ids
        colour = t["accent"] if accent else t["muted"]
        dash = ' stroke-dasharray="5,4"' if e.dashed else ""
        width = 2 if e.thick or accent else 1.4
        marker = f'url(#{uid}-arrow-accent)' if accent else f'url(#{uid}-arrow)'
        out.append(f'<path d="{rounded_path(e.points)}" fill="none" stroke="{colour}" stroke-width="{width}"{dash} marker-end="{marker}"/>')
    for nid in g.order:
        render_node(g.nodes[nid], t, out)
    for e in g.edges:
        box = getattr(e, "label_box", None)
        if box:
            x, y, w, h = box
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="3" fill="{t["paper"]}"/>')
            out.append(f'<text x="{x + w / 2:.1f}" y="{y + 13:.1f}" text-anchor="middle" font-family="{esc(t["font"])}" '
                       f'font-size="{EDGE_SIZE}" fill="{t["muted"]}">{esc(e.label)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def render_sequence_svg(seq, lay, title, theme, uid, eyebrow, src_hash):
    t = theme
    w, h = lay["width"], lay["height"]
    out = svg_open(w, h, uid, title, f"Sequence between {len(seq['participants'])} participants. Source sha1 {src_hash}.", t, eyebrow)
    out.insert(1, f"<!-- generated by sdd-diagrams; source-sha1: {src_hash}; do not edit by hand -->")
    top = HEADER_H + 4
    xs = lay["x"]
    frame_labels = []
    for f in sorted(lay["frames"], key=lambda f: f["depth"]):
        who = f["who"] or set(seq["participants"])
        x0 = min(xs[p] - lay["box_w"][p] / 2 for p in who) - 12 + 8 * f["depth"]
        x1 = max([xs[p] + lay["box_w"][p] / 2 for p in who] + [f.get("xmax", 0)]) + 12 - 8 * f["depth"]
        out.append(f'<rect x="{x0:.1f}" y="{f["y0"]:.1f}" width="{x1 - x0:.1f}" height="{f["y1"] - f["y0"]:.1f}" rx="6" fill="none" stroke="{t["rule"]}" stroke-width="1.25"/>')
        tag = f["kind"].upper()
        tw = text_width(tag, 10.5) + 14
        out.append(f'<rect x="{x0:.1f}" y="{f["y0"]:.1f}" width="{tw:.1f}" height="18" rx="2" fill="{t["paper2"]}" stroke="{t["rule"]}"/>')
        out.append(f'<text x="{x0 + 7:.1f}" y="{f["y0"] + 13:.1f}" font-family="{esc(t["mono"])}" font-size="10.5" fill="{t["muted"]}">{esc(tag)}</text>')
        if f["label"]:
            frame_labels.append((x0 + tw + 4, f["y0"] + 1, f"[{f['label']}]"))
        for ey, elabel in f["elses"]:
            out.append(f'<line x1="{x0:.1f}" y1="{ey:.1f}" x2="{x1:.1f}" y2="{ey:.1f}" stroke="{t["rule"]}" stroke-dasharray="5,4"/>')
            if elabel:
                frame_labels.append((x0 + 4, ey + 3, f"[{elabel}]"))
    for p in seq["participants"]:
        cx, bw = xs[p], lay["box_w"][p]
        out.append(f'<line x1="{cx}" y1="{top + 40}" x2="{cx}" y2="{lay["bottom"] + 8}" stroke="{t["rule"]}" stroke-width="1.25" stroke-dasharray="4,4"/>')
        fill = t["ink"] if seq["kinds"][p] == "actor" else t["paper"]
        tc = t["paper"] if seq["kinds"][p] == "actor" else t["ink"]
        out.append(f'<rect x="{cx - bw / 2:.1f}" y="{top}" width="{bw}" height="40" rx="6" fill="{fill}" stroke="{t["ink"]}" stroke-width="1.25"/>')
        out.append(f'<text x="{cx}" y="{top + 25}" text-anchor="middle" font-family="{esc(t["font"])}" font-size="{NAME_SIZE}" font-weight="600" fill="{tc}">{esc(seq["names"][p])}</text>')
    labels = []
    for r in lay["rows"]:
        if r[0] == "msg":
            _, a, b, text, dashed, cross, y = r
            xa, xb = xs[a], xs[b]
            dirn = 1 if xb > xa else -1
            colour = t["muted"] if dashed else t["ink"]
            dash = ' stroke-dasharray="5,4"' if dashed else ""
            marker = "" if cross else f' marker-end="url(#{uid}-arrow)"'
            out.append(f'<path d="M{xa},{y} L{xb - dirn * 1},{y}" stroke="{colour}" stroke-width="1.4"{dash} fill="none"{marker}/>')
            if cross:
                cx = xb - dirn * 6
                out.append(f'<path d="M{cx - 5},{y - 5} L{cx + 5},{y + 5} M{cx - 5},{y + 5} L{cx + 5},{y - 5}" stroke="{t["accent"]}" stroke-width="1.8"/>')
            lw = text_width(text, EDGE_SIZE) + 12
            labels.append(((xa + xb) / 2 - lw / 2, y - 26, lw, 18, text))
        elif r[0] == "self":
            _, a, text, dashed, y = r
            xa = xs[a]
            out.append(f'<path d="{rounded_path([(xa, y), (xa + 36, y), (xa + 36, y + 24), (xa + 2, y + 24)])}" fill="none" stroke="{t["ink"]}" stroke-width="1.4" marker-end="url(#{uid}-arrow)"/>')
            lw = text_width(text, EDGE_SIZE) + 12
            labels.append((xa + 44, y + 3, lw, 18, text))
        elif r[0] == "note":
            _, where, who, lines, y, nh, nx0, nw = r
            out.append(f'<rect x="{nx0:.1f}" y="{y:.1f}" width="{nw:.1f}" height="{nh}" rx="4" fill="{t["accentTint"]}" stroke="{t["rule"]}"/>')
            for k, l in enumerate(lines):
                out.append(f'<text x="{nx0 + 12:.1f}" y="{y + 20 + k * 16:.1f}" font-family="{esc(t["font"])}" font-size="12.5" fill="{t["ink"]}">{esc(l)}</text>')
    for x, y, text in frame_labels:
        fw = text_width(text, 12) + 8
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{fw:.1f}" height="16" rx="2" fill="{t["paper"]}"/>')
        out.append(f'<text x="{x + 4:.1f}" y="{y + 12:.1f}" font-family="{esc(t["font"])}" font-size="12" font-style="italic" fill="{t["muted"]}">{esc(text)}</text>')
    for x, y, lw, lh, text in labels:
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{lw:.1f}" height="{lh}" rx="3" fill="{t["paper"]}"/>')
        out.append(f'<text x="{x + lw / 2:.1f}" y="{y + 13:.1f}" text-anchor="middle" font-family="{esc(t["font"])}" font-size="{EDGE_SIZE}" fill="{t["ink"]}">{esc(text)}</text>')
    out.append("</svg>")
    return "\n".join(out)


# --------------------------------------------------------------------- draw.io output


def drawio_style(n, t):
    base = f"whiteSpace=wrap;html=1;fontFamily=Inter;fontSize=14;fontStyle=1;strokeColor={t['ink']};fontColor={t['ink']};"
    focal = "focal" in n.cls
    if n.kind == "decision":
        s = f"rhombus;{base}fillColor={t['paper2']};"
    elif n.kind == "terminal":
        s = f"rounded=1;arcSize=12;{base}fillColor={t['ink']};fontColor={t['paper']};"
    elif n.kind == "store":
        s = f"shape=cylinder3;boundedLbl=1;size=8;{base}fillColor={t['paper2']};"
    elif n.kind == "external":
        s = f"rounded=1;arcSize=10;dashed=1;{base}fillColor={t['paper']};"
    elif n.kind == "start":
        s = f"ellipse;fillColor={t['ink']};strokeColor={t['ink']};"
    elif n.kind == "end":
        s = f"ellipse;shape=doubleEllipse;fillColor={t['ink']};strokeColor={t['ink']};"
    else:
        s = f"rounded=1;arcSize={14 if n.kind == 'state' else 10};{base}fillColor={t['paper']};"
    if focal:
        s += f"strokeColor={t['accent']};strokeWidth=2;"
    return s


def drawio_graph_page(g, title, t, page_id):
    cells = []
    ids = {}
    for k, nid in enumerate(g.order):
        n = g.nodes[nid]
        cid = f"{page_id}-n{k}"
        ids[nid] = cid
        label = esc(n.label + (("<br><font face=\"monospace\" style=\"font-size:10px\">" + " · ".join(n.tags) + "</font>") if n.tags else ""))
        w, h = (n.w, n.h) if n.kind != "decision" else (up4(n.w + min(n.w * 0.25, 32)), up4(n.h + min(n.h * 0.4, 24)))
        x, y = n.x - (w - n.w) / 2, n.y - (h - n.h) / 2
        cells.append(f'<mxCell id="{cid}" value="{label}" style="{drawio_style(n, t)}" vertex="1" parent="1">'
                     f'<mxGeometry x="{x:.0f}" y="{y:.0f}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    for k, e in enumerate(g.edges):
        style = (f"edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;html=1;endArrow=block;endFill=1;"
                 f"strokeColor={t['muted']};fontColor={t['muted']};fontSize=12;labelBackgroundColor={t['paper']};")
        if e.dashed:
            style += "dashed=1;"
        pts = "".join(f'<mxPoint x="{x:.0f}" y="{y:.0f}"/>' for x, y in e.points[1:-1])
        cells.append(f'<mxCell id="{page_id}-e{k}" value="{esc(e.label)}" style="{style}" edge="1" parent="1" '
                     f'source="{ids[e.src]}" target="{ids[e.dst]}"><mxGeometry relative="1" as="geometry">'
                     f'<Array as="points">{pts}</Array></mxGeometry></mxCell>')
    return cells


def drawio_sequence_page(seq, lay, t, page_id):
    cells, top = [], HEADER_H + 4
    for k, p in enumerate(seq["participants"]):
        cx, bw = lay["x"][p], lay["box_w"][p]
        fill = t["ink"] if seq["kinds"][p] == "actor" else t["paper"]
        fc = t["paper"] if seq["kinds"][p] == "actor" else t["ink"]
        cells.append(f'<mxCell id="{page_id}-p{k}" value="{esc(seq["names"][p])}" style="rounded=1;arcSize=10;whiteSpace=wrap;html=1;'
                     f'fontStyle=1;fillColor={fill};fontColor={fc};strokeColor={t["ink"]};" vertex="1" parent="1">'
                     f'<mxGeometry x="{cx - bw / 2:.0f}" y="{top}" width="{bw}" height="40" as="geometry"/></mxCell>')
        cells.append(f'<mxCell id="{page_id}-l{k}" style="endArrow=none;dashed=1;strokeColor={t["rule"]};" edge="1" parent="1">'
                     f'<mxGeometry relative="1" as="geometry"><mxPoint x="{cx:.0f}" y="{top + 40}" as="sourcePoint"/>'
                     f'<mxPoint x="{cx:.0f}" y="{lay["bottom"] + 8:.0f}" as="targetPoint"/></mxGeometry></mxCell>')
    for k, r in enumerate(lay["rows"]):
        if r[0] == "msg":
            _, a, b, text, dashed, _cross, y = r
            style = f"html=1;endArrow=block;endFill=1;strokeColor={t['muted'] if dashed else t['ink']};labelBackgroundColor={t['paper']};verticalAlign=bottom;" + ("dashed=1;" if dashed else "")
            cells.append(f'<mxCell id="{page_id}-m{k}" value="{esc(text)}" style="{style}" edge="1" parent="1">'
                         f'<mxGeometry relative="1" as="geometry"><mxPoint x="{lay["x"][a]:.0f}" y="{y:.0f}" as="sourcePoint"/>'
                         f'<mxPoint x="{lay["x"][b]:.0f}" y="{y:.0f}" as="targetPoint"/></mxGeometry></mxCell>')
        elif r[0] == "note":
            _, where, who, lines, y, nh, nx, nw = r
            cells.append(f'<mxCell id="{page_id}-n{k}" value="{esc(" ".join(lines))}" style="shape=note;size=10;whiteSpace=wrap;html=1;'
                         f'fillColor={t["accentTint"]};strokeColor={t["rule"]};align=left;spacingLeft=8;" vertex="1" parent="1">'
                         f'<mxGeometry x="{nx:.0f}" y="{y:.0f}" width="{nw:.0f}" height="{nh}" as="geometry"/></mxCell>')
    for k, f in enumerate(lay["frames"]):
        who = f["who"] or set(seq["participants"])
        x0 = min(lay["x"][p] - lay["box_w"][p] / 2 for p in who) - 12
        x1 = max([lay["x"][p] + lay["box_w"][p] / 2 for p in who] + [f.get("xmax", 0)]) + 12
        label = esc(f"{f['kind'].upper()} [{f['label']}]" if f["label"] else f["kind"].upper())
        cells.append(f'<mxCell id="{page_id}-f{k}" value="{label}" style="rounded=1;arcSize=4;fillColor=none;strokeColor={t["rule"]};'
                     f'verticalAlign=top;align=left;spacingLeft=6;fontSize=11;fontColor={t["muted"]};" vertex="1" parent="1">'
                     f'<mxGeometry x="{x0:.0f}" y="{f["y0"]:.0f}" width="{x1 - x0:.0f}" height="{f["y1"] - f["y0"]:.0f}" as="geometry"/></mxCell>')
    return cells


def drawio_file(pages):
    body = []
    for page_id, name, cells in pages:
        body.append(f'<diagram id="{esc(page_id)}" name="{esc(name)}"><mxGraphModel grid="1" gridSize="4" guides="1" '
                    f'tooltips="1" connect="1" arrows="1" fold="1" page="0" pageScale="1" math="0" shadow="0"><root>'
                    f'<mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(cells) + "</root></mxGraphModel></diagram>")
    return '<mxfile host="sdd-diagrams" type="device">' + "".join(body) + "</mxfile>\n"


# --------------------------------------------------------------------- checks

BUDGET_WARN_NODES, BUDGET_MAX_NODES, BUDGET_MAX_EDGES, BUDGET_MAX_FOCAL = 9, 12, 14, 2


def overlaps(a, b, pad=0):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw + pad and bx < ax + aw + pad and ay < by + bh + pad and by < ay + ah + pad


def check_graph(g, title):
    errs, warns = list(g.errors), []
    real = [n for n in g.nodes.values() if n.kind not in ("start", "end")]
    if len(real) > BUDGET_MAX_NODES:
        errs.append(f"{len(real)} nodes: over the hard budget of {BUDGET_MAX_NODES}; split into overview + detail")
    elif len(real) > BUDGET_WARN_NODES:
        warns.append(f"{len(real)} nodes: above the comfortable budget of {BUDGET_WARN_NODES}; consider splitting")
    if len(g.edges) > BUDGET_MAX_EDGES:
        warns.append(f"{len(g.edges)} connections: above {BUDGET_MAX_EDGES}; consider splitting")
    focal = [n.id for n in g.nodes.values() if "focal" in n.cls]
    if len(focal) > BUDGET_MAX_FOCAL:
        errs.append(f"{len(focal)} focal nodes ({', '.join(focal)}): accent is for at most {BUDGET_MAX_FOCAL}")
    outdeg = {}
    for e in g.edges:
        outdeg[e.src] = outdeg.get(e.src, 0) + 1
    for n in g.nodes.values():
        if n.kind == "decision" and outdeg.get(n.id, 0) < 2:
            errs.append(f"decision `{n.id}` has {outdeg.get(n.id, 0)} exit(s); every decision needs all its exits")
        if n.kind == "decision" and outdeg.get(n.id, 0) >= 2:
            unlabeled = [e for e in g.edges if e.src == n.id and not e.label]
            if unlabeled:
                warns.append(f"decision `{n.id}` has unlabeled exits")
    linked = {e.src for e in g.edges} | {e.dst for e in g.edges}
    for n in g.nodes.values():
        if n.id not in linked and len(g.nodes) > 1:
            warns.append(f"node `{n.id}` is not connected")
    boxes = [(n.x, n.y, n.w, n.h, n.id) for n in g.nodes.values() if not n.dummy]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if overlaps(boxes[i][:4], boxes[j][:4]):
                errs.append(f"layout: nodes `{boxes[i][4]}` and `{boxes[j][4]}` overlap")
    labelled = [e for e in g.edges if getattr(e, "label_box", None)]
    for k, e in enumerate(labelled):
        lb = e.label_box
        for b in boxes:
            if overlaps(lb, b[:4]):
                warns.append(f"label `{e.label}` touches node `{b[4]}`")
        for e2 in labelled[k + 1:]:
            if overlaps(lb, e2.label_box):
                warns.append(f"labels `{e.label}` and `{e2.label}` overlap")
        crossed = {e2.src + "->" + e2.dst for e2 in g.edges if e2 is not e
                   for a, b in zip(e2.points, e2.points[1:]) if seg_hits_box(a, b, lb)}
        if crossed:
            warns.append(f"label `{e.label}` sits on connector(s) {', '.join(sorted(crossed))}")
        if lb[0] < 0 or lb[1] < 0 or lb[0] + lb[2] > g.width or lb[1] + lb[3] > g.height:
            warns.append(f"label `{e.label}` falls outside the canvas")
    for b in boxes:
        if b[0] + b[2] > g.width or b[1] + b[3] > g.height:
            errs.append(f"node `{b[4]}` falls outside the canvas")
    return errs, warns


# --------------------------------------------------------------------- driver


def slug(s):
    s = re.sub(r"[^\w\s-]", "", s.lower(), flags=re.UNICODE).strip()
    return re.sub(r"[\s_]+", "-", s) or "diagram"


def process(paths, out_dir=None, drawio=False, theme=None, feature_id=None, write=True):
    theme = theme or dict(DEFAULT_THEME)
    report = {"diagrams": [], "skipped": [], "errors": 0, "warnings": 0, "drawio": []}
    outputs = {}   # target folder -> {"fid", "pages", "gallery"}
    for path in paths:
        p = Path(path)
        target = Path(out_dir) if out_dir else p.parent / "diagrams"
        parts = p.parent.name.split("-")
        fid = (feature_id or "-".join(parts[:2])).strip("-") or "feature"
        bucket = outputs.setdefault(str(target), {"fid": fid, "pages": [], "gallery": []})
        prefix = "" if p.stem in ("spec", "discovery") else f"{p.stem}-"
        for title, src in extract_blocks(p):
            kind = diagram_kind(src)
            src_hash = hashlib.sha1(src.strip().encode("utf-8")).hexdigest()[:12]
            name = prefix + slug(title)
            uid = f"d-{slug(fid)}-{name}"
            entry = {"source": str(p), "title": title, "kind": kind, "name": name, "sha1": src_hash, "errors": [], "warnings": []}
            eyebrow = f"{fid} · {kind}"
            svg = None
            if kind in ("flowchart", "state"):
                g = parse_flowchart(src) if kind == "flowchart" else parse_state(src)
                if g.nodes:
                    layout_graph(g)
                    svg = render_graph_svg(g, title, theme, uid, eyebrow, src_hash)
                    entry["errors"], entry["warnings"] = check_graph(g, title)
                    if drawio:
                        bucket["pages"].append((uid, title, drawio_graph_page(g, title, theme, uid)))
                else:
                    entry["errors"] = g.errors or ["empty diagram"]
            elif kind == "sequence":
                seq = parse_sequence(src)
                entry["errors"] = list(seq["errors"])
                if seq["participants"]:
                    lay = layout_sequence(seq)
                    svg = render_sequence_svg(seq, lay, title, theme, uid, eyebrow, src_hash)
                    if len(seq["participants"]) > 6:
                        entry["warnings"].append(f"{len(seq['participants'])} participants: above 6, consider splitting")
                    msgs = sum(1 for it in seq["items"] if it[0] == "msg")
                    if msgs > 16:
                        entry["warnings"].append(f"{msgs} messages: above 16, consider splitting")
                    if drawio:
                        bucket["pages"].append((uid, title, drawio_sequence_page(seq, lay, theme, uid)))
                else:
                    entry["errors"].append("no participants")
            else:
                report["skipped"].append({"source": str(p), "title": title, "kind": kind,
                                          "why": "outside the portable subset; render with mermaid-cli or GitHub"})
                continue
            existing = target / f"{name}.svg"
            if not write:
                if not existing.exists():
                    entry["warnings"].append(f"{existing} is missing; run build")
                else:
                    m = re.search(r"source-sha1: ([0-9a-f]+)", existing.read_text(encoding="utf-8"))
                    if not m or m.group(1) != src_hash:
                        entry["warnings"].append(f"{existing} is stale (source changed); run build")
            if write and svg:
                target.mkdir(parents=True, exist_ok=True)
                (target / f"{name}.mmd").write_text(src.strip() + "\n", encoding="utf-8")
                (target / f"{name}.svg").write_text(svg, encoding="utf-8")
                entry["svg"] = str(target / f"{name}.svg")
                bucket["gallery"].append((title, kind, svg))
            report["errors"] += len(entry["errors"])
            report["warnings"] += len(entry["warnings"])
            report["diagrams"].append(entry)
    if write:
        for target, bucket in outputs.items():
            if not bucket["gallery"]:
                continue
            target = Path(target)
            if drawio and bucket["pages"]:
                path = target / f"{slug(bucket['fid'])}.drawio"
                path.write_text(drawio_file(bucket["pages"]), encoding="utf-8")
                report["drawio"].append(str(path))
            (target / "index.html").write_text(gallery_html(bucket["fid"], bucket["gallery"], theme), encoding="utf-8")
            mine = [d for d in report["diagrams"] if d.get("svg", "").startswith(str(target))]
            (target / "manifest.json").write_text(json.dumps({"feature": bucket["fid"], "diagrams": mine,
                                                              "skipped": report["skipped"]}, indent=2, ensure_ascii=False) + "\n",
                                                  encoding="utf-8")
    return report


def gallery_html(fid, items, t):
    parts = [f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>{esc(fid)} diagrams</title><style>body{{margin:0;background:{t["paper"]};color:{t["ink"]};font-family:{t["font"]}}}'
             f'main{{max-width:1200px;margin:0 auto;padding:32px 16px}}h1{{font-size:20px;margin:0 0 24px}}'
             f'section{{margin:0 0 40px}}.scroll{{overflow-x:auto;border:1px solid {t["rule"]};border-radius:6px;background:{t["paper"]}}}'
             f'.scroll svg{{display:block}}</style></head><body><main><h1>{esc(fid)} · How it works</h1>']
    for title, kind, svg in items:
        parts.append(f'<section data-diagram="{esc(slug(title))}" data-kind="{kind}"><div class="scroll">{svg}</div></section>')
    parts.append("</main></body></html>\n")
    return "".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["build", "check"])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out")
    ap.add_argument("--drawio", action="store_true")
    ap.add_argument("--theme")
    ap.add_argument("--tokens")
    ap.add_argument("--id")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    a = ap.parse_args(argv)
    theme = load_theme(a.theme, a.tokens)
    theme_issues = contrast_issues(theme)
    for issue in theme_issues:
        print(f"[WARN] {issue}")
    report = process(a.files, a.out, a.drawio, theme, a.id, write=a.command == "build")
    for d in report["diagrams"]:
        status = "FAIL" if d["errors"] else ("WARN" if d["warnings"] else "OK")
        print(f"[{status}] {d['source']} › {d['title']} ({d['kind']})" + (f" → {d.get('svg')}" if d.get("svg") else ""))
        for e in d["errors"]:
            print(f"    error: {e}")
        for w in d["warnings"]:
            print(f"    warn:  {w}")
    for s in report["skipped"]:
        print(f"[SKIP] {s['source']} › {s['title']} ({s['kind']}): {s['why']}")
    for path in report["drawio"]:
        print(f"draw.io: {path}")
    print(f"{len(report['diagrams'])} diagram(s), {report['errors']} error(s), {report['warnings']} warning(s), {len(report['skipped'])} skipped")
    return 1 if report["errors"] or (a.strict and (report["warnings"] or theme_issues)) else 0


if __name__ == "__main__":
    sys.exit(main())
