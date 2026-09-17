#!/usr/bin/env bash
# Sync spec-kit-dcm-workflow → installed extension + per-host artefacts. Two hosts,
# each ignoring the other's tree:
#   Copilot      .github/agents/, .github/prompts/, .agents/skills/
#   Claude Code  .claude/{commands,skills,hooks}/, .claude/settings.json, CLAUDE.md
# Everything generated is per-machine (gitignored); the tracked sources are
# commands/, skills/ and claude-code/. main() at the end is the running order.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$REPO_ROOT/spec-kit-dcm-workflow"
LIB="$SRC/scripts/lib"
EXT="$REPO_ROOT/.specify/extensions/dcm"
# Install dir of <= 2.9.0, when the id was `dcm-workflow`. Its local dcm-config.yml
# is carried over by sync_extension_package, then the directory is pruned.
LEGACY_EXT="$REPO_ROOT/.specify/extensions/dcm-workflow"
CLAUDE_SRC="$SRC/claude-code"
CONFIG="$EXT/dcm-config.yml"
FORCE_CONFIG=0

step() { printf '==> %s\n' "$*"; }
say()  { printf '    → %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '    ✗ %s\n' "$*" >&2; }
note() { printf '      %s\n' "$*" >&2; }

usage() {
  cat <<'EOF'
Usage: sync-dcm-extension.sh [--force-config]

Regenerates the installed extension, the per-IDE agents/prompts/commands and the
team skills. Safe to re-run.

--force-config  overwrite an existing dcm-config.yml with the template.
                Default is to leave your local config alone.
EOF
}

# One key from a YAML file, first match wins, "" if absent. `key` is a regex, so an
# indented key is `'[[:space:]]*version'`. grep, not yq: yq is not installed on the
# team's machines, so a `command -v yq` guard would never honour the key.
cfg_value() {
  local key="$1" file="$2"
  [[ -f "$file" ]] || return 0
  grep -E "^${key}:" "$file" 2>/dev/null | head -1 \
    | sed -E 's/^[^:]*:[[:space:]]*//; s/[[:space:]]*#.*$//' | tr -d '"'"'"' '
}

# From provides.commands, so the list cannot drift from what is declared.
dcm_commands() {
  sed -n 's/^[[:space:]]*- name: "speckit\.dcm\.\([a-z0-9][a-z0-9-]*\)".*/\1/p' "$SRC/extension.yml"
}

# tasks → DCM Tasks, publish-pr → DCM Publish PR. Derived, not tabulated.
display_name() {
  printf 'DCM %s' "$(printf '%s' "$1" | tr '-' ' ' \
    | awk '{ for (i = 1; i <= NF; i++) $i = toupper(substr($i, 1, 1)) substr($i, 2); print }' \
    | sed 's/Pr$/PR/')"
}

# Everything after the closing `---`; a later `---` is a horizontal rule, kept.
front_matter_body() { awk '/^---$/ { n++; if (n == 2) { p = 1; next } } p' "$1"; }

# The BASE spec-kit commands have no single name. `specify init` installs them either
# as skills (.claude/skills/speckit-specify/ → /speckit-specify) or as command files
# (.github/prompts/speckit.specify.prompt.md → /speckit.specify), and the separator
# follows the INSTALL MODE, not the host: spec-kit's own _invocation_style.py puts
# `claude` AND `copilot` in CONDITIONAL_SLASH_AGENTS. They diverge today only because
# ClaudeIntegration is a SkillsIntegration with no opt-out (`--no-skills` is rejected)
# while CopilotIntegration defaults to command files.
#
# So shared sources write `{speckit}plan` and each host renders its own name. This
# never applies to the DCM commands themselves: those are generated as FILES on both
# hosts, so `speckit.dcm.plan-guide` keeps its dots everywhere.
#
# Read from disk, not from .specify/init-options.json: that file tracks one single
# ai/ai_skills pair for the whole project, which cannot describe two hosts at once.
speckit_prefix() {  # <claude|copilot> → "speckit-" | "speckit."
  case "$1" in
    claude)
      [[ -d "$REPO_ROOT/.claude/skills/speckit-specify" ]] && { printf 'speckit-'; return 0; }
      [[ -f "$REPO_ROOT/.claude/commands/speckit.specify.md" ]] && { printf 'speckit.'; return 0; }
      ;;
    copilot)
      [[ -d "$REPO_ROOT/.github/skills/speckit-specify" ]] && { printf 'speckit-'; return 0; }
      [[ -f "$REPO_ROOT/.github/prompts/speckit.specify.prompt.md" ]] && { printf 'speckit.'; return 0; }
      ;;
  esac

  # Base commands are not installed for that host. init-options.json can only be
  # trusted for the ONE host it describes: it tracks a single ai/ai_skills pair, so
  # reading `ai_skills: true` there while resolving the OTHER host reports its mode
  # instead — which is exactly how Copilot was first announced as `speckit-`.
  local opts="$REPO_ROOT/.specify/init-options.json"
  if [[ -f "$opts" ]] && grep -q "\"ai\"[[:space:]]*:[[:space:]]*\"$1\"" "$opts" 2>/dev/null; then
    grep -q '"ai_skills"[[:space:]]*:[[:space:]]*true' "$opts" \
      && printf 'speckit-' || printf 'speckit.'
    return 0
  fi

  # Not described either — fall back to the integration's own default in spec-kit:
  # ClaudeIntegration is a SkillsIntegration (always skills), CopilotIntegration
  # defaults to command files and only switches on --integration-options="--skills".
  case "$1" in
    claude) printf 'speckit-' ;;
    *)      printf 'speckit.' ;;
  esac
}

