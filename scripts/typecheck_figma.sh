#!/usr/bin/env bash
# Type-check plugins/sdd-figma/figma-plugin/code.js against Figma's official Plugin API typings,
# independently of the hand-written mock in scripts/test_figma_plugin.js.
#
# Usage: scripts/typecheck_figma.sh [NODE_MODULES [code.js]]   (or FIGMA_TYPECHECK_NODE_MODULES=...)
#   NODE_MODULES holds `typescript` and `@figma/plugin-typings`, installed outside this repository:
#     mkdir -p /tmp/figma-typecheck && cd /tmp/figma-typecheck && npm init -y \
#       && npm install --ignore-scripts typescript@6 @figma/plugin-typings
#     scripts/typecheck_figma.sh /tmp/figma-typecheck/node_modules
#
# 1. tsc --noEmit --allowJs --checkJs: wrong method names, argument and enum types. Non-strict,
#    because strict mode on untyped JavaScript reports only noise.
# 2. dynamic-page scan (needs the TypeScript JS API, i.e. typescript <= 6): deprecated signatures
#    and properties (the sync ones throw with "documentAccess": "dynamic-page"), deprecated keys in
#    object literals, and writes to properties the typings call read-only under dynamic-page.
# Exit 0 = clean or skipped (no NODE_MODULES given), 1 = findings, 2 = setup error.
set -euo pipefail

NM="${1:-${FIGMA_TYPECHECK_NODE_MODULES:-}}"
if [ -z "$NM" ]; then
  echo "SKIP: no node_modules with typescript and @figma/plugin-typings given (see the header of $0)."
  exit 0
fi
REPO="$(cd "$(dirname "$0")/.." && pwd)"
CODE="${2:-$REPO/plugins/sdd-figma/figma-plugin/code.js}"
[ -d "$NM" ] || { echo "ERROR: $NM is not a directory" >&2; exit 2; }
NM="$(cd "$NM" && pwd)"
TSC="$NM/typescript/bin/tsc"
TYPINGS="$NM/@figma/plugin-typings/index.d.ts"
for f in "$TSC" "$TYPINGS"; do
  [ -f "$f" ] || { echo "ERROR: $f not found; install typescript and @figma/plugin-typings into $NM" >&2; exit 2; }
done
command -v node >/dev/null || { echo "ERROR: node is not installed" >&2; exit 2; }

status=0
echo "tsc $(node "$TSC" --version | sed 's/^Version //') · @figma/plugin-typings $(node -p "require('$NM/@figma/plugin-typings/package.json').version")"
if node "$TSC" --noEmit --pretty false --allowJs --checkJs --strict false --skipLibCheck \
    --target es2017 --lib es2017 "$TYPINGS" "$CODE"; then
  echo "tsc: 0 errors"
else
  status=1
fi

node - "$NM" "$CODE" "$TYPINGS" <<'JS' || status=1
const path = require("path"), fs = require("fs");
const [nm, file, typings] = process.argv.slice(2);
let ts;
try { ts = require(path.join(nm, "typescript")); } catch (e) { ts = null; }
if (!ts || typeof ts.createLanguageService !== "function") {
  console.log("dynamic-page scan: skipped (this typescript has no JS API; use typescript <= 6)");
  process.exit(0);
}
const opts = { allowJs: true, checkJs: true, noEmit: true, strict: false, skipLibCheck: true,
  target: ts.ScriptTarget.ES2017, lib: ["lib.es2017.d.ts"], types: [] };
const files = [typings, file];
const host = {
  getScriptFileNames: () => files, getScriptVersion: () => "1", getCompilationSettings: () => opts,
  getScriptSnapshot: (f) => fs.existsSync(f) ? ts.ScriptSnapshot.fromString(fs.readFileSync(f, "utf8")) : undefined,
  getCurrentDirectory: () => process.cwd(), getDefaultLibFileName: (o) => ts.getDefaultLibFilePath(o),
  fileExists: ts.sys.fileExists, readFile: ts.sys.readFile, readDirectory: ts.sys.readDirectory,
  directoryExists: ts.sys.directoryExists, getDirectories: ts.sys.getDirectories
};
const ls = ts.createLanguageService(host, ts.createDocumentRegistry());
const program = ls.getProgram(), checker = program.getTypeChecker(), sf = program.getSourceFile(file);
const found = [];
const at = (pos, msg) => {
  const lc = sf.getLineAndCharacterOfPosition(pos);
  found.push(`${path.relative(process.cwd(), file)}(${lc.line + 1},${lc.character + 1}): ${msg}`);
};
for (const d of ls.getSuggestionDiagnostics(file)) {
  if (d.reportsDeprecated) at(d.start, "deprecated: " + ts.flattenDiagnosticMessageText(d.messageText, " "));
}
const docOf = (sym) => (sym && sym.declarations || []).filter((d) => d.getSourceFile().fileName.indexOf("plugin-typings") >= 0)
  .map((d) => ts.getJSDocCommentsAndTags(d).map((j) => j.getText()).join(" ")).join(" ");
(function visit(n) {
  if (ts.isPropertyAccessExpression(n) && ts.isBinaryExpression(n.parent) && n.parent.left === n &&
      n.parent.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
    const doc = docOf(checker.getSymbolAtLocation(n.name));
    if (/dynamic-page/.test(doc) && /read-only/.test(doc)) at(n.name.getStart(), `"${n.name.text}" is read-only with documentAccess dynamic-page`);
  }
  if (ts.isPropertyAssignment(n) && ts.isObjectLiteralExpression(n.parent) && ts.isIdentifier(n.name)) {
    const type = checker.getContextualType(n.parent);
    const prop = type && checker.getPropertyOfType(type, n.name.text);
    if (/@deprecated/.test(docOf(prop))) at(n.name.getStart(), `deprecated: object key "${n.name.text}"`);
  }
  ts.forEachChild(n, visit);
})(sf);
found.forEach((f) => console.log(f));
console.log("dynamic-page scan: " + found.length + " finding(s)");
process.exit(found.length ? 1 : 0);
JS

[ "$status" -eq 0 ] && echo "PASS: code.js matches the Figma Plugin API typings" || echo "FAIL: see above"
exit "$status"
