# DCM Review Report — T001a (purge liste ALL_PURPOSE)

**Feature**: `specs/024-job-dlt-cluster-split` · Task **T001** / sub-PR **T001a**
**Jira**: DCINT-326 (Epic DCINT-325)
**Package**: `packages/dcm-databricks-pipeline` (domain: dataeng)
**Branch**: `dataeng/024-purge-liste-all-purpose-rollup-dlt` (base: `develop`)
**Stack**: python (module `pipelines`)
**Verdict**: **PASS**

## Scope of the diff

Pipeline code (`pipelines/gold_dbx_compute/`):
- `cluster_cost_rolling.py` — `daily` CTE now `WHERE cluster_type = '{CLUSTER_TYPE_ALL_PURPOSE}'` (import added).
- `cluster_efficiency_rolling.py` — same ALL_PURPOSE filter (import added).
- `cluster_governance.py` — final snapshot bounded to ALL_PURPOSE (was `<> 'OTHER'`).
- `forecast.py` — both CLUSTER passes `cluster_type NOT IN ('{CLUSTER_TYPE_JOB}','{CLUSTER_TYPE_PIPELINE}')` (was `!= JOB`); `CLUSTER_TYPE_PIPELINE` import added; docstrings updated.

Tests updated (4): `test_cluster_cost_rolling.py`, `test_cluster_efficiency_rolling.py`,
`test_cluster_governance.py`, `test_forecast.py`.

Spec/doc artefacts: `specs/024-job-dlt-cluster-split/` (tasks.md, stories/T001-*.md),
`specs/active-epics.json`, `docs/spike/job-dlt-cluster-separation/`.

## Gates

Note: `dcm-review.sh` reported FAIL only because `ruff`/`pytest` are not on the bare
shell PATH (the script does not invoke through `uv`). Gates were re-run correctly via
`uv run` from the package directory; results below are authoritative.

| Gate | Status | Detail |
|------|--------|--------|
| ruff (touched files) | PASS | 8/8 files `All checks passed!` (`uv run ruff check <file>`) |
| ruff (whole package) | PRE-EXISTING | 269 errors, all in untouched files (e.g. `tests/test_dlt_workflow.py` ANN001) — none reference a T001a file; not attributable to this diff |
| mypy | N/A (not a package gate) | dcm-verify matrix excludes mypy for `dcm-databricks-pipeline`. Only pre-existing noise: `--explicit-package-bases` module-layout error + missing `types-requests` stub at `forecast.py:440` (untouched line) |
| pytest (touched tests) | PASS | 66 passed |
| pytest (gold_dbx_compute dir) | PASS | 293 passed |

## Skills checklist (dcm-python + dcm-verify + dcm-testing)

- No secret / `.env` / credential in the diff — OK.
- No anti-pattern (no sync-in-async, no relative import, no f-string of user input;
  cluster-type constants come from `sql_helpers`, not literals) — OK.
- Absolute imports only (`from pipelines.gold_dbx_compute.sql_helpers import ...`) — OK.
- Naming convention: uses `cluster_type` values via named constants; no forbidden legacy
  `Compliance*`/`policy_*` names introduced — OK.
- Acceptance criterion SC-001 (gold liste tables retain only `cluster_type='ALL_PURPOSE'`)
  covered by new/updated assertions in all 4 test files — OK.
- Files changed subset of pipeline package scope + this feature's spec artefacts — OK.
- Behaviour change is tested (each filter change has a dedicated assertion) — OK.
- Small, reviewable diff — OK.

## Findings

- note: whole-package ruff shows 269 pre-existing errors in untouched files
  (`test_dlt_workflow.py` etc.). Out of scope for T001a; candidate for a separate lint
  cleanup task.
- note: SC-001 required a one-shot `DELETE` migration to purge historical JOB/PIPELINE
  rows from the 3 gold liste tables (documented in the story); validated PASS on dev.

**Verdict**: **PASS**
