#!/usr/bin/env bash
# DCM branch sync gate — run before starting to code on a child branch.
# Reports whether the current branch has the latest origin/develop.
#
# READ-ONLY BY DEFAULT: rebasing was once the default action, so *asking* whether the
# branch was current replayed the user's commits unasked. Mutation needs --sync. The
# fetch is the exception — it destroys nothing and "behind" means nothing without it.
#
# Usage: dcm-branch-sync-check.sh [--sync] [--base develop] [--strategy rebase|merge]
#
# Exit codes:
#   0  up to date (or not applicable) — safe to code
#   2  STOP — branch behind and untouched (stderr starts with BEHIND: re-run with
#      --sync), or --sync failed (SYNC FAILED: conflict, dirty tree, no remote —
#      needs a human)
#   1  usage / internal error
set -euo pipefail

BASE_BRANCH="develop"
STRATEGY="rebase"
DO_SYNC=0

usage() {
  cat <<'EOF'
Usage: dcm-branch-sync-check.sh [--sync] [--base develop] [--strategy rebase|merge]

Default (no --sync): fetch + report only. Nothing in the working tree or in the
branch history is modified. Exit 2 with "BEHIND" if the branch is not current.

--sync        actually sync the branch with origin/{base} (rewrites history with
              --strategy rebase, or creates a merge commit with --strategy merge)
--strategy    rebase  default. Branch not pushed/shared yet -> git rebase origin/{base}
              merge   branch already pushed/shared with other devs -> git merge origin/{base}
--check-only  accepted and ignored — this is now the default. Kept so older
              callers do not break.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sync) DO_SYNC=1; shift ;;
    --base) BASE_BRANCH="$2"; shift 2 ;;
    --strategy) STRATEGY="$2"; shift 2 ;;
    # Was the opt-in for read-only, which is now the default.
    --check-only) shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

case "$STRATEGY" in
  rebase|merge) ;;
  *) echo "Unknown --strategy: $STRATEGY (expected rebase|merge)" >&2; exit 1 ;;
esac

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

if [[ "$CURRENT_BRANCH" == "$BASE_BRANCH" || "$CURRENT_BRANCH" == "main" || "$CURRENT_BRANCH" == "HEAD" ]]; then
  echo "On $CURRENT_BRANCH — sync gate not applicable (not a child branch)"
  exit 0
fi

echo "git fetch origin $BASE_BRANCH ..."
if ! git fetch origin "$BASE_BRANCH" --quiet; then
  echo "SYNC FAILED — git fetch origin $BASE_BRANCH failed (network or remote branch missing)." >&2
  exit 2
fi

if ! git rev-parse --verify --quiet "origin/$BASE_BRANCH" >/dev/null; then
  echo "SYNC FAILED — origin/$BASE_BRANCH does not exist." >&2
  exit 2
fi

BEHIND="$(git rev-list --count "HEAD..origin/$BASE_BRANCH")"

if [[ "$BEHIND" -eq 0 ]]; then
  echo "OK — $CURRENT_BRANCH already up to date with origin/$BASE_BRANCH"
  exit 0
fi

if [[ "$DO_SYNC" -eq 0 ]]; then
  echo "BEHIND — $CURRENT_BRANCH is $BEHIND commit(s) behind origin/$BASE_BRANCH." >&2
  echo "         Nothing was modified. To sync (rewrites history with rebase):" >&2
  echo "           $0 --sync --strategy $STRATEGY --base $BASE_BRANCH" >&2
  exit 2
fi

# --sync from here on: the caller asked for the mutation.
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "SYNC FAILED — uncommitted changes present. Commit or stash before syncing with $BASE_BRANCH." >&2
  exit 2
fi

if [[ "$STRATEGY" == "rebase" ]]; then
  echo "git rebase origin/$BASE_BRANCH ... (--sync requested)"
  if git rebase "origin/$BASE_BRANCH"; then
    echo "OK — rebase done, $CURRENT_BRANCH synced with origin/$BASE_BRANCH"
    exit 0
  else
    echo "REBASE CONFLICT — resolve manually:" >&2
    echo "   git status  # see conflicting files" >&2
    echo "   # fix conflicts, then:" >&2
    echo "   git add . && git rebase --continue" >&2
    echo "   # or cancel:" >&2
    echo "   git rebase --abort" >&2
    exit 2
  fi
else
  echo "git merge origin/$BASE_BRANCH ... (--sync requested)"
  if git merge "origin/$BASE_BRANCH" --no-edit; then
    echo "OK — merge done, $CURRENT_BRANCH synced with origin/$BASE_BRANCH"
    exit 0
  else
    echo "MERGE CONFLICT — resolve manually:" >&2
    echo "   git status  # see conflicting files" >&2
    echo "   # fix conflicts, then:" >&2
    echo "   git add . && git commit" >&2
    echo "   # or cancel:" >&2
    echo "   git merge --abort" >&2
    exit 2
  fi
fi
