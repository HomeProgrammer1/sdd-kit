/*
 * SDD Kit Import: Figma plugin main thread. MIT licence, HomeProgrammer1.
 *
 * Reads one sdd-kit figma/bundle.json (sent by ui.html) and builds, in the open file:
 *   "<feature> · How it works"  every diagram SVG, stacked, each under a heading
 *   "<feature> · Screens"       one auto-layout frame per screen, prototype links,
 *                               token variables bound to fills, gaps, padding, radii
 * Each generated page carries a caption and pluginData with the sha1 of its sources.
 * Re-running never deletes anything: what this plugin generated before (pluginData
 * sdd=generated) moves to "<feature> · Archive", under one "Run <time>" section per run.
 *
 * Plain JavaScript on purpose: no optional chaining, no nullish coalescing,
 * no libraries, no network. Sizing (FILL/HUG) is set only after a node is
 * appended to its auto-layout parent.
 */
"use strict";

var MARK = "sdd";
var GENERATED = "generated";
var ARCHIVED = "archived";
var ARCHIVE = "archive";
var ROLE = "sddRole";

var DEFAULT_TOKENS = {
  "color.background": "#f7f7f8", "color.surface": "#ffffff", "color.surface-2": "#eeeef0",
  "color.text": "#18181d", "color.text-muted": "#5b5b66", "color.border": "#dcdce0",
  "color.primary": "#4338ca", "color.on-primary": "#ffffff", "color.primary-subtle": "#eef2ff",
  "color.danger": "#c62828", "color.danger-subtle": "#fdecec",
  "color.success": "#1b7a3a", "color.success-subtle": "#e8f5ec",
  "color.warning": "#8a5a00", "color.warning-subtle": "#fdf4e3",
  "color.info": "#1d5fbf", "color.info-subtle": "#e9f1fc", "color.overlay": "#18181d80",
  "radius.sm": 4, "radius.md": 8, "radius.lg": 16, "radius.full": 999,
  "font.size.caption": 12, "font.size.label": 14, "font.size.body": 16,
  "font.size.heading": 20, "font.size.title": 28, "font.size.display": 40
};

var TEXT_VARIANTS = {
  display: { size: 40, weight: "bold" },
  title: { size: 28, weight: "bold" },
  heading: { size: 20, weight: "semibold" },
  body: { size: 16, weight: "regular" },
  caption: { size: 12, weight: "regular" },
  label: { size: 14, weight: "medium" }
};
var TEXT_TONES = {
  "default": "color.text", muted: "color.text-muted", primary: "color.primary",
  danger: "color.danger", success: "color.success", warning: "color.warning", info: "color.info"
};
var BUTTONS = {
  primary: { fill: "color.primary", text: "color.on-primary" },
  secondary: { fill: "color.surface", stroke: "color.border", text: "color.text" },
  ghost: { fill: null, text: "color.primary" },
  danger: { fill: "color.danger", text: "color.on-primary" }
};
var ALERT_TONES = { info: 1, success: 1, warning: 1, danger: 1 };
var ALIGN = { start: "MIN", center: "CENTER", end: "MAX", stretch: "MIN" };
var JUSTIFY = { start: "MIN", center: "CENTER", end: "MAX", between: "SPACE_BETWEEN" };
var INLINE = { Button: 1, Link: 1, Badge: 1, Checkbox: 1, Toggle: 1, Avatar: 1, Pagination: 1 };
var CHART_KINDS = { line: 1, bar: 1, pie: 1 };
var CHART_BARS = [0.45, 0.7, 0.55, 0.9, 0.65, 0.8];
var VERTICAL_STRETCH = { dir: "VERTICAL", align: "stretch" };

var ctx = null;
var busy = false;

figma.showUI(__html__, { width: 400, height: 560, themeColors: true });

figma.ui.onmessage = function (msg) {
  if (!msg || typeof msg !== "object") return undefined;
  if (msg.type === "close") { figma.closePlugin(); return undefined; }
  if (msg.type !== "build") return undefined;
  if (busy) { post({ type: "log", level: "warn", text: "A build is already running." }); return undefined; }
  busy = true;
  return build(msg.bundle).then(function (report) {
    busy = false;
    post({ type: "done", summary: report.summary, report: report });
    figma.notify(report.summary, { timeout: 10000 });
    return report;
  }, function (err) {
    busy = false;
    var text = errText(err);
    post({ type: "error", text: text });
    figma.notify("SDD Kit Import failed: " + text, { error: true });
    return { error: text };
  });
};

// ------------------------------------------------------------------ run

async function build(bundle) {
  var t0 = Date.now();
  if (typeof bundle === "string") bundle = JSON.parse(bundle);
  if (!bundle || typeof bundle !== "object") throw new Error("bundle.json is not a JSON object.");
  ctx = {
    bundle: bundle,
    tokens: bundle.tokens && typeof bundle.tokens === "object" ? bundle.tokens : {},
    components: bundle.components && typeof bundle.components === "object" ? bundle.components : null,
    vars: {}, fonts: null, fontFamily: "", imports: {}, once: {},
    warnings: [], instanced: {}, drawn: {}, fallbacks: {}, clickables: [], pages: [],
    sources: bundle.sources && typeof bundle.sources === "object" ? bundle.sources : {},
    runAt: new Date().toISOString().replace(/\.\d+Z$/, "Z"), run: null, screen: null,
    stats: { diagrams: 0, screens: 0, links: 0, variables: 0, variablesCreated: 0, bindings: 0, collection: "", archived: 0 }
  };
  if (bundle.version !== 1) warn("Bundle version " + bundle.version + " (expected 1); trying anyway.");
  var feature = String(bundle.feature || "Feature");
  var diagrams = Array.isArray(bundle.diagrams) ? bundle.diagrams : [];
  var doc = bundle.screens && typeof bundle.screens === "object" ? bundle.screens : null;
  var screens = doc && Array.isArray(doc.screens) ? doc.screens : [];
  if (!diagrams.length && !screens.length) throw new Error("The bundle has no diagrams and no screens.");
  if (Array.isArray(bundle.warnings) && bundle.warnings.length) {
    log("build_bundle.py reported " + bundle.warnings.length + " warning(s); see the summary.");
    for (var w = 0; w < bundle.warnings.length; w++) ctx.warnings.push("bundle: " + bundle.warnings[w]);
  }

  log("Loading fonts…");
  await loadFonts();
  if (typeof figma.loadAllPagesAsync === "function") await figma.loadAllPagesAsync();
  log("Setting up variables…");
  await setupVariables();

  var built = [];
  if (diagrams.length) {
    var dPage = await generatedPage(feature + " · How it works", feature);
    built.push(dPage);
    log("Importing " + diagrams.length + " diagram(s)…");
    await buildDiagrams(dPage, diagrams);
    caption(dPage);
  }
  var sPage = null;
  if (screens.length) {
    sPage = await generatedPage(feature + " · Screens", feature);
    built.push(sPage);
    log("Building " + screens.length + " screen(s)…");
    await buildScreens(sPage, doc, screens, feature);
    caption(sPage);
  }
  var landing = sPage || built[0];
  await figma.setCurrentPageAsync(landing);
  try {
    var shown = landing.children.filter(isGenerated);
    if (shown.length && figma.viewport) figma.viewport.scrollAndZoomIntoView(shown);
  } catch (e) { /* viewport is cosmetic */ }
  return makeReport(feature, built, t0);
}

function makeReport(feature, pages, t0) {
  var s = ctx.stats;
  var nInst = total(ctx.instanced), nDrawn = total(ctx.drawn);
  var run = ctx.run;
  var summary = feature + ": " + pages.length + " page(s), " + s.screens + " screen(s), " + s.diagrams +
    " diagram(s), " + s.links + " prototype link(s), " + s.variables + " variable(s); components " +
    nInst + " instanced / " + nDrawn + " drawn" +
    (run ? "; " + s.archived + " earlier layer(s) archived to “" + run.page.name + "” › " + run.name : "") +
    (ctx.warnings.length ? "; " + ctx.warnings.length + " warning(s)" : "");
  return {
    summary: summary,
    feature: feature,
    pages: pages.map(function (p) { return p.name; }),
    diagrams: s.diagrams,
    screens: s.screens,
    links: s.links,
    variables: s.variables,
    variablesCreated: s.variablesCreated,
    collection: s.collection,
    bindings: s.bindings,
    font: ctx.fontFamily,
    instanced: ctx.instanced,
    drawn: ctx.drawn,
    fallbacks: ctx.fallbacks,
    archived: { layers: s.archived, page: run ? run.page.name : "", run: run ? run.name : "" },
    specSha1: specSha1(),
    warnings: ctx.warnings,
    seconds: Math.round((Date.now() - t0) / 100) / 10
  };
}

// ------------------------------------------------------------------ pages

/** @param {BaseNode} node */
function isGenerated(node) {
  try { return node.getPluginData(MARK) === GENERATED; } catch (e) { return false; }
}

/** @param {BaseNode} node */
function mark(node, role) {
  node.setPluginData(MARK, GENERATED);
  node.setPluginData(ROLE, role);
}

