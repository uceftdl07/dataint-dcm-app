#!/usr/bin/env bash
# dcm-track-session.sh — token tracking for one speckit step, appended to
# FEATURE_DIR/usage-log.jsonl. Sources, each one traced (skips included):
#   ~/.claude/projects/**/*.jsonl        → Claude tokens (real)
#   ~/Library/.../GitHub Copilot Chat.log → Copilot ccreq (estimated)
# Window starts at .dcm-step-start.json, written by dcm-step-start.sh.
#
# Usage (run at the end of a step, not by hand):
#   dcm-track-session.sh --feature-dir specs/011-xxx --step implement [--task T001]
#   dcm-track-session.sh --feature-dir specs/011-xxx --step implement --dry-run
#
# Options:
#   --feature-dir   Required. e.g. specs/011-system-tables
#   --step          Required. specify|tasks|implement|review|publish-pr|other
#   --task          Optional. e.g. T001
#   --dry-run       Print what would be written, don't write
#   --work-mode     speckit|direct|manual|ai (default: speckit)
#   --outcome       ok|fail|partial|skipped (default: ok)
set -euo pipefail

FEATURE_DIR=""
STEP=""
TASK=""
DRY_RUN=false
WORK_MODE="speckit"
OUTCOME="ok"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --feature-dir) FEATURE_DIR="$2"; shift 2 ;;
    --step)        STEP="$2";         shift 2 ;;
    --task)        TASK="$2";         shift 2 ;;
    --dry-run)     DRY_RUN=true;      shift 1 ;;
    --work-mode)   WORK_MODE="$2";    shift 2 ;;
    --outcome)     OUTCOME="$2";      shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$FEATURE_DIR" || -z "$STEP" ]]; then
  echo "Required: --feature-dir and --step" >&2
  echo "Usage: dcm-track-session.sh --feature-dir specs/011-xxx --step implement" >&2
  exit 2
fi

mkdir -p "$FEATURE_DIR"

python3 - \
  "$FEATURE_DIR" "$STEP" "$TASK" "$DRY_RUN" "$WORK_MODE" "$OUTCOME" \
  <<'PY'
import json, os, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

feature_dir, step, task, dry_run_s, work_mode, outcome = sys.argv[1:]
dry_run    = dry_run_s.lower() == "true"
now        = datetime.now(tz=timezone.utc)
log_path   = Path(feature_dir) / "usage-log.jsonl"

marker_path = Path(feature_dir) / ".dcm-step-start.json"
since = None
marker_info = None
if marker_path.exists():
    try:
        marker_info = json.loads(marker_path.read_text(encoding="utf-8"))
        since = datetime.fromisoformat(
            marker_info["started_at"].replace("Z", "+00:00")
        )
        print(f"[dcm-track] start marker found → since {marker_info['started_at']} (step: {marker_info.get('step','?')})")
        # Marker wins only where nothing explicit was passed
        if not step or step == "other":
            step = marker_info.get("step") or step
        if not task:
            task = marker_info.get("task") or ""
    except Exception as e:
        print(f"[dcm-track] ⚠️  Could not read .dcm-step-start.json: {e} — falling back to 90min window")

if since is None:
    since = now - timedelta(minutes=90)
    print(f"[dcm-track] No start marker found in {feature_dir}/.dcm-step-start.json")
    print(f"[dcm-track] Fallback: scanning last 90min window since {since.strftime('%Y-%m-%dT%H:%M:%SZ')}")

elapsed_min = int((now - since).total_seconds() / 60)
print(f"[dcm-track] Tracking window: {since.strftime('%H:%M:%S')} → {now.strftime('%H:%M:%S')} UTC ({elapsed_min} min)")

import subprocess

def git_info():
    def run(*args):
        try:
            r = subprocess.run(list(args), capture_output=True, text=True, timeout=5)
            return r.stdout.strip() or None
        except Exception:
            return None
    name   = run("git", "config", "user.name")
    email  = run("git", "config", "user.email")
    branch = run("git", "rev-parse", "--abbrev-ref", "HEAD")
    author = f"{name} <{email}>" if name and email else name or email
    return name, author, branch

actor, git_author, branch = git_info()

# USD per 1M tokens (input, output)
PRICES = {
    "claude-sonnet":    (3.00,  15.00),
    "claude-sonnet-4":  (3.00,  15.00),
    "claude-opus":      (15.00, 75.00),
    "claude-haiku":     (0.25,  1.25),
    "gpt-4o":           (2.50,  10.00),
    "gpt-4o-mini":      (0.15,  0.60),
    "o1":               (15.00, 60.00),
    "o3":               (10.00, 40.00),
    "default":          (3.00,  15.00),
}

