---
description: "Sync tasks.md completion status to Jira Stories"
tools:
  - read
  - read_file
  - list_dir
  - execute
  - "{mcp_server}/getJiraIssue"
  - "{mcp_server}/editJiraIssue"
  - "{mcp_server}/searchJiraIssuesUsingJql"
---

# DCM Sync Status — tasks.md → Jira

## Copilot — Agent mode (MANDATORY)

Use custom agent **DCM Sync Status** (not Ask). Needs **Atlassian MCP** + file read.

Do NOT send only `--spec ...` — use full sentence:

```
Sync Jira for spec 009-widget-inactive-cluster. T001 is [x] → Story DCINT-160 Done.
```

Syncs local task completion from `tasks.md` to Jira Story statuses.
Inspired by [spec-kit-jira sync-status](https://github.com/mbachorik/spec-kit-jira).

## User Input

$ARGUMENTS

Optional: `--spec <name>`, `--dry-run`

## Prerequisites

1. MCP server `{mcp_server}` configured
2. `specs/<spec-name>/dispatch-manifest.json` OR `jira-mapping.json` exists
3. Issues created via `/speckit.dcm.dispatch` (or `--jira-only`)
4. `tasks.md` has checkbox markers

## Load Configuration

From `.specify/extensions/dcm/dcm-config.yml`:

```yaml
status_mapping:
  completed: "Done"        # [x]
  pending: "To Do"         # [ ]
  in_progress: "In Progress"  # [~]
```

## Task Status Markers

Recognised by `scripts/dcm-parse-tasks.sh` (it owns the marker → status mapping; this
table only shows how each status lands in Jira):

| Marker | `status` from the parser | Jira target |
|--------|-------------------------|-------------|
| `- [x] T001 ...` | `completed` | Done |
| `- [ ] T001 ...` | `pending` | To Do |
| `- [~] T001 ...` | `in_progress` | In Progress |

## Steps

### 1. Detect spec

Priority: `--spec` → git branch (integration or child branch prefix) → single mapped spec.

Child branch `frontend/009-carousel-ui` → resolve parent spec via `dispatch-manifest.json`.

### 2. Parse tasks.md (MANDATORY — never by hand)

`tasks.md` is read **only** through the canonical parser, so the `task_id` → status
mapping is identical to the one dispatch used:

```bash
spec-kit-dcm-workflow/scripts/dcm-parse-tasks.sh --spec {spec-name}
# TSV: task_id <TAB> status <TAB> domain <TAB> slug <TAB> branch <TAB> sub_spec <TAB> title
```

```bash
while IFS=$'\t' read -r id status domain slug branch sub_spec title; do
  echo "$id → $status"
done < <(spec-kit-dcm-workflow/scripts/dcm-parse-tasks.sh --spec {spec-name})
```

`status` is already normalised to `pending` | `in_progress` | `completed` — do not
re-read the checkbox characters.

| Exit | Action |
|------|--------|
| 0 | continue |
| 1 | wrong `--spec` / no `tasks.md` → stop |
| **2** | `tasks.md` has **no conforming task line** → **STOP**. Format divergence, not "nothing to sync": syncing here would silently leave every Story untouched |
| 3 | `dcm-config.yml` unreadable → stop |

### 3. Load mapping

Read `dispatch-manifest.json` (preferred) or `jira-mapping.json`.

Join on `task_id`: parsed status (Step 2) → `jira_key`. A `task_id` present in
`tasks.md` but absent from the mapping was never dispatched — list it, do not create
anything here (`/speckit.dcm.dispatch` does that).

### 4. Sync each Story

For each mapped task:

1. Get current Jira issue status via `{mcp_server}/getJiraIssue`
2. Compare with local status from `tasks.md`
3. If different, transition issue to target status from `status_mapping`
4. Skip if already correct (idempotent)

```
Tool: {mcp_server}/editJiraIssue or transition tool
Issue: DCINT-124
Target status: Done (when [x] in tasks.md)
```

### 5. Update manifest

Update `status` field in `dispatch-manifest.json` for each task.

### 6. Epic progress + active-epics registry

Calculate: `completed / total * 100%`
Display progress on Epic (optional comment via editJiraIssue).

When **all tasks `[x]`** and all Stories synced to Done:

```bash
./spec-kit-dcm-workflow/scripts/dcm-active-epics-update.sh --spec {spec-name} --complete
```

Marks spec as `completed` in `specs/active-epics.json` (removes from conflict-check overlap).

### 7. Save sync log

`specs/<spec-name>/jira-sync-log.json`:

```json
{
  "synced_at": "ISO8601",
  "spec": "001-feature-x",
  "epic": "DCINT-123",
  "updated": ["DCINT-124"],
  "skipped": ["DCINT-125"],
  "completion_pct": 33
}
```

### 8. Report

```
✅ DCM Sync complete

Epic DCINT-123: 2/3 stories done (67%)

Updated:
  ✓ DCINT-124 T001 → Done
  ✓ DCINT-125 T002 → Done

Unchanged:
  ○ DCINT-126 T003 → To Do
```

## Notes

- Idempotent — safe to run multiple times
- Only syncs Story issues (one per task in DCM model)
- Does NOT auto-sync from Jira → tasks.md (one direction only)
- Run after merging child PR to **develop** and marking tasks complete

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Mapping not found | Run `/speckit.dcm.dispatch` first |
| Transition failed | Check workflow in Jira, adjust `status_mapping` |
| Child branch, spec unknown | Use `--spec 001-feature-x` |