// The page called `name` that carries pluginData sdd=`value`; a same-named page of the designer's is never taken over.
async function ownPage(name, value) {
  var pages = figma.root.children, clash = false;
  /** @type {PageNode} */
  var page = null;
  for (var i = 0; i < pages.length; i++) {
    if (pages[i].name !== name) continue;
    if (pages[i].getPluginData(MARK) === value) { page = pages[i]; break; }
    clash = true;
  }
  if (!page) {
    page = figma.createPage();
    page.name = name;
    page.setPluginData(MARK, value);
    if (clash) warn("A page named “" + name + "” exists but was not made by this plugin; left it alone and created a new one.");
  }
  if (typeof page.loadAsync === "function") await page.loadAsync();
  return page;
}

async function generatedPage(name, feature) {
  var page = await ownPage(name, GENERATED);
  await figma.setCurrentPageAsync(page);
  var old = page.children.filter(isGenerated);
  if (old.length) await archive(old, page, feature);
  log((old.length ? "Rebuilding " : "Creating ") + "page “" + name + "”" + (old.length ? "; archived its " + old.length +
    " earlier generated layer(s) to “" + ctx.run.page.name + "” › " + ctx.run.name : "") + ".");
  page.setPluginData("sddSources", JSON.stringify(ctx.sources));
  page.setPluginData("sddSpecSha1", specSha1());
  page.setPluginData("sddGeneratedAt", ctx.runAt);
  return page;
}

// Nothing generated earlier is deleted, because a designer may have edited it. It moves, unchanged,
// to "<feature> · Archive": one "Run <time>" section per run, holding one section per source page.
// Moved layers are re-marked sdd=archived, so they never count as generated again.
/** @param {SceneNode[]} layers @param {PageNode} from */
async function archive(layers, from, feature) {
  var PAD = 80, GAP = 160;
  if (!ctx.run) {
    var apage = await ownPage(feature + " · Archive", ARCHIVE);
    var bottom = 0, kids = apage.children;
    for (var k = 0; k < kids.length; k++) bottom = Math.max(bottom, kids[k].y + kids[k].height + GAP * 2);
    var runBox = figma.createSection();
    apage.appendChild(runBox);
    runBox.name = "Run " + ctx.runAt;
    runBox.setPluginData(MARK, ARCHIVE);
    runBox.x = 0;
    runBox.y = bottom;
    ctx.run = { page: apage, section: runBox, name: runBox.name, width: PAD, height: 0 };
  }
  /** @type {{ page: PageNode, section: SectionNode, name: string, width: number, height: number }} */
  var run = ctx.run;
  var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (var i = 0; i < layers.length; i++) {
    var n = layers[i];
    x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y);
    x1 = Math.max(x1, n.x + n.width); y1 = Math.max(y1, n.y + n.height);
  }
  var box = figma.createSection();
  run.section.appendChild(box);
  box.name = from.name;
  box.setPluginData(MARK, ARCHIVE);
  for (var j = 0; j < layers.length; j++) {
    var m = layers[j], dx = m.x - x0, dy = m.y - y0;
    box.appendChild(m);
    m.x = PAD + dx;
    m.y = PAD + dy;
    m.setPluginData(MARK, ARCHIVED);
    m.setPluginData("sddArchivedFrom", from.name);
    m.setPluginData("sddArchivedAt", ctx.runAt);
  }
  var w = Math.max(1, x1 - x0) + 2 * PAD, h = Math.max(1, y1 - y0) + 2 * PAD;
  box.resizeWithoutConstraints(w, h);
  box.x = run.width;
  box.y = PAD;
  run.width += w + PAD;
  run.height = Math.max(run.height, h + 2 * PAD);
  run.section.resizeWithoutConstraints(run.width, run.height);
  ctx.stats.archived += layers.length;
}

function specSha1() {
  var spec = ctx.sources.spec;
  return spec && typeof spec === "object" && spec.sha1 ? String(spec.sha1) : "";
}

// "Generated from spec <sha7> · <date>" above the page's content, so drift is visible without a plugin.
/** @param {PageNode} page */
function caption(page) {
  var sha = specSha1();
  var t = text("Generated from spec " + (sha ? sha.slice(0, 7) : "unknown") + " · " + ctx.runAt.slice(0, 10),
    { size: dimOf("font.size.caption", null, 12), weight: "medium", color: "color.text-muted", name: "Source caption" });
  page.appendChild(t);
  mark(t, "caption");
  t.setPluginData("sddSpecSha1", sha);
  t.x = 0;
  t.y = -t.height - 48;
}

// ------------------------------------------------------------------ diagrams

/** @param {PageNode} page */
async function buildDiagrams(page, diagrams) {
  var y = 0;
  for (var i = 0; i < diagrams.length; i++) {
    var d = diagrams[i] || {};
    var title = String(d.title || d.name || "Diagram " + (i + 1));
    var meta = String(d.kind || "diagram") + " · source sha1 " + String(d.sha1 || "unknown");
    var heading = text(title + "\n" + meta, { size: num(16), weight: "semibold", color: "color.text", name: "Heading / " + title });
    try {
      var start = title.length + 1, end = start + meta.length;
      heading.setRangeFontName(start, end, ctx.fonts.regular);
      heading.setRangeFontSize(start, end, 12);
      heading.setRangeFills(start, end, [paintOf("color.text-muted")]);
    } catch (e) { /* one style is fine */ }
    page.appendChild(heading);
    mark(heading, "diagram-heading");
    heading.x = 0;
    heading.y = y;
    var node;
    try {
      node = figma.createNodeFromSvg(String(d.svg || ""));
    } catch (e) {
      heading.remove();
      warn("Diagram “" + title + "”: SVG import failed (" + errText(e) + ").");
      continue;
    }
    page.appendChild(node);
    node.name = title;
    mark(node, "diagram");
    node.setPluginData("sddSha1", String(d.sha1 || ""));
    node.x = 0;
    node.y = y + heading.height + 12;
    y = node.y + node.height + 120;
    ctx.stats.diagrams++;
  }
}

// ------------------------------------------------------------------ screens

/** @param {PageNode} page */
async function buildScreens(page, doc, screens, feature) {
  var vp = doc.viewport && typeof doc.viewport === "object" ? doc.viewport : {};
  var mobile = doc.platform === "mobile";
  var W = toNumber(vp.width) || (mobile ? 390 : 1280);
  var H = toNumber(vp.height) || (mobile ? 844 : 800);
  var frames = {}, placed = [], first = null, x = 0;

  for (var i = 0; i < screens.length; i++) {
    var s = screens[i] || {};
    var id = String(s.id || "screen-" + (i + 1));
    var ac = Array.isArray(s.ac) ? s.ac : (s.ac ? [s.ac] : []);
    var label = id + " · " + String(s.state || "default") + (ac.length ? " · " + ac.join(", ") : "") + (s.note ? "\n" + s.note : "");
    var ann = text(label, { size: num(12), weight: "medium", color: "color.text-muted", name: "Annotation / " + id });
    page.appendChild(ann);
    mark(ann, "annotation");
    try { ann.resize(W, Math.max(1, ann.height)); ann.textAutoResize = "HEIGHT"; } catch (e) { /* keeps auto width */ }
    ann.x = x;

    var f = figma.createFrame();
    page.appendChild(f);
    f.name = id + " — " + String(s.title || id);
    mark(f, "screen");
    f.setPluginData("sddScreen", id);
    f.layoutMode = "VERTICAL";
    f.itemSpacing = 0;
    f.paddingTop = 0; f.paddingRight = 0; f.paddingBottom = 0; f.paddingLeft = 0;
    f.primaryAxisAlignItems = "MIN";
    f.counterAxisAlignItems = "MIN";
    f.fills = [paintOf("color.background")];
    f.clipsContent = true;
    f.resize(W, H);
    f.counterAxisSizingMode = "FIXED";
    f.primaryAxisSizingMode = "AUTO";
    var minOk = true;
    try { f.minHeight = H; } catch (e) { minOk = false; }
    f.x = x;
    frames[id] = f;
    if (!first) first = f;
    ctx.screen = f;

    if (s.body && typeof s.body === "object") await buildNode(s.body, f, { dir: "VERTICAL", align: "stretch", screen: id });
    else warn("Screen " + id + " has no body.");
    if (!minOk && f.height < H) { f.primaryAxisSizingMode = "FIXED"; f.resize(W, H); }
    placed.push({ frame: f, ann: ann });
    ctx.stats.screens++;
    x += W + 160;
  }

  var top = 0;
  for (var a = 0; a < placed.length; a++) top = Math.max(top, placed[a].ann.height);
  top += 16;
  for (var b = 0; b < placed.length; b++) {
    placed[b].frame.y = top;
    placed[b].ann.y = top - 16 - placed[b].ann.height;
  }

  await linkPrototype(frames, doc);
  if (first) {
    try { page.flowStartingPoints = [{ nodeId: first.id, name: String(doc.title || feature) }]; }
    catch (e) { warn("Could not set the prototype starting point (" + errText(e) + ")."); }
  }
}

async function linkPrototype(frames, doc) {
  var flows = Array.isArray(doc.flows) ? doc.flows : [];
  var covered = {};
  for (var i = 0; i < ctx.clickables.length; i++) {
    var c = ctx.clickables[i], target = c.link;
    for (var f = 0; f < flows.length; f++) {
      var fl = flows[f] || {};
      if (fl.from !== c.screen) continue;
      if (target ? fl.to === target : fl.on === c.label) { covered[f] = true; if (!target) target = String(fl.to || ""); }
    }
    if (!target) continue;
    var dest = frames[target];
    if (!dest) { warn(c.screen + ": " + c.type + " “" + c.label + "” links to unknown screen “" + target + "”."); continue; }
    if (await setClick(c.node, dest.id)) ctx.stats.links++;
  }
  for (var g = 0; g < flows.length; g++) {
    if (!covered[g] && flows[g]) warn("Flow " + flows[g].from + " → " + flows[g].to + ": no Button, Link or Tab “" + flows[g].on + "” on " + flows[g].from + ".");
  }
}

