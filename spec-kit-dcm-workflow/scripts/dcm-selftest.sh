#!/usr/bin/env bash
# DCM extension selftest — asserts the exit-code contract of every real gate, so a
# refactor turning "exit 2 = stop" into "exit 0 = go" is caught here and not on a
# teammate's branch.
#
# Usage: dcm-selftest.sh [--fixture <spec-folder>] [--with-network] [--with-sync]
#
#   --fixture       spec used as the passing case (default 009-widget-inactive-cluster);
#                   must have intake.json, tasks.md and stories/*.md
#   --with-network  also run dcm-branch-sync-check.sh for real (it fetches)
#   --with-sync     also run sync-dcm-extension.sh twice and check idempotence —
#                   opt-in because it REGENERATES .claude/, .github/ and the package
#
# Exit codes: 0 all checks passed · 1 at least one failed
#
# Read-only by default: nothing outside a mktemp dir is written; the stamp gate runs
# through DCM_REVIEW_STAMP_DIR so the real stamp is untouched.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "$SCRIPT_DIR/.." && pwd)"
# Not `a || b && c`: that groups as `(a||b) && c` and leaves two paths in the var.
if ! REPO_ROOT="$(git -C "$SRC" rev-parse --show-toplevel 2>/dev/null)"; then
  REPO_ROOT="$(cd "$SRC/.." && pwd)"
fi
EXT="$REPO_ROOT/.specify/extensions/dcm"

FIXTURE="009-widget-inactive-cluster"
WITH_NETWORK=0
WITH_SYNC=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fixture) FIXTURE="$2"; shift 2 ;;
    --with-network) WITH_NETWORK=1; shift ;;
    --with-sync) WITH_SYNC=1; shift ;;
    # The header block, whatever its length — a line range would print code.
    -h|--help) awk 'NR>1 { if (/^#/) { sub(/^# ?/, ""); print; next } exit }' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

cd "$REPO_ROOT"

TMPD="$(mktemp -d)"
trap 'rm -rf "$TMPD"' EXIT
ERRFILE="$TMPD/stderr"
TMP_STAMP="$TMPD/stamp"
mkdir -p "$TMP_STAMP"

PASSED=0
FAILED=0
NOTES=()

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; PASSED=$((PASSED + 1)); }
ko()   { printf '  \033[31m✗\033[0m %s\n' "$1"; FAILED=$((FAILED + 1)); }
note() { printf '  \033[33m·\033[0m %s\n' "$1"; NOTES+=("$1"); }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# check <label> <expected-exit> <command...>
# Streams captured SEPARATELY: stdout is data, stderr is warnings, and merging them
# would fail a content assertion on a script that behaves correctly.
LAST_OUT=""
LAST_ERR=""
check() {
  local label="$1" want="$2"; shift 2
  local rc
  LAST_OUT="$("$@" 2>"$ERRFILE")"; rc=$?
  LAST_ERR="$(cat "$ERRFILE")"
  if [[ "$rc" -eq "$want" ]]; then
    ok "$label — exit $rc"
  else
    ko "$label — expected exit $want, got $rc"
    [[ -n "$LAST_OUT" ]] && printf '%s\n' "$LAST_OUT" | sed 's/^/      | out: /'
    [[ -n "$LAST_ERR" ]] && printf '%s\n' "$LAST_ERR" | sed 's/^/      | err: /'
  fi
}

assert() { # assert <label> <condition-already-evaluated-rc>
  if [[ "$2" -eq 0 ]]; then ok "$1"; else ko "$1"; fi
}

head_ "Fixture — specs/$FIXTURE"
for f in intake.json tasks.md; do
  [[ -f "specs/$FIXTURE/$f" ]]; assert "specs/$FIXTURE/$f present" $?
