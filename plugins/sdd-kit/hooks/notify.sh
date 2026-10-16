#!/usr/bin/env bash
# Desktop notification. Opt in with SDD_NOTIFY=1 (e.g. in settings.local.json env).
[ "${SDD_NOTIFY:-0}" = "1" ] || exit 0
cat >/dev/null
msg="${1:-Claude Code}"
if command -v osascript >/dev/null; then osascript -e "display notification \"$msg\" with title \"Claude Code\""
elif command -v notify-send >/dev/null; then notify-send "Claude Code" "$msg"
elif command -v powershell.exe >/dev/null; then powershell.exe -NoProfile -Command "[console]::beep(800,200)"
fi
exit 0
