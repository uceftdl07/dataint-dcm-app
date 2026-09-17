# T001 — API exposition gold compute (clusters, warehouses, recommendations, forecast)

**Domain**: backend
**Package**: packages/dcm-backend, packages/dcm-commons
**Branch**: backend/015-compute-metrics-api
**Jira**: pending
**Depends on**: none (soft: Epic 012 gold tables)
**Work type**: feature

> **Branch** = git **branch name** only (e.g. `backend/015-compute-metrics-api`). Never a commit SHA.

## Description

Expose REST endpoints reading `gold_dbx_compute_*` Delta tables (via SQL Warehouse pool) for the Compute Metrics UI. Follow the lakeflow gold pattern (`lakeflow_jobs.py`, `lakeflow.py`): scoped LZ filter, pagination, server-side filters, empty-state when tables empty. Separate from legacy `GET /api/v1/compute` (`clusters.py`).

## Files to create/modify

- CREATE `packages/dcm-backend/app/api/routes/compute_metrics.py` — router mounted under `/api/v1/databricks/compute`
- CREATE `packages/dcm-backend/app/api/services/compute_metrics_clusters.py` — queries for cluster cost/efficiency/governance + overview aggregates + trend (`granularity=day|week|month`)
- CREATE `packages/dcm-backend/app/api/services/compute_metrics_warehouses.py` — warehouse cost/query perf + overview + trend + slow queries (soft-fail if table missing)
- CREATE `packages/dcm-backend/app/api/services/compute_metrics_recommendations.py` — list reco, KPI counts (open, savings, resolved 30d, high severity), open-count for nav badge
- CREATE `packages/dcm-backend/app/api/services/compute_metrics_forecast.py` — forecast series by `metric_name`
- UPDATE `packages/dcm-backend/app/api/routes/__init__.py` — register router
- CREATE `packages/dcm-commons/src/dcm_commons/schemas/compute_metrics.py` (or equivalent) — Pydantic response models shared with OpenAPI
- CREATE `packages/dcm-backend/tests/test_compute_metrics_*.py` — route + service tests (empty table, scope filter, pagination)

## Endpoints (minimum)

| Method | Path | Gold source | Notes |
|--------|------|-------------|-------|
| GET | `/clusters/overview` | cost + efficiency + governance + reco count | KPI aggregates |
| GET | `/clusters/cost` | `gold_dbx_compute_cluster_cost_daily` | filters: search, sku_group, sort |
| GET | `/clusters/efficiency` | `gold_dbx_compute_cluster_efficiency_daily` | filter: utilization_status, is_zombie |
| GET | `/clusters/governance` | `gold_dbx_compute_cluster_governance` | filters: severity, tags, dbr, auto-stop |
| GET | `/clusters/{cluster_id}` | join snapshot + latest daily | drawer detail |
| GET | `/clusters/{cluster_id}/cost-trend` | cost_daily | `granularity`, date range |
| GET | `/warehouses/overview` | cost + query_perf | KPI aggregates |
| GET | `/warehouses/cost` | `gold_dbx_compute_warehouse_cost_daily` | filter: warehouse_size, sort |
| GET | `/warehouses/query-performance` | `gold_dbx_compute_warehouse_query_performance_daily` | filters: failures, spill, latency threshold |
| GET | `/warehouses/slow-queries` | `warehouse_slow_queries` | **404 or `{enabled:false}` if table absent** |
| GET | `/warehouses/{warehouse_id}` | join | drawer detail |
| GET | `/warehouses/{warehouse_id}/cost-trend` | cost_daily | granularity |
| GET | `/recommendations` | `gold_dbx_compute_recommendations` | filters: object_type, category, severity |
| GET | `/recommendations/summary` | reco | KPI cards + open count |
| GET | `/forecast` | `gold_dbx_compute_forecast_daily` | `metric_name`, object scope |

Common query params (all list endpoints): `source_lz_id`, `cloud_provider`, `workspace_id`/`workspace_ids`, `period_start`, `period_end`, `page`, `page_size`.

## Acceptance Criteria

- [ ] All endpoints return HTTP 200 with `{ items: [], total: 0 }` (or equivalent) when gold tables are empty — no 500 (spec US1 scenario 2, FR-008).
- [ ] LZ scope enforced via `get_allowed_lz_ids` / `_scope_where` pattern (US1 scenario 3, NFR-002).
- [ ] Cluster cost list supports server-side `search`, `sku_group`, `sort=cost_desc|name` (US1 scenario 4, FR-004).
- [ ] Efficiency supports `utilization_status` including `ZOMBIE` via `is_zombie=true` filter (maquette Clusters §8).
- [ ] Cost trend endpoint aggregates with `date_trunc` for week/month — not raw daily dump for client re-aggregation (FR-005).
- [ ] Recommendations summary exposes `open_count` for nav badge (FR-007).
- [ ] Forecast endpoint returns all 5 V1 metrics: `cost_usd`, `dbu_quantity`, `cpu_util_p95_pct`, `query_count`, `queue_time_p95_ms` (SC-006).
- [ ] Slow-queries endpoint gracefully disabled when table missing (spec Clarifications — hide sub-view).
- [ ] OpenAPI / schema types exported for frontend code generation or manual TS types.
- [ ] Pagination capped (`page_size` max ~200, NFR-001).

## Tests

- `cd packages/dcm-backend && uv run pytest -q tests/test_compute_metrics_*.py`
- `uv run ruff check app/api/routes/compute_metrics.py app/api/services/compute_metrics_*.py`

## Out of scope

- Gold pipeline / DataEng (Epic 012).
- Removing legacy `GET /api/v1/compute`.
- DevOps API GW route registration (unless required by env — document in PR if needed).
- Writing to recommendations (read-only V1).

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside backend + dcm-commons scope
- [ ] Diff stays reviewable (prefer fewer changed files / one concern)
- [ ] Sub-spec checkboxes reviewed
- [ ] Jira Story lists **Git branch** name (not a commit SHA)

## Notes

- Mirror patterns from `packages/dcm-backend/app/api/services/lakeflow_jobs.py` (qualified_table, pagination, cache optional).
- Gold column names: `specs/012-compute-metrics-ingestion/contracts/gold-tables-contract.md` + spike `docs/spike/compute-metrics-definition/`.
- Cluster gold tables omit `source_lz_id` — scope via `workspace_id` mapping or global read per existing Databricks patterns; confirm with T002 during integration.
- Default filter thresholds (failure_rate ≥ 1%, spill > 0): use query params with maquette defaults until PO validates (spec `[NEEDS CLARIFICATION]`).
