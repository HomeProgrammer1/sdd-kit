#!/usr/bin/env python3
"""Is this tool call part of an sdd-kit run?

Shared by the guard and the formatter hook so that sdd-kit's process rails apply
to its own work and stay out of the way of everything else (other plugins,
ad-hoc requests, other workflows).

A call belongs to an SDD run when either
  * it comes from one of this marketplace's agents (agent_type "sdd-kit:…" or
    "sdd-design:…"), or
  * its session is the one recorded in an open specs/*/state.json ("session",
    written by /sdd-kit:sdd on start and on every resume).

Run as a script it reads the hook payload on stdin and exits 0 when the call
is part of a run, 1 otherwise.
"""
import json
import os
import sys
from pathlib import Path

OWN_AGENT_PREFIXES = ("sdd-kit:", "sdd-design:")
CLOSED_PHASES = ("done", "abandoned")


def project_root(payload):
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".")


def own_agent(payload):
    return str(payload.get("agent_type") or "").startswith(OWN_AGENT_PREFIXES)


def open_run_sessions(root):
    sessions = set()
    for state_file in root.glob("specs/*/state.json"):
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if state.get("phase") not in CLOSED_PHASES and state.get("session"):
            sessions.add(str(state["session"]))
    return sessions


def in_sdd_run(payload):
    if own_agent(payload):
        return True
    sid = str(payload.get("session_id") or "")
    return bool(sid) and sid in open_run_sessions(project_root(payload))


if __name__ == "__main__":
    try:
        sys.exit(0 if in_sdd_run(json.load(sys.stdin)) else 1)
    except Exception:
        sys.exit(1)
