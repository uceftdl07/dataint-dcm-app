---
description: "Dispatch Jira Epic + Stories and git child branches from tasks.md (idempotent resume)"
tools:
  - bash
  - "{mcp_server}/createJiraIssue"
  - "{mcp_server}/editJiraIssue"
  - "{mcp_server}/getJiraIssue"
  - "{mcp_server}/searchJiraIssuesUsingJql"
---

# DCM Dispatch — Jira + Git Branches (idempotent)

Single dispatch command, run after `tasks.md` is ready. It does both halves:

| Half | Creates | Skip with |
|------|---------|-----------|
| Jira | 1 Epic (from `spec.md`) + 1 Story per task | `--branches-only` |
| Git | 1 child branch per task, cut from fresh `origin/develop` | `--jira-only` |

**Idempotent**: re-run safe. Reports what's done vs remaining, processes only what is missing.

## User Input

$ARGUMENTS

Optional:
- `--spec <name>`
- `--jira-only` — skip git branches
- `--branches-only` — skip Jira
- `--no-push`
- `--dry-run` — resume report only, no MCP call, no git write
- `--force` — recreate all (Jira duplicates — confirm with the user first)
- `--consolidate` — one branch per domain instead of one per task (solo dev)

## Model preference (soft)

```bash
PREF=$(spec-kit-dcm-workflow/scripts/dcm-model-pref.sh --step dispatch)
echo "DCM model preference — step: dispatch → $PREF"
```

## Load configuration

From `.specify/extensions/dcm/dcm-config.yml`:
`mcp_server`, `project.key`, `mapping.*`, `defaults.epic`, `defaults.story`,
`work_types.*`, `git.child_branch_base`, `git.pr_target`, `git.push_to_origin`,
`multi_epic.*`.

`git.child_branch_pattern` and `git.domains` are **not** read here — `dcm-parse-tasks.sh`
owns them (Step 3).

## Steps

### 1. Detect spec directory

`--spec` → branch name → cwd → single spec.

**Multi-spec guard (MANDATORY)**: if 2+ `specs/*/` have `tasks.md` and `--spec` is missing
→ abort with the list. Config: `multi_epic.require_spec_arg_when_multiple`.

### 2. Conflict check (MANDATORY before Jira/git)

If `multi_epic.conflict_check_before_dispatch` (default true):

```bash
./spec-kit-dcm-workflow/scripts/dcm-conflict-check.sh --spec {spec-name}
# or --json for structured output
```

If `requires_acknowledgement: true` (domain overlap with another active epic):

1. Show the conflict report to the user
2. Verify `merge-strategy.md` has its **Cross-Epic Shared Files** section filled
3. Ask the user to confirm merge order before proceeding
4. If the user aborts → stop (no Jira, no git)

No `merge-strategy.md` and an overlap detected → create it from
`templates/merge-strategy.template.md` first.

### 3. Parse tasks.md (MANDATORY — never by hand)

`tasks.md` is read **only** through the canonical parser. It owns `task_id`, `status`,
`domain`, `slug` and the **branch name** (from `git.child_branch_pattern`), so dispatch,
sync-status and the sub-specs cannot drift to different answers:

```bash
PARSED=$(spec-kit-dcm-workflow/scripts/dcm-parse-tasks.sh --spec {spec-name} --json)
```

| Exit | Meaning | Action |
|------|---------|--------|
| 0 | tasks parsed | continue — `PARSED.tasks[]` is authoritative |
| 1 | usage error / spec or `tasks.md` not found | stop, fix `--spec` |
| **2** | `tasks.md` exists but **no conforming task line** | **STOP** — format divergence, not "nothing to dispatch". Fix `tasks.md` per `tasks.md` command rules, do not invent tasks |
| 3 | `dcm-config.yml` unreadable (`git.domains` / `child_branch_pattern`) | stop, fix the config |

Fields used below, per task: `task_id`, `title`, `status`, `domain`, `slug`, `branch`,
`sub_spec`, `jira_key`. `PARSED.counts.total` is `stories_total`; `PARSED.warnings[]`
must be shown to the user (an unexpected `domain=misc` usually means a missing domain
prefix in `tasks.md`).

