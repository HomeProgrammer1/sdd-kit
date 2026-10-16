#!/usr/bin/env node
/*
 * Tests for plugins/sdd-figma: build_bundle.py on the EXAMPLE-001 feature and the
 * dashboard example, then figma-plugin/code.js inside a strict mock of the Figma
 * Plugin API, then the spec drift warnings of render_prototype.py and build_bundle.py.
 * Node built-ins only. Run: node scripts/test_figma_plugin.js   (exit 1 on failure)
 * The mock is ours; scripts/typecheck_figma.sh checks code.js against Figma's own typings.
 */
"use strict";
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const vm = require("vm");
const { spawnSync } = require("child_process");

const REPO = path.resolve(__dirname, "..");
const PLUGIN = path.join(REPO, "plugins/sdd-figma/figma-plugin");
const BUILD = path.join(REPO, "plugins/sdd-figma/skills/figma-export/scripts/build_bundle.py");
const DIAGRAMS = path.join(REPO, "plugins/sdd-diagrams/skills/feature-diagrams/scripts/sdd_diagrams.py");
const SPEC = path.join(REPO, "plugins/sdd-kit/skills/init-project/template/specs/EXAMPLE-001-password-reset/spec.md");
const SCREENS = path.join(REPO, "plugins/sdd-design/skills/prototype/references/example.screens.json");
const DASHBOARD = path.join(REPO, "plugins/sdd-design/skills/prototype/references/example.dashboard.screens.json");
const DS = path.join(REPO, "plugins/sdd-design/skills/design-system-init/starter/components.json");
const RENDER = path.join(REPO, "plugins/sdd-design/skills/prototype/scripts/render_prototype.py");
const sha1 = (buf) => crypto.createHash("sha1").update(buf).digest("hex");

let failed = 0, passed = 0;
function check(name, ok, detail) {
  if (ok) { passed++; console.log("  ok   " + name); }
  else { failed++; console.log("  FAIL " + name + (detail !== undefined ? " (" + detail + ")" : "")); }
}

function py(args) {
  const r = spawnSync("python3", ["-I"].concat(args), { encoding: "utf8" });
  return { code: r.status, out: (r.stdout || "") + (r.stderr || "") };
}

// ------------------------------------------------------------------ strict Figma mock

