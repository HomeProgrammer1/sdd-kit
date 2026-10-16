#!/usr/bin/env python3
"""Repository checks for the sdd marketplace.

  * every JSON file parses; marketplace entries point at real plugins whose
    plugin.json name and version match
  * every skill and agent has the frontmatter Claude Code needs
  * every hook script hooks.json names exists
  * the guard allows/denies the cases below in each mode, inside and outside
    an SDD run
  * the diagram engine renders the example spec with no errors or warnings
  * the prototype renderer accepts the example screens with the starter design
    system (light and dark), including the contrast contract
  * the Figma plugin test passes (when node is installed)
  * no file mentions a name on the private deny list (stored as hashes only)

Run: python3 scripts/validate.py
For the manifests themselves also run: claude plugin validate . and
claude plugin validate plugins/<name>
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

repo = Path(__file__).resolve().parent.parent
plugins_dir = repo / "plugins"
kit = plugins_dir / "sdd-kit"
template = kit / "skills/init-project/template"
example_spec = template / "specs/EXAMPLE-001-password-reset/spec.md"
errors, notes = [], []
PY = [sys.executable, "-I"]


def load_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"{p.relative_to(repo)}: invalid JSON ({e})")
        return None


# ------------------------------------------------------------------ JSON + manifests
for p in sorted(repo.rglob("*.json")):
    if ".git" not in p.parts and "node_modules" not in p.parts:
        load_json(p)

market = load_json(repo / ".claude-plugin/marketplace.json") or {}
listed = set()
for entry in market.get("plugins", []):
    src = repo / entry.get("source", "")
    manifest = load_json(src / ".claude-plugin/plugin.json") if (src / ".claude-plugin/plugin.json").exists() else None
    if manifest is None:
        errors.append(f"marketplace: {entry.get('name')} → {entry.get('source')} has no plugin.json")
        continue
    listed.add(src.name)
    if manifest.get("name") != entry.get("name"):
        errors.append(f"marketplace: entry {entry.get('name')} != plugin.json name {manifest.get('name')}")
    if entry.get("version") and entry["version"] != manifest.get("version"):
        errors.append(f"marketplace: {entry['name']} version {entry['version']} != plugin.json {manifest.get('version')}")
for d in plugins_dir.iterdir():
    if d.is_dir() and d.name not in listed:
        errors.append(f"plugins/{d.name} is not listed in marketplace.json")


# ------------------------------------------------------------------ frontmatter
def frontmatter(p):
    m = re.match(r"^---\n(.*?)\n---\n", p.read_text(encoding="utf-8"), re.S)
    return m.group(1) if m else None


skills = list(plugins_dir.glob("*/skills/*/SKILL.md"))
agents = list(plugins_dir.glob("*/agents/*.md"))
for p in skills + agents:
    fm, rel = frontmatter(p), p.relative_to(repo)
    if fm is None:
        errors.append(f"{rel}: no frontmatter")
        continue
    if "description:" not in fm:
        errors.append(f"{rel}: missing description")
    name = re.search(r"^name:\s*(\S+)", fm, re.M)
    if p.parent.name == "agents" and not name:
        errors.append(f"{rel}: missing name")
    if p.name == "SKILL.md" and name and name.group(1) != p.parent.name:
        errors.append(f"{rel}: name '{name.group(1)}' != folder '{p.parent.name}'")
    if p.parent.name == "agents" and re.search(r"^hooks:", fm, re.M):
        errors.append(f"{rel}: plugin agents must not declare hooks (use the plugin's hooks.json)")
    if "${CLAUDE_PLUGIN_ROOT}" in p.read_text(encoding="utf-8") and p.parent.name == "agents":
        errors.append(f"{rel}: agents cannot rely on ${{CLAUDE_PLUGIN_ROOT}}; pass paths in the dispatch")

for p in template.glob(".claude/rules/*.md"):
    if frontmatter(p) is None:
        errors.append(f"{p.relative_to(repo)}: rule without paths: frontmatter")

for hooks in plugins_dir.glob("*/hooks/hooks.json"):
    for script in set(re.findall(r"hooks/[\w]+\.(?:py|sh)", hooks.read_text(encoding="utf-8"))):
        if not (hooks.parent.parent / script).exists():
            errors.append(f"{hooks.relative_to(repo)} references missing {script}")

# ------------------------------------------------------------------ guard
guard = kit / "hooks/guard.py"
proj = Path(tempfile.mkdtemp(prefix="sdd-guard-"))
(proj / "specs/F-1").mkdir(parents=True)
(proj / "specs/F-1/state.json").write_text(json.dumps({"id": "F-1", "phase": "implementing", "session": "S-RUN"}))
(proj / "specs/F-2").mkdir(parents=True)
(proj / "specs/F-2/state.json").write_text(json.dumps({"id": "F-2", "phase": "done", "session": "S-OLD"}))
P = str(proj)


def bash(cmd, **kw):
    return {"tool_name": "Bash", "cwd": P, "session_id": "S-OTHER", "tool_input": {"command": cmd}, **kw}


def write(path, **kw):
    return {"tool_name": "Write", "cwd": P, "session_id": "S-OTHER", "tool_input": {"file_path": path}, **kw}


ours = {"agent_type": "sdd-kit:implementer"}
run = {"session_id": "S-RUN"}
cases = [
    # mode, payload, deny?
    # outside any SDD run: only hard stops
    ("sdd", bash("rm -rf /"), True),
    ("sdd", bash("rm -rf ./build"), False),
    ("sdd", bash("git push --force origin main"), True),
    ("sdd", bash("git push --force origin feat/x"), False),
    ("sdd", bash("gh pr merge 12"), False),
    ("sdd", bash("npm publish"), False),
    ("sdd", write(P + "/.env"), False),
    ("sdd", write(P + "/.git/config"), True),
    ("sdd", write("/home/u/.ssh/id_ed25519"), True),
    ("sdd", write(P + "/src/a.ts", agent_type="architect"), False),
    ("sdd", bash("gh pr merge 12", session_id="S-OLD"), False),
    # sdd-kit's own agents: process rails
    ("sdd", bash("git push --force origin feat/x", **ours), True),
    ("sdd", bash("git push origin main", **ours), True),
    ("sdd", bash("git push -u origin feat/F-001-main-menu", **ours), False),
    ("sdd", bash("gh pr merge 12", **ours), True),
    ("sdd", bash("terraform apply", **ours), True),
    ("sdd", bash("npm test", **ours), False),
    ("sdd", write(P + "/.env", **ours), True),
    ("sdd", write(P + "/.env.example", **ours), False),
    ("sdd", write(P + "/src/app.ts", **ours), False),
    ("sdd", write(str(template / ".claude/settings.json"), **ours), True),
    ("sdd", write("/new/.claude/settings.json", **ours), False),
    ("sdd", write(P + "/src/a.ts", agent_type="sdd-kit:analyst"), True),
    ("sdd", write(P + "/specs/F-1/spec.md", agent_type="sdd-kit:analyst"), False),
    ("sdd", write(P + "/src/a.tsx", agent_type="sdd-design:ux-designer"), True),
    ("sdd", write(P + "/specs/F-1/design/screens.json", agent_type="sdd-design:ux-designer"), False),
    # the session running /sdd-kit:sdd (main session and any subagent in it)
    ("sdd", bash("gh pr merge 12", **run), True),
    ("sdd", bash("git push origin main", **run), True),
    ("sdd", write(P + "/src/a.ts", agent_type="architect", **run), True),
    # other modes
    ("strict", bash("gh pr merge 12"), True),
    ("strict", write(P + "/src/a.ts", agent_type="architect"), False),
    ("hard-only", bash("gh pr merge 12", **ours), False),
    ("hard-only", bash("rm -rf ~"), True),
    ("off", bash("rm -rf /"), False),
]
for mode, payload, should_deny in cases:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "SDD_GUARD": mode}
    out = subprocess.run(PY + [str(guard)], input=json.dumps(payload), capture_output=True, text=True, env=env).stdout
    if ('"deny"' in out) != should_deny:
        errors.append(f"guard[{mode}]: expected {'deny' if should_deny else 'allow'} for "
                      f"{payload.get('agent_type', '-')}/{payload.get('session_id')}: {payload['tool_input']}")
shutil.rmtree(proj, ignore_errors=True)

# ------------------------------------------------------------------ diagram engine
engine = plugins_dir / "sdd-diagrams/skills/feature-diagrams/scripts/sdd_diagrams.py"
with tempfile.TemporaryDirectory() as tmp:
    r = subprocess.run(PY + [str(engine), "build", str(example_spec), "--drawio", "--out", tmp], capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    if r.returncode != 0 or "0 error(s), 0 warning(s)" not in last:
        errors.append(f"sdd_diagrams on the example: {last or r.stderr.strip()[-300:]}")
    else:
        notes.append(f"diagrams: {last}")

# ------------------------------------------------------------------ prototype renderer
renderer = plugins_dir / "sdd-design/skills/prototype/scripts/render_prototype.py"
example_screens = plugins_dir / "sdd-design/skills/prototype/references/example.screens.json"
starter = plugins_dir / "sdd-design/skills/design-system-init/starter/components.json"
for theme in ("light", "dark"):
    r = subprocess.run(PY + [str(renderer), "check", str(example_screens), "--ds", str(starter), "--theme", theme],
                       capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    if r.returncode != 0 or "0 error(s), 0 warning(s)" not in last:
        errors.append(f"render_prototype ({theme}): {r.stdout.strip()[-400:] or r.stderr.strip()[-300:]}")
notes.append("prototype: example passes with the starter design system (light, dark)")

# ------------------------------------------------------------------ Figma plugin
figma_test = repo / "scripts/test_figma_plugin.js"
if figma_test.exists() and shutil.which("node"):
    r = subprocess.run(["node", str(figma_test)], capture_output=True, text=True, cwd=repo)
    if r.returncode != 0:
        errors.append("figma plugin test failed:\n" + (r.stdout + r.stderr).strip()[-800:])
    else:
        notes.append("figma: " + ((r.stdout.strip().splitlines() or ["ok"])[-1]))
elif figma_test.exists():
    notes.append("figma: node not installed, test skipped")

# ------------------------------------------------------------------ private deny list
# SHA-256 of lower-cased words that must never appear in this repository.
# Only hashes are stored, so the list itself names nothing.
DENY_HASHES = {
    "2183a5261f3c11ec8b7d3649816891ec86c677747a0640ea755bad35666cd984",
    "3256c7970188399480bfae5643bd8bd51f59f9c234d254bdcd0febcefee82085",
    "5b92e3c73ed3254437bb6be029d752b026829d77b4dabe38e3a6ec9e86965b8d",
    "649e2282a3dc84134363483f9d5b5478a416dbe06386e7165b07bcd3445d254d",
    "9373d6ca3bf15abaae0b75348edb8912826baf68c25e8dcb6310f2545e53ae1c",
    "dfe8da597dc90022b52d7b4f4be2810bfc4cb9793ece8c1e8fd63c693842e7f4",
}
deny_file = repo / "scripts/.deny-hashes"
if deny_file.exists():
    DENY_HASHES |= {l.strip() for l in deny_file.read_text().splitlines() if re.fullmatch(r"[0-9a-f]{64}", l.strip())}
text_ext = {".md", ".json", ".py", ".sh", ".js", ".html", ".txt", ".yml", ".yaml", ".mmd", ".svg", ".drawio", ""}
for p in repo.rglob("*"):
    if p.is_file() and ".git" not in p.parts and p.suffix in text_ext and p.name != ".deny-hashes":
        try:
            words = set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", p.read_text(encoding="utf-8", errors="ignore").lower()))
        except OSError:
            continue
        candidates = words | {w.replace("-", "") for w in words} | {part for w in words for part in w.split("-")}
        if any(hashlib.sha256(w.encode()).hexdigest() in DENY_HASHES for w in candidates):
            errors.append(f"{p.relative_to(repo)}: contains a name from the private deny list")

if errors:
    print("FAIL\n" + "\n".join(f"  - {e}" for e in errors))
    sys.exit(1)
print(f"OK: {len(listed)} plugins, {len(skills)} skills, {len(agents)} agents, "
      f"{len(list(template.glob('.claude/rules/*.md')))} rules, {len(cases)} guard cases")
for n in notes:
    print("   " + n)
