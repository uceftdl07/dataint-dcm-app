# DCM slash commands — source files

These files are the **source of truth** for the 9 DCM workflow commands.

`sync-dcm-extension.sh` copies them to:

| Host | Generated path | How to invoke |
|------|----------------|---------------|
| **Claude Code** | `.claude/commands/speckit.dcm.<name>.md` | `/speckit.dcm.<name>` |
| **GitHub Copilot (VS Code)** | `.github/prompts/speckit.dcm.<name>.prompt.md` + `.github/agents/` | `/speckit.dcm.<name>` in **Agent** mode |

**Not Cursor.** There is no `.cursor/` generation. Commands are built for Claude Code and Copilot only.

After editing a file here, run:

```bash
./spec-kit-dcm-workflow/scripts/sync-dcm-extension.sh
```

Then restart Claude Code or reload VS Code.

---

## Commands

| File | Slash command | What it does |
|------|---------------|--------------|
| [specify.md](./specify.md) | `/speckit.dcm.specify` | Scope intake (Q1–Q7), then writes `spec.md` + `intake.json`. Hook: `before_specify` (`--intake-only`). |
| [plan-guide.md](./plan-guide.md) | `/speckit.dcm.plan-guide` | Validates `## Prerequisites` in spec before native `/{speckit}plan`. Hook: `before_plan`. |
| [tasks.md](./tasks.md) | `/speckit.dcm.tasks` | Generates `tasks.md` + `stories/T00X-*.md` from spec. Hook: `before_tasks`. Flags: `--consolidate`, `--add`, `--append`. |
| [dispatch.md](./dispatch.md) | `/speckit.dcm.dispatch` | Creates Jira Epic + Stories and child git branches. Hook: `after_tasks` (optional). Flags: `--jira-only`, `--branches-only`. |
| [implement.md](./implement.md) | `/speckit.dcm.implement` | One task at a time: branch check, sync with develop, sub-spec load, checkpoints. Hook: `before_implement`. |
| [review.md](./review.md) | `/speckit.dcm.review` | Quality gates + skills review. `--commit` writes the pre-commit stamp (mandatory before `git commit`). |
| [publish-pr.md](./publish-pr.md) | `/speckit.dcm.publish-pr` | Commit, push child branch, open PR to `develop` via GitHub MCP. Copilot: Agent mode required. |
| [sync-status.md](./sync-status.md) | `/speckit.dcm.sync-status` | Syncs `tasks.md` `[x]` markers to Jira Story Done. Copilot: Agent mode + Atlassian MCP. |
| [usage-report.md](./usage-report.md) | `/speckit.dcm.usage-report` | Renders `usage-report.md` from `usage-log.jsonl`. **Read-only** — no tracking. |

### Token tracking flow

```
/speckit.dcm.specify     → dcm-step-start.sh → … work … → dcm-track-session.sh → usage-log.jsonl
/speckit.dcm.implement   → dcm-step-start.sh → … work … → dcm-track-session.sh → usage-log.jsonl
/speckit.dcm.usage-report → dcm-render-usage-report.sh → usage-report.md (zero tracking)
```

Other commands: add the same start/track pattern when needed. Manual fallback: `dcm-append-usage.sh`.

Full reference (English): [../COMMANDS.md](../COMMANDS.md).

---

## Host-specific notes

### Claude Code

- Native spec-kit commands use hyphens: `/speckit-plan`, `/speckit-tasks`, `/speckit-implement`.
- Commit gate: `.claude/hooks/` PreToolUse **and** `.git/hooks/pre-commit`.
- Token tracking: reads `~/.claude/projects/**/*.jsonl`.

### GitHub Copilot (VS Code)

- Native spec-kit commands use dots: `/speckit.plan`, `/speckit.tasks`, `/speckit.implement`.
- `dispatch`, `publish-pr`, `sync-status` require **Agent mode** and MCP (Atlassian, GitHub).
- Token tracking: reads VS Code `GitHub Copilot Chat.log`.

### Cursor

- **Unsupported.** Do not edit or add Cursor-specific instructions in these files.
- Old `.agents/skills/speckit-dcm-*` copies are removed by `sync-dcm-extension.sh`.
