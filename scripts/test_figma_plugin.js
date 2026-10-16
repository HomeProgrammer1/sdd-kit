#!/usr/bin/env node
/*
 * Tests for plugins/sdd-figma: build_bundle.py on the EXAMPLE-001 feature, then
 * figma-plugin/code.js inside a strict mock of the Figma Plugin API.
 * Node built-ins only. Run: node scripts/test_figma_plugin.js   (exit 1 on failure)
 */
"use strict";
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
const DS = path.join(REPO, "plugins/sdd-design/skills/design-system-init/starter/components.json");

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
  const log = { reactions: [], bound: [], paintBound: 0, ui: [], notify: [], closed: false, svg: 0, showUI: null };
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
      const kill = (n) => { n.removed = true; (n._kids || []).forEach(kill); };
      kill(this);
    }
    _sizing(axis, v) {
      if (["FIXED", "HUG", "FILL"].indexOf(v) < 0) throw new Error("layoutSizing" + axis + ": invalid value " + v);
      if (v !== "FIXED" && !isAuto(this.parent)) throw new Error("layoutSizing" + axis + " = " + v + " on '" + this.name + "': parent is not an auto-layout frame");
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
    createEllipse() { return onPage(new Node("ELLIPSE")); },
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

    const counts1 = [dPage, sPage].map((p) => p.children.length);
    const varCount1 = mock.variables.size;
    sPage.appendChild(Object.assign(mock.figma.createRectangle(), { name: "Designer note" }));
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