def cost_usd(model: str, inp: int, out: int) -> float:
    m = (model or "").lower()
    rate_in, rate_out = PRICES["default"]
    for key, rates in PRICES.items():
        if key != "default" and key in m:
            rate_in, rate_out = rates
            break
    return round((inp * rate_in + out * rate_out) / 1_000_000, 6)

# ccreq estimation: Copilot logs no token count, only a duration and a context.
MODEL_OUTPUT_RATES = {
    "gpt-4o-mini": (165, 150),
    "gpt-4o":      (110, 180),
    "claude-sonnet": (120, 220),
    "claude-opus":  (70,  300),
    "claude-haiku": (200, 120),
    "default":      (100, 200),
}
CONTEXT_PROFILES = {
    "panel/editAgent":              (4000, 10, 300),
    "panel/chat":                   (2000,  5, 200),
    "copilotLanguageModelWrapper":  (1000, 12, 150),
    "workspace/command":            (2500,  7, 250),
    "default":                      (1500,  8, 200),
}
CCREQ = re.compile(
    r"ccreq:([a-f0-9]+)\.copilotmd\s*\|\s*(success|error)\s*\|\s*([^|]+?)\s*\|\s*(\d+)ms\s*\|\s*\[([^\]]+)\]"
)
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})")

def estimate_copilot(model: str, duration_ms: int, context: str):
    profile = CONTEXT_PROFILES.get(context, CONTEXT_PROFILES["default"])
    base_input, input_ratio, overhead = profile
    norm = model.lower()
    rate, latency = MODEL_OUTPUT_RATES["default"]
    for key, conf in MODEL_OUTPUT_RATES.items():
        if key != "default" and key in norm:
            rate, latency = conf
            break
    gen_time = max(duration_ms - latency - overhead, 100)
    out  = int(gen_time / 1000.0 * rate + 0.999)
    inp  = max(base_input, int(out * input_ratio + 0.999))
    return inp, out

def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

rows         = []
sources_ok   = []       # (path, count, provider)
sources_skip = []       # (path, reason)

# 1. Claude — real tokens
claude_roots = [
    Path(os.environ.get("DCM_CLAUDE_ROOT", Path.home() / ".claude" / "projects")),
    Path.home() / ".config" / "claude",
]

for root in claude_roots:
    if not root.is_dir():
        sources_skip.append((str(root), "dir not found"))
        continue
    jsonl_files = list(root.rglob("*.jsonl"))
    if not jsonl_files:
        sources_skip.append((str(root), "no .jsonl files"))
        continue
    for path in jsonl_files:
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if mtime < since:
                continue
        except OSError:
            sources_skip.append((str(path), "stat() failed"))
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as e:
            sources_skip.append((str(path), f"unreadable: {e}"))
            continue

        count = 0
        for line in text.splitlines():
            if '"assistant"' not in line or '"usage"' not in line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "assistant":
                continue
            msg   = obj.get("message") or {}
            usage = msg.get("usage") or {}
            model = msg.get("model") or "claude"
            if not model or model.startswith("<"):
                continue
            tin  = usage.get("input_tokens")
            tout = usage.get("output_tokens")
            if tin is None and tout is None:
                continue
            ts_raw = obj.get("timestamp")
            try:
                row_dt = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                if row_dt.tzinfo is None:
                    row_dt = row_dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if row_dt < since or row_dt > now:
                continue

            tin  = tin or 0
            tout = tout or 0
            cr   = usage.get("cache_read_input_tokens") or 0
            cw   = usage.get("cache_creation_input_tokens") or 0
            rows.append({
                "ts":                 iso(now),
                "started_at":         iso(row_dt),
                "ended_at":           iso(row_dt),
                "step":               step,
                "task":               task or None,
                "work_mode":          work_mode,
                "outcome":            outcome,
                "provider":           "claude",
                "model":              model,
                "tokens_input":       tin,
                "tokens_output":      tout,
                "tokens_cache_read":  cr or None,
                "tokens_cache_write": cw or None,
                "tokens_total":       tin + tout,
                "cost_usd":           cost_usd(model, tin + cr, tout),
                "source":             "claude",
                "source_path":        str(path),
                "readable":           True,
                "estimated":          False,
                "actor":              actor,
                "git_author":         git_author,
                "branch":             branch,
                "notes":              f"claude-jsonl:{path.name}",
            })
            count += 1

        if count > 0:
            sources_ok.append((str(path), count, "claude"))

# 2. Copilot — ccreq lines, estimated
log_bases = []
if os.environ.get("DCM_COPILOT_LOG_ROOT"):
    log_bases.append(Path(os.environ["DCM_COPILOT_LOG_ROOT"]))
else:
    home = Path.home()
    log_bases += [
        home / "Library/Application Support/Code/logs",
        home / ".config/Code/logs",
    ]

