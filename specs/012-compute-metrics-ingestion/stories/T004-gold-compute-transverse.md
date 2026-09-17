# T004 — Gold transverse réactif: recommendations

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: dataeng/012-gold-compute-transverse
**Jira**: DCINT-224
**Depends on**: T002, T003
**Work type**: feature

> **Scope amended (2026-08-27)**: originally covered recommendations + forecast. `gold_dbx_compute_forecast_daily` was split off to **[T005](T005-gold-compute-forecast.md)** after a real job run showed `ai_forecast` requires a Pro/Serverless SQL Warehouse, incompatible with this job's generic serverless compute — a compute/architecture issue, not a recommendations defect. Everything below now describes the recommendations-only scope actually shipped in PR #219; forecast-specific content has been removed (see git history / T005 for that scope).

## Description

Extend `pipelines/gold_dbx_compute/` with the transverse reactive socle: `gold_dbx_compute_recommendations` (rule engine unifying FinOps/Rightsizing/Reliability/Governance anomalies across clusters and warehouses, cycle of life `OPEN`→`ACK`→`RESOLVED`) — FR-011.

## Files to create/modify

- UPDATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py` — add the `recommendations` spec. It does not carry the `initial_mode`/`incremental_lookback_days` fields used by T002/T003 (research.md R9 scope note): the rule engine re-evaluates against the full current state of the gold `*_daily`/`governance` tables each run (needed to correctly transition `OPEN`→`RESOLVED`).
- CREATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/recommendations.py` — rule engine per [compute_datamapping.md §4.1](../../../docs/spike/compute-metrics-definition/compute_datamapping.md): one rule per row of the reco table (efficiency `OVER`, `is_zombie`, missing auto-termination, missing tags, DBR obsolete, warehouse missing auto-stop, warehouse `OVER`, queue time threshold, failure rate threshold, spill threshold). `recommendation_id = sha2(workspace_id||object_type||object_id||category||first_seen_date)`; merge preserves `first_seen_date` while the anomaly stays `OPEN`/`ACK`, transitions to `RESOLVED` when the triggering condition no longer holds, and a later re-trigger after `RESOLVED` is a genuine new detection (new `first_seen_date`/`recommendation_id`).
- UPDATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/entrypoint.py` — register dispatch for the `recommendations` table key.
- UPDATE `packages/dcm-databricks-pipeline/resources/job_dcm_gold_dbx_compute.yml` — append `gold_recommendations` to the job graph, running **after** the cluster/warehouse tasks (`depends_on`), since it reads their output.
- CREATE `packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_recommendations.py` — asserts `recommendation_id` stability across 2 runs, `first_seen_date` preserved while `OPEN`/`ACK`, `OPEN`→`RESOLVED` transition when condition clears, NULL-safe rule predicates.

## Acceptance Criteria

- [x] Cluster with `is_zombie = true` → a `gold_dbx_compute_recommendations` row of appropriate `category` created/maintained, `first_seen_date`/`last_seen_date` updated, `status = 'OPEN'` while the condition persists (spec.md US4 scenario 1).
- [x] Previously-open recommendation whose condition no longer holds → `status` becomes `RESOLVED` (or is no longer regenerated as `OPEN`) (US4 scenario 3).
- [x] `job_dcm_gold_dbx_compute.yml` task graph ensures the recommendations task runs after cluster/warehouse tasks (`depends_on`).
- [x] At least the 4 business categories (FinOps, Rightsizing, Reliability, Governance) are represented across the seeded test data (SC-004). *(FinOps/Rightsizing/Governance from cluster rules; RELIABILITY from the warehouse `failure_rate_pct` rule)*

## Tests

- `uv run pytest -q tests/gold_dbx_compute/test_recommendations.py`
- `uv run ruff check pipelines/gold_dbx_compute/` / `uv run mypy pipelines/gold_dbx_compute/`
- Real job run against real data (`dev_local` target): `dcm_gold_dbx_compute` — 8/8 tasks SUCCESS, `gold_dbx_compute_recommendations` written with 6,443,881 rows.

## Out of scope

- Cluster/warehouse gold tables (delivered in T002/T003).
- `gold_dbx_compute_forecast_daily` / `ai_forecast` (split off to **[T005](T005-gold-compute-forecast.md)**, see scope note above).
- Backend/frontend exposure of recommendations (Epic-level "Out of scope").

## Before PR

- [x] Rebased/merged latest develop before PR (**must** rebase onto T002+T003's merged `specs.py`/`entrypoint.py`/`job_dcm_gold_dbx_compute.yml`)
- [x] Tests pass (121 passed)
- [x] No files outside `packages/dcm-databricks-pipeline`
- [x] Sub-spec checkboxes reviewed
- [x] Real job run against real data (see Tests) — replaces the full `quickstart.md` checklist as the closing criterion for this task, since that checklist originally assumed `forecast_daily` was in scope here too (now tracked on T005)

## Notes

- Closing this task no longer closes the Epic on its own — `forecast_daily` (T005) is required for that (cf. spec.md Success Criteria referencing forecasts).
- See `git log` on this branch / PR #219 for the recommendations-specific fixes applied after the initial implementation (NULL-safe rule predicates, `workspace_id` added to the merge key, `RESOLVED` rows excluded from the re-open lookup).

## Delivery — clusters + warehouses (2026-08-25)

Rebased onto `develop` (post-T003 merge, commit `203b873`) then implemented the full scope: `pipelines/gold_dbx_compute/recommendations.py` (`build_compute_recommendations`, all 10 rules of `compute_datamapping.md` §4.1 — 5 CLUSTER + 5 WAREHOUSE) and `pipelines/gold_dbx_compute/forecast.py` (`build_compute_forecast`, all 5 metrics of §4.2 — `cost_usd`/`dbu_quantity`/`cpu_util_p95_pct` clusters, `query_count`/`queue_time_p95_ms` warehouses). Both renamed from their cluster-only names (`build_cluster_recommendations`/`build_cluster_forecast`) to reflect the widened scope. Wired into `specs.py` (`RECOMMENDATIONS_SPEC`/`FORECAST_DAILY_SPEC`, `source_tables` extended to the 3 warehouse gold tables, neither with a watermark per R9 scope note), `entrypoint.py` (`_build_recommendations`, `_build_forecast_daily`), and `job_dcm_gold_dbx_compute.yml` (`gold_recommendations`/`gold_forecast_daily` `depends_on` extended to the warehouse tasks they now read).

**Rule engine dedup across object types**: `RIGHTSIZING` and `FINOPS` categories each combine a cluster rule and 1-3 warehouse rules that can co-trigger for the same category; deduplicated via `QUALIFY ROW_NUMBER() ... PARTITION BY (cloud_provider, workspace_id, object_type, object_id) ORDER BY rule_priority` (object_type included in the partition key, not just object_id, for correctness even though cluster_id/warehouse_id namespaces don't practically collide). `RELIABILITY` is warehouse-only (`failure_rate_pct` threshold) — the only source of that category, satisfying SC-004's "4 categories represented" requirement.

**Warehouse threshold constants** (`pipelines/gold_dbx_compute/specs.py`, no value fixed by `compute_datamapping.md` §4.1's generic "seuil" placeholder): `WAREHOUSE_QUEUE_TIME_P95_THRESHOLD_MS = 5000`, `WAREHOUSE_FAILURE_RATE_PCT_THRESHOLD = 5.0`, `WAREHOUSE_SPILL_QUERY_COUNT_THRESHOLD = 10`. Revisit with product/FinOps input if these defaults prove too sensitive/insensitive in practice.

**`recommendation_id` design note** (unchanged from prior pass): implemented as `sha2(object_type||object_id||category||first_seen_date)` (not the literal run date) so the hash stays stable across the whole OPEN→RESOLVED lifecycle of an anomaly — see `pipelines.gold_dbx_compute.recommendations` module docstring for the full rationale. *(Superseded below — `workspace_id` added to this hash.)*

**`source_lz_id` removed from all T004 gold tables** (unchanged from prior pass): no reliable `workspace_id -> lz_id` mapping exists today.

Gates run for this pass (package `packages/dcm-databricks-pipeline`): `uv run pytest -q tests/gold_dbx_compute/` → 128 passed; `uv run ruff check pipelines/gold_dbx_compute/ tests/gold_dbx_compute/` → clean; `databricks bundle validate -t dev` → OK. `uv run mypy` on this package hits a pre-existing repo-wide quirk ("Source file found twice under different module names"), unrelated to this change (documented in repo memory, CI has mypy disabled for this package).

## Delivery — real job run, fixes, forecast split off (2026-08-27)

First real job run against real data (`dev_local`) surfaced 3 recommendations-side defects, all found and fixed before this run: (1) `has_auto_stop = false`/`NOT dbr_is_lts_current` silently excluded every NULL row from 2 rule predicates — on real data `has_auto_stop` is NULL for the large majority of warehouses, so the "auto-stop missing" rule never fired at all; fixed with `COALESCE(x, false)`. (2) `recommendation_id`'s hash was missing `workspace_id` — `object_id` alone is not guaranteed unique cross-workspace, unlike `CLUSTER_DAILY_MERGE_KEYS`/`WAREHOUSE_DAILY_MERGE_KEYS` in T002/T003; hash is now `sha2(workspace_id||object_type||object_id||category||first_seen_date)`. (3) the `existing` state lookup read the full target table without filtering `status`, so a `RESOLVED` row could be matched again by business key and keep its original `first_seen_date` forever, contradicting the "new detection after resolution" behavior the module docstring already claimed; fixed by filtering `status IN ('OPEN', 'ACK')`.

Re-run after these fixes: job `dcm_gold_dbx_compute` (`dev_local`) — 8/9 tasks `SUCCESS` including `gold_recommendations` (`gold_dbx_compute_recommendations` written, 6,443,881 rows, `recommendation_id` bijective with its business key on the real table); `gold_forecast_daily` → `FAILED`, `[UNSUPPORTED_FEATURE.AI_FUNCTION_PREVIEW] ai_forecast is in preview and currently disabled in this environment`. Confirmed against Databricks' official `ai_forecast` docs: it requires a Pro/Serverless SQL Warehouse (V1 and V2 both), and this job's tasks run on a generic serverless `python_wheel_task` environment — structurally incompatible, unrelated to any of the 3 fixes above. `forecast_daily` split off to **T005** (own sub-spec, own branch `dataeng/012-gold-compute-forecast`) for a from-scratch redesign; `pipelines/gold_dbx_compute/forecast.py` and all forecast-specific wiring removed from this branch.

Gates after the split: `uv run pytest -q tests/gold_dbx_compute/` → 121 passed; `uv run ruff check` → clean; `databricks bundle validate -t dev_local` → OK.
