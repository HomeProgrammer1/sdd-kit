#!/usr/bin/env bash
# Status line: model | dir | git branch | context % | cost | active SDD run.
input=$(cat)
read -r model dir ctx cost < <(printf '%s' "$input" | python3 -c '
import sys, json
d = json.load(sys.stdin)
print((d.get("model") or {}).get("display_name","?"),
      ((d.get("workspace") or {}).get("current_dir") or ".").rstrip("/").split("/")[-1],
      int(((d.get("context_window") or {}).get("used_percentage") or 0)),
      "%.2f" % float((d.get("cost") or {}).get("total_cost_usd") or 0))' 2>/dev/null)
branch=$(git branch --show-current 2>/dev/null)
run=$(ls -t "${CLAUDE_PROJECT_DIR:-.}"/specs/*/state.json 2>/dev/null | head -1 | xargs -r dirname | xargs -r basename)
printf '[%s] %s%s | ctx %s%% | $%s%s' "$model" "$dir" "${branch:+ ($branch)}" "$ctx" "$cost" "${run:+ | spec: $run}"
