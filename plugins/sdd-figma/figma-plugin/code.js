/*
 * SDD Kit Import: Figma plugin main thread. MIT licence, HomeProgrammer1.
 *
 * Reads one sdd-kit figma/bundle.json (sent by ui.html) and builds, in the open file:
 *   "<feature> · How it works"  every diagram SVG, stacked, each under a heading
 *   "<feature> · Screens"       one auto-layout frame per screen, prototype links,
 *                               token variables bound to fills, gaps, padding, radii
 * Re-running replaces only what this plugin generated (pluginData sdd=generated).
 *
 * Plain JavaScript on purpose: no optional chaining, no nullish coalescing,
 * no libraries, no network. Sizing (FILL/HUG) is set only after a node is
 * appended to its auto-layout parent.
 */
"use strict";

var MARK = "sdd";
var GENERATED = "generated";
var ROLE = "sddRole";

var DEFAULT_TOKENS = {
  "color.background": "#f7f7f8", "color.surface": "#ffffff", "color.surface-2": "#eeeef0",
  "color.text": "#18181d", "color.text-muted": "#5b5b66", "color.border": "#dcdce0",
  "color.primary": "#4338ca", "color.on-primary": "#ffffff", "color.primary-subtle": "#eef2ff",
  "color.danger": "#c62828", "color.danger-subtle": "#fdecec",
  "color.success": "#1b7a3a", "color.success-subtle": "#e8f5ec",
  "color.warning": "#8a5a00", "color.warning-subtle": "#fdf4e3",
  "color.info": "#1d5fbf", "color.info-subtle": "#e9f1fc",
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
var INLINE = { Button: 1, Link: 1, Badge: 1, Checkbox: 1, Toggle: 1, Avatar: 1 };
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
    stats: { diagrams: 0, screens: 0, links: 0, variables: 0, variablesCreated: 0, bindings: 0, collection: "" }
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
    var dPage = await generatedPage(feature + " · How it works");
    built.push(dPage);
    log("Importing " + diagrams.length + " diagram(s)…");
    await buildDiagrams(dPage, diagrams);
  }
  var sPage = null;
  if (screens.length) {
    sPage = await generatedPage(feature + " · Screens");
    built.push(sPage);
    log("Building " + screens.length + " screen(s)…");
    await buildScreens(sPage, doc, screens, feature);
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
  var summary = feature + ": " + pages.length + " page(s), " + s.screens + " screen(s), " + s.diagrams +
    " diagram(s), " + s.links + " prototype link(s), " + s.variables + " variable(s); components " +
    nInst + " instanced / " + nDrawn + " drawn" +
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
    warnings: ctx.warnings,
    seconds: Math.round((Date.now() - t0) / 100) / 10
  };
}

// ------------------------------------------------------------------ pages

function isGenerated(node) {
  try { return node.getPluginData(MARK) === GENERATED; } catch (e) { return false; }
}

function mark(node, role) {
  node.setPluginData(MARK, GENERATED);
  node.setPluginData(ROLE, role);
}

async function generatedPage(name) {
  var pages = figma.root.children, page = null, clash = false;
  for (var i = 0; i < pages.length; i++) {
    if (pages[i].name !== name) continue;
    if (isGenerated(pages[i])) { page = pages[i]; break; }
    clash = true;
  }
  if (!page) {
    page = figma.createPage();
    page.name = name;
    page.setPluginData(MARK, GENERATED);
    if (clash) warn("A page named “" + name + "” exists but was not made by this plugin; left it alone and created a new one.");
  }
  if (typeof page.loadAsync === "function") await page.loadAsync();
  await figma.setCurrentPageAsync(page);
  var kids = page.children.slice(), removed = 0;
  for (var k = 0; k < kids.length; k++) {
    if (isGenerated(kids[k])) { kids[k].remove(); removed++; }
  }
  log((removed ? "Rebuilding " : "Creating ") + "page “" + name + "”" + (removed ? " (" + removed + " generated layers replaced)" : "") + ".");
  return page;
}

// ------------------------------------------------------------------ diagrams

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
    if (!covered[g] && flows[g]) warn("Flow " + flows[g].from + " → " + flows[g].to + ": no Button or Link “" + flows[g].on + "” on " + flows[g].from + ".");
  }
}

