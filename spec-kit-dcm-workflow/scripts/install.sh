#!/usr/bin/env bash
# One-shot installer for the extension — idempotent, re-run it to upgrade.
# Usage: ./spec-kit-dcm-workflow/scripts/install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SRC/.." && pwd)"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; }

# 1. Prerequisites --------------------------------------------------------
if ! command -v specify >/dev/null 2>&1; then
  err "'specify' CLI not found in PATH."
  err "Install it first: https://github.com/github/spec-kit (e.g. 'uv tool install specify-cli' or pipx)."
  exit 1
fi
ok "specify CLI found: $(specify --version 2>/dev/null || echo unknown)"

cd "$REPO_ROOT"

# 2. Retire the pre-2.9.2 registration -----------------------------------
# The old `dcm-workflow` registration declares the same speckit.dcm.* names, so step 3
# would fail on a command conflict. --keep-config leaves its dcm-config.yml on disk;
# sync-dcm-extension.sh copies it over, then prunes the directory.
# Capture then match, no `| grep -q`: grep exits at the first hit, specify dies of
# SIGPIPE (141) and pipefail makes the condition false — the removal was skipped.
INSTALLED_EXTENSIONS="$(specify extension list 2>/dev/null || true)"
if [[ "$INSTALLED_EXTENSIONS" == *dcm-workflow* ]]; then
  log "Removing the legacy 'dcm-workflow' registration (id renamed to 'dcm')"
  specify extension remove dcm-workflow --force --keep-config
fi

# 3. Add / overwrite local extension in dev mode --------------------------
# --force overwrites the install and clears stale command registrations.
log "Installing local extension (dev mode)"
specify extension add ./spec-kit-dcm-workflow --dev --force

# 4. Sync generated artifacts (agents, skills, commands, dcm-config) -------
log "Syncing agents / skills / commands / constitution"
chmod +x "$SRC/scripts/"*.sh 2>/dev/null || true
"$SRC/scripts/sync-dcm-extension.sh"

# 5. Install the dp-data-databricks-engineer agent (required subagent) -----
# implement delegates `dataeng` tasks to it (dcm-config.yml implement.domain_subagents).
# The agent is no longer vendored in this repo (`plugins/databricks-data-engineer/` is
# gone): it ships in the data-integration plugin of TotalEnergiesCode/dp-ai-tools and is
# deployed by APM. `--target` decides where the agent file lands, and only that target
# resolves the subagent — Copilot reads .github/agents/, Claude Code .claude/agents/.
DE_PLUGIN="TotalEnergiesCode/dp-ai-tools/plugins/data-integration"
DE_TARGET="copilot"
DE_AGENT="$REPO_ROOT/.github/agents/dp-data-databricks-engineer.agent.md"
if command -v apm >/dev/null 2>&1; then
  log "Installing $DE_PLUGIN --target $DE_TARGET (dataeng subagent)"
  # `--only apm` on purpose: a full install resolves MCP dependencies too and dies on an
  # unqualified server name declared upstream. The agent is an APM dependency, so nothing
  # of what the dataeng delegation needs is skipped.
  if apm install "$DE_PLUGIN" --target "$DE_TARGET" --only apm; then
    [[ -f "$DE_AGENT" ]] \
      && ok "dataeng subagent deployed: ${DE_AGENT#"$REPO_ROOT"/}" \
      || err "apm install succeeded but $DE_AGENT is missing — check 'apm audit'."
  else
    err "apm install failed for $DE_PLUGIN."
    err "dataeng implement tasks won't resolve the 'dp-data-databricks-engineer' subagent."
  fi
  log "On Claude Code, re-run it with --target claude (same plugin, .claude/agents/)."
else
  err "'apm' CLI not found in PATH — dataeng subagent not installed."
  err "Install apm, then: apm install $DE_PLUGIN --target $DE_TARGET --only apm"
fi
# The agent routes to the official Databricks skills, which the plugin does not
# redistribute. Without them it runs degraded (cyber rules only, no Databricks syntax):
#   databricks aitools install --path .agents/skills    # Copilot
#   databricks aitools install --path .claude/skills    # Claude Code
# Diagnosis: the dp-data-databricks-setup skill.

echo ""
ok "spec-kit-dcm-workflow installed."
log "Reload the window to pick up new commands (e.g. /speckit.dcm.specify):"
log "  VS Code + Copilot → Developer: Reload Window"
log "  Claude Code       → restart the session (.claude/settings.json hooks are read at startup)"
