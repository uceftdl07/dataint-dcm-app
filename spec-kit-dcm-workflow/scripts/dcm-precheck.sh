#!/usr/bin/env bash
# DCM hook gate — blocking pre-flight checks for the spec-driven steps, i.e. an
# exit-code contract instead of "MANDATORY / do NOT skip" prose.
#
# Usage: dcm-precheck.sh --gate <specify|plan|tasks|implement> [--spec <feature-dir>]
#
# Exit codes:
#   0  gate passed — safe to proceed
#   2  gate failed — required artifact missing (agent MUST stop)
#   1  usage / internal error
set -euo pipefail

GATE=""
SPEC_DIR=""

usage() {
  cat <<'EOF'
Usage: dcm-precheck.sh --gate <specify|plan|tasks|implement> [--spec <feature-dir>]

Gates:
  specify    require a *fresh* .specify/pending-intake.json (intake ran)
  plan       require a non-empty '## Prerequisites' section in FEATURE_DIR/spec.md
  tasks      require FEATURE_DIR/intake.json (scope persisted)
  implement  require FEATURE_DIR/tasks.md and at least one FEATURE_DIR/stories/*.md

FEATURE_DIR resolution (same order as the spec-kit commands):
  --spec <feature-dir>  →  $SPECIFY_FEATURE_DIRECTORY  →  .specify/feature.json
No fallback to "the last specs/*/": a gate that cannot identify the feature
exits 2 rather than checking a different one.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --gate) GATE="$2"; shift 2 ;;
    --spec) SPEC_DIR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

[[ -n "$GATE" ]] || { echo "Missing --gate" >&2; usage; exit 1; }

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

# Feature directory, resolved from the SAME sources as the spec-kit commands:
# --spec, then $SPECIFY_FEATURE_DIRECTORY, then .specify/feature.json.
#
# No "last specs/*/" fallback: it was `ls -d specs/*/ | sort | tail -1`, the
# lexicographic maximum, so working on 011 with a 015 on disk validated 015/spec.md
# — green on a file the command never touched. A gate that cannot tell which feature
# it guards must say so, not pick one.
#
# Sets FEATURE_DIR (empty on failure) + FEATURE_DIR_ERROR. Not called through
# `$(...)`: a subshell cannot report the reason back.
FEATURE_DIR=""
FEATURE_DIR_ERROR=""

