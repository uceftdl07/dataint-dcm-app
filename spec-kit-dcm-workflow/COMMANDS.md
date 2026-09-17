# DCM Workflow — Command Reference

English reference for every slash command provided by the **DCM Team Workflow** extension
(`extension.yml`, version **2.9.2**).

**Target IDEs:** **Claude Code** and **GitHub Copilot (VS Code)**. All commands, hooks, gates,
and token tracking are built for these two hosts. Cursor is not supported.

For behaviour details, flags, and gate scripts, the source of truth remains `commands/*.md`.
For token tracking and report generation, see [USAGE-AND-TOKENS.md](./USAGE-AND-TOKENS.md).

---

## Supported hosts — Claude Code & Copilot

The team workflow runs on **Claude Code** or **VS Code + GitHub Copilot** (pick one per repo).

| Host | `specify init` | DCM commands | Native spec-kit | Commit gate |
|------|----------------|--------------|-----------------|-------------|
| **Claude Code** | `--integration claude` | `/speckit.dcm.*` | `/speckit-plan`, `/speckit-tasks`, … | PreToolUse hook + git pre-commit |
| **GitHub Copilot** | `--integration copilot` | `/speckit.dcm.*` | `/speckit.plan`, `/speckit.tasks`, … | git pre-commit (+ Agent mode) |

After init, run once per machine:

```bash
./spec-kit-dcm-workflow/scripts/install.sh
# Claude Code → restart session
# VS Code     → Developer: Reload Window
```

Verify:

```bash
specify extension list                    # DCM Team Workflow v2.9.2
./spec-kit-dcm-workflow/scripts/dcm-selftest.sh
ls .claude/commands/speckit.dcm.*.md      # Claude Code
ls .github/prompts/speckit.dcm.*.prompt.md # Copilot
```

> **Not Cursor.** The Cursor integration layer was removed in v2.8.0. Do not expect
> `/speckit.dcm.*` to work in Cursor — use Claude Code or Copilot. Stale local files under
> `.cursor/` or `.agents/skills/speckit-dcm-*` are deleted by `sync-dcm-extension.sh`.

One repo = **one** spec-kit integration (`claude` **or** `copilot`). Full setup:
[GETTING-STARTED.md](./GETTING-STARTED.md).

---

## Command notation

| Host | DCM commands | Native spec-kit commands |
|------|--------------|--------------------------|
| **Claude Code** | `/speckit.dcm.<name>` | `/speckit-<name>` (e.g. `/speckit-plan`) |
| **GitHub Copilot** | `/speckit.dcm.<name>` | `/speckit.<name>` (e.g. `/speckit.plan`) |

DCM commands are generated as files and keep the dot on both hosts. Native spec-kit commands
use a hyphen on Claude Code (skill directory names cannot contain dots) and a dot on Copilot.

---

## Typical workflow order

```
/speckit.dcm.specify "…"     → scope intake, then spec.md + intake.json
/{speckit}clarify            → recommended, not enforced
/{speckit}plan               → before_plan hook runs plan-guide gate
/{speckit}tasks              → before_tasks hook runs DCM tasks generation
/speckit.dcm.dispatch        → Jira Epic + Stories + child git branches
/{speckit}implement T001     → before_implement hook: branch check, sub-spec, checkpoints
/speckit.dcm.review --commit → mandatory before every git commit
/speckit.dcm.review          → pre-PR quality review
/speckit.dcm.publish-pr      → push child branch, open PR to develop
/speckit.dcm.sync-status     → tasks.md [x] → Jira Story Done
/speckit.dcm.usage-report    → render token/model report (read-only)
```

---

## DCM extension commands

### Summary table

