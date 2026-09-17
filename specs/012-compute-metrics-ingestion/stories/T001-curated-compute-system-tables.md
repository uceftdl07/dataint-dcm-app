# T001 — Curated system tables compute (warehouses, warehouse_events, node_types)

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: dataeng/012-curated-compute-system-tables
**Jira**: pending
**Depends on**: none
**Work type**: feature

## Description

Extend the existing `pipelines/system_tables/` plugin with 3 new `IngestionSpec` entries so `system.compute.warehouses`, `system.compute.warehouse_events`, and `system.compute.node_types` are ingested into idempotent curated Delta tables, following exactly the same pattern already used for `curated_dbx_compute_clusters`/`curated_dbx_compute_node_timeline` (FR-001, FR-002, FR-003). No new ingestion mechanism — reuse `pipelines/common/` (readers, writers, transforms, incremental) as-is.

## Files to create/modify

- UPDATE `packages/dcm-databricks-pipeline/pipelines/system_tables/specs.py`
  - Add `CURATED_COMPUTE_WAREHOUSES = "curated_dbx_compute_warehouses"`, `CURATED_COMPUTE_WAREHOUSE_EVENTS = "curated_dbx_compute_warehouse_events"`, `CURATED_COMPUTE_NODE_TYPES = "curated_dbx_compute_node_types"` + matching `SOURCE_*` constants.
  - Add `WAREHOUSES_MERGE_KEYS = ("cloud_provider", "account_id", "workspace_id", "warehouse_id", "change_time")`, `WAREHOUSE_EVENTS_MERGE_KEYS = ("cloud_provider", "account_id", "workspace_id", "warehouse_id", "event_time", "event_type")`, `NODE_TYPES_MERGE_KEYS = ("cloud_provider", "account_id", "node_type")`.
  - Add `WAREHOUSES_SPEC = IngestionSpec(source_table=SOURCE_COMPUTE_WAREHOUSES, curated_table=CURATED_COMPUTE_WAREHOUSES, merge_keys=WAREHOUSES_MERGE_KEYS, watermark_column="change_time", initial_lookback_days=INITIAL_BACKFILL_DAYS, azure_fetch_batch_size=AZURE_BATCH_NESTED)`.
  - Add `WAREHOUSE_EVENTS_SPEC = IngestionSpec(source_table=SOURCE_COMPUTE_WAREHOUSE_EVENTS, curated_table=CURATED_COMPUTE_WAREHOUSE_EVENTS, merge_keys=WAREHOUSE_EVENTS_MERGE_KEYS, watermark_column="event_time", initial_lookback_days=INITIAL_BACKFILL_DAYS, azure_fetch_batch_size=AZURE_BATCH_NARROW)` — **pas de `partition_columns`** : `system.compute.warehouse_events` n'expose nativement aucune colonne date (seulement `event_time`) ; curated reste fidèle source stricte, aucune colonne dérivée/inventée (contrairement à `usage_date`/`event_date` qui existent nativement sur `billing.usage`/`access.audit`).
  - Add `NODE_TYPES_SPEC = IngestionSpec(source_table=SOURCE_COMPUTE_NODE_TYPES, curated_table=CURATED_COMPUTE_NODE_TYPES, merge_keys=NODE_TYPES_MERGE_KEYS)` (no watermark — full load, small referential table; curated stays strictly source-faithful, `gpu_count` kept as-is (NULL when absent in source) — the `coalesce(gpu_count, 0)` normalization is a gold-layer business rule, out of scope for T001, to be added with T002+ once `pipelines/gold_dbx_compute/` is scaffolded).
  - Add 3 entries to the `SPECS` registry dict (`"compute_warehouses"`, `"compute_warehouse_events"`, `"compute_node_types"`) — `SPEC_KEYS` derives automatically.
- UPDATE `packages/dcm-databricks-pipeline/resources/job_dcm_system_tables.yml` — add the 3 new keys to `for_each_task.inputs` (must stay aligned with `SPEC_KEYS`, per the existing guard-rail in `entrypoint.py::_selected_specs`).
- UPDATE `packages/dcm-databricks-pipeline/tests/system_tables/test_specs.py` — add assertions mirroring existing ones (e.g. `assert WAREHOUSES_SPEC.curated_table == "curated_dbx_compute_warehouses"`, merge keys, watermark).
- No changes needed to `ingest.py` or `entrypoint.py` (fully generic, spec-driven).