// documentAccess dynamic-page makes `reactions` read-only, so setReactionsAsync is the only way to write them.
/** @param {SceneNode & ReactionMixin} node */
async function setClick(node, destId) {
  /** @type {Reaction} */
  var click = { trigger: { type: "ON_CLICK" }, actions: [{ type: "NODE", destinationId: destId, navigation: "NAVIGATE", transition: null }] };
  try {
    await node.setReactionsAsync([click]);
    return true;
  } catch (e) {
    warn("Prototype link on “" + node.name + "” failed (" + errText(e) + ").");
    return false;
  }
}

// ------------------------------------------------------------------ node tree

async function buildNode(node, parent, pc) {
  if (!node || typeof node !== "object") { warn(pc.screen + ": skipped a node that is not an object."); return null; }
  var type = String(node.type || "Unknown");
  var spec = ctx.components && ctx.components[type] ? ctx.components[type] : null;
  var fig = spec && spec.figma && spec.figma.key ? spec.figma : null;
  var n = null;
  if (fig) {
    if (node.children && node.children.length) {
      warnOnce("container:" + type, type + " has children, so it is drawn instead of placing the library component.");
    } else {
      n = await placeInstance(node, type, fig, parent, pc);
      if (n) bump(ctx.instanced, type); else bump(ctx.fallbacks, type);
    }
  }
  if (!n) {
    var draw = DRAW[type];
    if (!draw) {
      warnOnce("type:" + type, "No drawing for component type “" + type + "”; placed a labelled placeholder.");
      draw = drawUnknown;
    }
    n = await draw(node, parent, pc);
    bump(ctx.drawn, type);
  }
  if (n && (type === "Button" || type === "Link")) {
    ctx.clickables.push({ node: n, type: type, screen: pc.screen, link: node.link ? String(node.link) : "", label: String(textOf(node) || "") });
  }
  return n;
}

async function children(node, frame, pc) {
  var list = Array.isArray(node.children) ? node.children : [];
  for (var i = 0; i < list.length; i++) await buildNode(list[i], frame, pc);
}