# stdin → stdout, `{speckit}` resolved for one host. Applied to `description:` as well
# as the body: both end up in front of a user.
render_tpl() { sed "s/{speckit}/$1/g"; }

# `description:` — one-liner or the folded `>-` form the team skills use.
front_matter_desc() {
  awk '
    /^description:[[:space:]]*>-?[[:space:]]*$/ { folded = 1; next }
    folded && /^[[:space:]]/ {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "")
      desc = desc (desc ? " " : "") $0
      next
    }
    folded { exit }
    /^description:/ { sub(/^description:[[:space:]]*/, ""); gsub(/"/, ""); desc = $0; exit }
    END { print desc }
  ' "$1"
}

front_matter_tools() {
  awk '/^tools:/ { flag = 1; next } /^---$/ { if (flag) exit } flag { print }' "$1"
}

# tools: in the frontmatter is Copilot vocabulary with {mcp_server} placeholders;
# each host needs its own names.
copilot_tools() {
  local tools
  tools="$(front_matter_tools "$1")"
  [[ -z "$tools" ]] && tools="  - execute"
  printf '%s' "$tools" | sed -e "s/{mcp_server}/${MCP_SERVER}/g" \
                             -e "s/{github_mcp_server}/${GITHUB_MCP_SERVER}/g" \
                             -e 's/- bash$/- execute/' -e 's/- bash /- execute /'
}

# An allowed-tools list missing a tool the command needs is worse than none: the
# baseline every DCM command uses, plus whatever the frontmatter implies.
claude_allowed_tools() {
  local cmd_file="$1" tools mcp="" extra=""
  tools="$(front_matter_tools "$cmd_file")"

  # Server-wide mcp__<server>: one typo in a per-tool name would deny it silently.
  printf '%s' "$tools" | grep -q '{mcp_server}' && mcp="${mcp}, mcp__${MCP_SERVER}"
  printf '%s' "$tools" | grep -q '{github_mcp_server}' && mcp="${mcp}, mcp__${GITHUB_MCP_SERVER}"

  # Only the implement command delegates today — detect it rather than hardcode it.
  # Both names on purpose: the subagent tool is `Agent` in current Claude Code and was
  # `Task` before. allowed-tools is an allowlist, so an entry naming a tool this version
  # does not have is inert — while a MISSING entry silently denies a delegation that
  # `domain_subagents_required: true` declares non-negotiable.
  grep -qiE 'runsubagent|subagent' "$cmd_file" && extra=", Agent, Task"

  printf 'Bash, Read, Write, Edit, Glob, Grep%s%s' "$extra" "$mcp"
}

sync_extension_package() {
  step "Sync extension package → $EXT"
  local dir name
  mkdir -p "$EXT/commands" "$EXT/templates" "$EXT/scripts/lib"
  cp "$SRC/extension.yml" "$SRC/dcm-config.template.yml" "$EXT/"
  # Glob, not a hand-kept list: two docs added later were never copied.
  cp "$SRC"/*.md "$EXT/"
  cp "$SRC"/commands/*.md "$EXT/commands/"
  cp "$SRC"/templates/*.md "$EXT/templates/"
  cp "$SRC"/templates/*.json "$EXT/templates/" 2>/dev/null || true
  cp "$SRC"/scripts/*.sh "$EXT/scripts/" 2>/dev/null || true
  cp "$LIB"/*.py "$EXT/scripts/lib/" 2>/dev/null || true
  chmod +x "$EXT/scripts/"*.sh "$SRC/scripts/"*.sh 2>/dev/null || true

  # Mirror copies; the ones the hosts read are written by sync_team_skills.
  for dir in "$SRC"/skills/*/; do
    [[ -f "${dir}SKILL.md" ]] || continue
    name="$(basename "$dir")"
    mkdir -p "$EXT/skills/$name"
    cp "${dir}SKILL.md" "$EXT/skills/$name/SKILL.md"
  done
  if [[ -f "$SRC/skills/README.md" ]]; then
    mkdir -p "$EXT/skills"
    cp "$SRC/skills/README.md" "$EXT/skills/"
  fi

  # The two commit gates, refreshed on every run: `specify extension add` copied
  # them once, so the $EXT copies stayed frozen with holes 2.8.0 had closed.
  mkdir -p "$EXT/claude-code/hooks" "$EXT/git-hooks"
  cp "$CLAUDE_SRC"/*.md "$CLAUDE_SRC"/*.json "$EXT/claude-code/" 2>/dev/null || true
  cp "$CLAUDE_SRC"/hooks/*.sh "$EXT/claude-code/hooks/" 2>/dev/null || true
  cp "$SRC"/git-hooks/* "$EXT/git-hooks/" 2>/dev/null || true
  chmod +x "$EXT/claude-code/hooks/"*.sh "$EXT/git-hooks/"* 2>/dev/null || true

  # dcm-config.yml holds local settings and this script is re-run after every
  # pull — never clobber it. After the id rename, take the old install's copy.
  if [[ ! -f "$CONFIG" && -f "$LEGACY_EXT/dcm-config.yml" ]]; then
    cp "$LEGACY_EXT/dcm-config.yml" "$CONFIG"
    say "dcm-config.yml migrated from .specify/extensions/dcm-workflow/ (id rename)"
  fi
  if [[ ! -f "$CONFIG" ]]; then
    cp "$SRC/dcm-config.template.yml" "$CONFIG"
    say "dcm-config.yml created from template"
  elif [[ "$FORCE_CONFIG" -eq 1 ]]; then
    cp "$CONFIG" "$CONFIG.bak"
    cp "$SRC/dcm-config.template.yml" "$CONFIG"
    say "dcm-config.yml overwritten (previous kept as dcm-config.yml.bak)"
  else
    say "dcm-config.yml kept (local settings preserved; --force-config to reset)"
    diff -q "$SRC/dcm-config.template.yml" "$CONFIG" >/dev/null 2>&1 \
      || info "note: it differs from the template — diff it if a new key is missing"
  fi
}

sync_constitution() {
  [[ -f "$SRC/memory/constitution.md" ]] || return 0
  mkdir -p "$EXT/memory" "$REPO_ROOT/.specify/memory"
  cp "$SRC/memory/constitution.md" "$EXT/memory/constitution.md"
  cp "$SRC/memory/constitution.md" "$REPO_ROOT/.specify/memory/constitution.md"
  step "Constitution synced → .specify/memory/constitution.md"
}

# Five commands resolve FEATURE_DIR through .specify/scripts/bash; without it the
# agent guesses. The scripts ship in the specify CLI (core_pack) — copy, not rewrite.
check_specify_scaffold() {
  step "Check .specify scaffold (upstream spec-kit scripts)"
  if [[ -f "$REPO_ROOT/.specify/scripts/bash/check-prerequisites.sh" ]]; then
    say ".specify/scripts/bash present"
    return 0
  fi
  if ! command -v specify >/dev/null 2>&1; then
    warn "specify CLI not found — cannot restore .specify/scripts/bash"
    note "Commands that resolve FEATURE_DIR will not work. Install spec-kit, then re-run."
    return 0
  fi

  local specify_py core_bash=""
  specify_py="$(head -1 "$(command -v specify)" | sed 's|^#!||; s|^ *||')"
  [[ -x "$specify_py" ]] && core_bash="$("$specify_py" -c 'import specify_cli, pathlib; print(pathlib.Path(specify_cli.__file__).parent / "core_pack" / "scripts" / "bash")' 2>/dev/null || true)"

  if [[ -n "$core_bash" && -d "$core_bash" ]]; then
    mkdir -p "$REPO_ROOT/.specify/scripts/bash"
    cp "$core_bash"/*.sh "$REPO_ROOT/.specify/scripts/bash/"
    chmod +x "$REPO_ROOT/.specify/scripts/bash/"*.sh
    say "restored $(ls "$REPO_ROOT/.specify/scripts/bash" | wc -l | tr -d ' ') scripts from the specify CLI core_pack"
  else
    warn "could not locate the specify core_pack scripts"
    note "Run 'specify init --here' to rebuild the .specify scaffold."
  fi
}

wire_hooks() {
  step "Wire hooks (.specify/extensions.yml ← extension.yml)"
  python3 "$LIB/wire_hooks.py" "$SRC/extension.yml" "$REPO_ROOT/.specify/extensions.yml"
}

# Copilot: .github/agents/ holds the agent, .github/prompts/ the entry point.
generate_copilot_agents() {
  step "Generate Copilot agents/prompts (.github/agents, .github/prompts)"
  mkdir -p "$REPO_ROOT/.github/agents" "$REPO_ROOT/.github/prompts"

  local cmd cmd_file desc tools name id count=0
  for cmd in $DCM_COMMANDS; do
    cmd_file="$SRC/commands/${cmd}.md"
    [[ -f "$cmd_file" ]] || continue
    desc="$(front_matter_desc "$cmd_file" | render_tpl "$COPILOT_SPECKIT")"
    tools="$(copilot_tools "$cmd_file")"
    name="$(display_name "$cmd")"
    id="speckit.dcm.${cmd}"

    cat > "$REPO_ROOT/.github/agents/${id}.agent.md" <<EOF
---
name: ${name}
description: "${desc}"
user-invocable: true
tools:
${tools}
---

<!-- Extension: dcm -->
<!-- Config: .specify/extensions/dcm/ -->
$(front_matter_body "$cmd_file" | render_tpl "$COPILOT_SPECKIT")
EOF

    cat > "$REPO_ROOT/.github/prompts/${id}.prompt.md" <<EOF
---
description: "${desc}"
agent: ${id}
argument-hint: --spec <feature-dir>
tools:
${tools}
---

Open in **Agent** mode with custom agent **${name}** (\`${id}\`).
Follow workflow in \`.github/agents/${id}.agent.md\`.
EOF
    count=$((count + 1))
  done
  say "${count} agent(s) + prompt(s) as speckit.dcm.<name>"
}

# Dotted filename → documented name: speckit.dcm.specify.md → /speckit.dcm.specify.
generate_claude_commands() {
  step "Generate Claude Code slash commands (.claude/commands/)"
  mkdir -p "$REPO_ROOT/.claude/commands"

  local cmd cmd_file desc
  CLAUDE_CMD_COUNT=0
  for cmd in $DCM_COMMANDS; do
    cmd_file="$SRC/commands/${cmd}.md"
    [[ -f "$cmd_file" ]] || continue
    desc="$(front_matter_desc "$cmd_file" | render_tpl "$CLAUDE_SPECKIT")"
    cat > "$REPO_ROOT/.claude/commands/speckit.dcm.${cmd}.md" <<EOF
---
description: "${desc}"
argument-hint: [--spec <feature-dir>]
allowed-tools: $(claude_allowed_tools "$cmd_file")
---

<!-- Generated by spec-kit-dcm-workflow/scripts/sync-dcm-extension.sh — do not edit. -->
<!-- Source: spec-kit-dcm-workflow/commands/${cmd}.md -->

Arguments: \$ARGUMENTS
$(front_matter_body "$cmd_file" | render_tpl "$CLAUDE_SPECKIT")
EOF
    CLAUDE_CMD_COUNT=$((CLAUDE_CMD_COUNT + 1))
  done
  say "${CLAUDE_CMD_COUNT} commands as /speckit.dcm.<name>"
}

# `specify extension add` also registers one skill per command — the same body a
# second time in every session's context. Prune only once the commands exist.
prune_duplicate_skills() {
  step "Remove duplicate DCM skill registrations (slash commands are canonical)"
  if [[ "$CLAUDE_CMD_COUNT" -eq 0 || ! -d "$REPO_ROOT/.claude/skills" ]]; then
    warn "no .claude/commands generated this run — skills left in place"
    return 0
  fi
  local dup count=0
  for dup in "$REPO_ROOT/.claude/skills"/speckit-dcm-*; do
    [[ -e "$dup" ]] || continue
    rm -rf "$dup"
    count=$((count + 1))
  done
  say "${count} duplicate skill(s) removed"
}

# Artefacts of older versions. Every pattern is DCM-scoped, never a blanket rm of
# a shared directory (.agents/skills also holds the databricks plugin's skills).
prune_legacy() {
  step "Clean up artefacts from previous versions"
  LEGACY_REMOVED=0

  drop() {  # rm each path that exists, counting
    local path
    for path in "$@"; do
      [[ -e "$path" ]] || continue
      rm -rf "$path"
      LEGACY_REMOVED=$((LEGACY_REMOVED + 1))
    done
  }

  drop_unknown_commands() {  # <dir> <prefix> <suffix> — keep only current commands
    local dir="$1" prefix="$2" suffix="$3" f cmd
    for f in "$dir/$prefix"*"$suffix"; do
      [[ -e "$f" ]] || continue
      cmd="$(basename "$f")"; cmd="${cmd#"$prefix"}"; cmd="${cmd%"$suffix"}"
      case " $DCM_COMMANDS " in *" $cmd "*) ;; *) drop "$f" ;; esac
    done
  }

  drop_unmirrored() {  # <installed-dir> <source-dir> — drop files absent from source
    local ext_dir="$1" src_dir="$2" f base
    [[ -d "$ext_dir" && -d "$src_dir" ]] || return 0
    for f in "$ext_dir"/*; do
      [[ -f "$f" ]] || continue          # files only: subdirectories get their own call
      base="$(basename "$f")"
      [[ -f "$src_dir/$base" ]] || drop "$f"
    done
  }

  # Cursor layer (dropped in 2.8.0) + every speckit-dcm-* clone under .agents.
  drop "$REPO_ROOT/.cursor/hooks.json" \
       "$REPO_ROOT/.cursor/hooks/dcm-before-commit-review.sh" \
       "$REPO_ROOT"/.cursor/skills/dcm-{python,react,verify,testing} \
       "$REPO_ROOT"/.agents/skills/speckit-dcm-* \
       "$REPO_ROOT"/.agents/commands/speckit.dcm*.md \
       "$REPO_ROOT"/.agents/commands/dcm-{python,react,verify,testing}.md
  # rmdir, not rm -rf: another tool may legitimately own these directories.
  rmdir "$REPO_ROOT/.cursor/hooks" "$REPO_ROOT/.agents/commands" 2>/dev/null || true

  # The speckit.dcm-workflow.* twins, then the names that no longer exist. The
  # glob must keep `-workflow`: speckit.dcm.* would delete what was just generated.
  drop "$REPO_ROOT"/.github/agents/speckit.dcm-workflow.*.agent.md \
       "$REPO_ROOT"/.github/prompts/speckit.dcm-workflow.*.prompt.md
  drop_unknown_commands "$REPO_ROOT/.github/agents" "speckit.dcm." ".agent.md"
  drop_unknown_commands "$REPO_ROOT/.github/prompts" "speckit.dcm." ".prompt.md"
  drop_unknown_commands "$REPO_ROOT/.claude/commands" "speckit.dcm." ".md"

  # $EXT is refreshed with cp, which never deletes. Nothing mechanical reads the
  # leftovers, but it is the directory a teammate greps to see what is installed.
  drop_unknown_commands "$EXT/commands" "" ".md"
  drop "$EXT/cursor-hooks" "$EXT/memory/model-preferences.md"

  # Same for what is copied by name: mirror the source instead of listing the
  # casualties — two deleted scripts stayed installed for versions.
  drop_unmirrored "$EXT/scripts"     "$SRC/scripts"
  drop_unmirrored "$EXT/scripts/lib" "$SRC/scripts/lib"
  drop_unmirrored "$EXT/templates"   "$SRC/templates"

  # sync_extension_package ran first, so the local config is already under $EXT.
  # The registry entry is install.sh's job (`specify extension remove`).
  drop "$LEGACY_EXT"

  say "${LEGACY_REMOVED} legacy artefact(s) removed (Cursor layer, long-form twins, dropped commands/scripts/templates)"
}

install_claude_commit_gate() {
  step "Install Claude Code commit gate (PreToolUse Bash → git commit)"
  if [[ ! -f "$CLAUDE_SRC/hooks/dcm-before-commit-review.sh" || ! -f "$CLAUDE_SRC/settings.json" ]]; then
    warn "claude-code/ missing from the extension — Claude Code commit gate NOT installed"
    note "(the git pre-commit hook below still blocks the commit itself)"
    return 0
  fi
  mkdir -p "$REPO_ROOT/.claude/hooks"
  cp "$CLAUDE_SRC/hooks/dcm-before-commit-review.sh" "$REPO_ROOT/.claude/hooks/"
  chmod +x "$REPO_ROOT/.claude/hooks/dcm-before-commit-review.sh" \
           "$CLAUDE_SRC/hooks/dcm-before-commit-review.sh"
  python3 "$LIB/merge_claude_settings.py" \
    "$REPO_ROOT/.claude/settings.json" "$CLAUDE_SRC/settings.json" \
    || note "Claude Code commit gate NOT active — the git pre-commit hook still is."
}

update_claude_md() {
  step "Update CLAUDE.md (managed DCM block)"
  if [[ ! -f "$CLAUDE_SRC/CLAUDE.template.md" ]]; then
    warn "claude-code/CLAUDE.template.md missing — CLAUDE.md not updated"
    return 0
  fi
  local version rendered
  version="$(cfg_value '[[:space:]]*version' "$SRC/extension.yml")"
  # CLAUDE.md is read by Claude Code only, but the template still goes through
  # render_tpl so the {speckit} token stays the single spelling in every source.
  rendered="$(mktemp)"
  render_tpl "$CLAUDE_SPECKIT" <"$CLAUDE_SRC/CLAUDE.template.md" >"$rendered"
  python3 "$LIB/update_claude_md.py" \
    "$REPO_ROOT/CLAUDE.md" "$rendered" "${version:-unknown}"
  rm -f "$rendered"

  # .mcp.json is never written: it approves remote endpoints for everyone.
  if [[ ! -f "$REPO_ROOT/.mcp.json" && -f "$CLAUDE_SRC/mcp.template.json" ]]; then
    info "note: no .mcp.json — /speckit.dcm.dispatch and /speckit.dcm.publish-pr cannot reach"
    info "      Jira/GitHub from Claude Code. To enable:"
    info "        cp spec-kit-dcm-workflow/claude-code/mcp.template.json .mcp.json"
  fi
}

# The gate that also covers plain terminal use. Two exclusive occupants of
# .git/hooks/pre-commit: the pre-commit framework (DCM gate + black/ruff/…,
# preferred), or the DCM standalone hook, which shadows the rest.
install_git_hook() {
  step "Install git pre-commit hook (Copilot / Claude / terminal)"
  local hook="$REPO_ROOT/.git/hooks/pre-commit" src="$SRC/git-hooks/pre-commit"
  chmod +x "$src" 2>/dev/null || true

  if [[ ! -d "$REPO_ROOT/.git/hooks" ]]; then
    say "skip (no .git/hooks — not a git worktree?)"
  elif command -v pre-commit >/dev/null 2>&1 && [[ -f "$REPO_ROOT/.pre-commit-config.yaml" ]]; then
    (cd "$REPO_ROOT" && pre-commit install)
    say "pre-commit framework installed — DCM gate + black/ruff/commitizen all run"
  else
    if [[ -f "$hook" ]] && ! diff -q "$src" "$hook" >/dev/null 2>&1; then
      cp "$hook" "$hook.bak-dcm"
      say "existing hook backed up to .git/hooks/pre-commit.bak-dcm"
    fi
    cp "$src" "$hook"
    chmod +x "$hook"
    say ".git/hooks/pre-commit ← DCM stamp check (standalone)"
    if [[ -f "$REPO_ROOT/.pre-commit-config.yaml" ]]; then
      warn "pre-commit is not installed, so ONLY the DCM review gate runs."
      note "The other hooks in .pre-commit-config.yaml (black, ruff, commitizen,"
      note "terraform_fmt…) are shadowed. To get all of them:"
      note "  pipx install pre-commit && pre-commit install"
      note "then re-run this script."
    fi
  fi
  info "Tip: any agent runs /speckit.dcm.review --commit then git commit"
}

# Team code skills. .claude/skills is where Claude Code looks: without the copy,
# "load skill dcm-verify" in the implement/review commands resolves to nothing.
sync_team_skills() {
  step "Sync team skills → .claude/skills, .agents/skills, .github"
  local dir name src_skill desc body names=""
  for dir in "$SRC"/skills/*/; do
    src_skill="${dir}SKILL.md"
    [[ -f "$src_skill" ]] || continue
    name="$(basename "$dir")"
    desc="$(front_matter_desc "$src_skill" | render_tpl "$COPILOT_SPECKIT")"
    body="$(front_matter_body "$src_skill" | render_tpl "$COPILOT_SPECKIT")"

    # sed, not cp: the skills reference the base spec-kit commands, whose name differs
    # per host. .agents/skills is the Copilot-side tree (see the header comment).
    mkdir -p "$REPO_ROOT/.claude/skills/$name" "$REPO_ROOT/.agents/skills/$name"
    render_tpl "$CLAUDE_SPECKIT"  <"$src_skill" >"$REPO_ROOT/.claude/skills/$name/SKILL.md"
    render_tpl "$COPILOT_SPECKIT" <"$src_skill" >"$REPO_ROOT/.agents/skills/$name/SKILL.md"

    mkdir -p "$REPO_ROOT/.github/agents" "$REPO_ROOT/.github/prompts"
    cat > "$REPO_ROOT/.github/agents/${name}.agent.md" <<EOF
---
description: "${desc}"
---

${body}
EOF
    printf -- '---\nagent: %s\n---\n' "$name" > "$REPO_ROOT/.github/prompts/${name}.prompt.md"
    names="${names}${names:+, }${name}"
  done
  say "${names:-none}"
  info "Source of truth is spec-kit-dcm-workflow/skills/<name>/SKILL.md — that is what"
  info "you edit and commit. Teammates get the update by re-running this script"
  info "after a git pull; the generated copies are never committed."
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force-config) FORCE_CONFIG=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

sync_extension_package
sync_constitution
check_specify_scaffold
wire_hooks

# Needs the config synced above; the template is the fallback on a first run.
MCP_SERVER="$(cfg_value mcp_server "$CONFIG")"
MCP_SERVER="${MCP_SERVER:-$(cfg_value mcp_server "$SRC/dcm-config.template.yml")}"
GITHUB_MCP_SERVER="$(cfg_value github_mcp_server "$CONFIG")"
GITHUB_MCP_SERVER="${GITHUB_MCP_SERVER:-$(cfg_value github_mcp_server "$SRC/dcm-config.template.yml")}"
DCM_COMMANDS="$(dcm_commands | tr '\n' ' ')"

# Resolved after check_specify_scaffold, so a first run sees the real install layout.
CLAUDE_SPECKIT="$(speckit_prefix claude)"
COPILOT_SPECKIT="$(speckit_prefix copilot)"
step "Base spec-kit command names"
say "Claude Code → /${CLAUDE_SPECKIT}specify   Copilot → /${COPILOT_SPECKIT}specify"
if [[ "$CLAUDE_SPECKIT" != "$COPILOT_SPECKIT" ]]; then
  info "the two hosts diverge (Claude is skills-only in spec-kit >=0.11); shared"
  info "sources use {speckit} and each host is rendered with its own separator."
fi

generate_copilot_agents
generate_claude_commands
prune_duplicate_skills
prune_legacy          # after generation: it prunes commands that no longer exist
install_claude_commit_gate
update_claude_md
install_git_hook
sync_team_skills

# .registry is written by `specify extension add`, never here: a plain sync leaves it — and
# `specify extension list` — a version behind, against a stale manifest_hash.
DCM_VER="$(cfg_value '[[:space:]]*version' "$SRC/extension.yml")"
REG_VER="$(sed -n '/"dcm": {/,/}/p' "$REPO_ROOT/.specify/extensions/.registry" 2>/dev/null \
  | sed -n 's/.*"version": "\([^"]*\)".*/\1/p' || true)"   # no .registry = not registered
[[ "$REG_VER" == "$DCM_VER" ]] \
  || warn "registry v${REG_VER:-none} ≠ extension.yml v${DCM_VER:-unknown} — run ./spec-kit-dcm-workflow/scripts/install.sh"

echo
step "Done."