async function setClick(node, destId) {
  var nav = { type: "NODE", destinationId: destId, navigation: "NAVIGATE", transition: null };
  var tries = [
    { trigger: { type: "ON_CLICK" }, actions: [nav] },
    { trigger: { type: "ON_CLICK" }, action: { type: "NODE", destinationId: destId, navigation: "NAVIGATE", transition: null, preserveScrollPosition: false } }
  ];
  var last = null;
  for (var i = 0; i < tries.length; i++) {
    try {
      if (typeof node.setReactionsAsync === "function") await node.setReactionsAsync([tries[i]]);
      else node.reactions = [tries[i]];
      return true;
    } catch (e) { last = e; }
  }
  warn("Prototype link on “" + node.name + "” failed (" + errText(last) + ").");
  return false;
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
    var box = alFrame("Control", "HORIZONTAL");
    box.primaryAxisAlignItems = "CENTER";
    box.counterAxisAlignItems = "CENTER";
    radius(box, dimOf("radius.sm", null, 4));
    if (node.checked) box.fills = [paintOf("color.primary")];
    else { box.fills = [paintOf("color.surface")]; stroke(box, "color.border", 1.5); }
    attach(box, row, 18, 18);
    if (node.checked) box.appendChild(text("✓", { size: num(12), weight: "bold", color: "color.on-primary", name: "Check" }));
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
      var main = set ? (set.defaultVariant || (set.children && set.children[0])) : null;
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

function findTextProperty(inst, name) {
  var props = inst.componentProperties || {};
  var keys = Object.keys(props);
  for (var i = 0; i < keys.length; i++) {
    var k = keys[i];
    if (props[k] && props[k].type === "TEXT" && (k.indexOf(name + "#") === 0 || k === name)) return k;
  }
  return null;
}

async function loadInstanceFonts(inst) {
  var texts = typeof inst.findAllWithCriteria === "function"
    ? inst.findAllWithCriteria({ types: ["TEXT"] })
    : inst.findAll(function (n) { return n.type === "TEXT"; });
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
    var cols = typeof V.getLocalVariableCollectionsAsync === "function" ? await V.getLocalVariableCollectionsAsync() : V.getLocalVariableCollections();
    var col = null;
    for (var i = 0; i < cols.length; i++) if (cols[i].name === name) { col = cols[i]; break; }
    var fresh = !col;
    if (fresh) col = V.createVariableCollection(name);
    var modeId = col.defaultModeId || col.modes[0].modeId;
    if (fresh && ds && ds.theme) { try { col.renameMode(modeId, String(ds.theme)); } catch (e) { /* keep "Mode 1" */ } }
    var all = typeof V.getLocalVariablesAsync === "function" ? await V.getLocalVariablesAsync() : V.getLocalVariables();
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
        v = createVariable(V, vname, col, kind);
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

function variableKind(path) {
  if (/^color\./.test(path)) return "COLOR";
  if (/^(space|radius)\./.test(path) || /^font\.size\./.test(path)) return "FLOAT";
  return null;
}

function createVariable(V, name, col, kind) {
  try { return V.createVariable(name, col, kind); }
  catch (e) { return V.createVariable(name, col.id, kind); }
}

function decorate(v, path, kind) {
  try { v.description = "sdd token " + path; } catch (e) { /* optional */ }
  try { v.setVariableCodeSyntax("WEB", "var(--" + path.replace(/\./g, "-") + ")"); } catch (e) { /* optional */ }
  var scopes = kind === "COLOR" ? ["ALL_FILLS", "STROKE_COLOR"]
    : /^radius\./.test(path) ? ["CORNER_RADIUS"]
    : /^font\.size\./.test(path) ? ["FONT_SIZE"] : ["GAP", "WIDTH_HEIGHT"];
  try { v.scopes = scopes; } catch (e) { /* default: all scopes */ }
}

function bindField(node, field, path) {
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

function bindFontSize(t, v) {
  try { t.setBoundVariable("fontSize", v); ctx.stats.bindings++; return; } catch (e) { /* try range binding */ }
  try { t.setRangeBoundVariable(0, t.characters.length, "fontSize", v); ctx.stats.bindings++; } catch (e) { /* plain size */ }
}

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
function attach(n, parent, w, h) {
  parent.appendChild(n);
  if (typeof w === "number") sizeAxis(n, "Horizontal", w);
  if (typeof h === "number") sizeAxis(n, "Vertical", h);
  if (w && typeof w !== "number") sizeAxis(n, "Horizontal", w);
  if (h && typeof h !== "number") sizeAxis(n, "Vertical", h);
  return n;
}

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

function setNum(node, field, d) {
  node[field] = d.v;
  bindField(node, field, d.path);
}

function pad4(f, t, r, b, l) {
  setNum(f, "paddingTop", t);
  setNum(f, "paddingRight", r);
  setNum(f, "paddingBottom", b);
  setNum(f, "paddingLeft", l);
}

function applyPadding(f, value) {
  if (value === undefined || value === null) return;
  var parts = Array.isArray(value) ? value : (typeof value === "string" && /\s/.test(value.trim()) ? value.trim().split(/\s+/) : [value]);
  var d = parts.map(function (p) { return dimOf(p, null, 0); });
  var top = d[0], right = d.length > 1 ? d[1] : d[0], bottom = d.length > 2 ? d[2] : d[0], left = d.length > 3 ? d[3] : right;
  pad4(f, top, right, bottom, left);
}

function radius(f, d) {
  f.cornerRadius = d.v;
  if (d.path && ctx.vars[d.path]) {
    bindField(f, "topLeftRadius", d.path);
    bindField(f, "topRightRadius", d.path);
    bindField(f, "bottomLeftRadius", d.path);
    bindField(f, "bottomRightRadius", d.path);
  }
}

function stroke(f, path, weight) {
  f.strokes = [paintOf(path)];
  f.strokeWeight = weight || 1;
  f.strokeAlign = "INSIDE";
}

function edgeStroke(f, path, side) {
  f.strokes = [paintOf(path)];
  f.strokeAlign = "INSIDE";
  try {
    f.strokeTopWeight = side === "Top" ? 1 : 0;
    f.strokeBottomWeight = side === "Bottom" ? 1 : 0;
    f.strokeLeftWeight = side === "Left" ? 1 : 0;
    f.strokeRightWeight = side === "Right" ? 1 : 0;
  } catch (e) { f.strokeWeight = 1; }
}

// ------------------------------------------------------------------ colour

function colorValue(path) {
  var c = parseColor(ctx.tokens[path]);
  return c || parseColor(DEFAULT_TOKENS[path]);
}

function paintOf(path, fallbackPath) {
  var c = colorValue(path);
  if (!c && fallbackPath) { path = fallbackPath; c = colorValue(path); }
  if (!c) { warnOnce("color:" + path, "No colour for " + path + "; used the text colour."); path = "color.text"; c = colorValue(path); }
  var paint = { type: "SOLID", color: { r: c.r, g: c.g, b: c.b } };
  if (c.a < 1) paint.opacity = c.a;
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
