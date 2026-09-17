#!/usr/bin/env bash
# Render FEATURE_DIR/usage-report.md from usage-log.jsonl — read only. Nothing tracks
# by itself: lines come from dcm-append-usage.sh / dcm-track-session.sh, called by the
# command bodies. An empty log means nobody tracked.
# Usage: dcm-render-usage-report.sh --feature-dir specs/001-foo
set -euo pipefail

FEATURE_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --feature-dir) FEATURE_DIR="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$FEATURE_DIR" ]]; then
  echo "Required: --feature-dir" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="${SCRIPT_DIR}/../templates/usage-report.template.md"
LOG="${FEATURE_DIR}/usage-log.jsonl"
OUT="${FEATURE_DIR}/usage-report.md"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "Template missing: $TEMPLATE" >&2
  exit 1
fi

touch "$LOG"

LINE_COUNT=0
if [[ -f "$LOG" ]]; then
  LINE_COUNT=$(grep -c "[^[:space:]]" "$LOG" 2>/dev/null || true)
fi
if [[ "$LINE_COUNT" -eq 0 ]]; then
  SPEC_SLUG=$(basename "$FEATURE_DIR")
  echo ""
  echo "⚠️  Aucune donnée de tracking pour : $SPEC_SLUG"
  echo ""
  echo "Ce spec n'a pas de fichier usage-log.jsonl rempli."
  echo "Le tracking automatique n'était pas encore actif pour les anciens epics."
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  Pour les nouveaux epics, le tracking démarre automatiquement"
  echo "  dès que tu lances : /speckit.dcm.specify"
  echo ""
  echo "  Pour activer le tracking sur cette machine, mets à jour"
  echo "  l'extension DCM en exécutant :"
  echo ""
  echo "    ./spec-kit-dcm-workflow/scripts/sync-dcm-extension.sh"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  exit 0
fi

python3 - "$TEMPLATE" "$LOG" "$OUT" "$FEATURE_DIR" <<'PY'
import json, re, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

template_path, log_path, out_path, feature_dir = sys.argv[1:]
rows = []
if Path(log_path).exists():
    for line in Path(log_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue

def fmt(n):
    if n is None:
        return "—"
    return f"{n:,}"

def money(v):
    if v is None:
        return "—"
    # Per-line costs are fractions of a cent (4 decimals), totals need a separator.
    if abs(v) < 1:
        return f"{v:.4f}"
    return f"{v:,.2f}"

def share(part, whole):
    if not whole:
        return "0%"
    return f"{round(100 * part / whole)}%"

def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}

def jira_link(key, url):
    if not key:
        return "—"
    return f"[{key}]({url})" if url else key

def cell(v):
    return str(v).replace("|", "\\|") if v not in ("", None) else "—"

by_model = defaultdict(lambda: {"runs": 0, "tokens": 0, "cost": 0.0, "providers": defaultdict(int)})
by_step = defaultdict(lambda: {"runs": 0, "tokens": 0, "cost": 0.0, "models": set(), "skills": set(), "logged": 0})
by_provider = defaultdict(lambda: {"runs": 0, "tokens": 0, "cost": 0.0, "real": 0})
total_in = total_out = total_cache = total = 0
total_cost = None
unknown = real_count = est_count = 0
match_seen = match_ok = 0
models, providers, work_modes, epic_skills = set(), set(), set(), set()
starts, ends = [], []
log_jira, log_pr = defaultdict(set), {}