done
ls "specs/$FIXTURE"/stories/*.md >/dev/null 2>&1
assert "specs/$FIXTURE/stories/*.md present" $?
[[ -f "$EXT/dcm-config.yml" ]]
assert "installed dcm-config.yml present (parse-tasks exits 3 without it)" $?

head_ "Gate — dcm-precheck.sh"
check "--gate tasks on fixture"      0 "$SCRIPT_DIR/dcm-precheck.sh" --gate tasks --spec "$FIXTURE"
check "--gate implement on fixture"  0 "$SCRIPT_DIR/dcm-precheck.sh" --gate implement --spec "$FIXTURE"
check "--gate tasks, unknown spec"   2 "$SCRIPT_DIR/dcm-precheck.sh" --gate tasks --spec __dcm_selftest_absent__
check "--gate implement, unknown"    2 "$SCRIPT_DIR/dcm-precheck.sh" --gate implement --spec __dcm_selftest_absent__
check "unknown gate name"            1 "$SCRIPT_DIR/dcm-precheck.sh" --gate __bogus__
check "missing --gate"               1 "$SCRIPT_DIR/dcm-precheck.sh"
# --gate specify and --gate plan read the repo root, so they run in a throwaway
# mini-repo: the real one would tie the result to whoever is mid-intake.
in_dir() { local d="$1"; shift; ( cd "$d" && "$@" ); }

sandbox() { # sandbox <name> → path of a fresh mini-repo
  local sb="$TMPD/$1"
  mkdir -p "$sb/.specify" "$sb/specs"
  git -C "$sb" init -q >/dev/null 2>&1 || true   # so rev-parse resolves here, not upward
  printf '%s\n' "$sb"
}

PRECHECK="$SCRIPT_DIR/dcm-precheck.sh"

SB="$(sandbox specify-gate)"
check "--gate specify, no pending intake"   2 in_dir "$SB" "$PRECHECK" --gate specify
printf '{"work_type":"feature","domains":["frontend"]}\n' > "$SB/.specify/pending-intake.json"
check "--gate specify, fresh intake"        0 in_dir "$SB" "$PRECHECK" --gate specify
printf '{"domains":["frontend"]}\n' > "$SB/.specify/pending-intake.json"
check "--gate specify, intake without work_type" 2 in_dir "$SB" "$PRECHECK" --gate specify
printf '{"work_type":"","domains":["frontend"]}\n' > "$SB/.specify/pending-intake.json"
check "--gate specify, empty work_type"          2 in_dir "$SB" "$PRECHECK" --gate specify
# The hole this closes: a leftover pending intake kept the gate green forever.
mkdir -p "$SB/specs/001-already-done"
printf '{"work_type":"feature","domains":["frontend"]}\n' > "$SB/.specify/pending-intake.json"
cp "$SB/.specify/pending-intake.json" "$SB/specs/001-already-done/intake.json"
check "--gate specify, leftover of a persisted intake" 2 in_dir "$SB" "$PRECHECK" --gate specify

SB="$(sandbox plan-gate)"
# No feature.json: the gate must refuse, not pick a specs/*/ of its choosing.
check "--gate plan, no feature context"     2 in_dir "$SB" "$PRECHECK" --gate plan
mkdir -p "$SB/specs/001-thing"
check "--gate plan, feature.json absent even with a specs/ dir" 2 in_dir "$SB" "$PRECHECK" --gate plan
printf '{"feature_directory":"specs/001-thing"}\n' > "$SB/.specify/feature.json"
check "--gate plan, no spec.md"             2 in_dir "$SB" "$PRECHECK" --gate plan
printf '# Spec\n\n## Objective\n\nSomething.\n' > "$SB/specs/001-thing/spec.md"
check "--gate plan, no Prerequisites heading" 2 in_dir "$SB" "$PRECHECK" --gate plan
printf '\n## Prerequisites\n\n- TODO\n\n## Impact\n\nx\n' >> "$SB/specs/001-thing/spec.md"
check "--gate plan, placeholder Prerequisites" 2 in_dir "$SB" "$PRECHECK" --gate plan
printf '# Spec\n\n## Prérequis\n\n- Intake confirmé.\n\n## Impact\n\nx\n' > "$SB/specs/001-thing/spec.md"
check "--gate plan, accented heading, no sizing bullet" 0 in_dir "$SB" "$PRECHECK" --gate plan
[[ "$LAST_ERR" == *"not blocking"* ]]
assert "--gate plan warns about the missing sizing bullet without failing" $?

