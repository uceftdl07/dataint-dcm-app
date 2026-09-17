---
description: "Generate markdown usage report — Claude / Copilot tokens per DCM step"
tools:
  - bash
  - read
  - create_file
  - edit
---

# DCM Usage Report — Claude + Copilot

Local audit: **provider** (claude/copilot/estimate), **model**, **tokens**, **cost**, **dates**,
**work_mode**, **outcome**, **actor**, **Jira/PR**, **AC coverage**.

Where a row comes from — each line is written by one of two scripts, nothing else:

| Provider | Written by | Quality |
|----------|-----------|---------|
| **claude** | `dcm-track-session.sh` — parses `~/.claude/projects/**/*.jsonl` (`type=assistant` + `message.usage`) | **real** |
| **copilot** | `dcm-track-session.sh` — VS Code `GitHub Copilot Chat.log` `ccreq` lines → duration × tok/s + context profile | **estimate ~75–85%** |
| **estimate** | `dcm-append-usage.sh` — saisie manuelle (`--append`) | manual |

## Model preference (soft)

```bash
PREF=$(spec-kit-dcm-workflow/scripts/dcm-model-pref.sh --step usage-report)
echo "DCM model preference — step: usage-report → $PREF"
```

## User Input

$ARGUMENTS

Optional:
- `--spec 011-carousel-scoring`
- `--append` — append current chat turn
- `--provider claude|copilot|estimate`
- `--step …` / `--task T001` / `--model …`
- `--work-mode speckit|direct|manual|ai`
- `--outcome ok|fail|partial|skipped`
- `--jira-keys DCINT-100,DCINT-101`
- `--pr-url https://…` / `--branch …`
- `--actor "Name"` / `--git-author "…"`
- `--input N` / `--output N` / `--cache-read N`
- `--started ISO` / `--ended ISO`
- `--source claude|copilot|manual|estimate`
- `--estimated true|false`
- `--notes "..."`

### work_mode

| Value | Meaning |
|-------|---------|
| `speckit` | via `/speckit.dcm.*` slash commands |
| `direct` | free chat message to agent |
| `manual` | human did work without AI |
| `ai` | AI generic (when unclear) |

Default: `speckit` for workflow steps; `direct` for `--step other`.

---

## Step 1 — Resolve FEATURE_DIR

```bash
.specify/scripts/bash/check-prerequisites.sh --json 2>/dev/null || true
ls -d specs/*/ 2>/dev/null | tail -5
```

`FEATURE_DIR=specs/{num}-{slug}`

---

## Step 2 — Rendu du rapport

> Cette commande **ne track pas**. Le tracking se fait **avant**, dans chaque commande
> workflow (`specify`, `implement`, …) via `dcm-step-start.sh` (début) puis
> `dcm-track-session.sh` (fin) → une ou plusieurs lignes dans `usage-log.jsonl`.
> Voir [USAGE-AND-TOKENS.md](../USAGE-AND-TOKENS.md).
>
> Ici : lecture seule de `usage-log.jsonl` → génération de `usage-report.md`.
> Un log vide veut dire que personne n'a tracké, pas que l'étape n'a rien coûté.
>
> Si le spec est un **ancien epic** (pas de `usage-log.jsonl`), le script affiche un message
> explicatif en français et s'arrête sans créer de rapport.

```bash
chmod +x spec-kit-dcm-workflow/scripts/dcm-render-usage-report.sh

spec-kit-dcm-workflow/scripts/dcm-render-usage-report.sh --feature-dir "$FEATURE_DIR"
```

---

## Step 3 — Optional `--append`

```bash
spec-kit-dcm-workflow/scripts/dcm-append-usage.sh \
  --feature-dir "$FEATURE_DIR" \
  --step "${STEP:-other}" \
  --task "${TASK:-}" \
  --work-mode "${WORK_MODE:-direct}" \
  --outcome "${OUTCOME:-ok}" \
  --provider "${PROVIDER:-estimate}" \
  --model "$MODEL" \
  --input "${INPUT:-}" --output "${OUTPUT:-}" \
  --source "${SOURCE:-manual}" \
  --estimated "${ESTIMATED:-true}" \
  --jira-keys "${JIRA_KEYS:-}" \
  --pr-url "${PR_URL:-}" \
  --branch "${BRANCH:-}" \
  --actor "${ACTOR:-}" \
  --started "${STARTED:-}" --ended "${ENDED:-}" \
  --notes "${NOTES:-}"
```

Actor / git author / branch auto-filled from `git` if omitted.  
Jira/PR enriched from `dispatch-manifest.json` when `--task` matches.

---

## Examples

```text
/speckit.dcm.usage-report --spec 011-xxx
/speckit.dcm.usage-report --spec 011-xxx --append --provider copilot --model gpt-5 \
  --work-mode direct --outcome ok --input 3000 --output 900 --source manual
/speckit.dcm.usage-report --spec 011-xxx --append --step implement --task T002 \
  --work-mode manual --outcome ok --provider estimate --notes "RBAC Azure done by hand"
```