# feature_directory out of .specify/feature.json — "" when absent or unparseable.
# Always returns 0: a parse failure is "no value", never an abort under `set -e`.
read_feature_json() {
  local fj=".specify/feature.json" val=""
  [[ -f "$fj" ]] || { printf ''; return 0; }
  val="$(python3 -c 'import json,sys
try:
    print(json.load(open(sys.argv[1])).get("feature_directory") or "")
except Exception:
    pass' "$fj" 2>/dev/null || true)"
  if [[ -z "$val" ]]; then
    val="$( { grep -E '"feature_directory"[[:space:]]*:' "$fj" 2>/dev/null || true; } \
      | head -1 | sed -E 's/^[^:]*:[[:space:]]*"([^"]*)".*$/\1/' )"
  fi
  printf '%s' "$val"
  return 0
}

resolve_feature_dir() {
  FEATURE_DIR=""
  FEATURE_DIR_ERROR=""
  local candidate="" origin=""

  if [[ -n "$SPEC_DIR" ]]; then
    origin="--spec"
    # A bare folder name is shorthand for specs/<name>.
    if [[ -d "$SPEC_DIR" ]]; then
      candidate="$SPEC_DIR"
    elif [[ -d "specs/$SPEC_DIR" ]]; then
      candidate="specs/$SPEC_DIR"
    else
      candidate="$SPEC_DIR"   # not a directory — reported below
    fi
  elif [[ -n "${SPECIFY_FEATURE_DIRECTORY:-}" ]]; then
    origin="\$SPECIFY_FEATURE_DIRECTORY"
    candidate="$SPECIFY_FEATURE_DIRECTORY"
  else
    origin=".specify/feature.json"
    candidate="$(read_feature_json)"
  fi

  if [[ -z "$candidate" ]]; then
    FEATURE_DIR_ERROR="no feature directory to check ($origin is empty or absent). Pass --spec <feature-dir>, or run /speckit.dcm.specify so it writes .specify/feature.json. This gate does not guess which specs/*/ you meant — it used to take the last one alphabetically, which silently checked the wrong feature."
    return 0
  fi

  candidate="${candidate#./}"
  candidate="${candidate%/}"
  if [[ ! -d "$candidate" ]]; then
    FEATURE_DIR_ERROR="$origin points at '$candidate', which is not a directory. Fix it, or pass --spec <feature-dir>."
    return 0
  fi
  FEATURE_DIR="$candidate"
}

fail() { echo "❌ GATE[$GATE] FAILED — $1" >&2; exit 2; }
pass() { echo "✅ GATE[$GATE] passed — $1"; exit 0; }

# Line number of the Prerequisites heading, either language — empty if absent.
# `pr[^ ]*requis` matches Prérequis whatever the locale (`é` is two bytes). One awk
# and no pipeline, so an early-closing pipe cannot fake a failure under `pipefail`.
prereq_start() {
  awk 'tolower($0) ~ /^##[[:space:]]+(prerequisites|pr[^[:space:]]*requis)[[:space:]]*:?[[:space:]]*$/ { print NR; exit }' "$1"
}

# Body of that section with placeholders dropped, so a heading followed by `TODO`
# counts as empty — which is what it is.
prereq_body() {
  local start; start="$(prereq_start "$1" || true)"
  [[ -n "$start" ]] || return 1
  awk -v start="$start" '
    NR <= start { next }
    /^##[[:space:]]/ { exit }
    {
      line = $0
      gsub(/^[[:space:]]*[-*+][[:space:]]*/, "", line)
      gsub(/[[:space:]]/, "", line)
      if (line == "" || line == "..." || line == "…" || line == "-") next
      if (toupper(line) == "TODO" || toupper(line) == "TBD" || toupper(line) == "N/A") next
      print
    }' "$1"
}

case "$GATE" in
  specify)
    PENDING=".specify/pending-intake.json"
    [[ -f "$PENDING" ]] \
      || fail "no $PENDING. Run the intake (/speckit.dcm.specify --intake-only) before creating spec.md."
    # specify.md copies the pending intake to FEATURE_DIR/intake.json then deletes it;
    # skip that last step and the leftover keeps this gate green for every later
    # feature, which inherits a previous scope. Byte-identical = leftover, not intake.
    for persisted in specs/*/intake.json; do
      [[ -f "$persisted" ]] || continue
      cmp -s "$PENDING" "$persisted" || continue
      fail "$PENDING is byte-identical to $persisted — leftover of a previous specify, not a fresh intake. Delete it, then run the intake again."
    done
    grep -qE '"work_type"[[:space:]]*:[[:space:]]*"[^"]+"' "$PENDING" \
      || fail "$PENDING has no work_type — the intake did not complete. Run it again."
    pass "fresh intake present — safe to write spec.md"
    ;;
  plan)
    resolve_feature_dir
    [[ -n "$FEATURE_DIR" ]] || fail "$FEATURE_DIR_ERROR"
    SPEC_MD="$FEATURE_DIR/spec.md"
    [[ -f "$SPEC_MD" ]] \
      || fail "$SPEC_MD missing. Run /speckit.dcm.specify before the plan step."
    # Captured, not piped: with `awk | grep -q`, grep closes the pipe on its first
    # match, awk takes a SIGPIPE and pipefail fails the gate on a valid spec.
    [[ -n "$(prereq_start "$SPEC_MD")" ]] \
      || fail "no '## Prerequisites' (or '## Prérequis') heading in $SPEC_MD. Every spec template ships one — restore it before planning."
    BODY="$(prereq_body "$SPEC_MD" || true)"
    [[ -n "$BODY" ]] \
      || fail "'## Prerequisites' in $SPEC_MD is empty or a placeholder. Fill it: small branches / few changed files per PR, intake confirmed, blocking deps resolved or deferred."
    # Warning on purpose: worth printing, not worth blocking a real spec over wording.
    grep -qiE 'small|petit|scoped|changed file|fichiers modifi|diff' <<<"$BODY" \
      || echo "ℹ️  GATE[plan] — no explicit 'small branches / few changed files' bullet. Recommended for PR review; not blocking." >&2
    pass "$SPEC_MD Prerequisites present and filled — safe to plan"
    ;;
  tasks)
    resolve_feature_dir
    [[ -n "$FEATURE_DIR" ]] || fail "$FEATURE_DIR_ERROR"
    [[ -f "$FEATURE_DIR/intake.json" ]] \
      || fail "$FEATURE_DIR/intake.json missing. Run /speckit.dcm.specify to persist the scope first."
    pass "$FEATURE_DIR/intake.json present — safe to generate tasks"
    ;;
  implement)
    resolve_feature_dir
    [[ -n "$FEATURE_DIR" ]] || fail "$FEATURE_DIR_ERROR"
    [[ -f "$FEATURE_DIR/tasks.md" ]] \
      || fail "$FEATURE_DIR/tasks.md missing. Run /speckit.dcm.tasks before implement."
    ls "$FEATURE_DIR"/stories/*.md >/dev/null 2>&1 \
      || fail "$FEATURE_DIR/stories/*.md missing. /speckit.dcm.tasks must generate the sub-specs first."
    pass "tasks.md + stories present — safe to implement"
    ;;
  *)
    echo "Unknown gate: $GATE" >&2; usage; exit 1 ;;
esac