| Command | Hook | Primary outputs | Who |
|---------|------|-----------------|-----|
| [`speckit.dcm.specify`](#speckitdcmspecify) | `before_specify` | `spec.md`, `intake.json` | Lead |
| [`speckit.dcm.plan-guide`](#speckitdcmplan-guide) | `before_plan` | gate pass/fail | — |
| [`speckit.dcm.tasks`](#speckitdcmtasks) | `before_tasks` | `tasks.md`, `stories/T00X-*.md` | Lead |
| [`speckit.dcm.dispatch`](#speckitdcmdispatch) | `after_tasks` (optional) | Jira issues, child branches, `dispatch-manifest.json` | Lead |
| [`speckit.dcm.implement`](#speckitdcmimplement) | `before_implement` | code on child branch, task checkpoints | Dev |
| [`speckit.dcm.review`](#speckitdcmreview) | — | review report, pre-commit stamp | Dev |
| [`speckit.dcm.publish-pr`](#speckitdcmpublish-pr) | — | pushed branch, GitHub PR | Dev |
| [`speckit.dcm.sync-status`](#speckitdcmsync-status) | — | Jira Story status updates | Dev / Lead |
| [`speckit.dcm.usage-report`](#speckitdcmusage-report) | — | `usage-report.md` from `usage-log.jsonl` | Anyone |

---

### `speckit.dcm.specify`

**File:** `commands/specify.md`

Entry point for a new feature. Runs in two phases:

1. **Intake (blocking)** — asks the user Q1–Q7: work type, domains, packages, ticket plan,
   and feature summary. Nothing is written under `specs/` until intake completes.
2. **Spec writing** — creates `specs/NNN-slug/spec.md` and `intake.json` from the intake answers.

| Flag | Effect |
|------|--------|
| `--intake-only` | Phase 1 only: writes `.specify/pending-intake.json` and stops. Used by the `before_specify` hook before native `/{speckit}specify`. |
| `--reuse-intake` | Skip questions and reuse an existing intake (explicit opt-in only). |

**When to use:** start of every epic. Re-run with `--intake-only` to change scope without
creating a second spec folder.

**Usage tracking:** `dcm-step-start.sh` when `FEATURE_DIR` is created (§ 2.1), then
`dcm-track-session.sh` at end. No `dcm-render-usage-report.sh` here — use
`/speckit.dcm.usage-report` separately.

**Hard gates:** none inside this command; the hook ordering prevents double spec creation.

---

### `speckit.dcm.plan-guide`

**File:** `commands/plan-guide.md`

Runs the **plan gate** before native `/{speckit}plan`. Calls `dcm-precheck.sh --gate plan`.

| Exit | Meaning |
|------|---------|
| **0** | `## Prerequisites` section exists and is filled → proceed to `/{speckit}plan` |
| **2** | Section missing or empty → **stop** and ask the user to complete it |

Does not write files. Only validates that the spec is ready for planning.

---

### `speckit.dcm.tasks`

**File:** `commands/tasks.md`

Generates `tasks.md` and one sub-spec per task under `stories/T00X-*.md`, **from the spec**
with no interactive questions. Hook: `before_tasks`.

| Flag | Effect |
|------|--------|
| *(none)* | Regenerate `tasks.md` + `stories/` from the current spec |
| `--append` | Append new T00X entries without overwriting existing ones |
| `--consolidate` | Collapse to **one task per domain** |
| `--add` | Add a single task after dispatch (sub-spec + Jira Story + branch for that task only) |
| `--spec <feature-dir>` | Target a specific spec folder |

**Hard gate:** `dcm-precheck.sh --gate tasks` (exit 2 = stop).

---

### `speckit.dcm.dispatch`

**File:** `commands/dispatch.md`

Creates the team dispatch artefacts after `tasks.md` is ready. Idempotent — safe to re-run;
only missing items are processed.

| Half | Creates | Skip with |
|------|---------|-----------|
| **Jira** | 1 Epic (from `spec.md`) + 1 Story per task | `--branches-only` |
| **Git** | 1 child branch per task from fresh `origin/develop` | `--jira-only` |

| Flag | Effect |
|------|--------|
| `--spec <name>` | Target spec folder |
| `--dry-run` | Resume report only, no MCP or git writes |
| `--force` | Recreate all (may duplicate Jira issues — confirm first) |
| `--consolidate` | One branch per domain instead of one per task |
| `--no-push` | Create branches locally without pushing |

**Outputs:** `dispatch-manifest.json`, `jira-mapping.json`, Jira Epic + Stories, child branches.

**Requires:** Atlassian MCP configured in `dcm-config.yml`.

---

### `speckit.dcm.implement`

**File:** `commands/implement.md`

Prepares and guides implementation of **one task at a time**. Hook: `before_implement`.

What it does:

1. Runs `dcm-precheck.sh --gate implement` (hard stop if tasks or sub-specs are missing).
2. Lists pending tasks via `dcm-parse-tasks.sh`.
3. Asks which task to implement (`T001`, `T002`, or `all`).
4. Verifies the developer is on the correct child branch.
5. Syncs with `develop` (rebase or merge — blocking).
6. Loads **only** the selected sub-spec (token discipline).
7. Delegates to domain subagents when required.
8. Runs a **checkpoint** after each task (continue / stop / review).

| Input | Effect |
|-------|--------|
| `T001` | Implement that task directly |
| `all` | Sequential implementation with checkpoints between tasks |

**Usage tracking:** `dcm-step-start.sh` at task start, `dcm-track-session.sh` at checkpoint.
Fallback `dcm-append-usage.sh` only if track-session writes 0 lines. No render here — use
`/speckit.dcm.usage-report`. See [USAGE-AND-TOKENS.md](./USAGE-AND-TOKENS.md).

---

### `speckit.dcm.review`

**File:** `commands/review.md`

Quality review before commit or before opening a PR. Two modes, same engine (`dcm-review.sh`):

| Mode | When | Output |
|------|------|--------|
| *(default)* | Before PR or at implement checkpoint "Review" | Report + verdict |
| `--commit` | **Mandatory before every `git commit`** | Report + verdict + **stamp** that unlocks the commit hook |

| Flag | Effect |
|------|--------|
| `--task T001` | Load sub-spec and package for that task |
| `--spec <feature-dir>` | Explicit feature context |
| `--duplication` / `--sonar` | Run jscpd / sonar-scanner if available |
| `--allow-warn` | Allow WARN stamp (only if config allows) |
| `--skip-gates` | Skills review only (discouraged) |
| `--dry-run` | Show findings, do not write stamp |

**Hard gate:** `git commit` is blocked until a valid stamp exists (`.git/hooks/pre-commit` +
Claude Code PreToolUse hook).

---

### `speckit.dcm.publish-pr`

**File:** `commands/publish-pr.md`

After implement + review PASS, commits local changes, pushes the child branch, and opens a
PR toward `develop` via GitHub MCP.

| Flag | Effect |
|------|--------|
| `--task T001` | Link PR to task in `dispatch-manifest.json` |
| `--dry-run` | Show plan only |
| `--skip-commit` | Branch already committed locally |
| `--skip-push` | Branch already on origin |
| `--draft` | Open as draft PR |
| `--title "…"` | Override PR title |

**Requires:** GitHub MCP configured. Run `/speckit.dcm.review` (without `--commit`) first.

---

### `speckit.dcm.sync-status`

**File:** `commands/sync-status.md`

Syncs local task completion from `tasks.md` checkbox markers to Jira Story statuses.

| Flag | Effect |
|------|--------|
| `--spec <name>` | Target spec folder |
| `--dry-run` | Show planned Jira updates without writing |

**Requires:** `dispatch-manifest.json` or `jira-mapping.json` from a prior dispatch.
Use after a PR is merged: mark the task `[x]` in `tasks.md`, then run this command.

---

### `speckit.dcm.usage-report`

**File:** `commands/usage-report.md`

Generates `usage-report.md` from the append-only `usage-log.jsonl`. **Render only — no
automatic tracking.**

| Flag | Effect |
|------|--------|
| `--spec 011-carousel-scoring` | Target spec folder |
| `--append` | Manually append one usage row for the current chat turn |

**How the log gets filled (before this command):**

| Step | Script | Role |
|------|--------|------|
| Start of a workflow step | `dcm-step-start.sh` | Writes `.dcm-step-start.json` (timestamp, actor, step, task) |
| End of a workflow step | `dcm-track-session.sh` | Reads Claude/Copilot local logs since the marker → appends to `usage-log.jsonl` |
| Manual entry | `dcm-append-usage.sh` | Append one row with explicit token counts |

This command only reads the log and renders the report. An empty log means nobody tracked
that epic yet — not that the work cost zero tokens.

Full details: [USAGE-AND-TOKENS.md](./USAGE-AND-TOKENS.md).

---

## Native spec-kit commands (referenced by DCM)

These are **not** part of the DCM extension but are wired into the workflow via hooks:

| Native command | DCM hook that runs first | Purpose |
|----------------|--------------------------|---------|
| `/{speckit}specify` | `speckit.dcm.specify --intake-only` | Scope intake before spec.md is written |
| `/{speckit}plan` | `speckit.dcm.plan-guide` | Validate Prerequisites section |
| `/{speckit}tasks` | `speckit.dcm.tasks` | Generate tasks.md + sub-specs |
| `/{speckit}implement` | `speckit.dcm.implement` | Branch check, sub-spec load, checkpoints |
| `/{speckit}clarify` | — | Optional clarification pass (recommended, not enforced) |

---

## Hooks (advisory)

Hooks tell the agent which DCM command to run; they do **not** execute automatically.
Hard stops come from shell scripts called inside command bodies (`dcm-precheck.sh`,
`dcm-branch-sync-check.sh`, `dcm-conflict-check.sh`, pre-commit gate).

| Hook | DCM command | Blocking |
|------|-------------|----------|
| `before_specify` | `speckit.dcm.specify --intake-only` | Advisory |
| `before_plan` | `speckit.dcm.plan-guide` | Gate exit 2 stops |
| `before_tasks` | `speckit.dcm.tasks` | Gate exit 2 stops |
| `before_implement` | `speckit.dcm.implement` | Gate + sync exit 2 stops |
| `after_tasks` | `speckit.dcm.dispatch` | Optional (prompted) |

---

## Supporting scripts (not slash commands)

| Script | Purpose |
|--------|---------|
| `scripts/dcm-precheck.sh --gate <step>` | Hard gate before specify / plan / tasks / implement |
| `scripts/dcm-step-start.sh` | Write start marker for token tracking window |
| `scripts/dcm-track-session.sh` | Collect tokens from Claude/Copilot logs → `usage-log.jsonl` |
| `scripts/dcm-append-usage.sh` | Manually append one usage row |
| `scripts/dcm-render-usage-report.sh` | Generate `usage-report.md` from log |
| `scripts/dcm-parse-tasks.sh` | Parse `tasks.md` into structured TSV |
| `scripts/dcm-branch-sync-check.sh` | Verify child branch is synced with develop |
| `scripts/dcm-conflict-check.sh` | Detect merge conflicts before dispatch |
| `scripts/dcm-review.sh` | Automated lint/test gates for review |
| `scripts/dcm-pre-commit-review-stamp.sh` | Write/check pre-commit review stamp |
| `scripts/sync-dcm-extension.sh` | Regenerate installed extension artefacts |
| `scripts/install.sh` | Full install (extension + hooks + gates) |

---

## Examples

```text
/speckit.dcm.specify Carousel scoring for DCM dashboard
/speckit.dcm.dispatch --spec 011-carousel-scoring
/speckit.dcm.implement T001
/speckit.dcm.review --commit
/speckit.dcm.publish-pr --task T001
/speckit.dcm.sync-status --spec 011-carousel-scoring
/speckit.dcm.usage-report --spec 011-carousel-scoring
```
