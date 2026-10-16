#!/usr/bin/env python3
"""sdd-kit PreToolUse guard.

Instructions in skills and CLAUDE.md describe intended behaviour; this script
is the part that does not depend on the model agreeing.

Two tiers, so sdd-kit protects its own runs without getting in the way of
other plugins or of ordinary requests:
  * HARD stops: irreversible damage to the machine or the repository itself.
    Applied in every session.
  * PROCESS rails: merges, deploys, publishing, force pushes, secrets, and the
    doc-only roles. Applied to sdd-kit's own work: calls from this
    marketplace's agents, and sessions running /sdd-kit:sdd (see sdd_session.py).

Mode (plugin option guard_mode, or the SDD_GUARD environment variable):
  sdd        default: hard stops everywhere, process rails in SDD runs
  strict     hard stops and process rails in every session
  hard-only  hard stops only
  off        nothing

Principles:
  * Python standard library only; no network; finishes in milliseconds.
  * Errors inside the guard let the call through ("fail open"), so a bug here
    cannot lock up a session. Add "onFailure": "block" to the handler in
    hooks.json if you prefer the stricter trade-off.
  * Each refusal says why, so the agent can pause instead of looping.

Scope limit: commands are matched as typed. Wrapped shells (bash -c "..."),
scripts that a command runs, and strings assembled at runtime are not
inspected. Permission deny rules and the autonomy-contract skill cover the
rest.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdd_session import in_sdd_run  # noqa: E402

HARD_BASH = [
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*\s+(/|~/?|\$HOME/?|\*|\.)(\s|$)", "recursive delete of a root, home, current or wildcard path"),
    (r"\bgit\s+push\b(?=.*(\s--force|\s-f\b|\s\+))(?=.*[\s:+](main|master)(\s|$))", "force push to main/master"),
]
HARD_WRITE = [
    (r"(^|/)\.git/", "git internals"),
    (r"(^|/)\.ssh/|(^|/)\.aws/credentials$", "machine credentials"),
]

RAIL_BASH = [
    (r"\bgit\s+push\b.*(\s--force\b|\s-f\b|\s--force-with-lease\b|\s\+\S)", "force push"),
    (r"\bgit\s+push\b.*[\s:](main|master|develop|production|release/\S+)(\s|$)", "push to a protected branch"),
    (r"\bgit\s+push\b.*\s--delete\b|\bgit\s+push\s+\S+\s+:\S+", "deleting a remote branch"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard (destroys uncommitted work)"),
    (r"\bgit\s+clean\s+-[a-zA-Z]*f", "git clean -f (destroys untracked files)"),
    (r"\bgit\s+(commit|push)\b.*--no-verify\b", "skipping git hooks with --no-verify"),
    (r"\b(gh\s+pr\s+merge|glab\s+mr\s+merge)\b", "merging, which is a human decision"),
    (r"\b(terraform|tofu)\s+(apply|destroy)\b", "infrastructure change"),
    (r"\bkubectl\s+(apply|delete|replace|patch|scale|rollout)\b", "cluster change"),
    (r"\bhelm\s+(install|upgrade|uninstall|rollback)\b", "cluster release change"),
    (r"\b(npm|pnpm|yarn)\s+publish\b|\bcargo\s+publish\b|\btwine\s+upload\b", "publishing a package"),
    (r"\bfastlane\s+\S*(release|deliver|upload|supply)|\bxcrun\s+altool\b", "app store upload"),
    (r"\b(vercel|netlify)\b.*--prod\b|\bfirebase\s+deploy\b|\bfly\s+deploy\b", "production deploy"),
    (r"\b(DROP\s+(TABLE|DATABASE)|TRUNCATE\s+TABLE)\b", "destructive SQL"),
    (r"(curl|wget)\s[^|]*\|\s*(ba|z)?sh\b", "running a downloaded script"),
    (r"\bchmod\s+-R\s+777\b", "world-writable permissions"),
]
RAIL_WRITE = [
    (r"(^|/)\.env(\.[^/]*)?$", ".env files hold secrets; edit .env.example instead"),
    (r"(^|/)secrets?/", "secrets directory"),
    (r"\.(pem|key|p12|keystore|jks|mobileprovision)$", "keys or signing material"),
    (r"(^|/)\.npmrc$", "registry credentials"),
]
ENV_EXAMPLE_OK = re.compile(r"(^|/)\.env\.(example|sample|template)$")

# Guardrail files may be created once (by /sdd-kit:init-project) but not edited by an agent.
PROTECTED_IF_EXISTS = re.compile(r"(^|/)\.claude/settings\.json$")

# Roles that produce documents only, and where they may write.
DOC_ONLY_ROLES = re.compile(r"(^|:)(analyst|architect|ux-designer)$")
DOC_PREFIXES = ("specs/", "docs/")

MODES = ("sdd", "strict", "hard-only", "off")


def mode():
    m = (os.environ.get("SDD_GUARD") or os.environ.get("CLAUDE_PLUGIN_OPTION_GUARD_MODE") or "sdd").strip().lower()
    return m if m in MODES else "sdd"


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            f"sdd-kit guard: {reason}. Treat this as final: do not look for a "
            "workaround. If this is an SDD run, record a pause in state.json; "
            "tell the human what is needed."
        ),
    }}))
    sys.exit(0)


def relative(path: str, payload: dict) -> str:
    root = (os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or "").replace("\\", "/").rstrip("/")
    return path[len(root) + 1:] if root and path.startswith(root + "/") else path


def main() -> None:
    m = mode()
    if m == "off":
        return
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name", "")
    tin = payload.get("tool_input") or {}
    rails = m == "strict" or (m == "sdd" and in_sdd_run(payload))

    if tool == "Bash":
        cmd = str(tin.get("command", ""))
        for pattern, reason in HARD_BASH + (RAIL_BASH if rails else []):
            if re.search(pattern, cmd, re.IGNORECASE):
                deny(reason)
        return

    path = str(tin.get("file_path") or tin.get("notebook_path") or "").replace("\\", "/")
    if not path:
        return
    for pattern, reason in HARD_WRITE:
        if re.search(pattern, path):
            deny(reason)
    if not rails:
        return
    agent = str(payload.get("agent_type", ""))
    ours = agent.startswith(("sdd-kit:", "sdd-design:")) or in_sdd_run(payload)
    if DOC_ONLY_ROLES.search(agent) and ours and not relative(path, payload).startswith(DOC_PREFIXES):
        deny(f"the {agent} role writes only under specs/ and docs/; code changes belong to the implementer")
    if ENV_EXAMPLE_OK.search(path):
        return
    for pattern, reason in RAIL_WRITE:
        if re.search(pattern, path):
            deny(reason)
    if PROTECTED_IF_EXISTS.search(path) and os.path.exists(path):
        deny("project guardrail settings are changed by humans, not agents")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
