#!/usr/bin/env bash
# Runs one of the hook scripts next to this file with whichever Python 3 is
# installed (python3, python, or the Windows "py" launcher), so a machine
# without a "python3" command does not silently lose the guard.
#   run.sh <script.py> [args]   run it, passing stdin through
#   run.sh --which              print the Python command, exit 1 if none
# Uses shell builtins only, so it also works with a minimal PATH.
here="${BASH_SOURCE[0]%/*}"
[ "$here" = "${BASH_SOURCE[0]}" ] && here=.

find_py() {
  local c
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; then
      printf '%s\n' "$c"; return 0
    fi
  done
  if command -v py >/dev/null 2>&1 && py -3 -c '' >/dev/null 2>&1; then
    printf '%s\n' "py -3"; return 0
  fi
  return 1
}

if [ "$1" = "--which" ]; then find_py; exit $?; fi
script="$1"; shift
if py=$(find_py); then
  # $py is unquoted on purpose: "py -3" is two words.
  exec $py "$here/$script" "$@"
fi

mode="${SDD_GUARD:-${CLAUDE_PLUGIN_OPTION_GUARD_MODE:-sdd}}"
case "$script" in
  session_context.py)
    # Shown to the user once per session.
    printf '%s\n' '{"systemMessage": "sdd-kit: Python 3.8+ was not found (tried python3, python, py), so the sdd-kit guard is NOT checking tool calls in this session. Install Python 3 to turn it on."}'
    exit 0 ;;
  guard.py)
    if [ "$mode" = strict ]; then
      echo "sdd-kit guard: Python 3 was not found, and strict mode refuses tool calls it cannot check." >&2
      exit 2
    fi
    exit 0 ;;
  sdd_session.py)
    case " $* " in *" --status "*) echo "Python 3 was not found, so the sdd-kit guard is not running." ;; esac
    exit 1 ;;
  *) exit 0 ;;
esac
