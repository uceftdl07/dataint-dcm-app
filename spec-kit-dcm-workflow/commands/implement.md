---
description: "Task selection, branch check, per-task checkpoints during /{speckit}implement"
tools:
  - bash
---

# DCM Implement — sélection de task, branche, checkpoints

Hook `before_implement`. Une task à la fois : sélection, vérification de branche, chargement
du seul sub-spec concerné, puis **checkpoint** (question / continue / stop / review).

```bash
spec-kit-dcm-workflow/scripts/dcm-model-pref.sh --step implement   # préférence, pas un lock
```

## User Input

$ARGUMENTS

Optional: `T001`, `T002`, or `all` (sequential with checkpoints).

## Gate (hard, blocking — before implementing)

Run the gate. Non-zero exit = STOP (tasks.md or sub-specs missing):

```bash
spec-kit-dcm-workflow/scripts/dcm-precheck.sh --gate implement --spec {FEATURE_DIR}
```

## Prerequisites

- `FEATURE_DIR/tasks.md` exists
- `FEATURE_DIR/stories/T00X-*.md` for selected task
- `FEATURE_DIR/intake.json` for package scope

## Step 1 — Detect feature directory

```bash
.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
```

## Step 2 — List pending tasks (parser only — never read tasks.md by hand)

```bash
spec-kit-dcm-workflow/scripts/dcm-parse-tasks.sh --spec {FEATURE_DIR}
# TSV: task_id <TAB> status <TAB> domain <TAB> slug <TAB> branch <TAB> sub_spec <TAB> title
```

Build the table straight from the columns — `domain` and `branch` are the same values
dispatch used, so a mismatch cannot be introduced here:

```
| ID | Domain | Title | Status | Branch | Sub-spec |
|----|--------|-------|--------|--------|----------|
| T001 | frontend | Carousel UI | pending | frontend/011-carousel-ui | stories/T001-….md |
```

Exit **2** = `tasks.md` exists but no line is conforming → **STOP** and say so. It is not
"no task left to implement".

## Step 3 — AskQuestion — which task?

If `$ARGUMENTS` empty:

```
Quelle task implémenter ?

○ T001 — {title} (pending)
○ T002 — {title} (pending)
○ Prochaine pending automatiquement
○ Stop
```

**RULE**: Implement **ONE task at a time** unless user explicitly says `all` (still checkpoint after each).

## Step 4 — Branch verification

Expected branch = `dispatch-manifest.json` entry for the `task_id` if it exists,
otherwise the `branch` column from Step 2 (same pattern, same source).

```bash
git rev-parse --abbrev-ref HEAD
```

AskQuestion if branch mismatch:

```
Branche attendue : frontend/carousel-ui
Branche actuelle : main

Checkout branche fille ?
○ Oui — git fetch && git checkout {branch}
○ Non — je suis déjà sur la bonne branche / je gère moi-même
```

Hotfix work_type: branch prefix `hotfix/` from intake.

## Step 4.5 — Sync with develop (MANDATORY, blocking — before any code)

**Never start coding on a stale branch.** Run the gate right after branch verification, before touching files. It is **read-only** — it fetches and reports, it does not rewrite history:

```bash
spec-kit-dcm-workflow/scripts/dcm-branch-sync-check.sh
```

- Exit `0` → branch is current, proceed to Step 5.
- Exit `2`, first stderr word `BEHIND` → the branch is behind and **nothing was changed**. Syncing rewrites the user's history, so you MUST NOT run `--sync` on your own. AskQuestion:

```
⚠️  {branch} est {N} commit(s) derrière origin/develop — rien n'a été modifié.

○ Rebase maintenant (réécrit tes {M} commits locaux par-dessus develop)
○ Merge à la place (branche déjà pushée/partagée — pas de réécriture)
○ Stop — je gère à la main
```

Then run the answer, once, explicitly:

```bash
# only after the user picked rebase or merge
spec-kit-dcm-workflow/scripts/dcm-branch-sync-check.sh --sync --strategy rebase   # or --strategy merge
```

- Reads `git.sync_before_implement_strategy` in `dcm-config.yml` (default `rebase`) — use it as the **pre-selected** option in the AskQuestion, not as permission to skip it.
- **Rebase**: branch has no commits pushed/shared yet. Keeps linear history, no merge commit before work even starts.
- **Merge**: the branch is already pushed and shared with other devs (rebase would rewrite shared history). Same command already used before PR (Step 8) — just less clean history.
- Exit `2`, first stderr word `SYNC FAILED` → conflict, dirty tree or missing remote. **STOP**, AskQuestion:

```
❌ Sync avec develop échoué ({conflict|dirty tree})

○ Je résous le conflit maintenant (git status / rebase --continue|--abort)
○ Stash mes changements puis retry
○ Stop — je gère à la main
```

Do NOT implement on top of a branch that is behind or that failed to sync — a task built on stale `develop` risks conflicts and duplicate work at PR time.

## Step 5 — Load context (TOKEN RULES)

**READ**:
- `FEATURE_DIR/stories/T00X-{slug}.md` — PRIMARY
- `FEATURE_DIR/intake.json` — packages allowed
- `plan.md` — ONLY if sub-spec references it
- Files listed in sub-spec ## Files section

**DO NOT READ** (token savings):
- Full `spec.md` unless user asks
- Other `stories/T00Y-*.md` for Y ≠ current task
- Packages outside intake.packages

## Step 5.5 — Backend check at implement (if Frontend-only ticket)

If `ticket_plan.ticket_domains` = Frontend only (no Backend ticket):

Before coding API calls, **verify** `dependency_gaps` resolution still holds:

```bash
# Re-check routes / hooks mentioned in sub-spec or intake
grep -r "inactive\|cluster" packages/dcm-backend/app/api/routes/ ...
grep -r "{endpoint from sub-spec}" packages/dcm-frontend/src/ ...
```

**If backend missing vs spec promise** → STOP, AskQuestion (plain labels):

```
⚠️ Tu avais choisi : Frontend seul avec mock / filtre UI
   Mais le code ne permet pas encore : {reason}

○ Continuer avec mock MSW / fixture (comme spec)
○ Ajouter un ticket Backend → /speckit.dcm.tasks --add
○ Stop — décision humaine
```

Do NOT silently add Backend code outside ticket plan.

## Step 5.7 — Domain subagent delegation (MANDATORY — blocking)

Read `implement.domain_subagents` in `dcm-config.yml`. If the selected task's
`domain` has a mapped subagent, the main agent **MUST NOT code the task itself** —
it delegates the whole implementation to that subagent.

| Task domain | Subagent |
|-------------|----------|
| `dataeng`   | dp-data-databricks-engineer |

The **identifier is the same on both hosts** (the agent file is deployed verbatim, its
frontmatter `name:` is authoritative); only the **call syntax** differs, so use the row
for the tool you are running in:

| Host | Call | Identifier |
|------|------|------------|
| Claude Code | `Agent(subagent_type: …)` — `Task(…)` sur les versions antérieures | `dp-data-databricks-engineer` (`.claude/agents/dp-data-databricks-engineer.agent.md`) |
| Copilot (VS Code) | custom agent / `runSubagent(agentName: …)` | `dp-data-databricks-engineer` (`.github/agents/dp-data-databricks-engineer.agent.md`) |

If the identifier does not resolve, the deployment step was skipped — the agent comes
from an APM plugin, not from this repo. Install it for **your** host rather than coding
the task yourself:

```bash
apm install TotalEnergiesCode/dp-ai-tools/plugins/data-integration \
  --target copilot --only apm     # Claude Code: --target claude
```

**Rule** (`domain_subagents_required: true`): delegation is **blocking**. For a
`dataeng` task there is no fallback to the main agent — the
`dp-data-databricks-engineer` subagent does the code.

Delegation payload (per task, after branch + sync gates pass) — identical whatever
the host, only the call syntax above changes:

```
description: "Implement T00X ({domain})"
prompt: "<sub-spec stories/T00X-*.md content> + allowed packages from intake.json
         + branch {branch}. Implement acceptance criteria, run dcm-verify gates
         (lint → types → tests → build) for touched package, report the
         'Skills lus :' line, files changed, and gate status."
```

The subagent's result feeds Step 6 (mark `[x]` only if it reports gates exit 0).
Do NOT skip delegation because the task looks small or the pattern is known.

## Step 6 — Implement loop

For selected task:

1. Mark task `[~]` in tasks.md (in progress) if was `[ ]`
2. **If domain has a mapped subagent (Step 5.7): delegate via the call for your host — do NOT code yourself.** Otherwise implement directly.
3. Execute sub-spec acceptance criteria — load **`dcm-testing`** when adding/updating tests
4. Implement files in package scope (or via subagent)
5. Run tests per sub-spec — **load skill `dcm-verify`**, run gates for touched package (lint → types → tests → build)
6. Mark sub-spec checkboxes `[x]` as done
7. Mark task `[x]` in tasks.md when complete **only if dcm-verify gates exit 0** (subagent-reported gates count)