for r in rows:
    step = r.get("step") or "—"
    model = r.get("model") or "—"
    provider = r.get("provider") or "—"
    ti, to, tt = r.get("tokens_input"), r.get("tokens_output"), r.get("tokens_total")
    cache = r.get("tokens_cache_read")
    cost = r.get("cost_usd")
    if model != "—":
        models.add(model)
    if provider != "—":
        providers.add(provider)
    if r.get("work_mode"):
        work_modes.add(r["work_mode"])
    if tt is None and (ti is not None or to is not None):
        tt = (ti or 0) + (to or 0)
    if ti is None and to is None and tt is None:
        unknown += 1
    else:
        total_in += ti or 0
        total_out += to or 0
        total += tt or 0
    total_cache += cache or 0
    if cost is not None:
        total_cost = (total_cost or 0.0) + cost
    if r.get("estimated") is False:
        real_count += 1
    else:
        est_count += 1
    if r.get("model_match") is not None:
        match_seen += 1
        if r["model_match"]:
            match_ok += 1
    for when, bucket in ((r.get("started_at") or r.get("ts"), starts), (r.get("ended_at") or r.get("ts"), ends)):
        if when:
            bucket.append(when)
    skills = [s for s in (r.get("skills_used") or []) if s]
    epic_skills.update(skills)
    for key in r.get("jira_keys") or []:
        log_jira[key].add(r.get("task") or "")
        if r.get("pr_url"):
            log_pr[key] = r["pr_url"]
    by_model[model]["runs"] += 1
    by_model[model]["tokens"] += tt or 0
    by_model[model]["cost"] += cost or 0.0
    by_model[model]["providers"][provider] += 1
    by_step[step]["runs"] += 1
    by_step[step]["tokens"] += tt or 0
    by_step[step]["cost"] += cost or 0.0
    by_step[step]["models"].add(model)
    by_step[step]["skills"].update(skills)
    by_step[step]["logged"] += 1 if skills else 0
    by_provider[provider]["runs"] += 1
    by_provider[provider]["tokens"] += tt or 0
    by_provider[provider]["cost"] += cost or 0.0
    by_provider[provider]["real"] += 1 if r.get("estimated") is False else 0

step_lines = [
    f"| `{s}` | {v['runs']} | **{fmt(v['tokens'])}** | {share(v['tokens'], total)} | "
    f"{', '.join(f'`{m}`' for m in sorted(v['models']))} | {money(v['cost'])} |"
    for s, v in sorted(by_step.items(), key=lambda x: -x[1]["tokens"])
] or ["| — | 0 | — | 0% | — | — |"]

provider_lines = [
    f"| `{p}` | {v['runs']} | {fmt(v['tokens'])} | {money(v['cost'])} | {share(v['real'], v['runs'])} |"
    for p, v in sorted(by_provider.items(), key=lambda x: -x[1]["tokens"])
] or ["| — | 0 | — | — | 0% |"]

model_lines = [
    f"| `{m}` | `{max(v['providers'].items(), key=lambda x: x[1])[0]}` | {v['runs']} | "
    f"{fmt(v['tokens'])} | {money(v['cost'])} |"
    for m, v in sorted(by_model.items(), key=lambda x: -x[1]["tokens"])
] or ["| — | — | 0 | — | — |"]

skill_lines = [
    f"| `{s}` | {v['runs']} | {', '.join(f'`{k}`' for k in sorted(v['skills'])) or '—'} | "
    f"{'explicite' if v['logged'] else 'non loggé'} |"
    for s, v in sorted(by_step.items(), key=lambda x: -x[1]["tokens"])
] or ["| — | 0 | — | non loggé |"]

mapping = load_json(Path(feature_dir) / "jira-mapping.json")
manifest = load_json(Path(feature_dir) / "dispatch-manifest.json")
epic = mapping.get("epic") or manifest.get("epic") or {}
epic_key = epic.get("key")
# dispatch-manifest.json is not schema-stable: the Story key appears as jira_key,
# jira or jira_story_key, the link as jira_url. Accept every spelling rather than
# render an empty Jira column.
stories = mapping.get("stories") or [
    {
        "task_id": d.get("task_id"),
        "key": d.get("jira_key") or d.get("jira") or d.get("jira_story_key"),
        "branch": d.get("branch"),
        "url": d.get("jira_url") or d.get("url"),
    }
    for d in (manifest.get("dispatch") or [])
]

jira_lines = []
if epic_key:
    jira_lines.append(
        f"| Epic | {jira_link(epic_key, epic.get('url'))} | — | — | {cell(log_pr.get(epic_key))} |"
    )
seen_keys = {epic_key}
for s in stories:
    key = s.get("key")
    seen_keys.add(key)
    branch = s.get("branch")
    jira_lines.append(
        f"| Story | {jira_link(key, s.get('url'))} | {cell(s.get('task_id'))} | "
        f"{('`%s`' % branch) if branch else '—'} | {cell(s.get('pr_url') or log_pr.get(key))} |"
    )