# The shipped template must pass, or the team learns to ignore the gate. Fixed path,
# not a glob: a glob matching nothing skips its body and leaves a green run.
TPL="$SRC/templates/spec.md"
[[ -f "$TPL" ]]
assert "templates/spec.md present (the gate check below is empty without it)" $?
if [[ -f "$TPL" ]]; then
  cp "$TPL" "$SB/specs/001-thing/spec.md"
  check "--gate plan on templates/spec.md" 0 in_dir "$SB" "$PRECHECK" --gate plan
fi

# The gate must check the feature the COMMAND acts on, not the one that sorts last
# (it used to be `ls -d specs/*/ | sort | tail -1`). Here 015 passes and 011 must
# not: a green result means the wrong-feature bug is back.
SB="$(sandbox plan-gate-wrong-feature)"
mkdir -p "$SB/specs/011-mine" "$SB/specs/015-other"
printf '# Spec\n\n## Prerequisites\n\n- Small branches, few changed files per PR.\n' \
  > "$SB/specs/015-other/spec.md"
printf '# Spec\n\n## Prerequisites\n\n- TODO\n' > "$SB/specs/011-mine/spec.md"
printf '{"feature_directory":"specs/011-mine"}\n' > "$SB/.specify/feature.json"
check "--gate plan checks feature.json's spec, not the last one alphabetically" \
  2 in_dir "$SB" "$PRECHECK" --gate plan
[[ "$LAST_ERR" == *011-mine* ]]
assert "the failure names specs/011-mine (the declared feature)" $?
check "--spec overrides feature.json" 0 in_dir "$SB" "$PRECHECK" --gate plan --spec 015-other

head_ "Gate — dcm-parse-tasks.sh"
check "TSV on fixture"          0 "$SCRIPT_DIR/dcm-parse-tasks.sh" --spec "$FIXTURE"
[[ "$(printf '%s' "$LAST_OUT" | grep -c $'\t')" -ge 1 ]]
assert "TSV output has at least one tab-separated task line" $?
printf '%s\n' "$LAST_OUT" | awk -F'\t' 'NF!=7 {exit 1}'
assert "every TSV line has exactly 7 columns" $?
printf '%s\n' "$LAST_OUT" | awk -F'\t' '$1 !~ /^T[0-9]+$/ {exit 1}'
assert "column 1 is a task id on every line" $?
[[ -n "$LAST_ERR" ]]
assert "the summary line goes to stderr, never to stdout" $?
if printf '%s\n' "$LAST_OUT" | awk -F'\t' '$3=="misc" {found=1} END {exit !found}'; then
  note "fixture has task(s) resolved to domain=misc — branch would be misc/…"
fi
check "--json on fixture"       0 "$SCRIPT_DIR/dcm-parse-tasks.sh" --spec "$FIXTURE" --json
printf '%s' "$LAST_OUT" | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null
assert "--json emits parseable JSON on stdout only" $?
check "unknown spec"            1 "$SCRIPT_DIR/dcm-parse-tasks.sh" --spec __dcm_selftest_absent__
check "missing --spec"          1 "$SCRIPT_DIR/dcm-parse-tasks.sh"
# Spec 010 uses a markdown table with glyphs → exit 2, never "0 tasks". A note and
# not an assert: it depends on spec content this script does not own.
if [[ -f "specs/010-databricks-usage-finops-curated/tasks.md" ]]; then
  "$SCRIPT_DIR/dcm-parse-tasks.sh" --spec 010-databricks-usage-finops-curated >/dev/null 2>&1
  rc=$?
  [[ "$rc" -eq 2 ]] && ok "spec 010 still exits 2 (format divergence, not '0 tasks')" \
                    || note "spec 010 now exits $rc (was 2 = format divergence)"
fi