seen_req = set()
for base in log_bases:
    if not base.is_dir():
        sources_skip.append((str(base), "dir not found"))
        continue

    chat_logs = list(base.rglob("GitHub Copilot Chat.log"))
    if not chat_logs:
        sources_skip.append((str(base), "no GitHub Copilot Chat.log found"))
        continue

    for log in chat_logs:
        try:
            mtime = datetime.fromtimestamp(log.stat().st_mtime, tz=timezone.utc)
            if mtime < since:
                sources_skip.append((str(log), f"no activity in window (last modified {mtime.strftime('%Y-%m-%d %H:%M')} UTC)"))
                continue
        except OSError:
            sources_skip.append((str(log), "stat() failed"))
            continue

        try:
            content = log.read_text(encoding="utf-8", errors="ignore")
        except OSError as e:
            sources_skip.append((str(log), f"unreadable: {e}"))
            continue

        count = 0
        for line in content.splitlines():
            if "ccreq:" not in line:
                continue
            m  = CCREQ.search(line)
            tm = TS_RE.search(line)
            if not m or not tm:
                continue
            req_id, status, model_str, dur_s, context = m.groups()
            if status != "success" or req_id in seen_req:
                continue
            seen_req.add(req_id)
            model = model_str.split("->")[0].strip() if "->" in model_str else model_str.strip()
            try:
                row_dt = datetime.strptime(tm.group(1), "%Y-%m-%d %H:%M:%S.%f").replace(
                    tzinfo=timezone.utc
                )
            except Exception:
                continue
            if row_dt < since or row_dt > now:
                continue

            tin, tout = estimate_copilot(model, int(dur_s), context)
            rows.append({
                "ts":                 iso(now),
                "started_at":         iso(row_dt),
                "ended_at":           iso(row_dt),
                "step":               step,
                "task":               task or None,
                "work_mode":          work_mode,
                "outcome":            outcome,
                "provider":           "copilot",
                "model":              model,
                "tokens_input":       tin,
                "tokens_output":      tout,
                "tokens_cache_read":  None,
                "tokens_cache_write": None,
                "tokens_total":       tin + tout,
                "cost_usd":           cost_usd(model, tin, tout),
                "source":             "copilot-chat-log",
                "source_path":        str(log),
                "readable":           True,
                "estimated":          True,
                "actor":              actor,
                "git_author":         git_author,
                "branch":             branch,
                "notes":              f"ccreq:{req_id[:8]} dur={dur_s}ms ctx={context}",
            })
            count += 1

        if count > 0:
            sources_ok.append((str(log), count, "copilot"))

# 3. Summary
sep = "─" * 60
print(sep)
print(f"dcm-track-session  step={step}  window={elapsed_min}min  actor={actor or '?'}")
print(f"feature-dir: {feature_dir}")
print(sep)

if sources_ok:
    print(f"\n✅ Sources lues ({len(sources_ok)}):")
    for path, count, provider in sources_ok:
        print(f"   [{provider}] {path}")
        print(f"          → {count} entrée(s) dans la fenêtre")
else:
    print("\n⚠️  Aucune source lue dans la fenêtre de temps.")

if sources_skip:
    print(f"\n⚠️  Sources non disponibles ({len(sources_skip)}) — mentionnées honnêtement:")
    for path, reason in sources_skip:
        print(f"   ✗ {path}")
        print(f"          raison: {reason}")

total_in  = sum(r["tokens_input"]  or 0 for r in rows)
total_out = sum(r["tokens_output"] or 0 for r in rows)
total_cost = sum(r["cost_usd"]     or 0 for r in rows)
estimated_count = sum(1 for r in rows if r["estimated"])

print(f"\n📊 Résumé: {len(rows)} ligne(s) | "
      f"in={total_in:,} | out={total_out:,} | "
      f"cost=${total_cost:.4f} | "
      f"estimées={estimated_count}/{len(rows)}")

if dry_run:
    print(f"\n[DRY-RUN] Rien écrit dans {log_path}")
    if rows:
        print("Exemple de la 1ère ligne:")
        print(json.dumps(rows[0], ensure_ascii=False, indent=2))
    sys.exit(0)

# 4. Write
if rows:
    with open(log_path, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\n✅ {len(rows)} ligne(s) écrite(s) → {log_path}")
else:
    print(f"\nℹ️  Aucune ligne à écrire (0 token dans la fenêtre).")
    print("   → Vérifiez que vous avez utilisé Claude ou Copilot pendant cette session.")

# Step is done — the marker must not widen the next window.
if not dry_run and marker_path.exists():
    marker_path.unlink()
    print(f"[dcm-track] marker supprimé : {marker_path}")

print(sep)
PY