Do **not** re-derive a branch name, a slug or a domain from the task title anywhere in
this command — use `task.branch`, `task.slug`, `task.domain`.

With `--consolidate`: group tasks by `domain`, one branch per domain named
`{domain}/{PARSED.spec_num}-{spec-short-name}`; every task of that domain maps to it.

### 4. Load ALL state files (RESUME audit)

Read if they exist:

| File | Tracks |
|------|--------|
| `jira-mapping.json` | Epic + Stories already created |
| `branches-created.json` | git branches already created |
| `dispatch-manifest.json` | cross-ref task_id ↔ Jira ↔ branch |
| `jira-create-log.json` | Jira run history |

Compute:

```
jira:
  epic_done     = epic.key present and not "pending_mcp"
  stories_done  = set of task_ids with a non-null key
  stories_total = PARSED.counts.total

git:
  branches_done  = in branches-created.json OR existing in `git branch --list` / `git branch -r`
  branches_total = distinct task.branch values (or per-domain branches with --consolidate)
```

### 5. Print MASTER RESUME REPORT (MANDATORY — talk to the user)

```
═══════════════════════════════════════════════════════════════
DCM Dispatch — Resume Report
═══════════════════════════════════════════════════════════════
Spec: 010-header-workspace-filter
Strategy: direct_to_base | Child base: develop | PR target: develop
Tasks: 25 parsed (pending 13 / in_progress 0 / completed 12)  ⚠ {N} parser warning(s)

── CONFLICT CHECK ──────────────────────────────────────────────
Active epics: {count} | Domain overlaps: {N}
  ⚠️ vs 010-header-filter — shared domain: frontend
  (or ✅ no overlap)

── JIRA ────────────────────────────────────────────────────────
Epic:     ✅ DCINT-200  🔗 https://tdf.atlassian.net/browse/DCINT-200
          (or ⏳ not created yet)
Stories:  12/25 done  |  13 remaining

── GIT ─────────────────────────────────────────────────────────
Branches: 1/1 done
  ✅ frontend/010-workspace-filter-routes

── THIS RUN WILL ───────────────────────────────────────────────
  ⏳ Create 13 missing Jira Stories
  ✅ Skip Epic (exists)
  ✅ Skip 1 branch (exists)
  ⏳ Update dispatch-manifest.json

Flags: resume (default) | --dry-run | --jira-only | --branches-only
═══════════════════════════════════════════════════════════════
```

If `--dry-run`: stop after the report.

If everything is complete:

```
✅ Dispatch already complete. Nothing to do.
Epic: DCINT-200 🔗 …   Stories: 25/25 | Branches: 1/1
Re-run with --force only if you need duplicates.
```

### 6. Jira dispatch (unless `--branches-only`)

Resume mode: skip the Epic if `epic_done`, create only `task_id`s missing from
`stories_done`, then **merge** `jira-mapping.json`. With `--force`: warn about
duplicates, require explicit confirmation.

#### 6a. Epic (only if missing)

Skip entirely if `work_types.{work_type}.jira_epic: false` (hotfix, dette) — Stories
only, `issueTypeName` from `work_types.{work_type}.jira_issue_type` when set (Bug).

- **Title**: first H1 of `spec.md`. If `multi_epic.epic_title_prefix` (default true),
  prefix with the spec number — `[009] Widget inactive cluster`. Never double-prefix.
- **Labels**: `defaults.epic.labels` + `work_types.{work_type}.labels`.
- Always `contentFormat: markdown` — never dump the raw spec without headings.

```
Tool: {mcp_server}/createJiraIssue
  cloudId: {from getAccessibleAtlassianResources}
  projectKey: {project.key}
  issueTypeName: Epic
  summary: [{spec_num}] {epic_title}
  contentFormat: markdown
  description: |
    ## Summary
    {1–3 sentences from spec H1 / Input}

    ## Spec
    `specs/{spec_name}/spec.md`

    ## Ticket plan
    - Work type: `{intake.work_type}` · Priority: `{intake.priority}`
    - Stories: {PARSED.counts.total} → {ticket_domains}

    ## Domain scope
    {short Domain Scope table from spec}

    ## Prerequisites
    {## Prerequisites / ## Prérequis section from spec.md — or "—"}

    ---
    ## Full spec
    {spec_content truncated to stay under 32000 chars}
```

