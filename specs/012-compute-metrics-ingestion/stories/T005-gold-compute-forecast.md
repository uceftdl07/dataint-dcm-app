# T005 — Gold transverse prédictif: forecast_daily (python_wheel_task, Statement Execution API)

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: dataeng/012-gold-compute-forecast
**Jira**: pending
**Depends on**: T002, T003
**Work type**: feature

> **Split off T004 (2026-08-27)**: `gold_dbx_compute_forecast_daily` was originally part of T004 together with `gold_dbx_compute_recommendations`. A real job run against real data (branch `dataeng/012-gold-compute-transverse`) showed `ai_forecast` requires a Pro/Serverless SQL Warehouse and fails with `[UNSUPPORTED_FEATURE.AI_FUNCTION_PREVIEW] ai_forecast is in preview and currently disabled in this environment` when run from the job's generic serverless `python_wheel_task` compute — confirmed against Databricks' official `ai_forecast` docs (Requirements section, V1 and V2 both). This is a compute/architecture problem, not a content bug: recommendations validated cleanly on the same job run and was kept on T004/PR #219; `forecast_daily` needs a different execution model, tracked here.

> **Scope extended (2026-08-31)**: implementing the `JOB` object-type projection surfaced that raw `cluster_type = 'JOB'` clusters (ephemeral, ~1 day of history each) produce a degenerate series for `ai_forecast` at the cluster grain. Fix requires a new upstream gold table, `gold_dbx_compute_job_cluster_cost_daily` (rollup of `cluster_cost_daily` by stable `job_id`), added as a task in the existing daily `dcm_gold_dbx_compute` job (`depends_on: gold_cluster_cost_daily`). Folded into T005 rather than split into its own task/branch/PR: it exists solely to make T005's own `JOB`-grain forecast meaningful, not an independent deliverable — same branch, same PR.

## Description

> **Amended (2026-08-31)**: the original plan below (native `sql_task`) was superseded during implementation — see the decision note right after this box.

~~Deliver `gold_dbx_compute_forecast_daily` as a **native SQL Warehouse flow**: a `sql_task` executing `MERGE INTO ... SELECT * FROM ai_forecast(...)` directly on a Pro/Serverless SQL Warehouse — no Python round-trip, no Statement Execution API glue, no client-side row fetch/coercion.~~ **Decision**: stay on the same pattern as every other gold builder in this module (`render_*_query` pure function + `build_*` + `pipelines.common.writers.merge_into_table`) instead of a one-off `sql_task`/native-SQL flow. `forecast.py` keeps a `python_wheel_task`: `render_forecast_query` builds the `ai_forecast` SQL text (pure, no execution), `build_compute_forecast` runs it via the Statement Execution API (`databricks.sdk`, `disposition=EXTERNAL_LINKS` to avoid the 25 MiB `INLINE` limit) against a Pro/Serverless `warehouse_id`, then reconstructs a Spark DataFrame so it flows through `merge_into_table` unchanged, like `cluster_cost_daily`/`cluster_efficiency_daily`/etc. Rationale: a native `sql_task` would be the only builder in the package not following the `render_*`/`build_*`/`merge_into_table` shape — one execution model to maintain, not two — and Statement Execution + `EXTERNAL_LINKS` already proved reliable on real data (T004 job run).

`ai_forecast` projects across clusters, jobs (rollup of ephemeral `JOB`-type clusters, see `job_cluster_cost_daily`) and warehouses (`cost_usd`, `dbu_quantity`, `cpu_util_p95_pct` for clusters; `cost_usd`, `dbu_quantity` for jobs; `cost_usd`, `dbu_quantity`, `query_count`, `queue_time_p95_ms` for warehouses) per [compute_datamapping.md §4.2](../../../docs/spike/compute-metrics-definition/compute_datamapping.md) — FR-012.

Delivered as its **own job** (`resources/job_dcm_gold_forecast.yml`), decoupled from the daily `dcm_gold_dbx_compute` job, on a **weekly** schedule (Monday 06:00 Europe/Paris, after the daily gold run at 05:00) — the forecast horizon is 7 days, recomputing daily would be redundant $ cost for no added value. Decision locked in.

## SQL content carried over from the first attempt

The first attempt already used the Statement Execution API from inside the `python_wheel_task` and turned out to be the kept design (see above, not just a discarded reference). SQL points validated on real data:

- `value_col => array('cost_usd', 'dbu_quantity')` (and similarly for the warehouse query-performance metrics) — the comma-separated string form (`'cost_usd,dbu_quantity'`) is read by `ai_forecast` as a single literal column name on this warehouse and fails with `PYTHON_TVF_REFERENCED_COLUMN_NOT_FOUND`.
- `observed` filtered to `period_start >= today - FORECAST_OBSERVED_LOOKBACK_DAYS` (14 days) before the `ai_forecast` call — without this, `ai_forecast` backfills a projection from the day after an object's *last real observation* to the horizon, regardless of how long ago that was; since 99%+ of `cluster_id`s are ephemeral (1 day of history, often stale by months/years), this produced years of spurious "forecast" rows per dead cluster. `FORECAST_HORIZON_DAYS` was also tightened from 14 to 7 alongside this fix.
- `workspace_id` added to `FORECAST_MERGE_KEYS` — `object_id` (`cluster_id`/`warehouse_id`) is not guaranteed unique cross-workspace, same reasoning as `CLUSTER_DAILY_MERGE_KEYS`/`WAREHOUSE_DAILY_MERGE_KEYS` in T002/T003.

## Files to create/modify