var DRAW = {
  Stack: async function (node, parent, pc) {
    var dir = node.direction === "horizontal" ? "HORIZONTAL" : "VERTICAL";
    var align = ALIGN[node.align] ? node.align : (dir === "VERTICAL" ? "stretch" : "center");
    var f = alFrame("Stack / " + dir.toLowerCase(), dir);
    setNum(f, "itemSpacing", dimOf(node.gap, null, 0));
    applyPadding(f, node.padding);
    f.counterAxisAlignItems = ALIGN[align];
    f.primaryAxisAlignItems = JUSTIFY[node.justify] || "MIN";
    if (node.fill === "background" || node.fill === "surface") f.fills = [paintOf("color." + node.fill)];
    else if (typeof node.fill === "string" && node.fill.indexOf("color.") === 0) f.fills = [paintOf(node.fill)];
    attach(f, parent, widthFor(node, pc, "block"), heightFor(pc));
    await children(node, f, { dir: dir, align: align, screen: pc.screen });
    return f;
  },

  Grid: async function (node, parent, pc) {
    var cols = Math.max(1, parseInt(node.columns, 10) || 2);
    var gap = dimOf(node.gap, "space.4", 16);
    var g = alFrame("Grid / " + cols + " columns", "VERTICAL");
    setNum(g, "itemSpacing", gap);
    applyPadding(g, node.padding);
    attach(g, parent, widthFor(node, pc, "block"), heightFor(pc));
    var kids = Array.isArray(node.children) ? node.children : [];
    for (var r = 0; r * cols < kids.length; r++) {
      var row = alFrame("Grid / row " + (r + 1), "HORIZONTAL");
      setNum(row, "itemSpacing", gap);
      row.counterAxisAlignItems = "MIN";
      attach(row, g, "FILL", "HUG");
      for (var c = 0; c < cols; c++) {
        var child = kids[r * cols + c];
        if (child) await buildNode(child, row, { dir: "HORIZONTAL", align: "start", cell: true, screen: pc.screen });
        else attach(alFrame("Grid / empty cell", "VERTICAL"), row, "FILL", "HUG");
      }
    }
    return g;
  },

  Card: async function (node, parent, pc) {
    var f = alFrame("Card", "VERTICAL");
    f.fills = [paintOf("color.surface")];
    stroke(f, "color.border");
    radius(f, dimOf("radius.lg", null, 16));
    applyPadding(f, node.padding !== undefined ? node.padding : "space.6");
    setNum(f, "itemSpacing", dimOf(node.gap, "space.4", 16));
    attach(f, parent, widthFor(node, pc, "block"), heightFor(pc));
    await children(node, f, { dir: "VERTICAL", align: "stretch", screen: pc.screen });
    return f;
  },

  Text: function (node, parent, pc) {
    var variant = TEXT_VARIANTS[node.variant] ? node.variant : "body";
    var v = TEXT_VARIANTS[variant];
    var t = text(node.text !== undefined && node.text !== null ? node.text : "", {
      size: dimOf("font.size." + variant, null, v.size), weight: v.weight,
      color: TEXT_TONES[node.tone] || "color.text", name: "Text / " + variant
    });
    placeText(t, parent, pc, node);
    return t;
  },

  Button: function (node, parent, pc) {
    var variant = BUTTONS[node.variant] ? node.variant : "primary";
    var look = BUTTONS[variant];
    var f = alFrame("Button / " + variant, "HORIZONTAL");
    f.primaryAxisAlignItems = "CENTER";
    f.counterAxisAlignItems = "CENTER";
    var py = dimOf("space.3", null, 12), px = dimOf("space.5", null, 20);
    pad4(f, py, px, py, px);
    radius(f, dimOf("radius.md", null, 8));
    f.fills = look.fill ? [paintOf(look.fill)] : [];
    if (look.stroke) stroke(f, look.stroke);
    attach(f, parent, node.full ? "FILL" : widthFor(node, pc, "inline"), "HUG");
    f.appendChild(text(node.label || "Button", { size: dimOf("font.size.body", null, 16), weight: "semibold", color: look.text, name: "Label" }));
    return f;
  },

  Link: function (node, parent, pc) {
    var f = alFrame("Link", "HORIZONTAL");
    attach(f, parent, widthFor(node, pc, "inline"), "HUG");
    f.appendChild(text(node.text || node.label || "Link", { size: dimOf("font.size.body", null, 16), weight: "medium", color: "color.primary", underline: true, name: "Label" }));
    return f;
  },

  TextField: function (node, parent, pc) { return drawField(node, parent, pc, false); },
  Select: function (node, parent, pc) { return drawField(node, parent, pc, true); },

  Checkbox: function (node, parent, pc) {
    var row = controlRow("Checkbox", node, parent, pc);
    checkBox(row, node.checked);
    controlLabel(row, node);
    return row;
  },

  Toggle: function (node, parent, pc) {
    var row = controlRow("Toggle", node, parent, pc);
    var track = alFrame("Control", "HORIZONTAL");
    track.primaryAxisAlignItems = node.on ? "MAX" : "MIN";
    track.counterAxisAlignItems = "CENTER";
    pad4(track, num(2), num(2), num(2), num(2));
    radius(track, dimOf("radius.full", null, 999));
    track.fills = [paintOf(node.on ? "color.primary" : "color.border")];
    attach(track, row, 36, 20);
    var knob = figma.createEllipse();
    knob.name = "Knob";
    knob.resize(16, 16);
    knob.fills = [paintOf("color.surface")];
    track.appendChild(knob);
    controlLabel(row, node);
    return row;
  },

  Alert: function (node, parent, pc) {
    var tone = ALERT_TONES[node.tone] ? node.tone : "info";
    var f = alFrame("Alert / " + tone, "VERTICAL");
    f.fills = [paintOf("color." + tone + "-subtle")];
    stroke(f, "color." + tone);
    radius(f, dimOf("radius.md", null, 8));
    applyPadding(f, "space.4");
    setNum(f, "itemSpacing", dimOf("space.1", null, 4));
    attach(f, parent, widthFor(node, pc, "block"), heightFor(pc));
    if (node.title) placeText(text(node.title, { size: dimOf("font.size.body", null, 16), weight: "semibold", color: "color." + tone, name: "Title" }), f, VERTICAL_STRETCH);
    if (node.text) placeText(text(node.text, { size: dimOf("font.size.body", null, 16), color: "color.text", name: "Text" }), f, VERTICAL_STRETCH);
    return f;
  },

  Badge: function (node, parent, pc) {
    var tone = String(node.tone || node.variant || "default");
    var toned = tone !== "default" && colorValue("color." + tone) !== null;
    var f = alFrame("Badge / " + tone, "HORIZONTAL");
    f.counterAxisAlignItems = "CENTER";
    f.fills = [paintOf(toned ? "color." + tone + "-subtle" : "color.surface-2", "color.surface-2")];
    radius(f, dimOf("radius.full", null, 999));
    var px = dimOf("space.2", null, 8);
    pad4(f, num(2), px, num(2), px);
    attach(f, parent, widthFor(node, pc, "inline"), "HUG");
    f.appendChild(text(node.text || tone, { size: dimOf("font.size.caption", null, 12), weight: "medium", color: toned ? "color." + tone : "color.text", name: "Label" }));
    return f;
  },

  Image: function (node, parent, pc) {
    var alt = String(node.alt || "Image");
    var f = alFrame("Image / " + alt, "HORIZONTAL");
    f.primaryAxisAlignItems = "CENTER";
    f.counterAxisAlignItems = "CENTER";
    f.fills = [paintOf("color.surface-2")];
    radius(f, dimOf("radius.md", null, 8));
    var w = widthFor(node, pc, "block");
    if (w === "HUG") w = 360;
    var ratio = parseRatio(node.ratio) || 16 / 9;
    attach(f, parent, w, Math.max(1, Math.round((typeof w === "number" ? w : 360) / ratio)));
    f.appendChild(text(alt, { size: dimOf("font.size.caption", null, 12), color: "color.text-muted", name: "Alt", align: "CENTER" }));
    return f;
  },

  Avatar: function (node, parent, pc) {
    var f = alFrame("Avatar / " + String(node.name || ""), "HORIZONTAL");
    f.primaryAxisAlignItems = "CENTER";
    f.counterAxisAlignItems = "CENTER";
    f.fills = [paintOf("color.primary-subtle")];
    f.cornerRadius = 20;
    attach(f, parent, 40, 40);
    f.appendChild(text(initials(node.name), { size: dimOf("font.size.label", null, 14), weight: "semibold", color: "color.primary", name: "Initials" }));
    return f;
  },

  List: function (node, parent, pc) {
    var f = alFrame("List", "VERTICAL");
    attach(f, parent, widthFor(node, pc, "block"), heightFor(pc));
    var items = Array.isArray(node.items) ? node.items : [];
    var sp2 = dimOf("space.2", null, 8), sp3 = dimOf("space.3", null, 12);
    for (var i = 0; i < items.length; i++) {
      if (i > 0) line(f, VERTICAL_STRETCH);
      var row = alFrame("List / item " + (i + 1), "HORIZONTAL");
      row.counterAxisAlignItems = "MIN";
      setNum(row, "itemSpacing", sp2);
      pad4(row, sp3, num(0), sp3, num(0));
      attach(row, f, "FILL", "HUG");
      row.appendChild(text("•", { color: "color.text-muted", name: "Bullet" }));
      var t = text(itemText(items[i]), { name: "Text" });
      row.appendChild(t);
      sizeAxis(t, "Horizontal", "FILL");
      setAutoHeight(t);
    }
    return f;
  },

  NavBar: function (node, parent, pc) {
    var f = alFrame("NavBar / " + String(node.title || ""), "HORIZONTAL");
    f.counterAxisAlignItems = "CENTER";
    setNum(f, "itemSpacing", dimOf("space.2", null, 8));
    var px = dimOf("space.4", null, 16);
    pad4(f, num(0), px, num(0), px);
    f.fills = [paintOf("color.surface")];
    edgeStroke(f, "color.border", "Bottom");
    attach(f, parent, widthFor(node, pc, "block"), 56);
    var hs = dimOf("font.size.heading", null, 20);
    if (node.back) f.appendChild(text("‹", { size: hs, color: "color.primary", name: "Back" }));
    if (node.title) f.appendChild(text(node.title, { size: hs, weight: "semibold", name: "Title" }));
    return f;
  },

  TabBar: function (node, parent, pc) {
    var f = alFrame("TabBar", "HORIZONTAL");
    f.fills = [paintOf("color.surface")];
    edgeStroke(f, "color.border", "Top");
    attach(f, parent, widthFor(node, pc, "block"), "HUG");
    var items = Array.isArray(node.items) ? node.items : [];
    var active = parseInt(node.active, 10) || 0;
    var py = dimOf("space.3", null, 12), px = dimOf("space.2", null, 8);
    for (var i = 0; i < items.length; i++) {
      var on = i === active, label = itemText(items[i]);
      var tab = alFrame("Tab / " + label, "VERTICAL");
      tab.primaryAxisAlignItems = "CENTER";
      tab.counterAxisAlignItems = "CENTER";
      pad4(tab, py, px, py, px);
      attach(tab, f, "FILL", "HUG");
      tab.appendChild(text(label, { size: dimOf("font.size.label", null, 14), weight: on ? "semibold" : "medium", color: on ? "color.primary" : "color.text-muted", name: "Label" }));
    }
    return f;
  },

  Sidebar: function (node, parent, pc) {
    var f = alFrame("Sidebar", "VERTICAL");
    f.fills = [paintOf("color.surface")];
    edgeStroke(f, "color.border", "Right");
    applyPadding(f, "space.3");
    setNum(f, "itemSpacing", dimOf("space.1", null, 4));
    attach(f, parent, typeof node.width === "number" ? node.width : 240, heightFor(pc));
    var items = Array.isArray(node.items) ? node.items : [];
    var active = parseInt(node.active, 10) || 0;
    var py = dimOf("space.2", null, 8), px = dimOf("space.3", null, 12);
    for (var i = 0; i < items.length; i++) {
      var on = i === active, label = itemText(items[i]);
      var it = alFrame("Sidebar / " + label, "HORIZONTAL");
      it.counterAxisAlignItems = "CENTER";
      pad4(it, py, px, py, px);
      radius(it, dimOf("radius.md", null, 8));
      it.fills = on ? [paintOf("color.primary-subtle")] : [];
      attach(it, f, "FILL", "HUG");
      it.appendChild(text(label, { size: dimOf("font.size.label", null, 14), weight: on ? "semibold" : "regular", color: on ? "color.primary" : "color.text", name: "Label" }));
    }
    return f;
  },

  Table: function (node, parent, pc) {
    var cols = Array.isArray(node.columns) ? node.columns : [];
    var rows = Array.isArray(node.rows) ? node.rows : [];
    var selected = Array.isArray(node.selected) ? node.selected : [];
    var f = alFrame("Table / " + cols.length + " columns", "VERTICAL");
    f.fills = [paintOf("color.surface")];
    stroke(f, "color.border");
    radius(f, dimOf("radius.md", null, 8));
    f.clipsContent = true;
    attach(f, parent, widthFor(node, pc, "block"), heightFor(pc));
    tableRow(f, node, cols, -1, false, pc);
    for (var r = 0; r < rows.length; r++) tableRow(f, node, Array.isArray(rows[r]) ? rows[r] : [], r, selected.indexOf(r) >= 0, pc);
    return f;
  },

  // Shown open: a scrim over the whole screen frame (absolute, stretched) with the dialog centred on it.
  Modal: async function (node, parent, pc) {
    var title = String(node.title || "Dialog");
    /** @type {FrameNode} */
    var root = ctx.screen || parent;
    var o = alFrame("Modal / " + title, "VERTICAL");
    o.primaryAxisAlignItems = "CENTER";
    o.counterAxisAlignItems = "CENTER";
    o.fills = [paintOf("color.overlay")];
    root.appendChild(o);
    try {
      o.layoutPositioning = "ABSOLUTE";
      o.primaryAxisSizingMode = "FIXED";
      o.counterAxisSizingMode = "FIXED";
      o.resize(root.width, root.height);
      o.x = 0;
      o.y = 0;
      o.constraints = { horizontal: "STRETCH", vertical: "STRETCH" };
    } catch (e) { warnOnce("modal", "Modal “" + title + "”: could not lay the scrim over the screen (" + errText(e) + ")."); }
    var d = alFrame("Dialog", "VERTICAL");
    d.fills = [paintOf("color.surface")];
    stroke(d, "color.border");
    radius(d, dimOf("radius.lg", null, 16));
    applyPadding(d, "space.6");
    setNum(d, "itemSpacing", dimOf("space.4", null, 16));
    attach(d, o, typeof node.width === "number" ? node.width : Math.max(240, Math.min(480, root.width - 32)), "HUG");
    placeText(text(title, { size: dimOf("font.size.heading", null, 20), weight: "semibold", name: "Title" }), d, VERTICAL_STRETCH);
    await children(node, d, { dir: "VERTICAL", align: "stretch", screen: pc.screen });
    var actions = Array.isArray(node.actions) ? node.actions : [];
    if (actions.length) {
      var row = alFrame("Actions", "HORIZONTAL");
      row.primaryAxisAlignItems = "MAX";
      row.counterAxisAlignItems = "CENTER";
      setNum(row, "itemSpacing", dimOf("space.3", null, 12));
      attach(row, d, "FILL", "HUG");
      for (var i = 0; i < actions.length; i++) await buildNode(actions[i], row, { dir: "HORIZONTAL", align: "center", screen: pc.screen });
    }
    return o;
  },

  Tabs: function (node, parent, pc) {
    var f = alFrame("Tabs", "HORIZONTAL");
    setNum(f, "itemSpacing", dimOf("space.1", null, 4));
    edgeStroke(f, "color.border", "Bottom");
    attach(f, parent, widthFor(node, pc, "block"), "HUG");
    var items = Array.isArray(node.items) ? node.items : [];
    var active = parseInt(node.active, 10) || 0;
    var py = dimOf("space.3", null, 12), px = dimOf("space.4", null, 16);
    for (var i = 0; i < items.length; i++) {
      var on = i === active, label = itemText(items[i]);
      var tab = alFrame("Tab / " + label, "VERTICAL");
      pad4(tab, py, px, py, px);
      if (on) edgeStroke(tab, "color.primary", "Bottom", 2);
      attach(tab, f, "HUG", "HUG");
      tab.appendChild(text(label, { size: dimOf("font.size.label", null, 14), weight: on ? "semibold" : "medium", color: on ? "color.primary" : "color.text-muted", name: "Label" }));
      var link = items[i] && typeof items[i] === "object" && items[i].link ? String(items[i].link) : "";
      if (!on) ctx.clickables.push({ node: tab, type: "Tab", screen: pc.screen, link: link, label: label });
    }
    return f;
  },

  Pagination: function (node, parent, pc) {
    var pages = Math.max(1, parseInt(node.pages, 10) || 1);
    var page = Math.min(pages, Math.max(1, parseInt(node.page, 10) || 1));
    var f = alFrame("Pagination / " + page + " of " + pages, "HORIZONTAL");
    f.counterAxisAlignItems = "CENTER";
    setNum(f, "itemSpacing", dimOf("space.1", null, 4));
    attach(f, parent, widthFor(node, pc, "inline"), "HUG");
    pageItem(f, "‹ Previous", false, page === 1);
    var list = pageList(page, pages);
    for (var i = 0; i < list.length; i++) {
      if (list[i] === null) f.appendChild(text("…", { size: dimOf("font.size.label", null, 14), color: "color.text-muted", name: "Gap" }));
      else pageItem(f, String(list[i]), list[i] === page, false);
    }
    pageItem(f, "Next ›", false, page === pages);
    return f;
  },

  // Value 0..100: a token-coloured bar inside a track; SCALE constraints keep the share when the track fills its parent.
  Progress: function (node, parent, pc) {
    var value = Math.max(0, Math.min(100, toNumber(node.value) || 0)), pct = Math.round(value) + "%";
    var f = alFrame("Progress / " + (node.label ? String(node.label) : pct), "VERTICAL");
    setNum(f, "itemSpacing", dimOf("space.2", null, 8));
    attach(f, parent, widthFor(node, pc, "field"), heightFor(pc));
    var head = alFrame("Header", "HORIZONTAL");
    head.primaryAxisAlignItems = "SPACE_BETWEEN";
    attach(head, f, "FILL", "HUG");
    if (node.label) head.appendChild(text(node.label, { size: dimOf("font.size.label", null, 14), weight: "medium", name: "Label" }));
    head.appendChild(text(pct, { size: dimOf("font.size.label", null, 14), color: "color.text-muted", name: "Value" }));
    var track = figma.createFrame();
    track.name = "Track";
    track.fills = [paintOf("color.surface-2")];
    track.clipsContent = true;
    track.resize(200, 8);
    radius(track, dimOf("radius.full", null, 999));
    attach(track, f, "FILL", 8);
    if (value > 0) {
      var bar = figma.createRectangle();
      bar.name = "Bar";
      bar.fills = [paintOf("color.primary")];
      track.appendChild(bar);
      bar.resize(Math.max(1, 2 * value), 8);
      bar.x = 0;
      bar.y = 0;
      radius(bar, dimOf("radius.full", null, 999));
      bar.constraints = { horizontal: "SCALE", vertical: "STRETCH" };
    }
    return f;
  },

  // A labelled placeholder, not a data visualisation: fixed decorative marks in token colours.
  Chart: function (node, parent, pc) {
    var kind = CHART_KINDS[node.kind] ? node.kind : "bar";
    var f = alFrame("Chart / " + kind, "VERTICAL");
    f.fills = [paintOf("color.surface")];
    stroke(f, "color.border");
    radius(f, dimOf("radius.lg", null, 16));
    applyPadding(f, "space.5");
    setNum(f, "itemSpacing", dimOf("space.3", null, 12));
    attach(f, parent, widthFor(node, pc, "block"), heightFor(pc));
    placeText(text(String(node.title || "Chart"), { size: dimOf("font.size.label", null, 14), weight: "semibold", name: "Title" }), f, VERTICAL_STRETCH);
    var H = 160, pad = dimOf("space.3", null, 12);
    var plot = alFrame("Plot", kind === "bar" ? "HORIZONTAL" : "VERTICAL");
    plot.fills = [paintOf("color.surface-2")];
    radius(plot, dimOf("radius.md", null, 8));
    pad4(plot, pad, pad, pad, pad);
    setNum(plot, "itemSpacing", dimOf("space.2", null, 8));
    plot.primaryAxisAlignItems = kind === "bar" ? "MIN" : "CENTER";
    plot.counterAxisAlignItems = kind === "bar" ? "MAX" : "CENTER";
    attach(plot, f, "FILL", H);
    var inner = H - 2 * pad.v;
    if (kind === "bar") {
      for (var i = 0; i < CHART_BARS.length; i++) {
        var b = figma.createRectangle();
        b.name = "Bar";
        b.fills = [paintOf("color.primary")];
        b.resize(24, Math.round(inner * CHART_BARS[i]));
        radius(b, dimOf("radius.sm", null, 4));
        plot.appendChild(b);
        sizeAxis(b, "Horizontal", "FILL");
      }
    } else if (kind === "line") {
      var v = figma.createVector();
      v.name = "Line";
      v.vectorPaths = [{ windingRule: "NONE", data: "M 0 90 L 60 60 L 120 72 L 180 30 L 240 44 L 300 10" }];
      v.fills = [];
      v.strokes = [paintOf("color.primary")];
      v.strokeWeight = 2;
      v.strokeJoin = "ROUND";
      plot.appendChild(v);
      sizeAxis(v, "Horizontal", "FILL");
      sizeAxis(v, "Vertical", "FILL");
    } else {
      var D = Math.min(120, inner), pie = figma.createFrame();
      pie.name = "Pie";
      pie.fills = [];
      pie.clipsContent = false;
      attach(pie, plot, D, D);
      var parts = [{ name: "Rest", color: "color.primary-subtle", from: 0, to: 2 * Math.PI },
        { name: "Slice", color: "color.primary", from: -Math.PI / 2, to: Math.PI * 0.9 }];
      for (var k = 0; k < parts.length; k++) {
        var e = figma.createEllipse();
        e.name = parts[k].name;
        e.resize(D, D);
        e.fills = [paintOf(parts[k].color)];
        e.arcData = { startingAngle: parts[k].from, endingAngle: parts[k].to, innerRadius: 0.55 };
        pie.appendChild(e);
      }
    }
    placeText(text("Placeholder: " + kind + " chart, not real data", { size: dimOf("font.size.caption", null, 12), color: "color.text-muted", name: "Note" }), f, VERTICAL_STRETCH);
    return f;
  },

  Divider: function (node, parent, pc) { return line(parent, pc); },

  Spacer: function (node, parent, pc) {
    var f = figma.createFrame();
    f.name = "Spacer";
    f.fills = [];
    f.resize(1, 1);
    parent.appendChild(f);
    try { f.layoutGrow = 1; } catch (e) { /* fixed 1px spacer */ }
    return f;
  }
};

