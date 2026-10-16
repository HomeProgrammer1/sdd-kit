#!/usr/bin/env python3
"""Repository checks for sdd-kit: JSON parses, every skill and agent has the
frontmatter Claude Code needs, every hook script hooks.json names exists, and
the guard allows/denies the cases below. Run: python3 scripts/validate.py
For the manifests themselves also run: claude plugin validate . and
claude plugin validate plugins/sdd-kit"""
import json
import re
import subprocess
import sys
from pathlib import Path

repo = Path(__file__).resolve().parent.parent
plugin = repo / "plugins/sdd-kit"
template = plugin / "skills/init-project/template"
errors = []

for p in [repo / ".claude-plugin/marketplace.json", plugin / ".claude-plugin/plugin.json", plugin / "hooks/hooks.json",
          template / ".mcp.json", template / ".claude/settings.json", *template.glob("mcp-connectors/*.json")]:
    try:
        json.loads(p.read_text())
    except Exception as e:
        errors.append(f"{p.relative_to(repo)}: invalid JSON ({e})")


def frontmatter(p):
    m = re.match(r"^---\n(.*?)\n---\n", p.read_text(), re.S)
    return m.group(1) if m else None


for p in [*plugin.glob("skills/*/SKILL.md"), *plugin.glob("agents/*.md")]:
    fm, rel = frontmatter(p), p.relative_to(repo)
    if fm is None:
        errors.append(f"{rel}: no frontmatter"); continue
    if "description:" not in fm:
        errors.append(f"{rel}: missing description")
    name = re.search(r"^name:\s*(\S+)", fm, re.M)
    if p.parent.name == "agents" and not name:
        errors.append(f"{rel}: missing name")
    if p.name == "SKILL.md" and name and name.group(1) != p.parent.name:
        errors.append(f"{rel}: name '{name.group(1)}' != folder '{p.parent.name}'")

for p in template.glob(".claude/rules/*.md"):
    if frontmatter(p) is None:
        errors.append(f"{p.relative_to(repo)}: rule without paths: frontmatter")

for script in set(re.findall(r"hooks/[\w]+\.(?:py|sh)", (plugin / "hooks/hooks.json").read_text())):
    if not (plugin / script).exists():
        errors.append(f"hooks.json references missing {script}")

guard = plugin / "hooks/guard.py"
cases = [
    ({"tool_name": "Bash", "tool_input": {"command": "git push --force origin feat/x"}}, True),
    ({"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}, True),
    ({"tool_name": "Bash", "tool_input": {"command": "git push -u origin feat/F-001-main-menu"}}, False),
    ({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}, True),
    ({"tool_name": "Bash", "tool_input": {"command": "rm -rf ./build"}}, False),
    ({"tool_name": "Bash", "tool_input": {"command": "gh pr merge 12"}}, True),
    ({"tool_name": "Bash", "tool_input": {"command": "terraform apply"}}, True),
    ({"tool_name": "Bash", "tool_input": {"command": "npm test"}}, False),
    ({"tool_name": "Write", "tool_input": {"file_path": "/repo/.env"}}, True),
    ({"tool_name": "Write", "tool_input": {"file_path": "/repo/.env.example"}}, False),
    ({"tool_name": "Edit", "tool_input": {"file_path": "/repo/src/app.ts"}}, False),
    ({"tool_name": "Edit", "tool_input": {"file_path": str(template / ".claude/settings.json")}}, True),
    ({"tool_name": "Write", "tool_input": {"file_path": "/new/.claude/settings.json"}}, False),
    ({"tool_name": "Write", "cwd": "/repo", "agent_type": "sdd-kit:analyst", "tool_input": {"file_path": "/repo/src/a.ts"}}, True),
    ({"tool_name": "Write", "cwd": "/repo", "agent_type": "sdd-kit:analyst", "tool_input": {"file_path": "/repo/specs/F-1/spec.md"}}, False),
    ({"tool_name": "Edit", "cwd": "/repo", "agent_type": "sdd-kit:implementer", "tool_input": {"file_path": "/repo/src/a.ts"}}, False),
]
for payload, should_deny in cases:
    out = subprocess.run([sys.executable, "-I", str(guard)], input=json.dumps(payload),
                         capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"}).stdout
    if ('"deny"' in out) != should_deny:
        errors.append(f"guard: expected {'deny' if should_deny else 'allow'} for {payload}")

if errors:
    print("FAIL\n" + "\n".join(f"  - {e}" for e in errors)); sys.exit(1)
print(f"OK: {len(list(plugin.glob('skills/*/SKILL.md')))} skills, {len(list(plugin.glob('agents/*.md')))} agents, "
      f"{len(list(template.glob('.claude/rules/*.md')))} rules, {len(cases)} guard cases")