- `pipelines/gold_dbx_compute/forecast.py` — `render_forecast_query` (pure SQL text) + `build_compute_forecast` (Statement Execution API call, DataFrame reconstruction), same shape as the other builders in the package.
- `resources/job_dcm_gold_forecast.yml` — new job, `python_wheel_task` (entry point `dcm-gold-dbx-compute`, `table=forecast_daily`), weekly schedule, `warehouse_id` variable (Pro/Serverless SQL Warehouse lookup).
- `_generated_at` stamped Spark-side (`current_timestamp()`) after the DataFrame is rebuilt from the Statement Execution rows, then written via the existing `merge_into_table` — no SQL-side schema evolution/MERGE to reimplement, it's inherited from the standard path.
- Test strategy settled: `render_forecast_query` is a pure function, tests assert directly on the generated SQL text (`test_forecast.py`), same principle as every other builder's `FakeSpark`-free pure-SQL tests in this package — no `.sql` file, no integration-only testing needed for this layer.
- `pipelines/gold_dbx_compute/job_cluster_cost_daily.py` — new builder, `gold_dbx_compute_job_cluster_cost_daily` (rollup of `cluster_cost_daily` by `job_id`, via `curated_dbx_lakeflow_job_task_run_timeline`'s `cluster_id -> job_id` lineage), the source table for T005's `JOB`-grain forecast (see Scope extended note above).
- `pipelines/gold_dbx_compute/specs.py` — `GOLD_JOB_CLUSTER_COST_DAILY`, `JOB_CLUSTER_DAILY_MERGE_KEYS`, `JOB_CLUSTER_COST_DAILY_SPEC` (table/column comments, merge keys).
- `pipelines/gold_dbx_compute/entrypoint.py` — `job_cluster_cost_daily` wired into the table dispatch, same pattern as the other gold tables.
- `resources/job_dcm_gold_dbx_compute.yml` — new task `gold_job_cluster_cost_daily` in the existing **daily** job, `depends_on: gold_cluster_cost_daily` (not the weekly forecast job — it runs on the same cadence as its source table).

## Acceptance Criteria

- [ ] Sufficient gold history → `gold_dbx_compute_forecast_daily` produces a projection for at least `cost_usd` and `cpu_util_p95_pct`, `method = 'ai_forecast'` (spec.md US4 scenario 2).
- [ ] The `python_wheel_task` executes end-to-end (Statement Execution API against a real Pro/Serverless SQL Warehouse, `EXTERNAL_LINKS` disposition) on real data, without the `AI_FUNCTION_PREVIEW`/`Inline byte limit` failures hit during the T004 attempt.
- [ ] Ephemeral/dead objects (no recent activity) do not generate spurious multi-year forecast backfills (carry over the `observed_lower_bound` fix, see above).
- [ ] `recommendation`-style cross-workspace collision is not possible on `FORECAST_MERGE_KEYS` (carry over `workspace_id`, see above).
- [x] Decision made and documented: separate weekly job (`dcm_gold_forecast`, Monday 06:00 Europe/Paris), `python_wheel_task` pattern consistent with the rest of the module (see Description).
- [ ] `gold_dbx_compute_job_cluster_cost_daily` rolls up `cluster_cost_daily` correctly by `job_id` (not by ephemeral `cluster_id`), with `job_name` resolved as-of `period_start` — enables a non-degenerate `JOB`-grain series for `ai_forecast`.
- [ ] `job_cluster_cost_daily` never double-counts against `cluster_cost_daily` (rollup of the same billing rows, not an independent cost source) — verify no downstream consumer sums both.

## Tests

- `render_forecast_query` (pure SQL text) unit-tested by assertion on the generated text — `test_forecast.py`, same principle as the other builders' pure-SQL tests, no `FakeSpark` needed for this layer.
- `build_compute_forecast`/Statement Execution API path: real execution against a SQL Warehouse on seeded/real data (the Statement Execution + DataFrame-reconstruction glue itself isn't unit-testable).
- `build_job_cluster_cost_daily` (`job_cluster_cost_daily.py`): standard `FakeSpark`/`build_*` unit tests, same pattern as `cluster_cost_daily`/`cluster_efficiency_daily` (`test_job_cluster_cost_daily.py`).
- `databricks bundle validate -t dev_local` on both the new forecast job resource and the amended `dcm_gold_dbx_compute` job resource (new task).
- Full `quickstart.md` end-to-end checklist (all Success Criteria SC-001 to SC-008) — closes the Epic once this and T004 are both done.

## Out of scope

- `gold_dbx_compute_recommendations` (delivered in T004/PR #219).
- Backend/frontend exposure of forecasts (Epic-level "Out of scope").
- Retroactive `JOB`-grain cost history beyond `job_task_run_timeline`'s own retention (~1 year) — see limitation documented in `job_cluster_cost_daily.py`.

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside `packages/dcm-databricks-pipeline`
- [ ] Diff stays reviewable (prefer fewer changed files / one concern)
- [ ] Sub-spec checkboxes reviewed
- [ ] Jira Story lists **Git branch** name (not a commit SHA)
- [ ] Full `quickstart.md` checklist run and green — this closes the Epic

## Notes

- Depends on the same T002/T003 gold tables as T004, but has no cross-read with T004's `gold_dbx_compute_recommendations` — independent of T004, can merge before or after it.
- See T004's sub-spec ("Delivery — real job run, fixes, forecast split off") for the full incident history and the official Databricks `ai_forecast` doc citation that grounds the compute-incompatibility finding.
- `gold_dbx_compute_job_cluster_cost_daily` touches `resources/job_dcm_gold_dbx_compute.yml` (daily job), not `job_dcm_gold_forecast.yml` (weekly) — two job resources change in this PR, by design (one prerequisite table on the daily cadence, one consumer on the weekly cadence).