async function drawUnknown(node, parent, pc) {
  var type = String(node.type || "Unknown");
  var f = alFrame("Unknown / " + type, "VERTICAL");
  applyPadding(f, "space.3");
  setNum(f, "itemSpacing", dimOf("space.2", null, 8));
  stroke(f, "color.border");
  try { f.dashPattern = [4, 4]; } catch (e) { /* solid border */ }
  radius(f, dimOf("radius.sm", null, 4));
  attach(f, parent, widthFor(node, pc, "block"), heightFor(pc));
  var what = textOf(node);
  placeText(text(type + (what ? ": " + what : ""), { size: dimOf("font.size.caption", null, 12), color: "color.text-muted", name: "Type" }), f, VERTICAL_STRETCH);
  await children(node, f, { dir: "VERTICAL", align: "stretch", screen: pc.screen });
  return f;
}

function drawField(node, parent, pc, select) {
  var label = node.label ? String(node.label) : "";
  var f = alFrame((select ? "Select / " : "TextField / ") + (label || "field"), "VERTICAL");
  setNum(f, "itemSpacing", dimOf("space.2", null, 8));
  attach(f, parent, widthFor(node, pc, "field"), heightFor(pc));
  if (label) placeText(text(label, { size: dimOf("font.size.label", null, 14), weight: "medium", name: "Label" }), f, VERTICAL_STRETCH);

  var box = alFrame("Input", "HORIZONTAL");
  box.counterAxisAlignItems = "CENTER";
  setNum(box, "itemSpacing", dimOf("space.2", null, 8));
  var px = dimOf("space.3", null, 12);
  pad4(box, num(0), px, num(0), px);
  box.fills = [paintOf("color.surface")];
  stroke(box, node.error ? "color.danger" : "color.border");
  radius(box, dimOf("radius.md", null, 8));
  attach(box, f, "FILL", 44);

  var hasValue = node.value !== undefined && node.value !== null && node.value !== "";
  var shown = null, color = "color.text", role = "Value";
  if (hasValue) shown = node.inputType === "password" ? bullets(node.value) : String(node.value);
  else if (node.placeholder) { shown = String(node.placeholder); color = "color.text-muted"; role = "Placeholder"; }
  else if (select) { shown = "Select…"; color = "color.text-muted"; role = "Placeholder"; }
  if (shown !== null) {
    var t = text(shown, { size: dimOf("font.size.body", null, 16), color: color, name: role });
    box.appendChild(t);
    sizeAxis(t, "Horizontal", "FILL");
    setAutoHeight(t);
  }
  if (select) box.appendChild(text("▾", { size: dimOf("font.size.body", null, 16), color: "color.text-muted", name: "Chevron" }));

  var small = dimOf("font.size.caption", null, 12);
  if (node.error) placeText(text(node.error, { size: small, color: "color.danger", name: "Error" }), f, VERTICAL_STRETCH);
  else if (node.hint) placeText(text(node.hint, { size: small, color: "color.text-muted", name: "Hint" }), f, VERTICAL_STRETCH);
  return f;
}