Write `epic.key` into `jira-mapping.json` immediately after success.

#### 6b. Stories (only missing task_ids)

One Story per task — never per Phase. Read `task.sub_spec` (already resolved by the
parser) for acceptance criteria, files and out-of-scope.

**HARD RULE — the Branch field is a git branch name, never a commit.** Use
`task.branch`. If the branch does not exist yet, write that planned name anyway.
Never a SHA, a short hash, or `origin/develop`.

```
Tool: {mcp_server}/createJiraIssue
  cloudId: …
  projectKey: {project.key}
  issueTypeName: {Story | work_types.{work_type}.jira_issue_type}
  summary: "{task_id}: {task.title}"
  contentFormat: markdown
  description: |
    ## Summary
    {1–2 sentences from the sub-spec Description}

    ## Context

    | Field | Value |
    |-------|-------|
    | Spec | `specs/{spec_name}` |
    | Work type | `{intake.work_type}` |
    | Domain | `{task.domain}` |
    | Package | `{package}` |
    | **Git branch** | `{task.branch}` |
    | Epic | {epic_key} |
    | Priority | `{intake.priority}` |
    | Spec-kit status | `{task.status}` |

    > **Git branch** = branch name only (e.g. `frontend/011-carousel-ui`). Never a commit SHA.

    ## Links
    - Sub-spec: `specs/{spec_name}/{task.sub_spec}`
    - Spec: `specs/{spec_name}/spec.md`
    - PR target: `{git.pr_target}`

    ## Acceptance Criteria
    {bullets from the sub-spec — first ~2000 chars if long}

    ## Out of scope
    {from the sub-spec if present}
  labels: {defaults.story.labels + work_type labels + domain:{task.domain}}
  additional_fields:   # Epic Link / parent per mapping.task_epic_link
```

On MCP failure for one task: log it, **continue** the others, report failures at the end.
Store `sub_spec` + `branch` per story in `jira-mapping.json`.

Append the run to `jira-create-log.json`:

```json
{ "runs": [ { "at": "ISO8601", "mode": "resume", "epic_created": false,
              "epic_skipped": "DCINT-200", "stories_created": ["DCINT-213"],
              "stories_skipped": ["T001"], "stories_failed": [] } ] }
```

### 7. Git dispatch (unless `--jira-only`)

**HARD RULE**: every child branch is cut from an **up-to-date `origin/{base}`** —
never from the current feature branch, never from a stale local base.

```bash
CFG=.specify/extensions/dcm/dcm-config.yml
BASE=$(awk '/^git:/{f=1;next} f&&/^[a-z]/{f=0} f&&/child_branch_base:/{print $2;exit}' "$CFG" | tr -d '" ')
BASE="${BASE:-develop}"

git fetch origin "$BASE"
git checkout "$BASE"
git pull --ff-only origin "$BASE"

LOCAL=$(git rev-parse HEAD); REMOTE=$(git rev-parse "origin/$BASE")
if [ "$LOCAL" != "$REMOTE" ]; then
  echo "ERROR: $BASE not synced with origin/$BASE — fix pull/rebase before creating branches"
  exit 1
fi
echo "OK base $BASE @ $LOCAL"
```

Then, for each **missing** branch only:

```bash
git branch "{task.branch}" "origin/$BASE"
git push -u origin "{task.branch}"   # if git.push_to_origin and not --no-push
```

Branch exists locally → skip with `status: "skipped_exists"`. Push fails → log, continue
the others. Merge into `branches-created.json` (never delete entries):

```json
{
  "spec": "010-header-workspace-filter",
  "branch_strategy": "direct_to_base",
  "child_branch_base": "develop",
  "pr_target": "develop",
  "updated_at": "ISO8601",
  "branches": [ { "task_id": "T001", "branch": "frontend/010-…", "status": "created" } ]
}
```