head_ "Gate — dcm-conflict-check.sh"
check "--json on fixture"  0 "$SCRIPT_DIR/dcm-conflict-check.sh" --spec "$FIXTURE" --json
printf '%s' "$LAST_OUT" | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null
assert "--json emits parseable JSON" $?
check "missing --spec"     1 "$SCRIPT_DIR/dcm-conflict-check.sh"
check "unknown spec dir"   1 "$SCRIPT_DIR/dcm-conflict-check.sh" --spec __dcm_selftest_absent__
check "unknown arg"        1 "$SCRIPT_DIR/dcm-conflict-check.sh" --spec "$FIXTURE" --nope

head_ "Gate — dcm-pre-commit-review-stamp.sh"
check "check with no stamp"   1 env DCM_REVIEW_STAMP_DIR="$TMP_STAMP" "$SCRIPT_DIR/dcm-pre-commit-review-stamp.sh" check
[[ "$LAST_OUT" == *MISSING* ]]
assert "check prints MISSING when there is no stamp" $?
STAMP="$SCRIPT_DIR/dcm-pre-commit-review-stamp.sh"

# `write` needs a non-empty index and these checks need to know exactly what is
# staged: own sandbox, own staged file, own stamp dir.
SB="$(sandbox stamp-gate)"
printf 'staged content\n' > "$SB/staged.txt"
git -C "$SB" add staged.txt >/dev/null 2>&1
SB_STAMP="$SB/.specify"
stamp_in() { in_dir "$SB" env DCM_REVIEW_STAMP_DIR="$SB_STAMP" "$STAMP" "$@"; }

# `write` is refused unless --report declares the same verdict.
REPORT_PASS="$SB/report-pass.md"
REPORT_FAIL="$SB/report-fail.md"
REPORT_MUTE="$SB/report-no-verdict.md"
printf '# DCM Review Report\n\n**Verdict**: **PASS** (fail=0 warn=0 skip=1)\n' > "$REPORT_PASS"
printf '# DCM Review Report\n\n**Verdict**: **FAIL** (fail=2 warn=0 skip=0)\n' > "$REPORT_FAIL"
printf '# DCM Review Report\n\nLooks fine to me.\n' > "$REPORT_MUTE"

check "write accepted, index staged + report agrees" 0 \
  stamp_in write --verdict PASS --report "$REPORT_PASS" --notes "dcm-selftest"
check "check passes on fresh stamp"   0 stamp_in check --require-pass
# The hole this closes: `write --verdict PASS` needed no evidence at all.
check "write refused without --report" 2 stamp_in write --verdict PASS
check "write refused, report missing"  2 \
  stamp_in write --verdict PASS --report "$SB/__absent__.md"
check "write refused, report declares no verdict" 2 \
  stamp_in write --verdict PASS --report "$REPORT_MUTE"
check "PASS stamp refused over a FAIL report" 2 \
  stamp_in write --verdict PASS --report "$REPORT_FAIL"
[[ "$LAST_ERR" == *FAIL* ]]
assert "the refusal names the report's actual verdict" $?
check "FAIL stamp accepted on a FAIL report" 0 \
  stamp_in write --verdict FAIL --report "$REPORT_FAIL"
check "check rejects a FAIL stamp"     1 stamp_in check
check "bad verdict rejected"           2 stamp_in write --verdict MAYBE --report "$REPORT_PASS"
# Refusals must not have clobbered the last accepted stamp.
stamp_in write --verdict PASS --report "$REPORT_PASS" >/dev/null 2>&1
python3 -c 'import json,sys
d = json.load(open(sys.argv[1]))
sys.exit(0 if d.get("report") and d.get("report_hash") else 1)' \
  "$SB_STAMP/pre-commit-review-stamp.json" 2>/dev/null
assert "stamp JSON carries report + report_hash" $?

# Nothing staged is still refused, whatever the report says.
SB2="$(sandbox stamp-gate-empty)"
check "write refused, nothing staged" 2 \
  in_dir "$SB2" env DCM_REVIEW_STAMP_DIR="$SB2/.specify" "$STAMP" \
  write --verdict PASS --report "$REPORT_PASS"