/** @param {FrameNode} parent */
function checkBox(parent, checked) {
  var box = alFrame("Control", "HORIZONTAL");
  box.primaryAxisAlignItems = "CENTER";
  box.counterAxisAlignItems = "CENTER";
  radius(box, dimOf("radius.sm", null, 4));
  if (checked) box.fills = [paintOf("color.primary")];
  else { box.fills = [paintOf("color.surface")]; stroke(box, "color.border", 1.5); }
  attach(box, parent, 18, 18);
  if (checked) box.appendChild(text("✓", { size: num(12), weight: "bold", color: "color.on-primary", name: "Check" }));
  return box;
}

// One table row (r = -1 for the header). Columns share the width equally; "end" columns align right.
/** @param {FrameNode} table */
function tableRow(table, node, cells, r, on, pc) {
  var head = r < 0, cols = Array.isArray(node.columns) ? node.columns : [];
  var sortable = node.sortable === true ? null : (Array.isArray(node.sortable) ? node.sortable : []);
  var row = alFrame(head ? "Header" : "Row " + (r + 1), "HORIZONTAL");
  row.counterAxisAlignItems = "CENTER";
  row.fills = [paintOf(head ? "color.surface-2" : (on ? "color.primary-subtle" : "color.surface"))];
  if (!head) edgeStroke(row, "color.border", "Top");
  attach(row, table, "FILL", "HUG");
  var py = dimOf("space.3", null, 12), px = dimOf("space.4", null, 16);
  var small = dimOf("font.size.label", null, 14);
  if (node.selectable) {
    var sel = alFrame("Select", "HORIZONTAL");
    sel.counterAxisAlignItems = "CENTER";
    pad4(sel, py, px, py, px);
    attach(sel, row, "HUG", "HUG");
    checkBox(sel, !head && on);
  }
  for (var c = 0; c < cols.length; c++) {
    var col = cols[c], label = col && typeof col === "object" ? String(col.label || "") : String(col);
    var end = col && typeof col === "object" && col.align === "end";
    var cell = alFrame((head ? "Column / " : "Cell / ") + label, "HORIZONTAL");
    cell.counterAxisAlignItems = "CENTER";
    cell.primaryAxisAlignItems = end ? "MAX" : "MIN";
    setNum(cell, "itemSpacing", dimOf("space.1", null, 4));
    pad4(cell, py, px, py, px);
    attach(cell, row, "FILL", "HUG");
    var v = head ? label : (c < cells.length ? cells[c] : "");
    if (!head && v && typeof v === "object") {
      DRAW.Badge({ text: String(v.text || ""), tone: v.tone }, cell, { dir: "HORIZONTAL", align: "center", screen: pc.screen });
      continue;
    }
    var t = text(v === null || v === undefined ? "" : String(v), { size: small, weight: head ? "medium" : "regular", color: head ? "color.text-muted" : "color.text", name: head ? "Label" : "Text" });
    cell.appendChild(t);
    if (end) t.textAlignHorizontal = "RIGHT";
    if (head && (sortable === null || sortable.indexOf(c) >= 0)) cell.appendChild(text("↕", { size: small, color: "color.text-muted", name: "Sort" }));
  }
}

/** @param {FrameNode} parent */
function pageItem(parent, label, current, disabled) {
  var f = alFrame("Page / " + label, "HORIZONTAL");
  f.primaryAxisAlignItems = "CENTER";
  f.counterAxisAlignItems = "CENTER";
  var py = dimOf("space.2", null, 8), px = dimOf("space.3", null, 12);
  pad4(f, py, px, py, px);
  radius(f, dimOf("radius.md", null, 8));
  f.fills = current ? [paintOf("color.primary")] : [];
  attach(f, parent, "HUG", "HUG");
  f.appendChild(text(label, { size: dimOf("font.size.label", null, 14), weight: current ? "semibold" : "regular",
    color: current ? "color.on-primary" : (disabled ? "color.text-muted" : "color.text"), name: "Label" }));
  return f;
}

// 1 … 4 5 6 … 12: first, last and the neighbours of the current page; null marks a gap.
function pageList(page, pages) {
  var out = [];
  for (var p = 1; p <= pages; p++) {
    if (pages <= 7 || p === 1 || p === pages || Math.abs(p - page) <= 1) out.push(p);
    else if (out[out.length - 1] !== null) out.push(null);
  }
  return out;
}

function controlRow(type, node, parent, pc) {
  var row = alFrame(type + " / " + String(node.label || ""), "HORIZONTAL");
  row.counterAxisAlignItems = "CENTER";
  setNum(row, "itemSpacing", dimOf("space.2", null, 8));
  attach(row, parent, widthFor(node, pc, "inline"), "HUG");
  return row;
}

function controlLabel(row, node) {
  if (node.label) row.appendChild(text(node.label, { size: dimOf("font.size.body", null, 16), name: "Label" }));
}

/** @param {FrameNode} parent */
function line(parent, pc) {
  var r = figma.createRectangle();
  r.name = "Divider";
  r.fills = [paintOf("color.border")];
  var vertical = pc.dir !== "HORIZONTAL";
  r.resize(vertical ? 100 : 1, vertical ? 1 : 24);
  parent.appendChild(r);
  if (vertical) sizeAxis(r, "Horizontal", "FILL");
  else if (pc.align === "stretch") sizeAxis(r, "Vertical", "FILL");
  return r;
}

// ------------------------------------------------------------------ library instances

async function importKey(key) {
  if (Object.prototype.hasOwnProperty.call(ctx.imports, key)) return ctx.imports[key];
  var found = null, errors = [];
  if (typeof figma.importComponentSetByKeyAsync === "function") {
    try {
      var set = await figma.importComponentSetByKeyAsync(key);
      // A component set's children are its variants (ComponentNode); the typings only promise SceneNode.
      var main = set ? (set.defaultVariant || /** @type {ComponentNode} */ (set.children && set.children[0])) : null;
      if (main) found = { set: set, main: main };
    } catch (e) { errors.push(errText(e)); }
  }
  if (!found && typeof figma.importComponentByKeyAsync === "function") {
    try {
      var comp = await figma.importComponentByKeyAsync(key);
      var parentSet = null;
      try { parentSet = comp && comp.parent && comp.parent.type === "COMPONENT_SET" ? comp.parent : null; } catch (e2) { parentSet = null; }
      if (comp) found = { set: parentSet, main: comp };
    } catch (e) { errors.push(errText(e)); }
  }
  if (!found) warn("Library key " + key + " could not be imported (" + (errors.join("; ") || "no import API") + "); drawing from tokens. Enable the library in this file to get instances.");
  ctx.imports[key] = found;
  return found;
}

async function placeInstance(node, type, fig, parent, pc) {
  var src = await importKey(String(fig.key));
  if (!src) return null;
  var inst = null;
  try {
    inst = src.main.createInstance();
    parent.appendChild(inst);
    var variant = node.variant || node.tone;
    if (fig.variantProperty && variant) {
      var props = {};
      var defs = null;
      try { defs = src.set ? src.set.componentPropertyDefinitions : null; } catch (e) { defs = null; }
      var options = defs && defs[fig.variantProperty] ? defs[fig.variantProperty].variantOptions : null;
      var match = pickOption(options, variant);
      if (match || !options) {
        props[fig.variantProperty] = match || String(variant);
        try { inst.setProperties(props); }
        catch (e) { warnOnce("variant:" + type + ":" + variant, type + ": could not set " + fig.variantProperty + "=" + variant + " (" + errText(e) + "); kept the default variant."); }
      } else {
        warnOnce("variant:" + type + ":" + variant, type + ": library has no " + fig.variantProperty + " “" + variant + "”; kept the default variant.");
      }
    }
    var label = textOf(node);
    if (fig.textProperty && label !== null) {
      var key = findTextProperty(inst, String(fig.textProperty));
      if (key) {
        await loadInstanceFonts(inst);
        var tp = {};
        tp[key] = String(label);
        inst.setProperties(tp);
      } else {
        warnOnce("textprop:" + type, type + ": library component has no text property “" + fig.textProperty + "”.");
      }
    }
    inst.name = type + (variant ? " / " + variant : "");
    var w = node.full ? "FILL" : widthFor(node, pc, INLINE[type] ? "inline" : "block");
    if (w !== "HUG") sizeAxis(inst, "Horizontal", w);
    return inst;
  } catch (e) {
    if (inst) { try { inst.remove(); } catch (e3) { /* already gone */ } }
    warn(type + ": library instance failed (" + errText(e) + "); drawn from tokens instead.");
    return null;
  }
}

function pickOption(options, wanted) {
  if (!options || !options.length) return null;
  var w = String(wanted).toLowerCase();
  for (var i = 0; i < options.length; i++) if (String(options[i]).toLowerCase() === w) return options[i];
  return null;
}

