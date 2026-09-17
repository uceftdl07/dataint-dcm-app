#!/usr/bin/env bash
# Print preferred model for a DCM workflow step from dcm-config.yml
# Usage: dcm-model-pref.sh --step implement
set -euo pipefail

STEP=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --step) STEP="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$STEP" ]]; then
  echo "Required: --step" >&2
  exit 2
fi

# Normalize aliases
case "$STEP" in
  speckit.dcm.specify|specify) STEP="specify" ;;
  speckit.plan|speckit.dcm.plan-guide|plan) STEP="plan" ;;
  speckit.dcm.tasks|speckit.tasks|tasks) STEP="tasks" ;;
  speckit.dcm.dispatch|dispatch) STEP="dispatch" ;;
  speckit.dcm.implement|speckit.implement|implement) STEP="implement" ;;
  speckit.dcm.review|review) STEP="review" ;;
  speckit.dcm.publish-pr|publish-pr) STEP="publish-pr" ;;
  speckit.dcm.sync-status|sync-status) STEP="sync-status" ;;
  speckit.dcm.usage-report|usage-report) STEP="usage-report" ;;
esac

CONFIGS=(
  ".specify/extensions/dcm/dcm-config.yml"
  "spec-kit-dcm-workflow/dcm-config.template.yml"
)

python3 - "$STEP" "${CONFIGS[@]}" <<'PY'
import re, sys
from pathlib import Path

step = sys.argv[1]
paths = [Path(p) for p in sys.argv[2:]]

def parse_prefs(text: str) -> dict[str, str]:
    # model_preferences: block — key at indent 0, then its indented children
    m = re.search(r"(?m)^model_preferences:\s*\n((?:[ \t]+.+\n)+)", text)
    if not m:
        return {}
    block = m.group(1)
    out = {}
    for line in block.splitlines():
        mm = re.match(r"^\s+([A-Za-z0-9_-]+)\s*:\s*[\"']?([^\"'#\n]+?)[\"']?\s*(?:#.*)?$", line)
        if not mm:
            continue
        k, v = mm.group(1), mm.group(2).strip()
        if k in ("enforce_banner", "ask_if_mismatch"):
            continue
        out[k] = v
    return out

prefs = {}
used = None
for p in paths:
    if p.is_file():
        prefs = parse_prefs(p.read_text(encoding="utf-8"))
        if prefs:
            used = str(p)
            break

preferred = prefs.get(step) or prefs.get("default") or "claude-sonnet"
print(preferred)
if used:
    print(f"# source: {used}", file=sys.stderr)
PY
