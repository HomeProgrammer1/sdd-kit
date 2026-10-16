#!/usr/bin/env bash
# PostToolUse(Write|Edit): during sdd-kit runs, format the edited file with the
# project's own formatter if one is installed. Never blocks: always exits 0.
input=$(cat)
PY=$(bash "$(dirname "$0")/run.sh" --which) || exit 0
file=$(printf '%s' "$input" | $PY -c 'import sys,json; print((json.load(sys.stdin).get("tool_input") or {}).get("file_path",""))' 2>/dev/null)
[ -z "$file" ] || [ ! -f "$file" ] && exit 0
# Only sdd-kit's own work, and only if the plugin option allows it, so other
# plugins and ad-hoc edits are never reformatted behind the user's back.
[ "${CLAUDE_PLUGIN_OPTION_FORMAT_ON_EDIT:-true}" = "false" ] && exit 0
[ "${SDD_FORMAT:-}" = "off" ] && exit 0
printf '%s' "$input" | $PY "$(dirname "$0")/sdd_session.py" || exit 0
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

case "$file" in
  *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|*.json|*.css|*.scss|*.html|*.vue|*.svelte|*.md|*.yml|*.yaml)
    [ -x node_modules/.bin/prettier ] && node_modules/.bin/prettier --write "$file" >/dev/null 2>&1 ;;
  *.py)
    if command -v ruff >/dev/null; then ruff format "$file" >/dev/null 2>&1
    elif command -v black >/dev/null; then black -q "$file" >/dev/null 2>&1; fi ;;
  *.go)    command -v gofmt >/dev/null && gofmt -w "$file" ;;
  *.rs)    command -v rustfmt >/dev/null && rustfmt "$file" >/dev/null 2>&1 ;;
  *.dart)  command -v dart >/dev/null && dart format "$file" >/dev/null 2>&1 ;;
  *.swift) command -v swiftformat >/dev/null && swiftformat "$file" >/dev/null 2>&1 ;;
  *.kt|*.kts) command -v ktlint >/dev/null && ktlint -F "$file" >/dev/null 2>&1 ;;
esac
exit 0
