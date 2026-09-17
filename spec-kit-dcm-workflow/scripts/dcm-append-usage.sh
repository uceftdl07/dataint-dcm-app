#!/usr/bin/env bash
# Append one usage row to FEATURE_DIR/usage-log.jsonl.
# Usage:
#   dcm-append-usage.sh --feature-dir specs/001-foo \
#     --step specify --provider claude --model claude-sonnet \
#     --work-mode speckit --outcome ok \
#     --input 1200 --output 800 --cache-read 200 \
#     --source claude --estimated false \
#     --jira-keys DCINT-100,DCINT-101 --pr-url https://… --branch frontend/001-x \
#     --actor "Zahra" --git-author "Zahra <z@…>" \
#     --model-recommended claude-sonnet \
#     --started 2026-07-27T10:00:00Z --ended 2026-07-27T10:12:00Z \
#     --notes "intake + spec.md" \
#     --skills "dcm-python,dcm-verify"
set -euo pipefail

FEATURE_DIR=""
STEP=""
TASK=""
PROVIDER=""
MODEL=""
MODEL_RECOMMENDED=""
INPUT=""
OUTPUT=""
CACHE_READ=""
CACHE_WRITE=""
SOURCE="estimate"
ESTIMATED="true"
STARTED=""
ENDED=""
NOTES=""
WORK_MODE=""
OUTCOME=""
JIRA_KEYS=""
PR_URL=""
BRANCH=""
ACTOR=""
GIT_AUTHOR=""
SKILLS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --feature-dir) FEATURE_DIR="$2"; shift 2 ;;
    --step) STEP="$2"; shift 2 ;;
    --task) TASK="$2"; shift 2 ;;
    --provider) PROVIDER="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --model-recommended) MODEL_RECOMMENDED="$2"; shift 2 ;;
    --input) INPUT="$2"; shift 2 ;;
    --output) OUTPUT="$2"; shift 2 ;;
    --cache-read) CACHE_READ="$2"; shift 2 ;;
    --cache-write) CACHE_WRITE="$2"; shift 2 ;;
    --source) SOURCE="$2"; shift 2 ;;
    --estimated) ESTIMATED="$2"; shift 2 ;;
    --started) STARTED="$2"; shift 2 ;;
    --ended) ENDED="$2"; shift 2 ;;
    --notes) NOTES="$2"; shift 2 ;;
    --work-mode) WORK_MODE="$2"; shift 2 ;;
    --outcome) OUTCOME="$2"; shift 2 ;;
    --jira-keys) JIRA_KEYS="$2"; shift 2 ;;
    --pr-url) PR_URL="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --actor) ACTOR="$2"; shift 2 ;;
    --git-author) GIT_AUTHOR="$2"; shift 2 ;;
    --skills) SKILLS="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$FEATURE_DIR" || -z "$STEP" ]]; then
  echo "Required: --feature-dir and --step" >&2
  exit 2
fi

# Default work_mode from step context
if [[ -z "$WORK_MODE" ]]; then
  case "$STEP" in
    specify|plan|tasks|dispatch|implement|review|publish-pr|sync-status)
      WORK_MODE="speckit"
      ;;
    other|direct)
      WORK_MODE="direct"
      ;;
    *)
      WORK_MODE="direct"
      ;;
  esac
fi

case "$WORK_MODE" in
  speckit|direct|manual|ai) ;;
  *) echo "Invalid --work-mode: $WORK_MODE (speckit|direct|manual|ai)" >&2; exit 2 ;;
esac
if [[ -n "$OUTCOME" ]]; then
  case "$OUTCOME" in
    ok|fail|partial|skipped) ;;
    *) echo "Invalid --outcome: $OUTCOME (ok|fail|partial|skipped)" >&2; exit 2 ;;
  esac
fi

# Infer the provider from source/model when it was not passed
if [[ -z "$PROVIDER" ]]; then
  case "${SOURCE}|${MODEL}" in
    *claude*|*anthropic*) PROVIDER="claude" ;;
    *copilot*|*gpt-4*|*gpt-5*) PROVIDER="copilot" ;;
    *) PROVIDER="estimate" ;;
  esac
fi

if [[ -z "$MODEL_RECOMMENDED" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ -x "$SCRIPT_DIR/dcm-model-pref.sh" ]]; then
    MODEL_RECOMMENDED="$("$SCRIPT_DIR/dcm-model-pref.sh" --step "$STEP" 2>/dev/null || true)"
  fi
fi

if [[ -z "$GIT_AUTHOR" ]]; then
  GIT_AUTHOR="$(git -C "$(pwd)" log -1 --format='%an <%ae>' 2>/dev/null || true)"
  if [[ -z "$GIT_AUTHOR" ]]; then
    _gn="$(git -C "$(pwd)" config user.name 2>/dev/null || true)"
    _ge="$(git -C "$(pwd)" config user.email 2>/dev/null || true)"
    if [[ -n "$_gn" ]]; then
      GIT_AUTHOR="$_gn${_ge:+ <$_ge>}"
    fi
  fi
fi
if [[ -z "$ACTOR" && -n "$GIT_AUTHOR" ]]; then
  ACTOR="$(echo "$GIT_AUTHOR" | sed 's/ <.*//')"
fi
if [[ -z "$BRANCH" && -z "$TASK" ]]; then
  BRANCH="$(git -C "$(pwd)" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
fi
# Enrich jira/pr/branch from dispatch-manifest when task known
MANIFEST="$FEATURE_DIR/dispatch-manifest.json"
if [[ -f "$MANIFEST" ]]; then
  ENRICH="$(python3 - "$MANIFEST" "$TASK" "$JIRA_KEYS" "$PR_URL" "$BRANCH" <<'PY'
