#!/usr/bin/env bash
# DCM pre-commit review stamp helper
# Write / check a stamp so the Claude Code PreToolUse hook and .git/hooks/pre-commit
# can gate `git commit` on an actual agent review.
#
# Usage:
#   dcm-pre-commit-review-stamp.sh write --verdict PASS|WARN|FAIL --report PATH [--notes "..."]
#   dcm-pre-commit-review-stamp.sh check [--max-age-min 120] [--require-pass]
#   dcm-pre-commit-review-stamp.sh clear
#
# `--report` is REQUIRED for write and the report must declare the same verdict:
# without it, `write --verdict PASS` needed no evidence at all and the gate enforced
# "an agent said it reviewed", not "the review passed". dcm-review.sh emits
# `**Verdict**: **PASS** (fail=0 …)`; a hand-written report must carry the same line.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
STAMP_DIR="${DCM_REVIEW_STAMP_DIR:-$REPO_ROOT/.specify}"
STAMP_FILE="$STAMP_DIR/pre-commit-review-stamp.json"
CMD="${1:-}"
shift || true

MAX_AGE_MIN=120
REQUIRE_PASS=false
VERDICT=""
REPORT=""
NOTES=""
BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
HEAD_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
STAGED_HASH="$(git -C "$REPO_ROOT" diff --cached -U0 2>/dev/null | shasum -a 256 2>/dev/null | awk '{print $1}' || echo none)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --verdict) VERDICT="$2"; shift 2 ;;
    --report) REPORT="$2"; shift 2 ;;
    --notes) NOTES="$2"; shift 2 ;;
    --max-age-min) MAX_AGE_MIN="$2"; shift 2 ;;
    --require-pass) REQUIRE_PASS=true; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

case "$CMD" in
  write)
    case "$VERDICT" in
      PASS|WARN|FAIL) ;;
      *) echo "ERROR: --verdict PASS|WARN|FAIL required" >&2; exit 2 ;;
    esac
    # The stamp is bound to the staged diff: on an empty index no commit could
    # ever match it.
    if git -C "$REPO_ROOT" diff --cached --quiet 2>/dev/null; then
      echo "ERROR: nothing staged — the stamp would not match any commit." >&2
      echo "       Stage what you are about to commit first (git add …), then review." >&2
      exit 2
    fi

    if [[ -z "$REPORT" ]]; then
      echo "ERROR: --report PATH required." >&2
      echo "       The stamp records a review, so there has to be a review to point at:" >&2
      echo "       run dcm-review.sh --report specs/<feature>/review-….md, then stamp that file." >&2
      exit 2
    fi
    if [[ ! -f "$REPORT" ]]; then
      echo "ERROR: report not found: $REPORT" >&2
      echo "       Write the report first (dcm-review.sh --report …), then stamp it." >&2
      exit 2
    fi
    if [[ ! -s "$REPORT" ]]; then
      echo "ERROR: report is empty: $REPORT" >&2
      exit 2
    fi
    # Tolerant of markdown emphasis and of both languages, strict about the value:
    # this is what stops a PASS stamp over a report that says FAIL.
    REPORT_VERDICT="$(grep -ioE 'verdict[^A-Za-z]*(PASS|WARN|FAIL)' "$REPORT" 2>/dev/null \
      | head -1 | grep -ioE '(PASS|WARN|FAIL)$' | tr '[:lower:]' '[:upper:]' || true)"
    if [[ -z "$REPORT_VERDICT" ]]; then
      echo "ERROR: $REPORT declares no verdict." >&2
      echo "       It needs a line the gate can read, e.g.: **Verdict**: **$VERDICT**" >&2
      exit 2
    fi
    if [[ "$REPORT_VERDICT" != "$VERDICT" ]]; then
      echo "ERROR: --verdict $VERDICT but $REPORT says $REPORT_VERDICT." >&2
      echo "       Fix the findings and re-run the review; do not stamp over its verdict." >&2
      exit 2
    fi

    REPORT_HASH="$(shasum -a 256 "$REPORT" 2>/dev/null | awk '{print $1}' || echo unknown)"
    mkdir -p "$STAMP_DIR"
    NOW="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    export DCM_STAMP_PATH="$STAMP_FILE" DCM_STAMP_NOW="$NOW" DCM_STAMP_BRANCH="$BRANCH" \
      DCM_STAMP_HEAD="$HEAD_SHA" DCM_STAMP_STAGED="$STAGED_HASH" DCM_STAMP_VERDICT="$VERDICT" \
      DCM_STAMP_REPORT="$REPORT" DCM_STAMP_REPORT_HASH="$REPORT_HASH" DCM_STAMP_NOTES="$NOTES"
    python3 <<'PY'
import json, os
doc = {
  "updated_at": os.environ["DCM_STAMP_NOW"],
  "branch": os.environ["DCM_STAMP_BRANCH"],
  "head_sha": os.environ["DCM_STAMP_HEAD"],
  "staged_hash": os.environ["DCM_STAMP_STAGED"],
  "verdict": os.environ["DCM_STAMP_VERDICT"],
  # Auditable after the fact: which report backed the commit, and whether it changed.
  "report": os.environ.get("DCM_STAMP_REPORT") or "",
  "report_hash": os.environ.get("DCM_STAMP_REPORT_HASH") or "",
  "notes": os.environ.get("DCM_STAMP_NOTES") or "",
  "command": "speckit.dcm.review --commit",
}
path = os.environ["DCM_STAMP_PATH"]
open(path, "w").write(json.dumps(doc, indent=2) + "\n")
print(f"Wrote stamp: {path} ({doc['verdict']} ← {doc['report']})")
PY
    ;;
  check)
    if [[ ! -f "$STAMP_FILE" ]]; then
      echo "MISSING"
      echo "No pre-commit review stamp at $STAMP_FILE" >&2
      exit 1
    fi
    python3 - "$STAMP_FILE" "$MAX_AGE_MIN" "$REQUIRE_PASS" "$BRANCH" "$STAGED_HASH" <<'PY'
import json, sys
from datetime import datetime, timezone, timedelta

path, max_age, require_pass, branch, staged = sys.argv[1:6]
max_age = int(max_age)
require_pass = require_pass.lower() == "true"
doc = json.load(open(path))
updated = datetime.fromisoformat(doc["updated_at"].replace("Z", "+00:00"))
age = datetime.now(timezone.utc) - updated
ok = True
reasons = []
if age > timedelta(minutes=max_age):
    ok = False
    reasons.append(f"stamp expired ({int(age.total_seconds()//60)}m > {max_age}m)")
if doc.get("branch") != branch:
    ok = False
    reasons.append(f"branch mismatch stamp={doc.get('branch')} now={branch}")
if doc.get("staged_hash") and staged and doc.get("staged_hash") != staged and staged != "none":
    ok = False
    reasons.append("staged diff changed since review — re-run /speckit.dcm.review --commit")
verdict = doc.get("verdict", "")
if require_pass and verdict != "PASS":
    ok = False
    reasons.append(f"verdict={verdict} (PASS required)")
elif verdict == "FAIL":
    ok = False
    reasons.append("verdict=FAIL")
if ok:
    print(f"OK {verdict}")
    sys.exit(0)
print("STALE_OR_FAIL")
print("; ".join(reasons), file=sys.stderr)
sys.exit(1)
PY
    ;;
  clear)
    rm -f "$STAMP_FILE"
    echo "Cleared $STAMP_FILE"
    ;;
  *)
    echo "Usage: $0 write|check|clear ..." >&2
    exit 2
    ;;
esac