/** @param {InstanceNode} inst */
function findTextProperty(inst, name) {
  var props = inst.componentProperties || {};
  var keys = Object.keys(props);
  for (var i = 0; i < keys.length; i++) {
    var k = keys[i];
    if (props[k] && props[k].type === "TEXT" && (k.indexOf(name + "#") === 0 || k === name)) return k;
  }
  return null;
}

/** @param {InstanceNode} inst */
async function loadInstanceFonts(inst) {
  var texts = inst.findAllWithCriteria({ types: ["TEXT"] });
  var seen = {};
  for (var i = 0; i < texts.length; i++) {
    var t = texts[i], fonts = [];
    if (t.fontName === figma.mixed) fonts = t.getRangeAllFontNames(0, t.characters.length);
    else fonts = [t.fontName];
    for (var j = 0; j < fonts.length; j++) {
      var id = fonts[j].family + "|" + fonts[j].style;
      if (seen[id]) continue;
      seen[id] = true;
      await figma.loadFontAsync(fonts[j]);
    }
  }
}

// ------------------------------------------------------------------ variables

async function setupVariables() {
  var V = figma.variables;
  if (!V || typeof V.createVariableCollection !== "function") {
    warn("This Figma has no Variables API; colours and sizes are plain values.");
    return;
  }
  try {
    var ds = ctx.bundle.designSystem;
    var name = ds && ds.name ? ds.name + " tokens" : "SDD tokens";
    // Only the async readers: the sync getLocalVariable*() throw under documentAccess dynamic-page.
    var cols = await V.getLocalVariableCollectionsAsync();
    /** @type {VariableCollection} */
    var col = null;
    for (var i = 0; i < cols.length; i++) if (cols[i].name === name) { col = cols[i]; break; }
    var fresh = !col;
    if (fresh) col = V.createVariableCollection(name);
    var modeId = col.defaultModeId || col.modes[0].modeId;
    if (fresh && ds && ds.theme) { try { col.renameMode(modeId, String(ds.theme)); } catch (e) { /* keep "Mode 1" */ } }
    var all = await V.getLocalVariablesAsync();
    var existing = {};
    for (var a = 0; a < all.length; a++) if (all[a].variableCollectionId === col.id) existing[all[a].name] = all[a];

    var created = 0, updated = 0, paths = Object.keys(ctx.tokens);
    for (var p = 0; p < paths.length; p++) {
      var path = paths[p], kind = variableKind(path);
      if (!kind) continue;
      var raw = ctx.tokens[path];
      var value = kind === "COLOR" ? parseColor(raw) : toNumber(raw);
      if (value === null) continue;
      var vname = path.split(".").join("/");
      var v = existing[vname];
      if (v && v.resolvedType !== kind) { warn("Variable " + vname + " exists with type " + v.resolvedType + "; left it alone."); continue; }
      if (!v) {
        v = V.createVariable(vname, col, kind);
        decorate(v, path, kind);
        created++;
      } else {
        updated++;
      }
      v.setValueForMode(modeId, value);
      ctx.vars[path] = v;
    }
    ctx.stats.variables = created + updated;
    ctx.stats.variablesCreated = created;
    ctx.stats.collection = name;
    log("Variables in “" + name + "”: " + created + " created, " + updated + " updated.");
  } catch (e) {
    ctx.vars = {};
    warn("Variables skipped (" + errText(e) + "); colours and sizes are plain values.");
  }
}

/** @returns {VariableResolvedDataType | null} */
function variableKind(path) {
  if (/^color\./.test(path)) return "COLOR";
  if (/^(space|radius)\./.test(path) || /^font\.size\./.test(path)) return "FLOAT";
  return null;
}

/** @param {Variable} v */
function decorate(v, path, kind) {
  try { v.description = "sdd token " + path; } catch (e) { /* optional */ }
  try { v.setVariableCodeSyntax("WEB", "var(--" + path.replace(/\./g, "-") + ")"); } catch (e) { /* optional */ }
  /** @type {VariableScope[]} */
  var scopes = kind === "COLOR" ? ["ALL_FILLS", "STROKE_COLOR"]
    : /^radius\./.test(path) ? ["CORNER_RADIUS"]
    : /^font\.size\./.test(path) ? ["FONT_SIZE"] : ["GAP", "WIDTH_HEIGHT"];
  try { v.scopes = scopes; } catch (e) { /* default: all scopes */ }
}

/** @param {FrameNode | RectangleNode} node @param {VariableBindableNodeField} field */
function bindField(node, field, path) {
  /** @type {Variable} */
  var v = path ? ctx.vars[path] : null;
  if (!v) return;
  try { node.setBoundVariable(field, v); ctx.stats.bindings++; }
  catch (e) { warnOnce("bind:" + field, "Could not bind " + field + " to a variable (" + errText(e) + ")."); }
}

// ------------------------------------------------------------------ fonts and text

