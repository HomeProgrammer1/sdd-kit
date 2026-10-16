#!/usr/bin/env python3
"""sdd-kit PreToolUse guard.

Instructions in skills and CLAUDE.md describe intended behaviour; this script
is the part that does not depend on the model agreeing. It refuses a short list
of actions no SDD run should take, whichever agent asks.

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

DENY_BASH = [
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*\s+(/|~/?|\$HOME/?|\*|\.)(\s|$)", "recursive delete of a root, home, current or wildcard path"),
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

DENY_WRITE = [
    (r"(^|/)\.env(\.[^/]*)?$", ".env files hold secrets; edit .env.example instead"),
    (r"(^|/)secrets?/", "secrets directory"),
    (r"\.(pem|key|p12|keystore|jks|mobileprovision)$", "keys or signing material"),
    (r"(^|/)\.git/", "git internals"),
    (r"(^|/)\.ssh/|(^|/)\.aws/credentials$|(^|/)\.npmrc$", "machine credentials"),
]
ENV_EXAMPLE_OK = re.compile(r"(^|/)\.env\.(example|sample|template)$")

# Guardrail files may be created once (by /sdd-kit:init-project) but not edited by an agent.
PROTECTED_IF_EXISTS = re.compile(r"(^|/)\.claude/settings\.json$")

# Roles that produce documents only.
DOC_ONLY_ROLES = re.compile(r"(^|:)(analyst|architect)$")
DOC_PREFIXES = ("specs/", "docs/")


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            f"sdd-kit guard: {reason}. Treat this as final: do not look for a "
            "workaround. Record a pause in state.json and tell the human what is needed."
        ),
    }}))
    sys.exit(0)


def relative(path: str, payload: dict) -> str:
    root = (os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or "").replace("\\", "/").rstrip("/")
    return path[len(root) + 1:] if root and path.startswith(root + "/") else path


def main() -> None:
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name", "")
    tin = payload.get("tool_input") or {}

    if tool == "Bash":
        cmd = str(tin.get("command", ""))
        for pattern, reason in DENY_BASH:
            if re.search(pattern, cmd, re.IGNORECASE):
                deny(reason)
        return

    path = str(tin.get("file_path") or tin.get("notebook_path") or "").replace("\\", "/")
    if not path:
        return
    if DOC_ONLY_ROLES.search(str(payload.get("agent_type", ""))) and not relative(path, payload).startswith(DOC_PREFIXES):
        deny(f"the {payload.get('agent_type')} role writes only under specs/ and docs/; code changes belong to the implementer")
    if ENV_EXAMPLE_OK.search(path):
        return
    for pattern, reason in DENY_WRITE:
        if re.search(pattern, path):
            deny(reason)
    if PROTECTED_IF_EXISTS.search(path) and os.path.exists(path):
        deny("project guardrail settings are changed by humans, not agents")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
