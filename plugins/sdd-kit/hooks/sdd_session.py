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

Fail closed for the guard: if an open run has no usable session recorded (the
field is missing, or the ${CLAUDE_SESSION_ID} placeholder was written
literally), the guard cannot tell which session runs it, so its rails apply to
every session in the project until the run records its session or is closed.
The formatter does not use this fallback: it only touches sdd-kit's own work.

As a script:
  sdd_session.py                      read a hook payload on stdin; exit 0 when the
                                      call is part of a run (exact match only), 1 otherwise
  sdd_session.py --status [--session ID]
                                      print, per open run, whether the rails are on
                                      for that session; exit 1 if any run's rails are
                                      not tied to its session
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


def usable_session(value):
    v = str(value or "").strip()
    return bool(v) and "${" not in v and "CLAUDE_SESSION_ID" not in v


def open_runs(root):
    """(run id, recorded session or None) for every run that is not closed."""
    runs = []
    for state_file in sorted(root.glob("specs/*/state.json")):
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if state.get("phase") in CLOSED_PHASES:
            continue
        session = state.get("session")
        runs.append((str(state.get("id") or state_file.parent.name), str(session) if usable_session(session) else None))
    return runs


def run_without_session(payload):
    """Id of an open run whose session is unknown, else None."""
    for run_id, session in open_runs(project_root(payload)):
        if session is None:
            return run_id
    return None


def in_sdd_run(payload, include_unrecorded=True):
    if own_agent(payload):
        return True
    runs = open_runs(project_root(payload))
    sid = str(payload.get("session_id") or "")
    if sid and sid in {s for _, s in runs if s}:
        return True
    return include_unrecorded and any(s is None for _, s in runs)


def status(session):
    runs = open_runs(Path(os.environ.get("CLAUDE_PROJECT_DIR") or "."))
    if not runs:
        print("No open SDD runs in specs/.")
        return 0
    loose = 0
    for run_id, recorded in runs:
        if recorded is None:
            loose += 1
            print(f"{run_id}: no session recorded, so the rails apply to EVERY session in this project. "
                  "Write the session id into state.json.")
        elif usable_session(session) and recorded == session:
            print(f"{run_id}: rails on for this session ({recorded}).")
        else:
            shown = session if usable_session(session) else "unknown (placeholder not substituted)"
            print(f"{run_id}: rails on for session {recorded}; this session is {shown}.")
            if not usable_session(session):
                loose += 1
    return 1 if loose else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--status"]:
        sid = args[args.index("--session") + 1] if "--session" in args and args.index("--session") + 1 < len(args) else ""
        sys.exit(status(sid))
    try:
        sys.exit(0 if in_sdd_run(json.load(sys.stdin), include_unrecorded=False) else 1)
    except Exception:
        sys.exit(1)
