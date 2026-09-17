#!/usr/bin/env bash
# Claude Code hook: PreToolUse(Bash) — gate `git commit` until the DCM pre-commit
# review stamp is OK. First of two layers; .git/hooks/pre-commit is the backstop.
#
# Installed to .claude/hooks/ by sync-dcm-extension.sh (source of truth:
# spec-kit-dcm-workflow/claude-code/).
#
# Protocol:
#   stdin  : {"tool_name":"Bash","tool_input":{"command":"..."},...}
#   deny   : stdout {"hookSpecificOutput":{"hookEventName":"PreToolUse",
#                    "permissionDecision":"deny","permissionDecisionReason":"..."}}
#   let be : exit 0 with NO output.
#
# Never "allow": in Claude Code that bypasses the user's own permission rules, so it
# would auto-approve whatever Bash command was inspected. Silence lets them apply.
#
# No `set -e`: an intermediate non-zero (grep with no match, missing helper) must not
# abort the script into a fail-open exit 0.
set -uo pipefail

STDIN_JSON="$(cat 2>/dev/null || true)"

emit_deny() {
  python3 -c '
import json, sys
print(json.dumps({
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": sys.argv[1],
  }
}))
' "$1" 2>/dev/null || printf '%s\n' "BLOCKED: $1" >&2
  exit 0
}

emit_note() {
  python3 -c '
import json, sys
print(json.dumps({"systemMessage": sys.argv[1]}))
' "$1" 2>/dev/null || true
  exit 0
}

# A parse failure means we cannot tell what is about to run. Exit 0 on purpose:
# .git/hooks/pre-commit still runs, so it degrades to one fewer layer, not no gate.
PARSED="$(printf '%s' "$STDIN_JSON" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(d.get("tool_name") or "")
print((d.get("tool_input") or {}).get("command") or "")
' 2>/dev/null)" || exit 0

TOOL_NAME="$(printf '%s\n' "$PARSED" | sed -n '1p')"
COMMAND="$(printf '%s\n' "$PARSED" | sed -n '2,$p')"

[[ "$TOOL_NAME" == "Bash" ]] || exit 0

# Only gate `git commit` — not status/add/diff/log/push. Every git GLOBAL option must
# be tolerated in between: `git -c core.hooksPath=/dev/null commit` slipped through a
# narrower regex, and that option also kills the git hook — both layers, silently.
GIT_GLOBAL_OPT='([[:space:]]+(-c[[:space:]]*[^[:space:]]+|-C[[:space:]]+[^[:space:]]+|--git-dir(=|[[:space:]]+)[^[:space:]]+|--work-tree(=|[[:space:]]+)[^[:space:]]+|--namespace(=|[[:space:]]+)[^[:space:]]+|--exec-path(=[^[:space:]]+)?|--no-pager|--no-replace-objects|--literal-pathspecs|--bare|-P|-p))*'
if ! printf '%s' "$COMMAND" \
  | grep -Eqi "(^|[;&|[:space:]])git${GIT_GLOBAL_OPT}[[:space:]]+commit([[:space:]]|$)"; then
  exit 0
fi

# Same escape hatch as the git hook, but announced: with --no-verify the git hook is
# skipped too, so this is the last layer that can say anything at all.
if printf '%s' "$COMMAND" | grep -Eqi -- '--no-verify|DCM_SKIP_PRE_COMMIT_REVIEW=1'; then
  emit_note "DCM: pre-commit review bypassed (--no-verify / DCM_SKIP_PRE_COMMIT_REVIEW=1). The git hook is skipped too — nothing reviewed this diff."
fi

# `-c core.hooksPath=…` removes the backstop and this layer at once, and announces
# nothing — so deny it and point at the documented bypass, which leaves a trace.
# Checked AFTER the escape hatches: an announced bypass stays an announced bypass.
if printf '%s' "$COMMAND" | grep -Eqi 'core\.hooksPath'; then
  emit_deny "DCM: this command sets core.hooksPath, which disables .git/hooks/pre-commit — the review gate would be gone with no trace. Run /speckit.dcm.review --commit and commit normally. If a bypass is genuinely needed, use the documented one so it is announced: DCM_SKIP_PRE_COMMIT_REVIEW=1 git commit …"
fi

REPO_ROOT="${CLAUDE_PROJECT_DIR:-}"
if [[ -z "$REPO_ROOT" || ! -d "$REPO_ROOT" ]]; then
  REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi

STAMP_HELPER="$REPO_ROOT/spec-kit-dcm-workflow/scripts/dcm-pre-commit-review-stamp.sh"
if [[ ! -x "$STAMP_HELPER" ]]; then
  emit_deny "DCM gate cannot run: $STAMP_HELPER is missing or not executable. Run ./spec-kit-dcm-workflow/scripts/sync-dcm-extension.sh, then retry."
fi

# review.before_commit_require_pass, read with grep: yq is not installed on the
# team's machines. Same read as git-hooks/pre-commit.
REQUIRE_PASS=1
CFG="$REPO_ROOT/.specify/extensions/dcm/dcm-config.yml"
if [[ -f "$CFG" ]]; then
  rp="$(grep -E '^[[:space:]]*before_commit_require_pass:' "$CFG" 2>/dev/null | head -1 \
    | sed -E 's/^[^:]*:[[:space:]]*//; s/[[:space:]]*#.*$//' | tr -d '"'"'"' ')"
  [[ "$rp" == "false" ]] && REQUIRE_PASS=0
fi

CHECK_ARGS=(check --max-age-min 120)
[[ "$REQUIRE_PASS" -eq 1 ]] && CHECK_ARGS+=(--require-pass)

ERR_FILE="$(mktemp)"
trap 'rm -f "$ERR_FILE"' EXIT

if "$STAMP_HELPER" "${CHECK_ARGS[@]}" >/dev/null 2>"$ERR_FILE"; then
  # Stamp valid — silent, so the normal Bash permission rules decide.
  exit 0
fi

REASON="$(tr '\n' ' ' <"$ERR_FILE" 2>/dev/null | cut -c1-240)"
[[ -z "$REASON" ]] && REASON="missing or invalid pre-commit review stamp"

emit_deny "DCM auto-review required before commit: the stamp is missing, stale or FAIL. Run /speckit.dcm.review --commit, fix the findings, then retry git commit. Detail: ${REASON}"
