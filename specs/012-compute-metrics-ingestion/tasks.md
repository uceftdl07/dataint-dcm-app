# Tasks: Ingestion Compute Metrics (Curated + Gold)

**Input**: Design documents from `/specs/012-compute-metrics-ingestion/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: Not explicitly requested as TDD in spec.md, but P1 (constitution) requires pytest/chispa tests land with each task — included per story.

**Organization**: DCM dispatch mode = **granular within a single domain (DataEng)**, matching `intake.json.ticket_plan` (4 Stories, 1 task = 1 Jira Story = 1 branch = 1 sub-spec). Each task below maps 1:1 to a User Story in [spec.md](./spec.md).

## Format: `[ID] [P?] DataEng Description → sub-spec`

- **[P]**: Can run in parallel (different files, no dependencies) — none here, see Dependencies (shared registry files force a sequential merge order even where implementation could start in parallel).
- All tasks are **DataEng**, package `packages/dcm-databricks-pipeline`.

## Tasks

- [x] T001 DataEng Curated system tables compute (warehouses, warehouse_events, node_types) → [stories/T001-curated-compute-system-tables.md](stories/T001-curated-compute-system-tables.md)
- [x] T002 DataEng Gold clusters — cost, efficiency/rightsizing, reliability, governance daily → [stories/T002-gold-compute-clusters.md](stories/T002-gold-compute-clusters.md)
- [x] T003 DataEng Gold SQL warehouses — cost, utilization/rightsizing, query performance daily → [stories/T003-gold-warehouses.md](stories/T003-gold-warehouses.md)
- [~] T004 DataEng Gold transverse réactif — recommendations (rule engine, clusters + warehouses, 10/10 rules) → [stories/T004-gold-compute-transverse.md](stories/T004-gold-compute-transverse.md) (validated end-to-end on real data — job run 8/8 tasks SUCCESS, `gold_dbx_compute_recommendations` written with 6,443,881 rows; PR #219 open. `forecast_daily` split off to T005, see Notes below)
- [ ] T005 DataEng Gold transverse prédictif — forecast_daily (`ai_forecast` via `python_wheel_task` + Statement Execution API, plus `job_cluster_cost_daily` rollup) → [stories/T005-gold-compute-forecast.md](stories/T005-gold-compute-forecast.md) (split off T004 after a real job run showed `ai_forecast` requires a Pro/Serverless SQL Warehouse, structurally incompatible with the job's generic serverless `python_wheel_task` compute — kept the module's standard `render_*`/`build_*`/`merge_into_table` pattern via the Statement Execution API rather than a one-off native `sql_task`; scope extended to `gold_dbx_compute_job_cluster_cost_daily`, a prerequisite for the `JOB`-grain forecast, in progress on `dataeng/012-gold-compute-forecast`)

## Dependencies & Execution Order

- **T001** — no dependency. Extends the existing `pipelines/system_tables/` plugin (adds 3 `IngestionSpec`). Blocks T002 and T003 (both read `curated_dbx_compute_node_types` / `curated_dbx_compute_warehouses` / `curated_dbx_compute_warehouse_events`).
- **T002** — depends on T001. Creates the **new** `pipelines/gold_dbx_compute/` plugin scaffolding (`__init__.py`, `specs.py` registry, `entrypoint.py`, `resources/job_dcm_gold_dbx_compute.yml`) alongside the cluster gold tables. T003 and T004 extend this scaffolding rather than recreate it.
- **T003** — depends on T001 and T002 (reuses the scaffolding T002 creates: `specs.py`, `entrypoint.py`, job resource). Not parallel-safe with T002 on those shared files (see `merge-strategy.md`) even though the business logic (`warehouse_metrics.py`) is an independent file.
- **T004** — depends on T002 and T003 (reads their gold `*_daily`/`governance` outputs to compute recommendations — cf. spec.md Story 4 "Why this priority"). Originally scoped to recommendations + forecast; `forecast_daily` split off to **T005** (see below) after a real job run revealed a compute incompatibility unrelated to the recommendations logic.
- **T005** — depends on T002 and T003 (same sources as T004, `forecast_daily` reads `gold_dbx_compute_cluster_cost_daily`/`_efficiency_daily` and `gold_dbx_compute_warehouse_query_performance_daily`), not on T004 (no cross-read between the two transverse tables). `ai_forecast` requires a Pro/Serverless SQL Warehouse — incompatible with the generic serverless `python_wheel_task` environment the rest of `dcm_gold_dbx_compute` runs on, so `forecast_daily` runs via the Statement Execution API from a `python_wheel_task` (same `render_*`/`build_*`/`merge_into_table` pattern as every other builder, not a one-off `sql_task`), as its own **separate weekly job**. Scope extended (2026-08-31) to also add `gold_dbx_compute_job_cluster_cost_daily` (rollup of `cluster_cost_daily` by `job_id`) as a **task inside the existing daily `dcm_gold_dbx_compute` job** — a prerequisite table for T005's own `JOB`-grain forecast, not an independent deliverable.

Recommended merge order: **T001 → T002 → T003 → T004 → T005** (sequential PRs to `develop`, per `merge-strategy.md`; T004 and T005 are independent of each other and could merge in either order once both are ready).

## Implementation Strategy

### MVP First (Story 1 + Story 2)

1. T001 — curated socle extended (blocking).
2. T002 — first gold slice (Clusters) delivers standalone FinOps/rightsizing/reliability/governance value — natural MVP checkpoint.
3. **STOP and VALIDATE**: run `quickstart.md` §1-3 against T001+T002 only, confirm SC-001/SC-002 (partial, clusters only)/SC-003/SC-006/SC-007/SC-008.

### Incremental Delivery

1. T001 → T002 (MVP: Clusters gold) → T003 (Warehouses gold) → T004 (recommendations) / T005 (forecast, independent of T004, can proceed in parallel once T002+T003 are merged).
2. Each task is independently testable per its sub-spec's Acceptance Criteria and `quickstart.md`.

## Notes

- No Setup/Foundational phase beyond T001: this Epic extends an existing, already-scaffolded package (`packages/dcm-databricks-pipeline`) — no new project initialization needed.
- Polish/cross-cutting (ruff/mypy zero-warning gate, `quickstart.md` full run, docs) is folded into each task's "Before PR" checklist (see each `stories/T00X-*.md`), not a separate phase, per DCM one-task-granularity convention.
- See [merge-strategy.md](merge-strategy.md) for shared-file conflict rules (`pipelines/gold_dbx_compute/specs.py`, `entrypoint.py`, `resources/job_dcm_gold_dbx_compute.yml` are touched by T002, T003, T004, **and T005** — see amendment below; T005 also adds its own job resource file `job_dcm_gold_forecast.yml` for the weekly forecast job).
- **T004/T005 split (amended 2026-08-27)**: T004 was originally one task covering both `gold_dbx_compute_recommendations` and `gold_dbx_compute_forecast_daily`. A real job run against real data (branch `dataeng/012-gold-compute-transverse`) showed `ai_forecast` requires a Pro/Serverless SQL Warehouse and fails with `[UNSUPPORTED_FEATURE.AI_FUNCTION_PREVIEW] ... disabled in this environment` on the generic serverless `python_wheel_task` compute the rest of the job uses — confirmed against Databricks' official `ai_forecast` docs (Requirements, V1 and V2). This is a compute/architecture issue orthogonal to the recommendations rule engine, which validated cleanly end-to-end. `forecast_daily` was split out into **T005**, as its own weekly-scheduled job. See [stories/T005-gold-compute-forecast.md](stories/T005-gold-compute-forecast.md).
- **T005 design + scope amendment (2026-08-31)**: (1) kept the module's standard `render_*`/`build_*`/`merge_into_table` pattern for `forecast_daily` via the Statement Execution API from a `python_wheel_task`, instead of the originally-planned native `sql_task` — avoids a second execution model in the package, and the Statement Execution + `EXTERNAL_LINKS` path already proved reliable on real data during the T004 job run. (2) extended T005's scope to `gold_dbx_compute_job_cluster_cost_daily` (new task in the **daily** `dcm_gold_dbx_compute` job, `depends_on: gold_cluster_cost_daily`) — a rollup of ephemeral `cluster_type = 'JOB'` clusters by stable `job_id`, needed because raw JOB clusters have too little history for a meaningful `ai_forecast` series at the cluster grain. Folded into T005 (same branch/PR) rather than a separate task, since it exists only to serve T005's own `JOB`-grain forecast. See [stories/T005-gold-compute-forecast.md](stories/T005-gold-compute-forecast.md).
