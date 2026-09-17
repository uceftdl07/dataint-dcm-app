#!/usr/bin/env bash
# DCM quality review — lint, types, tests, optional duplication/coverage/sonar
# Usage: dcm-review.sh --package packages/dcm-frontend [--base main] [--report path.md]
set -euo pipefail

PACKAGE_DIR=""
BASE_BRANCH="develop"
REPORT_PATH=""
COVERAGE_MIN=""
RUN_DUP=false
RUN_SONAR=false

usage() {
  cat <<'EOF'
Usage: dcm-review.sh --package <path> [options]

Options:
  --package PATH     Package root (e.g. packages/dcm-frontend)
  --base BRANCH      Git base for diff (default: develop)
  --report PATH      Write markdown report (default: stdout only)
  --coverage-min N   Fail if line coverage below N (requires coverage tools)
  --duplication      Run jscpd if installed
  --sonar            Run sonar-scanner if SONAR_TOKEN set
  -h, --help         Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --package) PACKAGE_DIR="$2"; shift 2 ;;
    --base) BASE_BRANCH="$2"; shift 2 ;;
    --report) REPORT_PATH="$2"; shift 2 ;;
    --coverage-min) COVERAGE_MIN="$2"; shift 2 ;;
    --duplication) RUN_DUP=true; shift ;;
    --sonar) RUN_SONAR=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

[[ -n "$PACKAGE_DIR" ]] || { echo "Missing --package" >&2; usage; exit 1; }
[[ -d "$PACKAGE_DIR" ]] || { echo "Package not found: $PACKAGE_DIR" >&2; exit 1; }

REPO_ROOT="$(git -C "$PACKAGE_DIR" rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
MERGE_BASE="$(git merge-base "origin/${BASE_BRANCH}" HEAD 2>/dev/null || git merge-base "$BASE_BRANCH" HEAD 2>/dev/null || echo "")"
CHANGED_FILES=""
if [[ -n "$MERGE_BASE" ]]; then
  CHANGED_FILES="$(git diff --name-only "$MERGE_BASE"...HEAD -- "$PACKAGE_DIR" 2>/dev/null || true)"
else
  CHANGED_FILES="$(git diff --name-only HEAD~1 -- "$PACKAGE_DIR" 2>/dev/null || true)"
fi

declare -a RESULTS=()
FAIL_COUNT=0
WARN_COUNT=0
SKIP_COUNT=0

record() {
  local gate="$1" status="$2" detail="$3"
  RESULTS+=("| $gate | $status | $detail |")
  case "$status" in
    FAIL) FAIL_COUNT=$((FAIL_COUNT + 1)) ;;
    WARN) WARN_COUNT=$((WARN_COUNT + 1)) ;;
    SKIP) SKIP_COUNT=$((SKIP_COUNT + 1)) ;;
  esac
}

run_gate() {
  local gate="$1"
  shift
  local log
  log="$(mktemp)"
  if (cd "$PACKAGE_DIR" && "$@") >"$log" 2>&1; then
    record "$gate" "PASS" "ok"
  else
    local excerpt
    excerpt="$(tail -20 "$log" | tr '\n' ' ' | cut -c1-120)"
    record "$gate" "FAIL" "$excerpt"
  fi
  rm -f "$log"
}

detect_stack() {
  if [[ -f "$PACKAGE_DIR/package.json" ]]; then
    echo "frontend"
  elif [[ -f "$PACKAGE_DIR/pyproject.toml" ]]; then
    # "python", not "backend": this covers dcm-commons, the collectors, lambda-ingestion
    # and the pipeline too — calling them all "backend" is what led to hardcoding
    # dcm-backend's layout below.
    echo "python"
  else
    echo "unknown"
  fi
}