function createMock(opts) {
  opts = opts || {};
  let seq = 0;
  const nodes = new Map();
  const log = { reactions: [], bound: [], paintBound: 0, ui: [], notify: [], closed: false, svg: 0, showUI: null, removed: 0 };
  const avail = opts.fonts || [
    ["Inter", "Regular"], ["Inter", "Medium"], ["Inter", "Semi Bold"], ["Inter", "Bold"],
    ["Roboto", "Regular"], ["Roboto", "Medium"], ["Roboto", "Bold"]
  ];
  const availSet = new Set(avail.map((f) => f[0] + "|" + f[1]));
  const loaded = new Set();
  const fkey = (f) => f && f.family + "|" + f.style;
  const BINDABLE = new Set(["width", "height", "itemSpacing", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
    "topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius", "strokeWeight", "minWidth", "maxWidth",
    "minHeight", "maxHeight", "counterAxisSpacing", "opacity", "visible", "characters"]);
  const isAuto = (n) => !!n && (n.type === "FRAME" || n.type === "COMPONENT" || n.type === "INSTANCE") && !!n.layoutMode && n.layoutMode !== "NONE";
  const CONSTRAINT = ["MIN", "CENTER", "MAX", "STRETCH", "SCALE"];
  let allLoaded = false;
  let current = null;
  const pages = [];
  const variables = new Map();
  const collections = [];
  const mixed = Symbol("mixed");

  class Node {
    constructor(type) {
      this.id = (++seq) + ":" + (seq * 7 % 100);
      this.type = type; this.name = type; this.parent = null; this.removed = false;
      this._pd = {}; this.x = 0; this.y = 0; this.width = 100; this.height = 100;
      this.fills = []; this.strokes = []; this._reactions = [];
      nodes.set(this.id, this);
    }
    setPluginData(k, v) { if (typeof v !== "string") throw new Error("setPluginData: value must be a string"); this._pd[k] = v; }
    getPluginData(k) { return this._pd[k] || ""; }
    resize(w, h) {
      if (!(w >= 0.01 && h >= 0.01)) throw new Error("resize: invalid size " + w + "x" + h);
      this.width = w; this.height = h;
    }
    remove() {
      if (this.parent) { const kids = this.parent._kids; const i = kids.indexOf(this); if (i >= 0) kids.splice(i, 1); }
      this.parent = null;
      log.removed++;
      const kill = (n) => { n.removed = true; (n._kids || []).forEach(kill); };
      kill(this);
    }
    get layoutPositioning() { return this._pos || "AUTO"; }
    set layoutPositioning(v) {
      if (v !== "AUTO" && v !== "ABSOLUTE") throw new Error("layoutPositioning: invalid value " + v);
      if (v === "ABSOLUTE" && !isAuto(this.parent)) throw new Error("layoutPositioning ABSOLUTE on '" + this.name + "': parent is not an auto-layout frame");
      this._pos = v;
    }
    get constraints() { return this._con || { horizontal: "MIN", vertical: "MIN" }; }
    set constraints(c) {
      if (!c || CONSTRAINT.indexOf(c.horizontal) < 0 || CONSTRAINT.indexOf(c.vertical) < 0) throw new Error("constraints: invalid value " + JSON.stringify(c));
      this._con = { horizontal: c.horizontal, vertical: c.vertical };
    }
    _sizing(axis, v) {
      if (["FIXED", "HUG", "FILL"].indexOf(v) < 0) throw new Error("layoutSizing" + axis + ": invalid value " + v);
      if (v !== "FIXED" && !isAuto(this.parent)) throw new Error("layoutSizing" + axis + " = " + v + " on '" + this.name + "': parent is not an auto-layout frame");
      if (v === "FILL" && this._pos === "ABSOLUTE") throw new Error("FILL is not valid on an absolutely positioned child ('" + this.name + "')");
      if (v === "HUG" && !(this.type === "TEXT" || isAuto(this))) throw new Error("HUG is only valid on auto-layout frames and text ('" + this.name + "')");
      this["_ls" + axis] = v;
    }
    get layoutSizingHorizontal() { return this._lsHorizontal || "FIXED"; }
    set layoutSizingHorizontal(v) { this._sizing("Horizontal", v); }
    get layoutSizingVertical() { return this._lsVertical || "FIXED"; }
    set layoutSizingVertical(v) { this._sizing("Vertical", v); }
    setBoundVariable(field, variable) {
      if (!variable || typeof variable !== "object" || !variables.has(variable.id)) throw new Error("setBoundVariable: expected a Variable object");
      if (!BINDABLE.has(field)) throw new Error("setBoundVariable: field " + field + " is not bindable on " + this.type);
      this.boundVariables = this.boundVariables || {};
      this.boundVariables[field] = { type: "VARIABLE_ALIAS", id: variable.id };
      log.bound.push({ node: this.id, field: field, id: variable.id });
    }
    get reactions() { return this._reactions; }
    set reactions(v) { throw new Error("Cannot set reactions with documentAccess: dynamic-page. Use setReactionsAsync."); }
    async setReactionsAsync(rs) {
      if (!Array.isArray(rs)) throw new Error("reactions must be an array");
      for (const r of rs) {
        if (!r.trigger || r.trigger.type !== "ON_CLICK") throw new Error("unexpected trigger");
        if (!Array.isArray(r.actions) || r.action !== undefined) throw new Error("expected 'actions' array");
        for (const a of r.actions) {
          if (a.type !== "NODE" || a.navigation !== "NAVIGATE") throw new Error("unexpected action");
          const dest = nodes.get(a.destinationId);
          if (!dest || dest.removed) throw new Error("destination " + a.destinationId + " does not exist");
        }
      }
      this._reactions = rs;
      log.reactions.push({ node: this, reactions: rs });
    }
  }

  class Container extends Node {
    constructor(type) { super(type); this._kids = []; }
    get children() { return this._kids.slice(); }
    appendChild(c) {
      if (!(c instanceof Node)) throw new Error("appendChild: not a node");
      if (c === this) throw new Error("appendChild: cycle");
      if (c.type === "SECTION" && this.type !== "PAGE" && this.type !== "SECTION") throw new Error("A section can only be placed on a page or in another section");
      if (c.type === "PAGE") throw new Error("appendChild: a page cannot be a child");
      if (c.parent) { const k = c.parent._kids; k.splice(k.indexOf(c), 1); }
      this._kids.push(c); c.parent = this;
    }
    findAll(fn) {
      const out = [];
      const walk = (n) => { (n._kids || []).forEach((c) => { if (!fn || fn(c)) out.push(c); walk(c); }); };
      walk(this); return out;
    }
    findAllWithCriteria(c) { return this.findAll((n) => c.types.indexOf(n.type) >= 0); }
  }

  class Frame extends Container {
    constructor(type) {
      super(type || "FRAME");
      this.layoutMode = "NONE"; this.fills = [{ type: "SOLID", color: { r: 1, g: 1, b: 1 } }];
      this.itemSpacing = 0; this.paddingTop = 0; this.paddingRight = 0; this.paddingBottom = 0; this.paddingLeft = 0;
      this.primaryAxisSizingMode = "AUTO"; this.counterAxisSizingMode = "AUTO";
      this.primaryAxisAlignItems = "MIN"; this.counterAxisAlignItems = "MIN"; this.clipsContent = true; this.cornerRadius = 0;
      this.layoutGrow = 0;
    }
    get minHeight() { return this._minH === undefined ? null : this._minH; }
    set minHeight(v) {
      if (!isAuto(this) && !isAuto(this.parent)) throw new Error("minHeight needs auto layout");
      this._minH = v;
    }
    resizeWithoutConstraints(w, h) { Node.prototype.resize.call(this, w, h); }
  }

  // Sections: children keep coordinates relative to the section; no auto layout, no resize constraints.
  class Section extends Container {
    constructor() { super("SECTION"); this.fills = []; this.sectionContentsHidden = false; }
    resize(w, h) { this.resizeWithoutConstraints(w, h); }
    resizeWithoutConstraints(w, h) { Node.prototype.resize.call(this, w, h); }
  }

  class Ellipse extends Node {
    constructor() { super("ELLIPSE"); this._arc = { startingAngle: 0, endingAngle: 2 * Math.PI, innerRadius: 0 }; }
    get arcData() { return this._arc; }
    set arcData(a) {
      if (!a || ["startingAngle", "endingAngle", "innerRadius"].some((k) => typeof a[k] !== "number" || !isFinite(a[k])) || a.innerRadius < 0 || a.innerRadius > 1) {
        throw new Error("arcData: expected { startingAngle, endingAngle, innerRadius 0..1 }");
      }
      this._arc = { startingAngle: a.startingAngle, endingAngle: a.endingAngle, innerRadius: a.innerRadius };
    }
  }

  class Vector extends Node {
    constructor() { super("VECTOR"); this._paths = []; this.strokeWeight = 1; this.strokeJoin = "MITER"; }
    get vectorPaths() { return this._paths; }
    set vectorPaths(v) {
      if (!Array.isArray(v) || v.some((p) => !p || ["NONZERO", "EVENODD", "NONE"].indexOf(p.windingRule) < 0 || typeof p.data !== "string" || !/^\s*M/.test(p.data))) {
        throw new Error("vectorPaths: expected [{ windingRule, data: 'M …' }]");
      }
      this._paths = v.slice();
    }
    get vectorNetwork() { return {}; }
    set vectorNetwork(v) { throw new Error("vectorNetwork is read-only with documentAccess: dynamic-page; use setVectorNetworkAsync"); }
  }

  class Text extends Node {
    constructor() {
      super("TEXT");
      this._font = { family: "Inter", style: "Regular" }; this._chars = ""; this._size = 12; this._tar = "WIDTH_AND_HEIGHT";
      this.fills = [{ type: "SOLID", color: { r: 0, g: 0, b: 0 } }]; this.textAlignHorizontal = "LEFT";
    }
    _need(what) { if (!loaded.has(fkey(this._font))) throw new Error("Cannot " + what + ": font " + fkey(this._font) + " is not loaded"); }
    get fontName() { return this._font; }
    set fontName(f) { if (!loaded.has(fkey(f))) throw new Error("set fontName: font " + fkey(f) + " is not loaded"); this._font = { family: f.family, style: f.style }; this._layout(); }
    get characters() { return this._chars; }
    set characters(s) { this._need("set characters"); if (typeof s !== "string") throw new Error("characters must be a string"); this._chars = s; this._layout(); }
    get fontSize() { return this._size; }
    set fontSize(v) { this._need("set fontSize"); if (!(v >= 1)) throw new Error("bad fontSize"); this._size = v; this._layout(); }
    get textAutoResize() { return this._tar; }
    set textAutoResize(v) { this._need("set textAutoResize"); this._tar = v; this._layout(); }
    get textDecoration() { return this._dec || "NONE"; }
    set textDecoration(v) { this._need("set textDecoration"); this._dec = v; }
    setRangeFontName(s, e, f) { this._need("setRangeFontName"); if (!loaded.has(fkey(f))) throw new Error("range font not loaded"); }
    setRangeFontSize(s, e, v) { this._need("setRangeFontSize"); }
    setRangeFills(s, e, v) { this._need("setRangeFills"); }
    getRangeAllFontNames() { return [this._font]; }
    resize(w, h) { super.resize(w, h); if (this._tar === "WIDTH_AND_HEIGHT") this._tar = "NONE"; this._layout(); }
    setBoundVariable(field, variable) {
      if (field === "fontSize") { this._need("bind fontSize"); this.boundVariables = this.boundVariables || {}; this.boundVariables.fontSize = { type: "VARIABLE_ALIAS", id: variable.id }; log.bound.push({ node: this.id, field: field, id: variable.id }); return; }
      super.setBoundVariable(field, variable);
    }
    _layout() {
      const lines = this._chars.split("\n"), cw = this._size * 0.55, lh = this._size * 1.25;
      if (this._tar === "WIDTH_AND_HEIGHT") {
        this.width = Math.max(1, Math.max.apply(null, lines.map((l) => l.length)) * cw);
        this.height = lines.length * lh;
      } else if (this._tar === "HEIGHT") {
        const per = Math.max(1, Math.floor(this.width / cw));
        this.height = lines.reduce((n, l) => n + Math.max(1, Math.ceil(l.length / per)), 0) * lh;
      }
    }
  }

  class Page extends Container {
    constructor(name) { super("PAGE"); this.name = name; this._loaded = false; this._flow = []; }
    get children() {
      if (!this._loaded && !allLoaded && current !== this) throw new Error("Page '" + this.name + "' is not loaded; call loadAsync()");
      return this._kids.slice();
    }
    async loadAsync() { this._loaded = true; }
    appendChild(c) {
      if (!this._loaded && !allLoaded && current !== this) throw new Error("Page '" + this.name + "' is not loaded; call loadAsync()");
      super.appendChild(c);
    }
    get flowStartingPoints() { return this._flow; }
    set flowStartingPoints(v) {
      for (const p of v) {
        const n = nodes.get(p.nodeId);
        if (!n || n.parent !== this || n.type !== "FRAME") throw new Error("flow starting point must be a top-level frame on the page");
        if (typeof p.name !== "string") throw new Error("flow name must be a string");
      }
      this._flow = v.slice();
    }
  }

  function onPage(n) { current._kids.push(n); n.parent = current; return n; }

  const first = new Page("Page 1");
  first._loaded = true;
  pages.push(first);
  current = first;
  const userRect = onPage(new Node("RECTANGLE"));
  userRect.name = "User drawing";

  // ---- library (component sets by key)
  function makeLibrarySet(key) {
    const set = new Container("COMPONENT_SET");
    set.name = "Button";
    set.componentPropertyDefinitions = {
      Variant: { type: "VARIANT", defaultValue: "Primary", variantOptions: ["Primary", "Secondary", "Ghost", "Danger"] },
      "Label#12:0": { type: "TEXT", defaultValue: "Button" }
    };
    const comp = new Frame("COMPONENT");
    comp.layoutMode = "HORIZONTAL";
    comp.name = "Variant=Primary";
    set.appendChild(comp);
    comp.createInstance = function () {
      const inst = new Frame("INSTANCE");
      inst.layoutMode = "HORIZONTAL";
      inst.name = "Button";
      inst.componentProperties = { Variant: { type: "VARIANT", value: "Primary" }, "Label#12:0": { type: "TEXT", value: "Button" } };
      const label = new Text();
      label._font = { family: "Inter", style: "Medium" };
      inst.appendChild(label);
      inst.setProperties = function (props) {
        for (const k of Object.keys(props)) {
          const def = set.componentPropertyDefinitions[k];
          if (!def) throw new Error("Unknown component property " + k);
          if (def.type === "VARIANT" && def.variantOptions.indexOf(props[k]) < 0) throw new Error("Invalid variant value " + props[k]);
          if (def.type === "TEXT") { if (!loaded.has(fkey(label._font))) throw new Error("Font " + fkey(label._font) + " not loaded"); label._chars = props[k]; }
          inst.componentProperties[k].value = props[k];
        }
      };
      return onPage(inst);
    };
    set.defaultVariant = comp;
    log.library = (log.library || 0) + 1;
    return set;
  }
  const libraryKeys = opts.libraryKeys || {};

  const variablesApi = {
    async getLocalVariableCollectionsAsync() { return collections.slice(); },
    async getLocalVariablesAsync(type) { return Array.from(variables.values()).filter((v) => !type || v.resolvedType === type); },
    getLocalVariables() { throw new Error("getLocalVariables is not supported with dynamic-page"); },
    getLocalVariableCollections() { throw new Error("getLocalVariableCollections is not supported with dynamic-page"); },
    createVariableCollection(name) {
      const id = "VariableCollectionId:" + (++seq);
      const c = {
        id: id, name: name, modes: [{ modeId: id + "/m0", name: "Mode 1" }],
        renameMode(modeId, n) { const m = this.modes.find((x) => x.modeId === modeId); if (!m) throw new Error("no mode"); m.name = n; }
      };
      c.defaultModeId = c.modes[0].modeId;
      collections.push(c);
      return c;
    },
    createVariable(name, collection, type) {
      if (!collection || typeof collection !== "object" || collections.indexOf(collection) < 0) throw new Error("createVariable: expected a VariableCollection");
      if (/[.{}]/.test(name)) throw new Error("Invalid variable name " + name);
      if (["COLOR", "FLOAT", "STRING", "BOOLEAN"].indexOf(type) < 0) throw new Error("bad type " + type);
      for (const v of variables.values()) if (v.variableCollectionId === collection.id && v.name === name) throw new Error("duplicate variable name " + name);
      const v = {
        id: "VariableID:" + (++seq), name: name, resolvedType: type, variableCollectionId: collection.id,
        valuesByMode: {}, scopes: ["ALL_SCOPES"], codeSyntax: {}, description: "",
        setValueForMode(modeId, value) {
          if (!collection.modes.some((m) => m.modeId === modeId)) throw new Error("bad mode");
          if (type === "COLOR" && !(value && typeof value.r === "number" && typeof value.g === "number" && typeof value.b === "number")) throw new Error("COLOR needs {r,g,b}");
          if (type === "FLOAT" && typeof value !== "number") throw new Error("FLOAT needs a number");
          this.valuesByMode[modeId] = value;
        },
        setVariableCodeSyntax(platform, s) { this.codeSyntax[platform] = s; }
      };
      variables.set(v.id, v);
      return v;
    },
    setBoundVariableForPaint(paint, field, variable) {
      if (field !== "color" || !paint || paint.type !== "SOLID" || !variable || !variables.has(variable.id)) throw new Error("setBoundVariableForPaint: bad arguments");
      log.paintBound++;
      return Object.assign({}, paint, { boundVariables: { color: { type: "VARIABLE_ALIAS", id: variable.id } } });
    }
  };

  const figma = {
    mixed: mixed,
    root: { type: "DOCUMENT", get children() { return pages.slice(); } },
    get currentPage() { return current; },
    set currentPage(p) { throw new Error("Setting figma.currentPage is not supported with dynamic-page; use setCurrentPageAsync"); },
    async setCurrentPageAsync(p) { if (!(p instanceof Page)) throw new Error("not a page"); current = p; p._loaded = true; },
    async loadAllPagesAsync() { allLoaded = true; },
    createPage() { const p = new Page("Page " + (pages.length + 1)); pages.push(p); return p; },
    createFrame() { return onPage(new Frame()); },
    createText() { return onPage(new Text()); },
    createRectangle() { return onPage(new Node("RECTANGLE")); },
    createEllipse() { return onPage(new Ellipse()); },
    createVector() { return onPage(new Vector()); },
    createSection() { return onPage(new Section()); },
    createNodeFromSvg(svg) {
      if (typeof svg !== "string" || !/^\s*<svg[\s>]/.test(svg) || !/<\/svg>\s*$/.test(svg)) throw new Error("Failed to parse SVG");
      const f = new Frame();
      f.name = "svg"; f.fromSvg = true; f.fills = [];
      const w = /\swidth="([\d.]+)"/.exec(svg), h = /\sheight="([\d.]+)"/.exec(svg);
      f.width = w ? parseFloat(w[1]) : 100; f.height = h ? parseFloat(h[1]) : 100;
      log.svg++;
      return onPage(f);
    },
    async loadFontAsync(f) { if (!availSet.has(fkey(f))) throw new Error("The font \"" + f.family + " " + f.style + "\" could not be loaded"); loaded.add(fkey(f)); },
    async listAvailableFontsAsync() { return avail.map((f) => ({ fontName: { family: f[0], style: f[1] } })); },
    async importComponentSetByKeyAsync(key) { if (libraryKeys[key] !== "set") throw new Error("Component set not found for key " + key); return makeLibrarySet(key); },
    async importComponentByKeyAsync(key) { throw new Error("Component not found for key " + key); },
    showUI(html, o) { log.showUI = { html: html, opts: o }; },
    ui: { onmessage: null, postMessage(m) { log.ui.push(m); }, resize() {} },
    notify(t) { log.notify.push(t); return { cancel() {} }; },
    closePlugin() { log.closed = true; },
    viewport: { scrollAndZoomIntoView() {} },
    variables: opts.noVariables ? undefined : variablesApi
  };
  return { figma, log, pages, nodes, variables, collections, userRect, loaded };
}

