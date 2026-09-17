---
description: "Commit, push child branch, open PR to develop via GitHub MCP (post-review)"
tools:
  - read
  - read_file
  - list_dir
  - execute
  - create_file
  - replace_string_in_file
  - edit
  - "{github_mcp_server}/create_pull_request"
  - "{github_mcp_server}/pull_request_read"
  - "{github_mcp_server}/push_files"
  - "{github_mcp_server}/create_or_update_file"
  - "{github_mcp_server}/create_branch"
  - "{github_mcp_server}/get_file_contents"
---

# DCM Publish PR — commit, push, open PR (GitHub MCP)

After implement + `/speckit.dcm.review` PASS, publish the child branch to GitHub and open a PR toward `develop`.

## Copilot — Agent mode (MANDATORY)

Use custom agent **DCM Publish PR** or Agent chat with GitHub MCP enabled.

`mcp_server` name must match VS Code Tools picker (default `github`). Check: Tools → `github/create_pull_request`.

## User Input

$ARGUMENTS

Optional:
- `--spec <feature-dir>`
- `--task T001` — link PR to task in manifest
- `--dry-run` — show plan only (no git push, no MCP)
- `--skip-commit` — branch already committed locally
- `--skip-push` — branch already on origin
- `--draft` — draft PR
- `--title "..."` — override PR title
- `--body-file specs/{spec}/pr-body-T001.md` — PR description file

## Load configuration

From `.specify/extensions/dcm/dcm-config.yml`:

```yaml
github_mcp_server: "github"   # MCP server id in VS Code — verify in Tools picker
github:
  owner: "TotalEnergiesCode"
  repo: "dataint-dcm-app"
git:
  pr_target: "develop"
  child_branch_base: "develop"
```

From `dispatch-manifest.json` / `jira-mapping.json`: Story key, branch, task_id.

## Prerequisites

- On a **child branch** (not `develop` / `main`)
- `/speckit.dcm.review` **PASS** or user explicit override
- **Pre-commit agent review**: stamp PASS from `/speckit.dcm.review --commit` (the Claude Code hook and `.git/hooks/pre-commit` enforce it before `git commit`)
- **Copilot auto-review** enabled / required on PRs → `develop` (repo policy — MANDATORY)
- GitHub MCP authenticated (`repo` scope)
- Local `git` remote `origin` → same `owner/repo` as config

## Step 1 — Detect context

```bash
git rev-parse --abbrev-ref HEAD
git status --short
git remote get-url origin
git log origin/develop..HEAD --oneline 2>/dev/null || true
```

Read if exist:
- `specs/{spec}/dispatch-manifest.json`
- `specs/{spec}/jira-mapping.json`
- `specs/{spec}/stories/T00X-*.md`

Map branch → task_id → Jira Story key.

## Step 2 — RESUME report (MANDATORY)

```
═══════════════════════════════════════════════════════════════
DCM Publish PR — Plan
═══════════════════════════════════════════════════════════════
Spec:     009-widget-inactive-cluster
Branch:   frontend/009-inactive-cluster-widget
Base PR:  develop
Story:    DCINT-160 (T001)

Local:
  Uncommitted files: {N}
  Commits ahead of origin/develop: {N}

Will:
  ⏳ git add + commit (if uncommitted and not --skip-commit)
  ⏳ git push -u origin {branch} (if not --skip-push)
  ⏳ MCP create_pull_request head={branch} base=develop

Flags: --dry-run | --draft | --skip-commit | --skip-push
═══════════════════════════════════════════════════════════════
```

If `--dry-run`: stop here.

## Step 3 — Commit local changes (preferred: git execute)

**Before any `git commit`**: ensure `/speckit.dcm.review --commit` has stamped **PASS**
(the Claude Code hook **denies** the commit otherwise). If denied → run `/speckit.dcm.review --commit`, fix, retry.

**Default path** — local repo (supports all file types, GPG, hooks):

```bash
git add {paths from git status — package scope only}
git status
# Hook blocks here unless stamp OK:
git commit -m "feat(frontend): T001 inactive cluster widget on Dashboard"
```