# The import package to type-check and measure coverage on. Hardcoded as `app` it
# was dcm-backend's layout and nobody else's: `mypy app` then fails on a path that
# does not exist, a FAIL about nothing, on 5 of the 6 Python packages.
#
# pyproject.toml is the authority — every DCM package declares its module in
# `packages = ["…"]`. Filesystem probing is only a fallback, and cannot come first:
# a module may be a namespace dir with no __init__.py (the pipeline's `pipelines/`).
detect_python_module() {
  local pyproject="$PACKAGE_DIR/pyproject.toml" mod="" d base

  if [[ -f "$pyproject" ]]; then
    mod="$( { grep -E '^[[:space:]]*packages[[:space:]]*=' "$pyproject" 2>/dev/null || true; } \
      | head -1 | grep -oE '"[^"]+"' | head -1 | tr -d '"' || true)"
    # Unresolvable (src/ layout, glob, typo) → not a usable target, fall through.
    [[ -n "$mod" && ! -d "$PACKAGE_DIR/$mod" ]] && mod=""
  fi

  if [[ -z "$mod" ]]; then
    for d in "$PACKAGE_DIR"/*/; do
      [[ -d "$d" ]] || continue
      base="$(basename "$d")"
      case "$base" in
        tests|test|docs|scripts|dist|build|notebooks|resources|schemas|fixtures|.*) continue ;;
      esac
      [[ -f "$d/__init__.py" ]] || continue
      mod="$base"; break
    done
  fi

  printf '%s' "$mod"
}

STACK="$(detect_stack)"
PY_MODULE=""
[[ "$STACK" == "python" ]] && PY_MODULE="$(detect_python_module)"

case "$STACK" in
  frontend)
    run_gate "eslint" npm run lint
    run_gate "typescript" npm run typecheck
    run_gate "vitest" npm test
  if [[ -n "$COVERAGE_MIN" ]]; then
    log="$(mktemp)"
    if (cd "$PACKAGE_DIR" && npx vitest run --coverage 2>"$log"); then
      record "coverage" "PASS" "vitest --coverage ok (min ${COVERAGE_MIN}% not parsed — check report)"
    else
      record "coverage" "SKIP" "vitest coverage unavailable — install @vitest/coverage-v8"
    fi
    rm -f "$log"
  fi
    ;;
  python)
    # Bare `ruff` / `pytest` / `mypy` resolve against the system PATH, outside the
    # project environment. On a uv-managed package that is not a nuance: pytest
    # cannot import the package's own conftest and reports an ImportError, i.e. a
    # FAIL that says nothing about the code — exactly what the mypy gate below
    # refuses to do. Measured on dcm-databricks-pipeline: bare `pytest` FAILs on
    # conftest while `uv run pytest` passes 731 tests.
    #
    # `uv pip install --system` was the previous attempt at the same problem. It
    # installs into whatever Python is on PATH, and `|| true` swallowed the failure
    # — so the gates kept running against a system env that never got the deps. It
    # stays as the fallback for a package uv does not manage as a project.
    PY_RUN=()
    if command -v uv >/dev/null 2>&1; then
      if [[ -f "$PACKAGE_DIR/uv.lock" || -d "$PACKAGE_DIR/.venv" ]]; then
        PY_RUN=(uv run --)
      else
        (cd "$PACKAGE_DIR" && uv pip install --system -e ".[dev]" >/dev/null 2>&1) || true
      fi
    fi
    # bash 3.2 (macOS stock) + `set -u`: expanding an empty array is an error, hence
    # the `${arr[@]+…}` guard rather than a plain "${arr[@]}".
    PY_PREFIX=(${PY_RUN[@]+"${PY_RUN[@]}"})

    run_gate "ruff" ${PY_PREFIX[@]+"${PY_PREFIX[@]}"} ruff check .
    # SKIP with the reason, never FAIL: a gate that fails on its own
    # misconfiguration teaches the team to ignore it.
    if ! (cd "$PACKAGE_DIR" && ${PY_PREFIX[@]+"${PY_PREFIX[@]}"} mypy --version) >/dev/null 2>&1; then
      record "mypy" "SKIP" "mypy not installed"
    elif [[ -z "$PY_MODULE" ]]; then
      record "mypy" "SKIP" "no import package found — declare it in $PACKAGE_DIR/pyproject.toml (packages = [\"…\"])"
    else
      run_gate "mypy" ${PY_PREFIX[@]+"${PY_PREFIX[@]}"} mypy "$PY_MODULE"
    fi
    run_gate "pytest" ${PY_PREFIX[@]+"${PY_PREFIX[@]}"} pytest
    if [[ -n "$COVERAGE_MIN" ]]; then
      if [[ -z "$PY_MODULE" ]]; then
        record "coverage" "SKIP" "no import package found — cannot target --cov"
      else
        log="$(mktemp)"
        if (cd "$PACKAGE_DIR" && ${PY_PREFIX[@]+"${PY_PREFIX[@]}"} pytest "--cov=$PY_MODULE" --cov-report=term-missing 2>"$log"); then
          record "coverage" "PASS" "pytest --cov=$PY_MODULE ok (min ${COVERAGE_MIN}% not parsed — check report)"
        else
          record "coverage" "SKIP" "pytest-cov not installed"
        fi
        rm -f "$log"
      fi
    fi
    ;;
  *)
    record "stack" "FAIL" "no package.json and no pyproject.toml in $PACKAGE_DIR — not a package this script can gate"
    ;;
esac

if [[ "$RUN_DUP" == true ]]; then
  if command -v jscpd >/dev/null 2>&1; then
    log="$(mktemp)"
    if jscpd "$PACKAGE_DIR" --min-lines 8 --reporters console --silent 2>"$log"; then
      record "duplication" "PASS" "no clones above threshold"
    else
      record "duplication" "WARN" "$(tail -5 "$log" | tr '\n' ' ' | cut -c1-120)"
    fi
    rm -f "$log"
  else
    record "duplication" "SKIP" "jscpd not installed (npm i -g jscpd)"
  fi
fi

if [[ "$RUN_SONAR" == true ]]; then
  if [[ -n "${SONAR_TOKEN:-}" ]] && command -v sonar-scanner >/dev/null 2>&1; then
    if sonar-scanner -Dsonar.projectBaseDir="$PACKAGE_DIR" >/dev/null 2>&1; then
      record "sonar" "PASS" "scanner finished"
    else
      record "sonar" "FAIL" "sonar-scanner failed — check sonar-project.properties"
    fi
  else
    record "sonar" "SKIP" "SONAR_TOKEN or sonar-scanner missing"
  fi
fi

VERDICT="PASS"
[[ $FAIL_COUNT -gt 0 ]] && VERDICT="FAIL"
[[ $FAIL_COUNT -eq 0 && $WARN_COUNT -gt 0 ]] && VERDICT="WARN"

REPORT="$(cat <<EOF
# DCM Review Report

**Package**: \`$PACKAGE_DIR\`
**Branch**: \`$BRANCH\` (base: \`$BASE_BRANCH\`)
**Stack**: $STACK${PY_MODULE:+ (module \`$PY_MODULE\`)}
**Verdict**: **$VERDICT** (fail=$FAIL_COUNT warn=$WARN_COUNT skip=$SKIP_COUNT)

## Changed files

\`\`\`
${CHANGED_FILES:-"(none detected vs base)"}
\`\`\`

## Gates

| Gate | Status | Detail |
|------|--------|--------|
$(printf '%s\n' "${RESULTS[@]}")

## Next

- Agent: cross-check diff vs \`dcm-python\` / \`dcm-react\` skills + sub-spec acceptance criteria
- If PASS: open PR to integration branch
- If FAIL: fix and re-run \`/speckit.dcm.review\`
EOF
)"

if [[ -n "$REPORT_PATH" ]]; then
  mkdir -p "$(dirname "$REPORT_PATH")"
  printf '%s\n' "$REPORT" >"$REPORT_PATH"
  echo "Report: $REPORT_PATH"
fi

printf '%s\n' "$REPORT"

[[ "$VERDICT" != "FAIL" ]]