for key in sorted(k for k in log_jira if k not in seen_keys):
    tasks = ", ".join(sorted(t for t in log_jira[key] if t)) or None
    jira_lines.append(f"| Story | {key} | {cell(tasks)} | — | {cell(log_pr.get(key))} |")
if not jira_lines:
    jira_lines = ["| — | — | — | — | — |"]

ac_done = ac_total = 0
spec_path = Path(feature_dir) / "spec.md"
if spec_path.exists():
    in_ac = False
    for line in spec_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            in_ac = "acceptance criteria" in heading or "critères d" in heading
            continue
        if in_ac:
            m = re.match(r"\s*[-*]\s*\[( |x|X)\]", line)
            if m:
                ac_total += 1
                if m.group(1).lower() == "x":
                    ac_done += 1

if real_count and not est_count:
    accuracy = "réel"
elif est_count and not real_count:
    accuracy = "estimé"
else:
    accuracy = f"mixte ({share(real_count, real_count + est_count)} réel)"

slug = Path(feature_dir).name
text = Path(template_path).read_text(encoding="utf-8")
repl = {
    "{FEATURE_DIR}": feature_dir,
    "{SPEC_SLUG}": slug,
    "{EPIC}": jira_link(epic_key, epic.get("url")),
    "{STORIES}": ", ".join(
        jira_link(s.get("key"), s.get("url")) for s in stories if s.get("key")
    ) or "—",
    "{PERIOD_START}": min(starts) if starts else "—",
    "{PERIOD_END}": max(ends) if ends else "—",
    "{GENERATED_AT}": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "{TOTAL_TOKENS}": fmt(total if rows else None),
    "{TOTAL_INPUT}": fmt(total_in if rows else None),
    "{TOTAL_OUTPUT}": fmt(total_out if rows else None),
    "{TOTAL_CACHE_READ}": fmt(total_cache if rows else None),
    "{TOTAL_COST}": money(total_cost),
    "{ACCURACY_LABEL}": accuracy if rows else "—",
    "{REAL_COUNT}": str(real_count),
    "{EST_COUNT}": str(est_count),
    "{STEP_COUNT}": str(len(rows)),
    "{UNKNOWN_COUNT}": str(unknown),
    "{PROVIDERS}": ", ".join(sorted(providers)) or "—",
    "{MODELS}": ", ".join(sorted(models)) or "—",
    "{WORK_MODES}": ", ".join(sorted(work_modes)) or "—",
    "{AC_COVERAGE}": (
        f"{ac_done}/{ac_total} ({share(ac_done, ac_total)})"
        if ac_total
        else "— (pas de section Acceptance Criteria dans spec.md)"
    ),
    "{PREF_MATCH}": f"{share(match_ok, match_seen)} ({match_ok}/{match_seen})" if match_seen else "—",
    "{EPIC_SKILLS}": ", ".join(f"`{s}`" for s in sorted(epic_skills)) or "— (aucun skill loggé)",
    "{REPORT_NAME}": f"{epic_key}-{slug}.md" if epic_key else f"{slug}.md",
}
for k, v in repl.items():
    text = text.replace(k, v)

def fill(marker, lines):
    return text.replace(f"<!-- {marker} -->", "\n".join(lines))

text = fill("BY_STEP", step_lines)
text = fill("JIRA_TABLE", jira_lines)
text = fill("BY_PROVIDER", provider_lines)
text = fill("BY_MODEL", model_lines)
text = fill("SKILLS_USED", skill_lines)

leftover = sorted(set(re.findall(r"\{[A-Z][A-Z0-9_]*\}", text)))
leftover += sorted(set(re.findall(r"<!--\s*[A-Z][A-Z0-9_]*\s*-->", text)))
if leftover:
    print(f"Rendu incomplet — placeholders non résolus dans {template_path} :", file=sys.stderr)
    for key in leftover:
        print(f"  - {key}", file=sys.stderr)
    print("Rapport non écrit. Corrige le template ou le renderer.", file=sys.stderr)
    raise SystemExit(1)

Path(out_path).write_text(text, encoding="utf-8")
print(out_path)
PY
