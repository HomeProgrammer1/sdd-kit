#!/usr/bin/env python3
"""sdd-kit PreToolUse guard.

Instructions in skills and CLAUDE.md describe intended behaviour; this script
is the part that does not depend on the model agreeing.

Two tiers, so sdd-kit protects its own runs without getting in the way of
other plugins or of ordinary requests:
  * HARD stops: irreversible damage to the machine or the repository itself.
    Applied in every session.
  * PROCESS rails: merges, approvals, deploys, publishing, force pushes,
    secrets, and the doc-only roles. Applied to sdd-kit's own work: calls from
    this marketplace's agents, and sessions running /sdd-kit:sdd (see
    sdd_session.py, which also covers runs that forgot to record a session).

Mode (plugin option guard_mode, or the SDD_GUARD environment variable):
  sdd        default: hard stops everywhere, process rails in SDD runs
  strict     hard stops and process rails in every session; a guard error blocks
  hard-only  hard stops only
  off        nothing

How commands are read: the command is split into simple commands at ; && ||
| & newlines, subshells and backticks, after quotes are dropped, so the body
of bash -c "..." / sh -c '...' / eval "..." is checked like a typed command.
rm and git push are parsed token by token (flag order and spelling do not
matter, git's -C/-c options are skipped, refs/heads/ prefixes are stripped).
Common one-liners (shutil.rmtree, fs.rmSync, FileUtils.rm_rf) on a root or
home path are caught too.

Scope limit: scripts that a command runs, and strings assembled at runtime
(variables, base64, downloaded code) are not inspected. Permission deny rules
and the autonomy-contract skill cover the rest. A quoted mention such as
echo "rm -rf /" is treated like the command itself; that is deliberate.

Principles:
  * Python standard library only; no network; finishes in milliseconds.
  * In sdd, hard-only and off modes an error inside the guard lets the call
    through ("fail open"), so a bug here cannot lock up a session. In strict
    mode an error blocks the call instead.
  * Each refusal says why, so the agent can pause instead of looping.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdd_session import in_sdd_run, run_without_session  # noqa: E402

# ------------------------------------------------------------------ patterns

# Matched against each simple command (quotes dropped) and the raw command.
HARD_BASH = [
    (r"\bfind\s+(/|~/?|\$\{?HOME\}?/?)(\s|$).*(-delete\b|-exec\s+rm\b)", "deleting files from the root or home directory with find"),
    (r"\b(shutil\.rmtree|FileUtils\.rm_rf|FileUtils\.remove_dir|fs\.rmSync|fs\.rm|rimraf(Sync)?)\s*\(\s*['\"]?(/|~|\.|\$HOME|os\.path\.expanduser\(\s*['\"]~['\"]\s*\)|Path\.home\(\))['\"]?\s*[,)]",
     "recursive delete of a root, home or current directory from a script one-liner"),
    (r"\bmkfs(\.\w+)?\s|\bdd\s+[^|]*\bof=/dev/(sd|nvme|disk|hd)", "overwriting a disk"),
]
HARD_WRITE = [
    (r"(^|/)\.git/", "git internals"),
    (r"(^|/)\.ssh/|(^|/)\.aws/credentials$|(^|/)\.config/gcloud/|(^|/)\.kube/config$", "machine credentials"),
]

RAIL_BASH = [
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard (destroys uncommitted work)"),
    (r"\bgit\s+clean\s+-[a-zA-Z]*f", "git clean -f (destroys untracked files)"),
    (r"\bgit\s+(commit|push|merge|rebase)\b.*--no-verify\b", "skipping git hooks with --no-verify"),
    (r"\b(gh\s+pr\s+merge|glab\s+mr\s+merge)\b", "merging, which is a human decision"),
    (r"\b(gh|glab)\s+api\b.*(/pulls/\d+/merge|/merge_requests/\d+/merge)\b|\bcurl\b.*(/pulls/\d+/merge|/merge_requests/\d+/merge)\b",
     "merging through the API, which is a human decision"),
    (r"\bgh\s+pr\s+review\b.*(\s--approve\b|\s-a\b)|\bglab\s+mr\s+approve\b", "approving a pull request, which is a human decision"),
    (r"\b(gh|glab)\s+release\s+create\b", "publishing a release"),
    (r"\b(terraform|tofu)\s+(apply|destroy|import)\b|\bpulumi\s+(up|destroy)\b", "infrastructure change"),
    (r"\bkubectl\s+(apply|delete|replace|patch|scale|rollout|edit|drain)\b", "cluster change"),
    (r"\bhelm\s+(install|upgrade|uninstall|rollback)\b", "cluster release change"),
    (r"\b(npm|pnpm|yarn|bun)\s+publish\b|\bcargo\s+publish\b|\btwine\s+upload\b|\bgem\s+push\b|\bdocker\s+push\b",
     "publishing a package or image"),
    (r"\bfastlane\s+\S*(release|deliver|upload|supply|pilot)|\bxcrun\s+altool\b|\beas\s+(submit|update)\b", "app store upload"),
    (r"\b(vercel|netlify)\b.*--prod\b|\bfirebase\s+deploy\b|\bfly\s+deploy\b|\b(cdk|sls|serverless)\s+deploy\b"
     r"|\bgcloud\b.*\bdeploy\b|\bwrangler\s+(deploy|publish)\b|\bsupabase\s+db\s+push\b", "production deploy"),
    (r"\b(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE\s+TABLE)\b", "destructive SQL"),
    (r"(curl|wget)\s[^|]*\|\s*(sudo\s+)?(ba|z)?sh\b", "running a downloaded script"),
    (r"\bchmod\s+-R\s+777\b", "world-writable permissions"),
]
RAIL_WRITE = [
    (r"(^|/)\.env(\.[^/]*)?$", ".env files hold secrets; edit .env.example instead"),
    (r"(^|/)secrets?/", "secrets directory"),
    (r"\.(pem|key|p12|keystore|jks|mobileprovision)$", "keys or signing material"),
    (r"(^|/)\.npmrc$|(^|/)\.pypirc$", "registry credentials"),
]
ENV_EXAMPLE_OK = re.compile(r"(^|/)\.env\.(example|sample|template)$")

# Guardrail files may be created once (by /sdd-kit:init-project) but not edited by an agent.
PROTECTED_IF_EXISTS = re.compile(r"(^|/)\.claude/settings\.json$")

# Roles that produce documents only, and where they may write.
DOC_ONLY_ROLES = re.compile(r"(^|:)(analyst|architect|ux-designer)$")
DOC_PREFIXES = ("specs/", "docs/")

MODES = ("sdd", "strict", "hard-only", "off")
MAIN_BRANCHES = ("main", "master")
PROTECTED_BRANCHES = re.compile(r"^(main|master|develop|production|release/.+)$")

# ------------------------------------------------------------------ command parsing

SEPARATORS = re.compile(r"&&|\|\||[;|&\n()`]|\$\(")
DANGEROUS_RM_TARGET = re.compile(r"^(/+|/\*|~/?\*?|\$\{?HOME\}?/?\*?|\*|\.{1,2}/?\*?)$")
GIT_OPTS_WITH_VALUE = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path")


def simple_commands(cmd: str):
    """Token lists, one per simple command, with quotes dropped so wrapped shells are seen."""
    flat = re.sub(r"[\"']", " ", cmd.replace("\\\n", " "))
    out = []
    for seg in SEPARATORS.split(flat):
        tokens = [t for t in seg.split() if t]
        if tokens:
            out.append(tokens)
    return out


def command_name(token: str) -> str:
    return token.lstrip("\\").rsplit("/", 1)[-1]


def rm_danger(tokens) -> bool:
    for i, tok in enumerate(tokens):
        if command_name(tok) != "rm":
            continue
        recursive, targets, end_of_flags = False, [], False
        for arg in tokens[i + 1:]:
            if not end_of_flags and arg == "--":
                end_of_flags = True
            elif not end_of_flags and arg.startswith("--"):
                recursive |= arg == "--recursive"
            elif not end_of_flags and arg.startswith("-") and len(arg) > 1:
                recursive |= bool(re.search(r"[rR]", arg))
            else:
                targets.append(arg)
        if recursive and any(DANGEROUS_RM_TARGET.match(t) for t in targets):
            return True
    return False


def git_push(tokens):
    """(flags, refspecs, git -C dir) for a git push, or None."""
    for i, tok in enumerate(tokens):
        if command_name(tok) != "git":
            continue
        j, cwd = i + 1, None
        while j < len(tokens) and tokens[j].startswith("-"):
            opt = tokens[j]
            if opt in GIT_OPTS_WITH_VALUE and j + 1 < len(tokens):
                if opt == "-C":
                    cwd = tokens[j + 1]
                j += 2
            else:
                j += 1
        if j < len(tokens) and tokens[j] == "push":
            args = tokens[j + 1:]
            flags = [a for a in args if a.startswith("-")]
            positional = [a for a in args if not a.startswith("-")]
            return flags, positional[1:], cwd   # positional[0] is the remote
    return None


def current_branch(cwd):
    try:
        r = subprocess.run(["git", "-C", cwd or ".", "symbolic-ref", "--short", "-q", "HEAD"],
                           capture_output=True, text=True, timeout=2)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def push_findings(tokens, payload):
    """Hard and rail reasons for one git push."""
    parsed = git_push(tokens)
    if not parsed:
        return [], []
    flags, refspecs, git_cwd = parsed
    force = any(f in ("--force", "--mirror") or f.startswith("--force-with-lease") or re.fullmatch(r"-[a-zA-Z]*f[a-zA-Z]*", f)
                for f in flags) or any(r.startswith("+") for r in refspecs)
    delete = "--delete" in flags or "-d" in flags or any(r.startswith(":") for r in refspecs)
    targets = []
    for r in refspecs:
        dst = r.lstrip("+").split(":")[-1]
        targets.append(re.sub(r"^refs/heads/", "", dst))
    if not refspecs and not any(f in ("--all", "--mirror", "--tags") for f in flags):
        base = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or "."
        cwd = git_cwd if git_cwd and os.path.isabs(git_cwd) else os.path.join(base, git_cwd or "")
        branch = current_branch(cwd)
        if branch:
            targets.append(branch)
    hits_main = "--mirror" in flags or ("--all" in flags and force) or any(t in MAIN_BRANCHES for t in targets)
    hard, rails = [], []
    if force and hits_main:
        hard.append("force push to main/master")
    if delete and any(t in MAIN_BRANCHES for t in targets):
        hard.append("deleting main/master on the remote")
    if force:
        rails.append("force push")
    if delete:
        rails.append("deleting a remote branch")
    if any(PROTECTED_BRANCHES.match(t) for t in targets) or "--all" in flags or "--mirror" in flags:
        rails.append("push to a protected branch")
    if "--tags" in flags or any(r.startswith("refs/tags/") for r in refspecs):
        rails.append("pushing tags (a release)")
    return hard, rails


# ------------------------------------------------------------------ decision

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


def rails_suffix(payload) -> str:
    orphan = run_without_session(payload)
    if orphan:
        return (f" (rails apply to every session here because the open run {orphan} has no session recorded; "
                "finish or abandon it, or let /sdd-kit:sdd resume it)")
    return ""


def check_bash(cmd: str, rails: bool, payload: dict) -> None:
    commands = simple_commands(cmd)
    texts = [cmd] + [" ".join(t) for t in commands]
    for tokens in commands:
        if rm_danger(tokens):
            deny("recursive delete of a root, home, current or wildcard path")
    for pattern, reason in HARD_BASH:
        if any(re.search(pattern, t, re.IGNORECASE) for t in texts):
            deny(reason)
    rail_hits = []
    for tokens in commands:
        hard, rail = push_findings(tokens, payload)
        if hard:
            deny(hard[0])
        rail_hits += rail
    if not rails:
        return
    if rail_hits:
        deny(rail_hits[0] + rails_suffix(payload))
    for pattern, reason in RAIL_BASH:
        if any(re.search(pattern, t, re.IGNORECASE) for t in texts):
            deny(reason + rails_suffix(payload))


def main() -> None:
    m = mode()
    if m == "off":
        return
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name", "")
    tin = payload.get("tool_input") or {}
    rails = m == "strict" or (m == "sdd" and in_sdd_run(payload))

    if tool == "Bash":
        check_bash(str(tin.get("command", "")), rails, payload)
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
        deny(f"the {agent} role writes only under specs/ and docs/; code changes belong to the implementer" + rails_suffix(payload))
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
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        if mode() == "strict":
            deny(f"the guard could not check this call ({type(exc).__name__}), and strict mode blocks what it cannot check")
        sys.exit(0)