head_ "Gate — dcm-branch-sync-check.sh"
check "--help"               0 "$SCRIPT_DIR/dcm-branch-sync-check.sh" --help
check "unknown --strategy"   1 "$SCRIPT_DIR/dcm-branch-sync-check.sh" --strategy sideways
check "unknown option"       1 "$SCRIPT_DIR/dcm-branch-sync-check.sh" --nope
if [[ "$WITH_NETWORK" -eq 1 ]]; then
  "$SCRIPT_DIR/dcm-branch-sync-check.sh" >/dev/null 2>&1; rc=$?
  # 0 = up to date, 2 = BEHIND or fetch failed; 1 would mean arg handling broke.
  [[ "$rc" -eq 0 || "$rc" -eq 2 ]]
  assert "real run returns 0 or 2 (got $rc)" $?
else
  note "dcm-branch-sync-check.sh real run skipped (--with-network to include; it fetches)"
fi

# Catches a rename or a deletion: a command declared but gone, a template path that
# no longer resolves, a command body calling a removed script.
head_ "Structure — declarations vs disk"
missing=0
while read -r rel; do
  [[ -z "$rel" ]] && continue
  [[ -f "$SRC/$rel" ]] || { ko "extension.yml declares $rel — not on disk"; missing=1; }
done < <(grep -oE '(commands|templates)/[A-Za-z0-9._-]+\.(md|json)' "$SRC/extension.yml" | sort -u)
[[ "$missing" -eq 0 ]] && ok "every commands/ and templates/ path in extension.yml exists"

undeclared=0
for f in "$SRC"/commands/*.md; do
  b="commands/$(basename "$f")"
  grep -q "$b" "$SRC/extension.yml" || { ko "$b exists but is not declared in extension.yml"; undeclared=1; }
done
[[ "$undeclared" -eq 0 ]] && ok "every commands/*.md is declared in extension.yml"

deadref=0
while read -r rel; do
  [[ -z "$rel" ]] && continue
  [[ -f "$SRC/$rel" ]] || { ko "a command body calls $rel — not on disk"; deadref=1; }
done < <(grep -ohE 'scripts/(lib/)?[a-z0-9_-]+\.(sh|py)' "$SRC"/commands/*.md | sort -u)
[[ "$deadref" -eq 0 ]] && ok "every scripts/ path referenced by a command exists"

# The two checks below read the package as prose, minus the lines describing a
# REMOVAL: the docs record what a merge deleted, and naming the dead file is the
# point of such a line. Cost: a stale reference on one of those lines is missed.
GONE='supprim|removed|dropped|fusionn|merged|ancien|legacy|renomm|renamed'
live_prose() {
  grep -rh '' "$SRC" --include="*.md" --include="*.sh" --include="*.yml" --include="*.py" \
    | grep -viE "$GONE"
}

# A `commands/<name>.md` path holds no `/speckit.dcm.*` token, so the name check
# below cannot see it — five pointers to merged-away commands survived that way.
deadcmdref=0
while read -r rel; do
  [[ -z "$rel" ]] && continue
  [[ -f "$SRC/$rel" ]] || { ko "$rel is referenced in the package — not on disk"; deadcmdref=1; }
done < <(live_prose | grep -oE 'commands/[a-z0-9-]+\.md' | sort -u)
[[ "$deadcmdref" -eq 0 ]] && ok "every commands/*.md path mentioned in the package exists"

# Declared command names, once — both checks below compare against this list.
DECLARED="$(sed -n 's/^[[:space:]]*- name: "\(speckit\.dcm\.[a-z0-9-]*\)".*/\1/p' "$SRC/extension.yml" | tr '\n' ' ')"

# A hook can only name a REGISTERED command and nothing verifies it at runtime.
# First token only — the rest of the string is flags (`--intake-only`).
danglinghook=0
while read -r cmd; do
  [[ -z "$cmd" ]] && continue
  case " $DECLARED " in
    *" $cmd "*) ;;
    *) ko "hooks: names $cmd — not in provides.commands"; danglinghook=1 ;;
  esac