## Step 7 — CHECKPOINT (MANDATORY after each task)

When task T00X marked `[x]`, **STOP** and AskQuestion:

```
✅ T00X terminée — {title}
   Fichiers modifiés : {list}
   Branche : {branch}

Prochaine pending : T00Y — {next title} (ou aucune)

Que veux-tu faire ?
1. Question — sur T00X ou la suite (ne pas démarrer T00Y)
2. Continue — passer à T00Y
3. Stop — je prends la main (PR, tests, sync Jira)
4. Review — lancer `/speckit.dcm.review` (gates + skills) puis récap diff
```

**WAIT for user response.** Do NOT auto-start next task.

### Checkpoint responses

| Choice | Action |
|--------|--------|
| Question | Answer, stay on completed task context |
| Continue | Go to Step 3 for next pending T00Y |
| Stop | Remind: PR → `develop`, `/speckit.dcm.sync-status` |
| Review | Run `/speckit.dcm.review --task T00X`, show report + skill findings |
| Commit | Run `/speckit.dcm.review --commit` first (the Claude Code hook and `.git/hooks/pre-commit` block `git commit` without a PASS stamp) |

### Sub-spec sub-tasks

If sub-spec has unchecked items when user wants to close task:

```
Sous-tasks ouvertes dans stories/T00X.md :
- [ ] Mettre à jour README

Clôturer T00X quand même ou finir sous-tasks ?
```

## Step 8 — All tasks complete

When no pending tasks:

```
✅ Toutes les tasks [x] pour {feature}

Rappels :
- PR branches filles → **develop** (base à jour avant PR : `git merge origin/develop`)
- /speckit.dcm.sync-status
- Pas de branche mère git — spec dans `specs/NNN-*` seulement
```

## Implement agent integration

The main `/{speckit}implement` agent MUST:
1. Wait for this hook before loading tasks.md broadly
2. Follow one-task-at-a-time rule
3. Honor checkpoint — never batch T001+T002 without user "Continue"
4. Delegate to the mapped subagent (Step 5.7) for any task whose domain is in `implement.domain_subagents` (e.g. `dataeng` → `dp-data-databricks-engineer`) — never code such a task itself

## Troubleshooting

| Issue | Fix |
|-------|-----|
| No sub-spec | Run `/speckit.dcm.tasks` again, or `/speckit.dcm.tasks --add` |
| No dispatch branch | Run `/speckit.dcm.dispatch --branches-only` |
| User says Continue | Next pending only |
| Sync gate conflict (rebase) | `git status` → fix conflicts → `git add . && git rebase --continue` (or `--abort`) |
| Sync gate says `BEHIND` | Expected — the gate never syncs by itself. Ask the user, then `dcm-branch-sync-check.sh --sync` |
| Sync gate fails — dirty tree | Commit or `git stash` local changes, re-run `dcm-branch-sync-check.sh --sync` |

## Usage log (tokens / model)

**Au début** de la task, poser le marqueur de début (sinon la mesure retombe sur une
fenêtre de 90 min, beaucoup moins juste) :

```bash
spec-kit-dcm-workflow/scripts/dcm-step-start.sh \
  --feature-dir "$FEATURE_DIR" --step implement --task "T00X"
```

**À la fin** (checkpoint `[x]` ou Stop/Review), mesure depuis les logs Claude ou Copilot :

```bash
spec-kit-dcm-workflow/scripts/dcm-track-session.sh \
  --feature-dir "$FEATURE_DIR" --step implement --task "T00X"
```

Si `dcm-track-session.sh` n'écrit aucune ligne (0 activité dans la fenêtre), fallback
manuel uniquement :

```bash
spec-kit-dcm-workflow/scripts/dcm-append-usage.sh \
  --feature-dir "$FEATURE_DIR" \
  --step implement \
  --task "T00X" \
  --work-mode speckit \
  --outcome ok \
  --provider "<claude|copilot|estimate>" \
  --model "<detected>" \
  --source manual \
  --notes "implement checkpoint — track-session empty"
# If work was free chat (no slash): --work-mode direct
# If human coded without AI: --work-mode manual --outcome ok --provider estimate
```

Ne **pas** appeler `dcm-render-usage-report.sh` ici — le rapport est généré via
`/speckit.dcm.usage-report` uniquement.