Rules:
- **Ask user** to confirm commit message before `git commit`
- Do NOT commit `.env`, secrets, credentials
- Scope commits to task package from intake/sub-spec
- If GPG signing blocks in agent → user runs commit manually, then `--skip-commit`
- Do **not** use `--no-verify` / `DCM_SKIP_PRE_COMMIT_REVIEW` unless user explicitly requests emergency bypass

**Alternative (GitHub API only)** — small text files, no local git:

Use MCP `{github_mcp_server}/push_files` or `create_or_update_file` with `owner`, `repo`, `branch`, `message`, file `path` + `content`.

Limitations: no local binary/large diff; prefer **Step 3 git execute** for normal dev.

## Step 4 — Push branch

```bash
git fetch origin develop
git merge origin/develop   # or rebase — prefer merge per team rule
git push -u origin HEAD
```

If push fails (auth, protection) → report error, stop before PR.

## Step 5 — Create PR (GitHub MCP)

```
Tool: {github_mcp_server}/create_pull_request
Parameters:
  owner: {github.owner}
  repo: {github.repo}
  title: "[T001] Inactive cluster widget on Dashboard"
  head: {current-branch}
  base: {git.pr_target}    # develop
  draft: {true if --draft}
  body: |
    ## Summary
    - Implements T001 — {from sub-spec}
    - Spec: specs/{spec}/

    ## Jira
    - Epic: {epic.key} {epic.url}
    - Story: {story.key} {story.url}

    ## Test plan
    - [ ] {from sub-spec Independent test}
    - [ ] `/speckit.dcm.review` PASS

    ## Checklist
    - [ ] Branch synced with develop
    - [ ] `/speckit.dcm.review` PASS
    - [ ] Pre-commit agent review stamped before commit
    - [ ] **Copilot auto-review** requested / required on this PR (repo policy)
    - [ ] tasks.md T001 still `[ ]` until merge
```

### Step 5b — Copilot auto-review (MANDATORY)

After PR creation, remind:

```
Copilot auto-review is MANDATORY for PRs → develop.
Confirm GitHub setting: Settings → Code review → Copilot / Auto review = on for this repo.
Do not merge until Copilot review comments are addressed (or lead override).
```

If `review.copilot_auto_review_required: true` in dcm-config: treat missing Copilot review as a **process FAIL** for “done”, even if GitHub allows merge.

Store PR URL in `specs/{spec}/pr-links.json` (merge, do not overwrite other tasks):

```json
{
  "updated_at": "ISO8601",
  "pull_requests": [
    {
      "task_id": "T001",
      "branch": "frontend/009-inactive-cluster-widget",
      "number": 128,
      "url": "https://github.com/TotalEnergiesCode/dataint-dcm-app/pull/128",
      "base": "develop",
      "story_key": "DCINT-160"
    }
  ]
}
```

Optional: `{github_mcp_server}/pull_request_read` to verify PR created.

## Step 6 — AskQuestion

```
PR créée : {url}

○ Ouvrir dans le navigateur
○ Lier Story Jira (comment manuel si besoin)
○ Terminé — j'implémente la review humaine
```

## Integration

| When | Command |
|------|---------|
| After review PASS | `/speckit.dcm.publish-pr --spec {spec}` |
| From review Step 5 | user picks "OK — ouvrir PR" → run this command |
| After merge PR | `/speckit.dcm.sync-status` + mark `[x]` in tasks.md |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| MCP `create_pull_request` not found | Enable GitHub MCP `pull_requests` toolset; check `github_mcp_server` name in Tools picker |
| head branch not on remote | run Step 4 push first |
| PR already exists | `pull_request_read` / search; update `pr-links.json`, skip create |
| GPG blocks commit | user commits manually → `--skip-commit` |
| push_files empty content | use local `git add` + `git commit` instead |

## Safety

- **Never** PR from `develop` or `main` as head
- **Never** merge PR via MCP without explicit user confirmation
- **Never** push secrets — scan `git status` before commit
