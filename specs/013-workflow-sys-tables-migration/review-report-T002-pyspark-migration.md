# DCM Review Report — pre-commit

**Package**: `packages/dcm-databricks-pipeline` (+ 1 comment-only change in `packages/dcm-backend`)
**Branch**: `dataeng/migrate_workflow_pyspark` (base: `develop`)
**Task**: T002 — Vues-pont + re-sourcing gold `workflow` (`specs/013-workflow-sys-tables-migration`), suite architecturale de `review-report-T002.md` : les 8 agrégats gold sont extraits de `dlt_03_gold_layer.py` vers un package PySpark standalone `pipelines/gold_dbx_workflow/`, sur le modèle de `gold_dbx_compute`/`gold_dbx_usage` (rationale documenté dans `docs/spike/define-tool-curated-to-gold/DCM-datamodel-DLT-vs-PySpark-et-structure-jobs.md`).
**Stack**: dataeng (Python/PySpark, pas de DLT dans le nouveau package)
**Scope of this review**: diff **staged** (rien n'est encore commité sur cette branche vs `develop`)

**Verdict**: **PASS**

## Changed files (staged)

```
packages/dcm-backend/app/api/services/databricks_workspaces_page.py        (comment only, no behavior change)
packages/dcm-databricks-pipeline/pipelines/dlt_03_gold_layer.py            (workflow block removed: 1280 -> 471 lines)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_workflow/__init__.py   (new)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_workflow/bridges.py    (new)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_workflow/concurrency_1min.py (new)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_workflow/duration_drift.py   (new)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_workflow/duration_percentiles.py (new)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_workflow/entrypoint.py (new)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_workflow/runs.py       (new)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_workflow/specs.py      (new)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_workflow/success_rate.py (new)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_workflow/task_failure_rate.py (new)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_workflow/task_health.py (new)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_workflow/tasks.py      (new)
packages/dcm-databricks-pipeline/resources/job_dcm_gold_dbx_workflow.yml  (new job bundle, 8 independent tasks)
packages/dcm-databricks-pipeline/pyproject.toml                           (new entry point dcm-gold-dbx-workflow)
packages/dcm-databricks-pipeline/tests/gold_dbx_workflow/*                (new test suite: conftest, bridges, builders, specs, entrypoint)
packages/dcm-databricks-pipeline/tests/test_dlt_03_gold_layer.py         (workflow tests removed, non-workflow tests kept)
packages/dcm-databricks-pipeline/tests/test_dlt_workflow.py             (workflow gold tests removed, curated/collector tests kept intact)
```

`dcm-review.sh` (package-wide, base-diff-aware) reported "(none detected vs base)" and used its committed-history diff logic — expected here since nothing is committed yet on this branch (staged-only). Gates below were run directly against the staged tree.

## Gates

| Gate | Status | Detail |
|------|--------|--------|
| pytest | **PASS** | `931 passed` (whole package, 0 failed) |
| ruff (whole package) | **PASS (with pre-existing debt)** | 242 errors total, vs **271 on `develop` baseline** (checked via `git worktree add develop`) → **net -29**, no new rule category. The 27 errors inside `tests/gold_dbx_workflow/*` (ANN001/002/003/202/204/205 on fixture stubs) are the *same categories and same style* already present across the whole `tests/` tree (e.g. `tests/gold_dbx_compute/`, `tests/gold_dbx_usage/`), and are offset by the removal of the workflow block from `test_dlt_workflow.py` / `dlt_03_gold_layer.py`. `pipelines/gold_dbx_workflow/` (non-test) has **0** ruff errors. |
| mypy (whole package) | **PASS (with pre-existing debt)** | 209 errors in 32 files, vs **220 errors in 28 files on `develop` baseline** → **net -11**. `mypy --strict pipelines/gold_dbx_workflow/` (non-test) = **0 errors** (confirmed). The only new-file errors are 4 `no-untyped-def` in `tests/gold_dbx_workflow/test_bridges.py`, same category as pre-existing `no-untyped-def` debt elsewhere in `tests/` (e.g. `tests/common/test_transforms.py`, `tests/gold_dbx_compute/test_entrypoint.py`). `pipelines/sqs_to_volume_drain.py:dbutils` errors flagged by the raw gate script are **pre-existing, unrelated file, not touched by this diff** (confirmed: no diff on that file). |
| coverage / duplication / sonar | SKIP | not requested (`coverage_min: 0`, no `--duplication`/`--sonar`) |

Conclusion on gates: raw `ruff`/`mypy` exit codes are non-zero because both tools run **package-wide** and this package carries known pre-existing debt (documented in the `[tool.mypy]` comment in `pyproject.toml` and in the prior `review-report-T002.md`). Comparing against the actual `develop` baseline shows this diff **reduces** total error count in both tools and introduces **no new rule category** — consistent with the precedent set in `review-report-T002.md` ("WARN — no new category introduced").

## Skill review (dcm-python, dcm-testing, dcm-verify)

1. **Secrets/credentials**: none found (`grep -rniE "password|secret|token|api_key|aws_access|BEGIN (RSA|PRIVATE)"` on the new package/job-yaml/tests → only a comment stating "Aucun secret"). ✅
2. **Anti-patterns (dcm-python)**:
   - No relative imports across packages (all `from __future__ import annotations`, `from typing import ...`, absolute `pipelines.*`). ✅
   - Source constraint respected: every actual read call (`spark.read.table(jobs_table/job_run_timeline_table/job_task_run_timeline_table)`) resolves to `curated_dbx_lakeflow_*` FQNs; `curated_dbx_workflow_runs`/`curated_dbx_workflow_task_runs` only appear in comments explaining the forbidden legacy source, never in an actual read path. ✅ (grep-verified)
   - Reshaping uses `groupBy` + `max_by`/`bool_and` per bridge (grain-defining aggregation), not `qualify row_number()` as the primary mechanism — the two `row_number()` usages found are for (a) latest-non-deleted job version dedup and (b) `attempt_number`/`retry_count` derivation, both explicitly allowed by the story's acceptance criteria, not grain construction. ✅
   - `status`/`trigger_type` CASE mapping present in `bridges.py` (lines ~143, 157, 271, 285, 299). ✅
   - No `__pycache__` staged. ✅
3. **Acceptance criteria (story T002) coverage** — re-verified against the code, not just the story checkboxes:
   - GROUP BY reshaping (min/max/max_by, `bool_and` guard) ✅
   - Grain `(cloud_provider, account_id, workspace_id, workflow_id, run_id[, task_id])`, `source_lz_id` deviation documented ✅
   - Status/trigger_type CASE mapping ✅
   - Lost fields = NULL, documented degraded fields ✅
   - 8 gold tables kept (builders: success_rate, duration_percentiles, duration_drift, task_failure_rate, concurrency_1min, task_health, runs, tasks) ✅
   - ruff/mypy: no new debt category (see Gates above) ✅
   - **Gate PO manuel (quickstart §3)**: still **not run** in this session — this was already flagged as outstanding in `review-report-T002.md` and remains outside the scope a commit-time code review can validate. Not a code blocker; tracked separately in `tasks.md` (T002 marked `[~]`).
4. **Scope**: both touched packages (`dcm-databricks-pipeline`, `dcm-backend`) are listed in `intake.json.packages`. The `dcm-backend` change is a documentation-only comment (verified via diff), zero behavior change. No refactor outside the workflow domain. ✅
5. **Tests**: full new suite under `tests/gold_dbx_workflow/` (conftest, bridges, builders, specs, entrypoint) mirrors the `gold_dbx_compute`/`gold_dbx_usage` test pattern; old workflow-gold tests correctly removed from `test_dlt_workflow.py`/`test_dlt_03_gold_layer.py` while collector/curated tests for `workflow` are explicitly kept intact (T003 scope, untouched). ✅
6. **Diff size**: large (net package addition + 828-line removal from `dlt_03_gold_layer.py`), but structurally a 1:1 mechanical move (8 builders mirroring 8 removed functions) plus a symmetric test suite — reviewable file-by-file, consistent with the existing `gold_dbx_compute`/`gold_dbx_usage` precedent, not an unrelated churn. 🟢 note, not a blocker.
7. **Jira story / branch name**: this branch (`dataeng/migrate_workflow_pyspark`) is not the one named in `dispatch-manifest.json` for T002 (`dataeng/013-bridge-views-regold-workflow`) — it appears to be a follow-up/rework branch continuing T002's scope with a different architecture (standalone PySpark package instead of DLT bridge views), documented by the untracked spike doc. 🟡 risk: confirm before PR whether this should merge as a continuation of T002 or be reconciled with a Jira/branch rename, so "Jira Story lists Git branch name" (T002's Before-PR checklist) stays accurate.

## Findings

- 🟢 note `packages/dcm-databricks-pipeline/pipelines/gold_dbx_workflow/*`: clean extraction, 0 mypy/ruff error in non-test source files.
- 🟡 risk `dataeng/migrate_workflow_pyspark` vs `dispatch-manifest.json` branch name for T002: reconcile Jira/branch naming before PR (see point 7 above).
- 🟡 risk T002 quickstart §3 gate (PO sign-off) still pending — non-blocking for commit, blocking for T003 teardown per `tasks.md`.

## Next

- `git commit` unblocked by this stamp (PASS).
- Before PR: run/confirm quickstart §3 gate + PO sign-off, reconcile branch naming with `dispatch-manifest.json`/Jira if this supersedes `dataeng/013-bridge-views-regold-workflow`.
