#!/usr/bin/env python3
"""SessionStart: print open SDD runs so a new or resumed session knows where
work stands. Stdout of a SessionStart hook is added to Claude's context."""
import json
import os
from pathlib import Path

try:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
    lines = []
    for state_file in sorted(root.glob("specs/*/state.json")):
        s = json.loads(state_file.read_text(encoding="utf-8"))
        if s.get("phase") in ("done", "abandoned"):
            continue
        pause = s.get("pause") or {}
        lines.append(
            f"- {state_file.parent.name}: phase={s.get('phase')} level={s.get('autonomy')}"
            + (f" PAUSED: {pause.get('reason')}" if pause else "")
        )
    if lines:
        print("Open SDD runs (specs/*/state.json):\n" + "\n".join(lines)
              + "\nResume one with /sdd-kit:sdd <ID>; status: /sdd-kit:sdd-status.")
except Exception:
    pass
