# DCM Review Report

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/012-gold-compute-forecast` (base: `develop`, task: T005)
**Mode**: `--commit` (staged diff)
**Stack**: python (module `pipelines`)
**Verdict**: **PASS**

## Changed files (staged)

```
.gitignore
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_cost_daily.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_efficiency_daily.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_governance.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_reliability_daily.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/entrypoint.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/forecast.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/job_cluster_cost_daily.py   (new)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/sql_helpers.py
packages/dcm-databricks-pipeline/resources/job_dcm_gold_dbx_compute.yml
packages/dcm-databricks-pipeline/resources/job_dcm_gold_forecast.yml
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_cluster_cost_daily.py
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_cluster_efficiency_daily.py
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_cluster_governance.py
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_cluster_reliability_daily.py
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_forecast.py
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_job_cluster_cost_daily.py  (new)
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_specs.py
specs/012-compute-metrics-ingestion/spec.md
specs/012-compute-metrics-ingestion/stories/T005-gold-compute-forecast.md
specs/012-compute-metrics-ingestion/tasks.md
```

> **Re-review note**: this diff supersedes the prior stamped review at this same
> report path — the staged content changed (spec docs amended) after that stamp
> was written, invalidating it (`staged_hash` mismatch). Package code is
> unchanged since then; gates were re-run to confirm.

## Gates

`dcm-review.sh`'s bare `ruff`/`pytest` are not on `PATH` in this shell (uv-managed venv) — re-run manually via `uv run`, scoped to the changed area, per `dcm-verify` skill.

| Gate | Status | Detail |
|------|--------|--------|
| ruff | **PASS** | `uv run ruff check .` → 278 pre-existing errors, **0** under `pipelines/gold_dbx_compute/**` (all in unrelated `tests/test_dlt_workflow.py`, not touched by this diff) |
| mypy | SKIP | package declares no mypy config (per `dcm-verify` gate matrix, expected for `dcm-databricks-pipeline`) |
| pytest | **PASS** | `uv run pytest -q tests/gold_dbx_compute` → 164 passed; full package `uv run pytest -q` → 278 passed |

## Skill review (dcm-python / dcm-testing / dcm-verify)

1. **Secrets** — none in the diff (checked for password/secret/token/key patterns; only match is the unrelated `notification_email` job param).
2. **Scope** — all files under `packages/dcm-databricks-pipeline/` (dataeng package scope, matches intake). No cross-LZ calls introduced.
3. **Acceptance criteria (T005 sub-spec)**:
   - ✅ `object_type='JOB'` projection added, sourced from the new `gold_dbx_compute_job_cluster_cost_daily` rollup.
   - ✅ `FORECAST_MERGE_KEYS` includes `workspace_id` (cross-workspace collision guard, carried over as required).
   - ✅ `observed` bounded by `observed_lower_bound` before every `ai_forecast` call (ephemeral-object backfill guard, carried over).
   - ✅ **Resolved in this diff** — the sub-spec's original ask (native `.sql` file + `sql_task` job) is superseded by an explicit, documented decision box in [stories/T005-gold-compute-forecast.md](stories/T005-gold-compute-forecast.md) and `spec.md`: keep the module's standard `render_*`/`build_*`/`merge_into_table` pattern via the Statement Execution API rather than a one-off `sql_task`. Description/Files/Acceptance Criteria/Tests sections amended accordingly (AC checkbox now `[x]`). This is a legitimate architecture decision, not an unaddressed gap.
4. **Undocumented scope addition** — ✅ **Resolved in this diff** — `job_cluster_cost_daily.py`/`GOLD_JOB_CLUSTER_COST_DAILY` is now documented in the sub-spec's Description ("Scope extended" note), Files to create/modify, Acceptance Criteria, Tests, and Out-of-scope/Notes sections, matching what was actually delivered. Validated against real data with tracked findings (`validation-findings-job-cluster-cost-daily.md`, F001–F007, all triaged/accepted or fixed).
5. **Bug fixes carried to sibling builders** — `change_time <= period_start` → `change_time < period_start + INTERVAL 1 DAY` (as-of join midnight-truncation bug, F005) and the new `cluster_type <> 'OTHER'` filter are applied consistently across all 4 cluster builders (cost/efficiency/governance/reliability) — matches the validation registry, tests updated accordingly (164 passed).
6. **Tests** — new `test_job_cluster_cost_daily.py` (149 lines) and updated tests for every touched builder; no behavior change left uncovered.
7. **Small PR** — diff is broad (9 pipeline files + resources + tests + 3 spec docs) but each file change is a small, coherent piece of the same T005 slice (JOB grain forecasting, design decision writeback) or a documented cross-cutting bugfix — acceptable, not off-topic churn.

## Findings

- 🟢 Bugfixes (F004/F005/F006 mitigation via `cluster_type <> 'OTHER'`) consistently carried across the 4 sibling cluster builders, matches validation registry.
- 🟢 Both prior findings (native `sql_task` redesign, undocumented `job_cluster_cost_daily` scope) are resolved in this diff via sub-spec/spec.md amendments — no open blockers or risks remain for this commit.

## Next

- Commit unblocked (PASS, no blocker).
- Before PR: remaining open AC items in the T005 sub-spec (real end-to-end job run against a real Pro/Serverless SQL Warehouse, `job_cluster_cost_daily` correctness verification, double-count check) still need to be ticked off — tracked there, not blocking this commit.