Legacy `git.branch_strategy: integration_branch`: children are cut from the spec
integration branch and PR back into it. Warn if the current branch is not that base.

After the branches exist, prefer `{mcp_server}/editJiraIssue` on each Story so the
**Git branch** field matches the real branch name (still never a SHA).

### 8. Update the active-epics registry (MANDATORY)

```bash
./spec-kit-dcm-workflow/scripts/dcm-active-epics-update.sh \
  --spec {spec-name} \
  --title "{H1 from spec.md}" \
  --domains {distinct task.domain values} \
  --packages {from intake} \
  --branches {from branches-created.json} \
  --epic-key {DCINT-XXX} \
  --status in_progress
```

Commit `specs/active-epics.json` so the team's conflict-check sees this epic.
Mark `--complete` when all tasks are `[x]` and every Story is Done (sync-status does it too).

### 9. Merge dispatch-manifest.json

Cross-ref by `task_id`. **Merge**, never overwrite existing keys:

```json
{
  "updated_at": "ISO8601",
  "spec": "010-header-workspace-filter",
  "branch_strategy": "direct_to_base",
  "child_branch_base": "develop",
  "pr_target": "develop",
  "integration_branch": null,
  "epic": { "key": "DCINT-200", "url": "https://tdf.atlassian.net/browse/DCINT-200" },
  "dispatch": [
    { "task_id": "T001", "jira_key": "DCINT-213", "branch": "frontend/010-…",
      "domain": "frontend", "sub_spec": "stories/T001-….md", "status": "pending" }
  ],
  "summary": {
    "jira_stories_done": 25, "jira_stories_total": 25,
    "branches_done": 1, "branches_total": 1, "status": "complete"
  }
}
```

### 10. Final REPORT (MANDATORY)

```
═══════════════════════════════════════════════════════════════
✅ DCM Dispatch — Complete
═══════════════════════════════════════════════════════════════

📋 Epic: DCINT-200 — Add Workspace Filter to Header
   🔗 https://tdf.atlassian.net/browse/DCINT-200

This run:
  Jira:  +13 Stories created | 12 skipped | 0 failed
  Git:   +0 branches created | 1 skipped

Overall:
  Stories: 25/25 ✅   Branches: 1/1 ✅

Devs:
  git fetch && git checkout frontend/010-workspace-filter-routes
  PR → develop

Modèle Jira DCM (rappel) :
  • 1 Epic DCINT = spec / feature entière
  • {N} Stories = 1 par task (T001, T002…) — liées à l'Epic

───────────────────────────────────────────────────────────────
📍 PROCHAINES ÉTAPES — dispatch terminé
───────────────────────────────────────────────────────────────

  Coder task par task :
    → `/{speckit}implement T001`
    → checkout de la branche depuis dispatch-manifest.json
    → PR vers develop

  Après merge + task [x] dans tasks.md :
    → `/speckit.dcm.sync-status`  (Jira Story → Done)

  Scope / tickets à revoir ?
    → `/speckit.dcm.specify --intake-only` ou `/speckit.dcm.tasks --add --spec {spec-name}`

  Toutes tasks [x] + Stories Done :
    → l'Epic peut passer Done (sync ou manuel Jira)
───────────────────────────────────────────────────────────────

💾 specs/010-header-workspace-filter/dispatch-manifest.json
═══════════════════════════════════════════════════════════════
```

## Hook Integration

`after_tasks` hook — optional prompt after `/{speckit}tasks`. Same resume logic on re-run.

## Troubleshooting

| Situation | Action |
|-----------|--------|
| Partial Jira (12/25) | re-run — creates the remaining 13 |
| Branches exist, no Jira | `--jira-only` |
| Jira done, no branches | `--branches-only` |
| Parser exit 2 | `tasks.md` is not in checkbox format — fix it, never dispatch from a guess |
| Parser warns `domain=misc` | the task title has no domain prefix — fix `tasks.md`, do not force the branch |
| Multiple specs, wrong dispatch | pass `--spec <name>` |
| Cross-epic frontend conflict | conflict-check + merge-strategy Cross-Epic section |
| Epic done, still in registry | `dcm-active-epics-update.sh --spec X --complete` |