done < <(awk '/^hooks:/ { h = 1 } h && /command:/ {
           sub(/.*command:[[:space:]]*/, ""); gsub(/"/, ""); print $1 }' "$SRC/extension.yml" | sort -u)
[[ "$danglinghook" -eq 0 ]] && ok "every hooks: command resolves to a declared command"

# Same for the prose: a doc or deny message naming a command that no longer exists
# is a dead end the user cannot debug (found a `pr` alias advertised long after).
unknownref=0
while read -r cmd; do
  [[ -z "$cmd" ]] && continue
  case " $DECLARED " in
    *" $cmd "*) ;;
    *) ko "$cmd is referenced in the package but is not a declared command"; unknownref=1 ;;
  esac
done < <(live_prose | grep -oE 'speckit\.dcm\.[a-z0-9-]+' | sort -u)
[[ "$unknownref" -eq 0 ]] && ok "every /speckit.dcm.* name in the package is declared"

# The agent deletes the `[work_type: …]` blocks that do not apply, so a marker naming
# a work type that does not exist is a block nobody fills and nobody deletes.
WORKTYPES="$(awk '/^work_types:/ { w = 1; next } w && /^[a-z]/ { exit }
                  w && /^  [a-z_]+:[[:space:]]*$/ { gsub(/[ :]/, ""); print }' \
             "$SRC/dcm-config.template.yml" | tr '\n' ' ')"
badmarker=0
while read -r wt; do
  [[ -z "$wt" ]] && continue
  case " $WORKTYPES " in
    *" $wt "*) ;;
    *) ko "templates/spec.md marks a block [work_type: $wt] — no such work type in dcm-config"; badmarker=1 ;;
  esac
done < <(grep -oE '\[work_type: [a-z, ]+\]' "$SRC/templates/spec.md" 2>/dev/null \
           | sed 's/\[work_type: //; s/\]//' | tr ',' '\n' | tr -d ' ' | sort -u)
[[ "$badmarker" -eq 0 ]] && ok "every [work_type: …] block in templates/spec.md names a declared work type"

# Base spec-kit commands have a per-host name (`speckit-plan` on Claude Code,
# `speckit.plan` on Copilot). Shared sources must write `{speckit}plan` so that
# sync-dcm-extension.sh can render each host: a hardcoded `/speckit.plan` is a name
# that resolves on exactly one of the two, silently.
SPECKIT_BASE='specify|plan|tasks|implement|clarify|analyze|checklist|constitution|converge|taskstoissues'
hardcoded=0
while read -r hit; do
  [[ -z "$hit" ]] && continue
  ko "hardcoded base command: $hit — use /{speckit}<name>"
  hardcoded=1
done < <(grep -rnE "/speckit\.($SPECKIT_BASE)\b" \
           "$SRC"/commands "$SRC"/skills "$SRC"/claude-code 2>/dev/null | head -20)
[[ "$hardcoded" -eq 0 ]] && ok "no hardcoded base spec-kit command name in the rendered sources"

# Same class of bug, different blast radius: scripts/ is copied VERBATIM, never rendered,
# so a `{speckit}` token there would reach the user literally. A script may only name the
# DCM commands, which keep their dots on both hosts — any base name it prints is wrong for
# one host. Two exclusions, both legitimate: comment lines (they explain the rule) and path
# literals like `commands/speckit.specify.md`, which speckit_prefix() probes on disk.
# The docs (GUIDE/README/CONTRACTS) are deliberately out of scope — their Notation tables
# spell both names out on purpose.
scripthard=0
while read -r hit; do
  [[ -z "$hit" ]] && continue
  ko "script prints a base command name: $hit — name a DCM command or stay host-neutral"
  scripthard=1
done < <(grep -rnE "/speckit\.($SPECKIT_BASE)\b" "$SRC"/scripts 2>/dev/null \
           | grep -vE ':[[:space:]]*#' \
           | grep -vE '(commands|prompts|skills|agents)/speckit\.' | head -20)
[[ "$scripthard" -eq 0 ]] && ok "no script prints a base spec-kit command name"

# The mirror check: a `{speckit}` token that reaches a host unresolved is worse than a
# wrong separator — `/{speckit}plan` resolves nowhere at all.
unresolved=0
for d in "$REPO_ROOT/.claude/commands" "$REPO_ROOT/.claude/skills" \
         "$REPO_ROOT/.github/prompts" "$REPO_ROOT/.github/agents" "$REPO_ROOT/CLAUDE.md"; do
  [[ -e "$d" ]] || continue
  if grep -rq '{speckit}' "$d" 2>/dev/null; then
    ko "$d still contains an unresolved {speckit} token — re-run sync-dcm-extension.sh"
    unresolved=1
  fi