async function loadFonts() {
  var families = [];
  var dsFamily = String(ctx.tokens["font.family.sans"] || "").split(",")[0].replace(/["']/g, "").trim();
  if (dsFamily && !/^(-|ui-)|system|^(sans-serif|serif|monospace)$/i.test(dsFamily)) families.push(dsFamily);
  if (families.indexOf("Inter") < 0) families.push("Inter");
  if (families.indexOf("Roboto") < 0) families.push("Roboto");
  for (var i = 0; i < families.length && !ctx.fonts; i++) {
    ctx.fonts = await loadFamily(families[i]);
    if (ctx.fonts) ctx.fontFamily = families[i];
  }
  if (!ctx.fonts) {
    var list = await figma.listAvailableFontsAsync();
    if (!list || !list.length) throw new Error("No fonts are available in this Figma.");
    var firstFont = list[0].fontName;
    ctx.fonts = await loadFamily(firstFont.family);
    if (!ctx.fonts) {
      await figma.loadFontAsync(firstFont);
      ctx.fonts = { regular: firstFont, medium: firstFont, semibold: firstFont, bold: firstFont };
    }
    ctx.fontFamily = firstFont.family;
  }
  if (ctx.fontFamily !== families[0]) warn(families[0] + " is not available; text uses " + ctx.fontFamily + ".");
  log("Font: " + ctx.fontFamily + ".");
}

async function loadFamily(family) {
  var regular = await firstLoadable(family, ["Regular", "Book", "Normal", "Roman"]);
  if (!regular) return null;
  var medium = (await firstLoadable(family, ["Medium"])) || regular;
  var bold = (await firstLoadable(family, ["Bold"])) || medium;
  var semibold = (await firstLoadable(family, ["Semi Bold", "SemiBold", "Semibold", "Demi Bold"])) || bold;
  return { regular: regular, medium: medium, semibold: semibold, bold: bold };
}

async function firstLoadable(family, styles) {
  for (var i = 0; i < styles.length; i++) {
    var font = { family: family, style: styles[i] };
    try { await figma.loadFontAsync(font); return font; } catch (e) { /* try the next style */ }
  }
  return null;
}

function text(chars, o) {
  var t = figma.createText();
  t.fontName = ctx.fonts[o.weight || "regular"];
  t.characters = String(chars);
  var size = o.size || dimOf("font.size.body", null, 16);
  t.fontSize = size.v;
  if (size.path && ctx.vars[size.path]) bindFontSize(t, ctx.vars[size.path]);
  t.fills = [paintOf(o.color || "color.text")];
  if (o.underline) t.textDecoration = "UNDERLINE";
  if (o.align) t.textAlignHorizontal = o.align;
  t.name = o.name || "Text";
  return t;
}

/** @param {TextNode} t @param {Variable} v */
function bindFontSize(t, v) {
  try { t.setBoundVariable("fontSize", v); ctx.stats.bindings++; return; } catch (e) { /* try range binding */ }
  try { t.setRangeBoundVariable(0, t.characters.length, "fontSize", v); ctx.stats.bindings++; } catch (e) { /* plain size */ }
}

/** @param {TextNode} t @param {FrameNode} parent @param {any} pc @param {any} [node] */
function placeText(t, parent, pc, node) {
  parent.appendChild(t);
  var w = node ? widthFor(node, pc, "text") : (pc.dir === "VERTICAL" || pc.cell ? "FILL" : "HUG");
  if (w === "FILL" || typeof w === "number") {
    sizeAxis(t, "Horizontal", w);
    setAutoHeight(t);
  }
  if (pc.dir === "VERTICAL" && (pc.align === "center" || pc.align === "end")) t.textAlignHorizontal = pc.align === "center" ? "CENTER" : "RIGHT";
  return t;
}

/** @param {TextNode} t */
function setAutoHeight(t) {
  try { t.textAutoResize = "HEIGHT"; } catch (e) { /* keeps current resize mode */ }
}

// ------------------------------------------------------------------ layout helpers

function alFrame(name, dir) {
  var f = figma.createFrame();
  f.name = name;
  f.layoutMode = dir;
  f.fills = [];
  f.clipsContent = false;
  f.itemSpacing = 0;
  f.paddingTop = 0; f.paddingRight = 0; f.paddingBottom = 0; f.paddingLeft = 0;
  f.primaryAxisSizingMode = "AUTO";
  f.counterAxisSizingMode = "AUTO";
  return f;
}

// Append first, then size: Figma rejects FILL/HUG on a node outside an auto-layout parent.
// Fixed (numeric) sizes go first: resize() can reset an axis that was already FILL or HUG.
/** @param {SceneNode & LayoutMixin} n @param {BaseNode & ChildrenMixin} parent */
function attach(n, parent, w, h) {
  parent.appendChild(n);
  if (typeof w === "number") sizeAxis(n, "Horizontal", w);
  if (typeof h === "number") sizeAxis(n, "Vertical", h);
  if (w && typeof w !== "number") sizeAxis(n, "Horizontal", w);
  if (h && typeof h !== "number") sizeAxis(n, "Vertical", h);
  return n;
}

/** @param {SceneNode & LayoutMixin} n */
function sizeAxis(n, axis, mode) {
  if (typeof mode === "number") {
    try {
      if (axis === "Horizontal") n.resize(mode, Math.max(1, n.height));
      else n.resize(Math.max(1, n.width), mode);
    } catch (e) { warnOnce("resize", "Could not resize " + n.name + " (" + errText(e) + ")."); }
    mode = "FIXED";
  }
  try { n["layoutSizing" + axis] = mode; }
  catch (e) { warnOnce("sizing:" + axis + mode, "Could not set " + axis.toLowerCase() + " sizing " + mode + " on " + n.name + " (" + errText(e) + ")."); }
}

function widthFor(node, pc, kind) {
  var w = node ? node.width : undefined;
  if (w === "fill") return "FILL";
  if (w === "hug") return kind === "text" || kind === "block" || kind === "inline" || kind === "field" ? "HUG" : null;
  if (typeof w === "number" && w > 0) return w;
  if (typeof w === "string" && /^\d+(\.\d+)?(px)?$/.test(w.trim())) return parseFloat(w);
  if (pc.cell) return "FILL";
  if (pc.dir === "VERTICAL") return kind === "inline" ? "HUG" : "FILL";
  return kind === "field" ? 280 : "HUG";
}

function heightFor(pc) {
  return pc.dir === "HORIZONTAL" && pc.align === "stretch" ? "FILL" : "HUG";
}

function num(v) { return { v: v, path: null }; }

// A size from a token path ("space.4"), a pixel number, or "16px"; path is kept for binding.
function dimOf(value, fallbackPath, fallbackPx) {
  if (value === undefined || value === null || value === "") {
    return fallbackPath ? dimOf(fallbackPath, null, fallbackPx) : num(fallbackPx || 0);
  }
  if (typeof value === "number") return num(value);
  var s = String(value).trim();
  var m = /^(-?\d+(?:\.\d+)?)(px)?$/.exec(s);
  if (m) return num(parseFloat(m[1]));
  var t = tokenNumber(s);
  if (t !== null) return { v: t, path: s };
  warnOnce("token:" + s, "Unknown size token “" + s + "”; used " + (fallbackPx || 0) + " px.");
  return num(fallbackPx || 0);
}

function tokenNumber(path) {
  var v = toNumber(ctx.tokens[path]);
  if (v !== null) return v;
  if (typeof DEFAULT_TOKENS[path] === "number") return DEFAULT_TOKENS[path];
  var sp = /^space\.(\d+)$/.exec(path);
  return sp ? 4 * parseInt(sp[1], 10) : null;
}

function toNumber(v) {
  if (typeof v === "number" && isFinite(v)) return v;
  if (typeof v === "string") {
    var m = /^\s*(-?\d+(?:\.\d+)?)\s*(px)?\s*$/.exec(v);
    if (m) return parseFloat(m[1]);
  }
  return null;
}

/** @param {FrameNode} node @param {"itemSpacing" | "paddingTop" | "paddingRight" | "paddingBottom" | "paddingLeft"} field */
function setNum(node, field, d) {
  node[field] = d.v;
  bindField(node, field, d.path);
}

/** @param {FrameNode} f */
function pad4(f, t, r, b, l) {
  setNum(f, "paddingTop", t);
  setNum(f, "paddingRight", r);
  setNum(f, "paddingBottom", b);
  setNum(f, "paddingLeft", l);
}

/** @param {FrameNode} f */
function applyPadding(f, value) {
  if (value === undefined || value === null) return;
  var parts = Array.isArray(value) ? value : (typeof value === "string" && /\s/.test(value.trim()) ? value.trim().split(/\s+/) : [value]);
  var d = parts.map(function (p) { return dimOf(p, null, 0); });
  var top = d[0], right = d.length > 1 ? d[1] : d[0], bottom = d.length > 2 ? d[2] : d[0], left = d.length > 3 ? d[3] : right;
  pad4(f, top, right, bottom, left);
}

/** @param {FrameNode | RectangleNode} f */
function radius(f, d) {
  f.cornerRadius = d.v;
  if (d.path && ctx.vars[d.path]) {
    bindField(f, "topLeftRadius", d.path);
    bindField(f, "topRightRadius", d.path);
    bindField(f, "bottomLeftRadius", d.path);
    bindField(f, "bottomRightRadius", d.path);
  }
}

/** @param {FrameNode} f @param {string} path @param {number} [weight] */
function stroke(f, path, weight) {
  f.strokes = [paintOf(path)];
  f.strokeWeight = weight || 1;
  f.strokeAlign = "INSIDE";
}

/** @param {FrameNode} f @param {string} path @param {string} side @param {number} [weight] */
function edgeStroke(f, path, side, weight) {
  var w = weight || 1;
  f.strokes = [paintOf(path)];
  f.strokeAlign = "INSIDE";
  try {
    f.strokeTopWeight = side === "Top" ? w : 0;
    f.strokeBottomWeight = side === "Bottom" ? w : 0;
    f.strokeLeftWeight = side === "Left" ? w : 0;
    f.strokeRightWeight = side === "Right" ? w : 0;
  } catch (e) { f.strokeWeight = w; }
}

// ------------------------------------------------------------------ colour

function colorValue(path) {
  var c = parseColor(ctx.tokens[path]);
  return c || parseColor(DEFAULT_TOKENS[path]);
}

/** @returns {SolidPaint} */
function paintOf(path, fallbackPath) {
  var c = colorValue(path);
  if (!c && fallbackPath) { path = fallbackPath; c = colorValue(path); }
  if (!c) { warnOnce("color:" + path, "No colour for " + path + "; used the text colour."); path = "color.text"; c = colorValue(path); }
  /** @type {SolidPaint} */
  var paint = { type: "SOLID", color: { r: c.r, g: c.g, b: c.b }, opacity: c.a };
  /** @type {Variable} */
  var v = ctx.vars[path];
  if (v) {
    try { paint = figma.variables.setBoundVariableForPaint(paint, "color", v); ctx.stats.bindings++; }
    catch (e) { warnOnce("paint", "Could not bind colours to variables (" + errText(e) + ")."); }
  }
  return paint;
}

function parseColor(v) {
  if (typeof v !== "string") return null;
  var s = v.trim();
  var m = /^#([0-9a-f]{3,8})$/i.exec(s);
  if (m) {
    var h = m[1];
    if (h.length === 3 || h.length === 4) h = h.split("").map(function (ch) { return ch + ch; }).join("");
    if (h.length !== 6 && h.length !== 8) return null;
    return {
      r: parseInt(h.slice(0, 2), 16) / 255, g: parseInt(h.slice(2, 4), 16) / 255, b: parseInt(h.slice(4, 6), 16) / 255,
      a: h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1
    };
  }
  m = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,/]+([\d.]+%?))?\s*\)$/i.exec(s);
  if (m) {
    var a = m[4] === undefined ? 1 : (m[4].slice(-1) === "%" ? parseFloat(m[4]) / 100 : parseFloat(m[4]));
    return { r: parseFloat(m[1]) / 255, g: parseFloat(m[2]) / 255, b: parseFloat(m[3]) / 255, a: a };
  }
  return null;
}

// ------------------------------------------------------------------ small helpers

function textOf(node) {
  if (node.label !== undefined && node.label !== null) return node.label;
  if (node.text !== undefined && node.text !== null) return node.text;
  if (node.title !== undefined && node.title !== null) return node.title;
  return null;
}

function itemText(item) {
  if (item && typeof item === "object") return String(item.label || item.text || item.title || "");
  return String(item);
}

function bullets(value) {
  return new Array(Math.min(Math.max(String(value).length, 8), 24) + 1).join("•");
}

function initials(name) {
  var parts = String(name || "?").trim().split(/\s+/);
  return (parts[0].charAt(0) + (parts.length > 1 ? parts[parts.length - 1].charAt(0) : "")).toUpperCase();
}

function parseRatio(r) {
  if (typeof r === "number" && r > 0) return r;
  var m = /^\s*(\d+(?:\.\d+)?)\s*[:/x]\s*(\d+(?:\.\d+)?)\s*$/.exec(String(r || ""));
  return m && parseFloat(m[2]) > 0 ? parseFloat(m[1]) / parseFloat(m[2]) : null;
}

function bump(map, key) { map[key] = (map[key] || 0) + 1; }

function total(map) {
  var n = 0, keys = Object.keys(map);
  for (var i = 0; i < keys.length; i++) n += map[keys[i]];
  return n;
}

function errText(e) {
  if (!e) return "unknown error";
  return e.message ? String(e.message) : String(e);
}

function post(msg) {
  try { figma.ui.postMessage(msg); } catch (e) { /* UI closed */ }
}

function log(text) { post({ type: "log", level: "info", text: text }); }

function warn(text) {
  if (ctx) ctx.warnings.push(text);
  post({ type: "log", level: "warn", text: text });
}

function warnOnce(key, text) {
  if (ctx.once[key]) return;
  ctx.once[key] = true;
  warn(text);
}