import json, sys
path, task, jira, pr, branch = sys.argv[1:]
try:
    data = json.load(open(path, encoding="utf-8"))
except Exception:
    print(f"{jira}|{pr}|{branch}")
    raise SystemExit(0)
epic = (data.get("epic") or {})
matched = False
for row in data.get("dispatch") or []:
    if task and row.get("task_id") == task:
        matched = True
        keys = []
        if jira:
            keys.extend([k.strip() for k in jira.split(",") if k.strip()])
        # dispatch-manifest.json spells the Story key three ways across specs
        # (jira_key, jira, jira_story_key) — reading one loses the enrichment.
        row_key = row.get("jira_key") or row.get("jira") or row.get("jira_story_key")
        if row_key and row_key not in keys:
            keys.append(row_key)
        jira = ",".join(keys) if keys else jira
        if not branch and row.get("branch"):
            branch = row["branch"]
        if not pr and row.get("pr_url"):
            pr = row["pr_url"]
        break
# Fall back to the Epic key only when no task row matched
if not jira and not matched and epic.get("key"):
    jira = epic["key"]
print(f"{jira}|{pr}|{branch}")
PY
)"
  JIRA_KEYS="${ENRICH%%|*}"
  REST="${ENRICH#*|}"
  PR_URL="${REST%%|*}"
  BRANCH="${REST#*|}"
fi

if [[ -z "$BRANCH" ]]; then
  BRANCH="$(git -C "$(pwd)" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
fi
mkdir -p "$FEATURE_DIR"
LOG="$FEATURE_DIR/usage-log.jsonl"
TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
STARTED="${STARTED:-$TS}"
ENDED="${ENDED:-$TS}"

python3 - "$LOG" "$TS" "$STEP" "$TASK" "$PROVIDER" "$MODEL" "$INPUT" "$OUTPUT" \
  "$CACHE_READ" "$CACHE_WRITE" "$SOURCE" "$ESTIMATED" "$STARTED" "$ENDED" "$NOTES" \
  "$WORK_MODE" "$OUTCOME" "$JIRA_KEYS" "$PR_URL" "$BRANCH" \
  "$ACTOR" "$GIT_AUTHOR" "$MODEL_RECOMMENDED" "$SKILLS" <<'PY'
import json, sys
from datetime import datetime

(
    path, ts, step, task, provider, model, inp, out,
    cache_r, cache_w, source, estimated, started, ended, notes,
    work_mode, outcome, jira_keys, pr_url, branch,
    actor, git_author, model_recommended, skills_raw,
) = sys.argv[1:]

def num(v):
    if v is None or v == "" or str(v).lower() in ("null", "none", "unknown", "-"):
        return None
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return None

def parse_bool(v):
    return str(v).lower() in ("1", "true", "yes", "y")

def nonempty(v):
    return v if v not in ("", None) else None

# Approximate public list rates, USD / 1M tokens (input, output)
RATES = {
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "claude-sonnet": (3.0, 15.0),
    "claude-opus": (15.0, 75.0),
    "claude-haiku": (0.8, 4.0),
    "composer": (3.0, 15.0),
    "copilot": (2.5, 10.0),
}
FALLBACK = (3.0, 15.0)

def rate_for(model_name):
    if not model_name:
        return FALLBACK
    key = model_name.lower()
    for k, v in RATES.items():
        if k in key:
            return v
    return FALLBACK

inp_n, out_n = num(inp), num(out)
cr_n, cw_n = num(cache_r), num(cache_w)
total = None
if inp_n is not None or out_n is not None:
    total = (inp_n or 0) + (out_n or 0)

duration_s = None
try:
    t0 = datetime.fromisoformat(started.replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(ended.replace("Z", "+00:00"))
    duration_s = max(0, int((t1 - t0).total_seconds()))
except Exception:
    duration_s = None

cost = None
if inp_n is not None or out_n is not None:
    rin, rout = rate_for(model or None)
    cost = ((inp_n or 0) / 1_000_000) * rin + ((out_n or 0) / 1_000_000) * rout
    if cr_n:
        cost += (cr_n / 1_000_000) * (rin * 0.1)

jira_list = [k.strip() for k in (jira_keys or "").split(",") if k.strip()] or None
skills_list = [s.strip() for s in (skills_raw or "").split(",") if s.strip()] or None

model_match = None
if model and model_recommended:
    ml, rl = model.lower(), model_recommended.lower()
    model_match = rl in ml or ml in rl or any(
        tok in ml and tok in rl for tok in ("sonnet", "opus", "haiku", "composer", "gpt", "copilot")
    )

row = {
    "ts": ts,
    "started_at": started or ts,
    "ended_at": ended or ts,
    "duration_s": duration_s,
    "step": step,
    "task": nonempty(task),
    "work_mode": work_mode or "direct",  # speckit | direct | manual | ai
    "outcome": nonempty(outcome),  # ok | fail | partial | skipped
    "provider": provider or "estimate",  # claude | copilot | estimate
    "model": nonempty(model),
    "model_recommended": nonempty(model_recommended),
    "model_match": model_match,
    "tokens_input": inp_n,
    "tokens_output": out_n,
    "tokens_cache_read": cr_n,
    "tokens_cache_write": cw_n,
    "tokens_total": total,
    "cost_usd": round(cost, 6) if cost is not None else None,
    "source": source or "estimate",  # claude|copilot|manual|estimate|unknown
    "estimated": parse_bool(estimated) if estimated != "" else True,
    "jira_keys": jira_list,
    "pr_url": nonempty(pr_url),
    "branch": nonempty(branch),
    "actor": nonempty(actor),
    "git_author": nonempty(git_author),
    "notes": nonempty(notes),
    "skills_used": skills_list,
}
with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps(row, ensure_ascii=False) + "\n")
print(path)
PY