done
[[ "$unresolved" -eq 0 ]] && ok "no unresolved {speckit} token in any generated artefact"

# Same bug one level deeper: the base skills build a hook's slash command by replacing dots
# with hyphens, so `speckit.dcm.specify` is announced as `/speckit-dcm-specify` — a name that
# exists nowhere (the hyphen twins are pruned on purpose). CLAUDE.md is what maps it back.
grep -q 'speckit-dcm-' "$REPO_ROOT/CLAUDE.md" 2>/dev/null
assert "CLAUDE.md maps the hyphenated hook name back to /speckit.dcm.…" $?

# `domain_subagents_required: true` makes the dataeng delegation non-negotiable, and the
# subagent tool is named `Agent` in current Claude Code (it was `Task` before). Since
# allowed-tools is an allowlist, a line naming only `Task` denies the delegation at the
# tool layer — while the command body still reads perfectly, so nothing else here notices.
# Assert the RENDERED line: the bug would live in claude_allowed_tools(), not in the source.
impl_cmd="$REPO_ROOT/.claude/commands/speckit.dcm.implement.md"
if [[ -f "$impl_cmd" ]]; then
  grep -m1 '^allowed-tools:' "$impl_cmd" | grep -qw 'Agent'
  assert "implement allowed-tools grants the Agent tool (delegation is blocking)" $?
  grep -qE '\bAgent\(' "$SRC/commands/implement.md"
  assert "commands/implement.md names the Claude Code call as Agent(…)" $?
else
  note "$impl_cmd not generated — run sync-dcm-extension.sh"
fi

for h in "$REPO_ROOT/.git/hooks/pre-commit" "$REPO_ROOT/.claude/hooks/dcm-before-commit-review.sh"; do
  if [[ -f "$h" ]]; then
    [[ -x "$h" ]]; assert "$(basename "$(dirname "$h")")/$(basename "$h") installed and executable" $?
  else
    note "$h not installed — run sync-dcm-extension.sh"
  fi
done

if [[ "$WITH_SYNC" -eq 1 ]]; then
  head_ "Sync — idempotence (regenerates .claude/, .github/, installed package)"
  "$SCRIPT_DIR/sync-dcm-extension.sh" >/dev/null 2>&1
  assert "first run succeeds" $?
  out2="$("$SCRIPT_DIR/sync-dcm-extension.sh" 2>&1)"; rc=$?
  assert "second run succeeds" $rc
  left="$(printf '%s\n' "$out2" | grep -oE '[0-9]+ legacy artefact' | grep -oE '^[0-9]+' | head -1)"
  [[ "${left:-0}" -eq 0 ]]
  assert "second run removes 0 legacy artefact (converged), got ${left:-?}" $?
  # The only intentional differences between source and installed package.
  drift="$(diff -rq "$SRC" "$EXT" 2>&1 \
    | grep -vE '(\.extensionignore|\.specify-dev|dcm-config\.yml|: specs$)' || true)"
  [[ -z "$drift" ]]
  assert "source ↔ installed package has no unexpected drift" $?
  [[ -n "$drift" ]] && printf '%s\n' "$drift" | sed 's/^/      | /'
else
  note "sync idempotence skipped (--with-sync to include; it regenerates artefacts)"
fi

printf '\n\033[1m%s\033[0m\n' "═══════════════════════════════════════════════════════════"
printf 'dcm-selftest — %d passed, %d failed' "$PASSED" "$FAILED"
[[ "${#NOTES[@]}" -gt 0 ]] && printf ', %d note(s)' "${#NOTES[@]}"
printf '\n'
if [[ "$FAILED" -eq 0 ]]; then
  printf '\033[32mOK\033[0m — gate contracts unchanged\n'
  exit 0
fi
printf '\033[31mFAILED\033[0m — a gate no longer behaves as documented\n'
exit 1