function loadPlugin(mock) {
  const code = fs.readFileSync(path.join(PLUGIN, "code.js"), "utf8");
  const context = vm.createContext({ figma: mock.figma, __html__: "<html>ui</html>", console: console });
  vm.runInContext(code, context, { filename: "code.js" });
  return context;
}

async function runBuild(mock, bundle) {
  const before = mock.log.ui.length;
  const ret = mock.figma.ui.onmessage({ type: "build", bundle: bundle }, { origin: "null" });
  await Promise.resolve(ret);
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    const m = mock.log.ui.slice(before).find((x) => x.type === "done" || x.type === "error");
    if (m) return m;
    await new Promise((r) => setTimeout(r, 10));
  }
  throw new Error("build did not finish");
}

const role = (n, r) => n.getPluginData("sdd") === "generated" && n.getPluginData("sddRole") === r;
const isGen = (n) => n.getPluginData("sdd") === "generated";
const pageNamed = (mock, name) => mock.pages.filter((p) => p.name === name);
const allIn = (node) => node.findAll ? node.findAll(() => true) : [];

// ------------------------------------------------------------------ tests

async function main() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "sdd-figma-test-"));
  try {
    console.log("build_bundle.py");
    const feat = path.join(tmp, "EXAMPLE-001");
    fs.mkdirSync(path.join(feat, "design"), { recursive: true });
    let r = py([DIAGRAMS, "build", SPEC, "--out", path.join(feat, "diagrams")]);
    check("sdd_diagrams build exits 0", r.code === 0, r.out.slice(-300));
    fs.copyFileSync(SCREENS, path.join(feat, "design", "screens.json"));
    fs.copyFileSync(SPEC, path.join(feat, "spec.md"));
    r = py([BUILD, feat, "--ds", DS]);
    check("build_bundle exits 0", r.code === 0, r.out.slice(-400));
    check("build_bundle prints a one-line summary", /\[OK\] EXAMPLE-001: 3 diagram\(s\), 5 screen\(s\)/.test(r.out), r.out.trim().split("\n").pop());
    const bundlePath = path.join(feat, "figma", "bundle.json");
    const bundle = JSON.parse(fs.readFileSync(bundlePath, "utf8"));
    check("bundle version/feature", bundle.version === 1 && bundle.feature === "EXAMPLE-001", bundle.feature);
    check("bundle has 3 diagrams with SVG + sha1", bundle.diagrams.length === 3 && bundle.diagrams.every((d) => /^<svg/.test(d.svg) && d.sha1));
    check("arrowhead markers are inlined", bundle.diagrams.every((d) => d.svg.indexOf("marker-end=") < 0));
    check("bundle has 5 screens and 5 flows", bundle.screens.screens.length === 5 && bundle.screens.flows.length === 5);
    check("tokens resolved and flat", bundle.tokens["color.primary"] === "#4338ca" && bundle.tokens["space.4"] === 16 &&
      bundle.tokens["font.family.sans"] === "Inter, system-ui, sans-serif", JSON.stringify(bundle.tokens["color.primary"]));
    check("designSystem metadata", bundle.designSystem && bundle.designSystem.name === "my-design-system" && bundle.designSystem.version === "0.1.0");
    check("no validation warnings on the example", bundle.warnings.length === 0, bundle.warnings.join(" | "));
    const src = bundle.sources || {};
    const manifest1 = JSON.parse(fs.readFileSync(path.join(feat, "diagrams", "manifest.json"), "utf8"));
    check("sources: sha1 of spec.md and screens.json", src.spec && src.spec.sha1 === sha1(fs.readFileSync(path.join(feat, "spec.md"))) &&
      src.screens && src.screens.sha1 === sha1(fs.readFileSync(path.join(feat, "design", "screens.json"))), JSON.stringify(src).slice(0, 200));
    check("sources: one full sha1 per diagram source, prefixed by the manifest's sha1", Array.isArray(src.diagrams) && src.diagrams.length === 3 &&
      src.diagrams.every((d, i) => /^[0-9a-f]{40}$/.test(d.sha1) && d.sha1.indexOf(manifest1.diagrams[i].sha1) === 0 && d.path === "diagrams/" + d.name + ".mmd"),
      JSON.stringify(src.diagrams));

    const proj = path.join(tmp, "proj");
    const feat2 = path.join(proj, "specs", "EXAMPLE-001");
    fs.mkdirSync(path.join(feat2, "design"), { recursive: true });
    fs.writeFileSync(path.join(proj, "CLAUDE.md"), "# Project\n- Design system: " + DS + " (starter, light theme)\n");
    const bad = JSON.parse(fs.readFileSync(SCREENS, "utf8"));
    bad.screens[0].body.children[0].children.push({ type: "Carousel" }, { type: "Button", variant: "huge", label: "X", link: "nowhere" });
    fs.writeFileSync(path.join(feat2, "design", "screens.json"), JSON.stringify(bad));
    r = py([BUILD, feat2, "--theme", "dark", "--out", path.join(tmp, "b2.json")]);
    const b2 = r.code === 0 ? JSON.parse(fs.readFileSync(path.join(tmp, "b2.json"), "utf8")) : null;
    check("design system found via CLAUDE.md, theme applied", b2 && b2.designSystem.name === "my-design-system" && b2.designSystem.theme === "dark", r.out.slice(-300));
    check("unknown type/variant/link are warned", b2 && ["Carousel", "huge", "nowhere"].every((w) => b2.warnings.some((x) => x.indexOf(w) >= 0)) &&
      /\[WARN\].*Carousel/.test(r.out), b2 && b2.warnings.join(" | "));
    check("missing diagrams are warned, not fatal", b2 && b2.warnings.some((x) => x.indexOf("feature-diagrams") >= 0));
    fs.mkdirSync(path.join(tmp, "EMPTY-1"));
    r = py([BUILD, path.join(tmp, "EMPTY-1"), "--ds", DS]);
    check("nothing to export exits 1", r.code === 1, r.code);

    console.log("figma-plugin/manifest.json + code.js");
    const manifest = JSON.parse(fs.readFileSync(path.join(PLUGIN, "manifest.json"), "utf8"));
    check("manifest fields", manifest.id === "sdd-kit-import" && manifest.name === "SDD Kit Import" && manifest.api === "1.0.0" &&
      manifest.documentAccess === "dynamic-page" && manifest.editorType.join() === "figma" &&
      manifest.networkAccess.allowedDomains.join() === "none" && manifest.main === "code.js" && manifest.ui === "ui.html");
    const code = fs.readFileSync(path.join(PLUGIN, "code.js"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
    check("code.js has no ?. or ??", !/\?\.(?!\d)/.test(code) && code.indexOf("??") < 0);

    // Run 1 + 2: plain bundle, idempotency
    const mock = createMock();
    loadPlugin(mock);
    check("showUI(__html__, 400x560)", mock.log.showUI && mock.log.showUI.html === "<html>ui</html>" && mock.log.showUI.opts.width === 400 && mock.log.showUI.opts.height === 560);
    let res = await runBuild(mock, bundle);
    check("run 1 finished without error", res.type === "done", res.text);
    const report = res.report || {};
    const dName = "EXAMPLE-001 · How it works", sName = "EXAMPLE-001 · Screens";
    let dPages = pageNamed(mock, dName), sPages = pageNamed(mock, sName);
    check("2 generated pages with expected names", dPages.length === 1 && sPages.length === 1 &&
      dPages[0].getPluginData("sdd") === "generated" && sPages[0].getPluginData("sdd") === "generated");
    const dPage = dPages[0], sPage = sPages[0];
    const dFrames = dPage.children.filter((n) => role(n, "diagram"));
    check("3 diagram frames from SVG, named after titles", dFrames.length === 3 && dFrames.every((f) => f.fromSvg) &&
      dFrames.map((f) => f.name).join() === "Flow,Sequence,State", dFrames.map((f) => f.name).join());
    check("each diagram has a heading above it", dPage.children.filter((n) => role(n, "diagram-heading")).length === 3 &&
      dFrames.every((f, i) => i === 0 || f.y > dFrames[i - 1].y + dFrames[i - 1].height + 119));
    const screens = sPage.children.filter((n) => role(n, "screen"));
    check("5 screen frames with auto layout, width 1280, min height 800", screens.length === 5 &&
      screens.every((f) => f.layoutMode === "VERTICAL" && f.width === 1280 && f.minHeight === 800 && f.primaryAxisSizingMode === "AUTO"),
      screens.map((f) => f.layoutMode + "/" + f.width).join());
    check("screen frames named '<id> — <title>', left to right with 160 px gap", screens[0].name === "enter-email — Enter email" &&
      screens.every((f, i) => f.x === i * (1280 + 160)));
    const anns = sPage.children.filter((n) => role(n, "annotation"));
    check("annotation above each frame", anns.length === 5 && anns[1].characters.indexOf("check-inbox · success · AC-1, AC-2\nSame message") === 0 &&
      anns.every((a, i) => a.y + a.height <= screens[i].y), anns[1] && anns[1].characters);
    const screenIds = new Set(screens.map((f) => f.id));
    const links = mock.log.reactions.filter((x) => x.reactions[0].actions.every((a) => screenIds.has(a.destinationId)));
    check("at least 5 reactions to existing screen frames", links.length >= 5 && report.links >= 5, links.length);
    const byName = (n) => screens.find((f) => f.name.indexOf(n + " — ") === 0);
    const expired = links.find((x) => x.node.name === "Button / ghost" && x.reactions[0].actions[0].destinationId === byName("link-expired").id);
    check("ghost button on check-inbox links to link-expired", !!expired);
    check("flow starting point is the first screen", sPage.flowStartingPoints.length === 1 && sPage.flowStartingPoints[0].nodeId === screens[0].id);
    const col = mock.collections.filter((c) => c.name === "my-design-system tokens");
    const colorVars = Array.from(mock.variables.values()).filter((v) => v.resolvedType === "COLOR");
    check("variable collection with COLOR variables incl. color.primary", col.length === 1 && colorVars.some((v) => v.name === "color/primary"), colorVars.map((v) => v.name).join());
    const floatVars = Array.from(mock.variables.values()).filter((v) => v.resolvedType === "FLOAT").map((v) => v.name);
    check("FLOAT variables for space/radius/font.size", ["space/4", "radius/md", "font/size/body"].every((n) => floatVars.indexOf(n) >= 0) &&
      !floatVars.some((n) => /^(palette|scale|font\/weight)/.test(n)), floatVars.join());
    check("fills bound to colour variables", mock.log.paintBound > 20, mock.log.paintBound);
    const fields = new Set(mock.log.bound.map((b) => b.field));
    check("itemSpacing/padding/corner radii bound to variables", ["itemSpacing", "paddingTop", "paddingLeft", "topLeftRadius"].every((f) => fields.has(f)), Array.from(fields).join());
    const all = allIn(sPage);
    const names = all.map((n) => n.name);
    check("layers named after component types", ["Card", "Button / primary", "TextField / Email", "Alert / info", "Checkbox / Sign me out on other devices", "Link"].every((n) => names.indexOf(n) >= 0));
    const pw = all.find((n) => n.name === "TextField / New password");
    check("TextField draws label, 44 px input and hint", pw && pw.children.length === 3 && pw.children[1].height === 44 && pw.children[2].name === "Hint");
    const fullBtn = all.find((n) => n.name === "Button / primary");
    check("full Button fills its parent", fullBtn.layoutSizingHorizontal === "FILL");
    check("plugin stays open and notifies", !mock.log.closed && mock.log.notify.some((t) => t.indexOf("EXAMPLE-001") === 0));
    check("report counts drawn components", report.drawn && report.drawn.Button === 6 && report.drawn.Text === 8 && report.drawn.TextField === 3 && Object.keys(report.instanced).length === 0, JSON.stringify(report.drawn));
    check("clean example builds without warnings", report.warnings.length === 0, (report.warnings || []).join(" | "));
    const sha7 = src.spec.sha1.slice(0, 7);
    const caps = [dPage, sPage].map((p) => p.children.filter((n) => role(n, "caption")));
    check("each generated page has a 'Generated from spec <sha7> · <date>' caption above its content", caps.every((c, i) => c.length === 1 &&
      new RegExp("^Generated from spec " + sha7 + " · \\d{4}-\\d{2}-\\d{2}$").test(c[0].characters) && c[0].y + c[0].height < 0 &&
      [dPage, sPage][i].children.every((n) => n === c[0] || n.y >= 0)), caps.map((c) => c[0] && c[0].characters).join(" | "));
    check("pages carry the bundle's sources in pluginData", [dPage, sPage].every((p) => p.getPluginData("sddSources") === JSON.stringify(bundle.sources) &&
      p.getPluginData("sddSpecSha1") === src.spec.sha1) && report.specSha1 === src.spec.sha1);
    check("first run archives nothing", report.archived.layers === 0 && pageNamed(mock, "EXAMPLE-001 · Archive").length === 0, JSON.stringify(report.archived));

    const counts1 = [dPage, sPage].map((p) => p.children.length);
    const varCount1 = mock.variables.size;
    const run1 = { [dName]: dPage.children.slice(), [sName]: sPage.children.slice() };
    const run1All = run1[dName].concat(run1[sName]);
    const offsets = (list) => list.map((n) => (n.x - list[0].x) + "," + (n.y - list[0].y)).join(" ");
    const layout1 = [offsets(run1[dName]), offsets(run1[sName])];
    sPage.appendChild(Object.assign(mock.figma.createRectangle(), { name: "Designer note" }));
    screens[0].appendChild(Object.assign(mock.figma.createRectangle(), { name: "Designer tweak" }));
    screens[1].name = "check-inbox — renamed by a designer";
    const removed1 = mock.log.removed, ui1 = mock.log.ui.length;
    res = await runBuild(mock, bundle);
    check("run 2 finished without error", res.type === "done", res.text);
    dPages = pageNamed(mock, dName); sPages = pageNamed(mock, sName);
    check("run 2: no duplicate pages", dPages.length === 1 && sPages.length === 1 && dPages[0] === dPage && sPages[0] === sPage);
    const gen = (p) => p.children.filter((n) => n.getPluginData("sdd") === "generated").length;
    check("run 2: same number of top-level children per generated page", gen(dPage) === counts1[0] && gen(sPage) === counts1[1],
      [gen(dPage), gen(sPage)] + " vs " + counts1);
    check("run 2: user layers untouched", sPage.children.some((n) => n.name === "Designer note") && !mock.userRect.removed && mock.pages[0].children.length === 1);
    check("run 2: variables reused, not duplicated", mock.variables.size === varCount1 && mock.collections.length === 1 && res.report.variablesCreated === 0);
    const live = new Set(sPage.children.filter((n) => role(n, "screen")).map((f) => f.id));
    const live2 = mock.log.reactions.slice(-res.report.links).filter((x) => !x.node.removed && live.has(x.reactions[0].actions[0].destinationId));
    check("run 2: reactions point at the new frames", live2.length >= 5, live2.length);
    const aName = "EXAMPLE-001 · Archive";
    const aPages = pageNamed(mock, aName);
    check("run 2: deletes nothing", mock.log.removed === removed1 && run1All.every((n) => !n.removed), mock.log.removed - removed1);
    check("run 2: archive page created once and marked sdd=archive (not generated)", aPages.length === 1 &&
      aPages[0].getPluginData("sdd") === "archive" && mock.pages.indexOf(aPages[0]) > mock.pages.indexOf(sPage));
    const aPage = aPages[0];
    const runs = aPage ? aPage.children : [];
    const runRe = /^Run \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
    check("run 2: one 'Run <ISO date-time>' section holding one section per source page", runs.length === 1 && runs[0].type === "SECTION" &&
      runRe.test(runs[0].name) && runs[0].getPluginData("sdd") === "archive" &&
      runs[0].children.map((c) => c.type + ":" + c.name).join() === "SECTION:" + dName + ",SECTION:" + sName, runs.map((r) => r.name).join());
    const groups = runs.length ? runs[0].children : [];
    check("run 2: every earlier generated layer moved there, re-marked sdd=archived", groups.length === 2 &&
      [dName, sName].every((pn, i) => run1[pn].length === groups[i].children.length && run1[pn].every((n) => n.parent === groups[i] &&
        n.getPluginData("sdd") === "archived" && n.getPluginData("sddArchivedFrom") === pn && n.getPluginData("sddArchivedAt") + "" !== "")));
    check("run 2: archived layers keep their relative layout and fit their section", groups.length === 2 &&
      groups.every((g) => g.children.every((n) => n.x >= 0 && n.y >= 0 && n.x + n.width <= g.width && n.y + n.height <= g.height)) &&
      groups[1].x >= groups[0].x + groups[0].width && runs[0].width >= groups[1].x + groups[1].width &&
      offsets(run1[dName]) === layout1[0] && offsets(run1[sName]) === layout1[1], offsets(run1[sName]) + " vs " + layout1[1]);
    check("run 2: designer edits survive on the archive page", screens[0].children.some((n) => n.name === "Designer tweak") &&
      screens[1].name === "check-inbox — renamed by a designer" && allIn(aPage).indexOf(screens[0]) >= 0);
    check("run 2: generated pages hold only new layers", [dPage, sPage].every((p) => p.children.filter((n) => n.getPluginData("sdd") === "generated")
      .every((n) => run1All.indexOf(n) < 0)) && !isGen(aPage) && allIn(aPage).every((n) => n.getPluginData("sdd") !== "generated"));
    const ar = res.report.archived || {};
    check("run 2: report says how many layers were archived and where", ar.layers === run1All.length && ar.page === aName && ar.run === runs[0].name &&
      res.report.summary.indexOf(run1All.length + " earlier layer(s) archived to “" + aName + "” › " + runs[0].name) >= 0, res.report.summary);
    const logs2 = mock.log.ui.slice(ui1).filter((m) => m.type === "log").map((m) => m.text);
    check("run 2: the UI log names the archive for each page", [dName, sName].every((pn) => logs2.some((t) => t.indexOf("page “" + pn + "”; archived its " +
      run1[pn].length + " earlier generated layer(s) to “" + aName + "” › " + runs[0].name) >= 0)), logs2.join(" | "));

    // Another re-run: its Run section goes below the first one, which stays as it was
    const run2All = [dPage, sPage].reduce((a, p) => a.concat(p.children.filter(isGen)), []);
    const firstRun = runs[0], firstBox = { y: firstRun.y, h: firstRun.height, n: allIn(firstRun).length };
    res = await runBuild(mock, bundle);
    const runs3 = aPage.children;
    check("re-run: second Run section below the first, first unchanged", res.type === "done" && pageNamed(mock, aName).length === 1 &&
      runs3.length === 2 && runs3[0] === firstRun && runs3[1].y >= firstBox.y + firstBox.h && allIn(firstRun).length === firstBox.n &&
      run1All.every((n) => !n.removed && allIn(firstRun).indexOf(n) >= 0) && run2All.every((n) => allIn(runs3[1]).indexOf(n) >= 0),
      runs3.map((r) => r.name + "@" + r.y).join());

    // Run 3: library keys (one importable, one missing) fall back without crashing
    const libBundle = JSON.parse(JSON.stringify(bundle));
    libBundle.components.Button.figma = { key: "btn-set-key", variantProperty: "Variant", textProperty: "Label" };
    libBundle.components.Alert.figma = { key: "missing-key", variantProperty: "Tone", textProperty: "Title" };
    const mock3 = createMock({ libraryKeys: { "btn-set-key": "set" } });
    loadPlugin(mock3);
    res = await runBuild(mock3, libBundle);
    check("run 3 (library keys) finished without error", res.type === "done", res.text);
    const r3 = res.report || {};
    const s3 = pageNamed(mock3, sName)[0];
    const insts = allIn(s3).filter((n) => n.type === "INSTANCE");
    check("Button placed as library instances with variant + label", r3.instanced.Button === 6 && insts.length === 6 &&
      insts.some((i) => i.componentProperties.Variant.value === "Ghost") && insts.some((i) => i.componentProperties["Label#12:0"].value === "Send link"),
      JSON.stringify(r3.instanced));
    check("missing key falls back to drawing (no crash)", r3.drawn.Alert === 3 && r3.fallbacks.Alert === 3 &&
      r3.warnings.some((w) => w.indexOf("missing-key") >= 0) && allIn(s3).some((n) => n.name === "Alert / danger"));
    check("instances get prototype links", mock3.log.reactions.filter((x) => x.node.type === "INSTANCE").length >= 5);

    // Run 4: no Variables API, no Inter: Roboto + plain colours
    const mock4 = createMock({ noVariables: true, fonts: [["Roboto", "Regular"], ["Roboto", "Medium"], ["Roboto", "Bold"]] });
    loadPlugin(mock4);
    res = await runBuild(mock4, bundle);
    const s4 = res.type === "done" ? pageNamed(mock4, sName)[0] : null;
    check("run 4 (no variables, no Inter) builds with plain colours and Roboto", res.type === "done" && res.report.font === "Roboto" &&
      res.report.variables === 0 && mock4.log.paintBound === 0 && s4.children.filter((n) => role(n, "screen")).length === 5, res.text || (res.report && res.report.font));

    // Run 5: only an odd font: falls back to the first available font
    const mock5 = createMock({ fonts: [["Comic Neue", "Light"]] });
    loadPlugin(mock5);
    res = await runBuild(mock5, bundle);
    check("run 5 falls back to the first available font", res.type === "done" && res.report.font === "Comic Neue", res.text);

    // Run 6: the dashboard example exercises Table, Modal, Tabs, Pagination, Progress and Chart
    console.log("dashboard example (new components)");
    const dash = path.join(tmp, "DASH-1");
    fs.mkdirSync(path.join(dash, "design"), { recursive: true });
    fs.copyFileSync(DASHBOARD, path.join(dash, "design", "screens.json"));
    r = py([BUILD, dash, "--ds", DS]);
    const db = r.code === 0 ? JSON.parse(fs.readFileSync(path.join(dash, "figma", "bundle.json"), "utf8")) : null;
    check("build_bundle accepts the dashboard (only the missing-diagrams warning)", db && db.screens.screens.length === 3 &&
      db.warnings.length === 1 && db.warnings[0].indexOf("diagrams") >= 0 && db.sources.spec === null && db.sources.screens.sha1 === sha1(fs.readFileSync(DASHBOARD)),
      db ? db.warnings.join(" | ") : r.out.slice(-300));
    const mock7 = createMock();
    loadPlugin(mock7);
    res = await runBuild(mock7, db);
    const r7 = res.report || {};
    check("dashboard builds; its only warning is the bundle's", res.type === "done" && r7.warnings.length === 1 && r7.warnings[0].indexOf("bundle: ") === 0,
      res.text || (r7.warnings || []).join(" | "));
    check("new components are drawn, none as placeholders", r7.drawn && r7.drawn.Table === 2 && r7.drawn.Modal === 1 && r7.drawn.Tabs === 3 &&
      r7.drawn.Pagination === 2 && r7.drawn.Progress === 2 && r7.drawn.Chart === 3 && !allIn(pageNamed(mock7, "EXAMPLE-002 · Screens")[0]).some((n) => /^Unknown/.test(n.name)),
      JSON.stringify(r7.drawn));
    const s7 = pageNamed(mock7, "EXAMPLE-002 · Screens")[0];
    const f7 = s7.children.filter((n) => role(n, "screen"));
    const frame7 = (id) => f7.find((f) => f.getPluginData("sddScreen") === id);
    const all7 = allIn(s7), named = (re, under) => allIn(under || s7).filter((n) => re.test(n.name));
    const varOf = (paint) => paint && paint.boundVariables ? Array.from(mock7.variables.values()).find((v) => v.id === paint.boundVariables.color.id) : null;
    const table = named(/^Table \/ 5 columns$/, frame7("invoices"))[0];
    const head = table && table.children[0];
    check("Table: header + one frame per row, select column, sort markers, badge cells", table && table.children.length === 7 &&
      head.name === "Header" && head.children[0].name === "Select" && head.children.length === 6 &&
      named(/^Sort$/, head).length === 3 && named(/^Badge \/ danger$/, table.children[2]).length === 1 &&
      table.children.slice(1).every((row) => row.layoutSizingHorizontal === "FILL" && row.children.slice(1).every((c) => c.layoutSizingHorizontal === "FILL")),
      table && table.children.map((c) => c.name + ":" + c.children.length).join());
    check("Table: selected row and header use semantic colour variables", table && varOf(table.children[2].fills[0]).name === "color/primary-subtle" &&
      varOf(head.fills[0]).name === "color/surface-2" && named(/^Check$/, table.children[2]).length === 1 && named(/^Check$/, table.children[1]).length === 0);
    const modal = all7.find((n) => /^Modal \//.test(n.name));
    const confirmF = frame7("confirm-delete");
    check("Modal: absolute scrim over the whole screen, stretched, overlay colour", modal && modal.parent === confirmF &&
      modal.layoutPositioning === "ABSOLUTE" && modal.constraints.horizontal === "STRETCH" && modal.constraints.vertical === "STRETCH" &&
      modal.width === confirmF.width && modal.height === confirmF.height && varOf(modal.fills[0]).name === "color/overlay" &&
      confirmF.children[confirmF.children.length - 1] === modal, modal && modal.name);
    const dialog = modal && modal.children[0];
    const acts = dialog && dialog.children.find((n) => n.name === "Actions");
    const toId = (n) => { const x = mock7.log.reactions.filter((e) => e.node === n).pop(); return x ? x.reactions[0].actions[0].destinationId : null; };
    check("Modal: dialog with title, body and action buttons linked to their screens", dialog && dialog.name === "Dialog" &&
      dialog.children[0].characters === "Delete invoice INV-1047?" && acts && acts.children.length === 2 &&
      acts.children.every((b) => /^Button \//.test(b.name) && toId(b) === frame7("invoices").id) && dialog.width === 480);
    const tabOn = named(/^Tab \/ Overview$/, frame7("overview"))[0], tabInv = named(/^Tab \/ Invoices$/, frame7("overview"))[0];
    check("Tabs: active tab underlined in primary, other tabs link to their screens", tabOn && tabOn.strokeBottomWeight === 2 &&
      varOf(tabOn.strokes[0]).name === "color/primary" && toId(tabInv) === frame7("invoices").id && toId(tabOn) === null &&
      toId(named(/^Tab \/ Overview$/, frame7("invoices"))[0]) === frame7("overview").id);
    const pg = named(/^Pagination \/ 2 of 8$/, frame7("invoices"))[0];
    check("Pagination: previous, 1 2 3 … 8, next; current page filled", pg && pg.children.map((c) => c.type === "TEXT" ? c.characters : c.children[0].characters).join(" ") ===
      "‹ Previous 1 2 3 … 8 Next ›" && varOf(pg.children[2].fills[0]).name === "color/primary" && pg.children[1].fills.length === 0,
      pg && pg.children.map((c) => c.name).join());
    const pr = named(/^Progress \/ Invoices sent/, frame7("overview"))[0];
    const track = pr && pr.children.find((n) => n.name === "Track"), bar = track && track.children[0];
    check("Progress: track fills its parent, bar is value % of it and scales with it", track && track.layoutSizingHorizontal === "FILL" && track.height === 8 &&
      bar && bar.width === track.width * 0.72 && bar.constraints.horizontal === "SCALE" && varOf(bar.fills[0]).name === "color/primary" &&
      pr.children[0].children.map((t) => t.characters).join("|") === "Invoices sent (720 of 1,000)|72%");
    const plot = (kind) => { const c = named(new RegExp("^Chart / " + kind + "$"), frame7("overview"))[0]; return c && c.children.find((n) => n.name === "Plot"); };
    const bars = plot("bar"), linePlot = plot("line"), piePlot = plot("pie");
    check("Chart: labelled placeholders (bars, a vector line, a donut) in token colours", bars && bars.children.length === 6 &&
      bars.children.every((b) => b.type === "RECTANGLE" && b.layoutSizingHorizontal === "FILL") &&
      linePlot && linePlot.children[0].type === "VECTOR" && /^M /.test(linePlot.children[0].vectorPaths[0].data) && linePlot.children[0].layoutSizingVertical === "FILL" &&
      piePlot && piePlot.children[0].children.length === 2 && piePlot.children[0].children.every((e) => e.type === "ELLIPSE" && e.arcData.innerRadius === 0.55) &&
      named(/^Note$/, frame7("overview")).every((t) => /^Placeholder: (bar|line|pie) chart, not real data$/.test(t.characters)));
    check("dashboard flows are all linked (tabs, buttons, modal actions)", r7.links >= 6 && !r7.warnings.some((w) => /^Flow /.test(w)), r7.links);
    check("caption says the spec is unknown when the feature has no spec.md", s7.children.some((n) => role(n, "caption") &&
      /^Generated from spec unknown · \d{4}-\d{2}-\d{2}$/.test(n.characters)));

    // Spec drift: screens.json records the sha1 of the spec.md it was built from
    console.log("spec drift");
    const drift = path.join(tmp, "DRIFT-1");
    fs.mkdirSync(path.join(drift, "design"), { recursive: true });
    fs.writeFileSync(path.join(drift, "spec.md"), "# Billing\n- AC-1 overview\n- AC-2 totals\n- AC-3 list\n- AC-4 select\n- AC-5 confirm delete\n");
    const dDoc = JSON.parse(fs.readFileSync(DASHBOARD, "utf8"));
    dDoc.spec_sha1 = sha1(fs.readFileSync(path.join(drift, "spec.md")));
    fs.writeFileSync(path.join(drift, "design", "screens.json"), JSON.stringify(dDoc, null, 2));
    const dScreens = path.join(drift, "design", "screens.json");
    const OLDER = "screens.json was built from an older spec.md; re-run the prototype";
    r = py([RENDER, "check", dScreens, "--ds", DS]);
    check("render check: matching spec_sha1 gives no drift warning", r.code === 0 && r.out.indexOf(OLDER) < 0 && /0 error\(s\), 0 warning\(s\)/.test(r.out) && r.out.indexOf("info:") < 0, r.out.slice(-300));
    fs.appendFileSync(path.join(drift, "spec.md"), "Totals are shown in the account currency.\n");
    r = py([RENDER, "check", dScreens, "--ds", DS, "--spec", path.join(drift, "spec.md")]);
    check("render check: changed spec.md prints the drift warning and the new sha1", r.code === 0 && r.out.indexOf("warn:  " + OLDER) >= 0 &&
      r.out.indexOf(sha1(fs.readFileSync(path.join(drift, "spec.md")))) >= 0, r.out.slice(-400));
    r = py([BUILD, drift, "--ds", DS, "--out", path.join(tmp, "drift.json")]);
    const dr = r.code === 0 ? JSON.parse(fs.readFileSync(path.join(tmp, "drift.json"), "utf8")) : null;
    check("build_bundle warns about the same drift", dr && dr.warnings.some((w) => w.indexOf(OLDER) === 0) && dr.sources.spec.sha1 !== dDoc.spec_sha1, r.out.slice(-300));
    delete dDoc.spec_sha1;
    fs.writeFileSync(dScreens, JSON.stringify(dDoc));
    r = py([RENDER, "check", dScreens, "--ds", DS]);
    check("render check: without spec_sha1 it prints the value to record (info, not a warning)", r.code === 0 && /0 warning\(s\)/.test(r.out) &&
      /info: .*has sha1 [0-9a-f]{40}; record it as "spec_sha1"/.test(r.out), r.out.slice(-300));

    // Bad input surfaces an error, not a crash
    const mock6 = createMock();
    loadPlugin(mock6);
    res = await runBuild(mock6, { version: 1, feature: "X", diagrams: [], screens: null });
    check("empty bundle reports an error", res.type === "error" && /no diagrams and no screens/.test(res.text));
  } finally {
    if (!process.env.KEEP_TMP) fs.rmSync(tmp, { recursive: true, force: true });
    else console.log("kept " + tmp);
  }
  console.log((failed ? "FAIL" : "PASS") + ": " + passed + " passed, " + failed + " failed");
  process.exit(failed ? 1 : 0);
}

main().catch((e) => { console.error("FAIL: " + (e && e.stack || e)); process.exit(1); });
