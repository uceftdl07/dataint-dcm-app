#!/usr/bin/env bash
# dcm-step-start.sh — marker written when a step begins; dcm-track-session.sh reads
# it to know the exact start of the tracking window.
#
# Usage (called by the speckit commands, not by hand):
#   dcm-step-start.sh --feature-dir specs/011-xxx --step specify
#   dcm-step-start.sh --feature-dir specs/011-xxx --step implement --task T001
set -euo pipefail

FEATURE_DIR=""
STEP=""
TASK=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --feature-dir) FEATURE_DIR="$2"; shift 2 ;;
    --step)        STEP="$2";         shift 2 ;;
    --task)        TASK="$2";         shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$FEATURE_DIR" || -z "$STEP" ]]; then
  echo "Required: --feature-dir and --step" >&2
  exit 2
fi

mkdir -p "$FEATURE_DIR"

python3 - "$FEATURE_DIR" "$STEP" "$TASK" <<'PY'
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

feature_dir, step, task = sys.argv[1:]
now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def git(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip() or None
    except Exception:
        return None

actor  = git(["git", "config", "user.name"])
branch = git(["git", "rev-parse", "--abbrev-ref", "HEAD"])
email  = git(["git", "config", "user.email"])

marker = {
    "step":       step,
    "task":       task or None,
    "started_at": now,
    "actor":      actor,
    "email":      email,
    "branch":     branch,
}

marker_path = Path(feature_dir) / ".dcm-step-start.json"
marker_path.write_text(json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"[dcm-track] step '{step}' started at {now} — actor: {actor or '?'}")
PY