## Acceptance Criteria

- [x] `curated_dbx_compute_warehouses` populated with one row per `(cloud_provider, account_id, workspace_id, warehouse_id, change_time)`, `delete_time` NULL for active warehouses (spec.md US1 scenario 1).
- [x] `curated_dbx_compute_warehouse_events` appends new events without duplicating already-ingested ones; strictly source-faithful (no `event_date` — the source table exposes no dedicated date column, only `event_time`; no partitioning declared) (US1 scenario 2).
- [ ] `curated_dbx_compute_node_types` referential populated, `gpu_count` kept raw (NULL when absent in source) — curated stays strictly source-faithful; defaulting to 0 is a gold-layer transform, deferred to a later task (T002+, `pipelines/gold_dbx_compute/`), not T001 (US1 scenario 3).
- [x] Re-running the job on the same window produces 0 duplicate rows (SC-003, FR-014).
- [x] `for_each_task.inputs` in `job_dcm_system_tables.yml` includes the 3 new keys and matches `SPEC_KEYS` exactly (no drift).
- [x] Azure + AWS both populate their rows (`cloud_provider` discriminates) — FR-013.
- [x] Initial backfill covers 30 days (`initial_lookback_days=INITIAL_BACKFILL_DAYS`) — FR-017.

## Tests

- `uv run pytest -q tests/system_tables/test_specs.py`
- `uv run ruff check pipelines/system_tables/` / `uv run mypy pipelines/system_tables/`

## Out of scope

- Gold layer computation (T002/T003/T004).
- Any Lakebase sync of these curated tables (not required — internal to the medallion).

## Before PR

- [ ] Rebased/merged latest develop before PR
- [x] Tests pass (`uv run pytest -q tests/system_tables/`)
- [x] No files outside `packages/dcm-databricks-pipeline`
- [x] Sub-spec checkboxes reviewed

## Notes

- Reuses `INITIAL_BACKFILL_DAYS = 30` (already defined in `specs.py`) — matches spec.md Clarification Q5 exactly, no new constant needed.
- See [research.md R6](../research.md) and [data-model.md](../data-model.md) for the full grain/key rationale.

### Deviations & known limitations (post-T002 fix)

- **Ajout a posteriori de `curated_dbx_job_task_run_timeline`** (`system.lakeflow.job_task_run_timeline`), fichier proprietaire T001 (`system_tables/specs.py`). Necessaire pour corriger `gold_dbx_compute_cluster_efficiency_daily` (T002) : `idle_pct`/`active_hours`/`is_zombie` reposaient sur `curated_dbx_query_history`, verifie en prod comme ne tracant QUE les requetes sur SQL Warehouses (jamais sur des clusters classiques). Meme pattern que les autres tables d'evenements volumineuses (`watermark_column="period_start_time"`, `initial_lookback_days=INITIAL_BACKFILL_DAYS`, `azure_fetch_batch_size=AZURE_BATCH_NESTED` — colonnes `compute`/`compute_ids`/`task_parameters` imbriquees). Grain reel confirme en prod (DESCRIBE + echantillon, warehouse `fcc5098720414937`) : plusieurs lignes par tache (une par periode d'etat/compute, jusqu'a 85 lignes/tache observees sur des jobs continus/streaming) ; `run_id` sur cette table est deja l'ID du run de TACHE (nom trompeur, a ne pas confondre avec `run_id` de `job_run_timeline` qui designe le run de JOB). Cle de merge retenue : `(cloud_provider, account_id, workspace_id, job_id, run_id, task_key, period_start_time)`. `compute` (array<struct<type,cluster_id,warehouse_id>>) ingere tel quel (pas d'explode en curated, fidelite source stricte) ; son exploitation (chevauchement de periode, filtrage `cluster_id`) est un traitement GOLD (`pipelines/gold_dbx_compute/cluster_metrics.py`). Voir aussi Notes de [T002-gold-compute-clusters.md](T002-gold-compute-clusters.md).
