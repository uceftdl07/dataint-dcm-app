# T002 — Vues-pont DLT + re-sourcing gold + gate

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: dataeng/013-bridge-views-regold-workflow
**Jira**: [DCINT-237](https://tdf.atlassian.net/browse/DCINT-237)
**Depends on**: T001
**Work type**: technique

## Description

Créer 2 vues-pont DLT de reshaping (`_wf_runs_bridge`, `_wf_task_runs_bridge`) qui reproduisent **exactement** le schéma des anciennes `curated_dbx_workflow_runs` / `_task_runs`, alimentées par **agrégation `GROUP BY`** des curated `system.lakeflow.*` (jamais `qualify row_number()`), puis re-sourcer les 8 fonctions gold `gold_dbx_workflow_*` (`dlt.read("curated_dbx_workflow_runs")` → `dlt.read("_wf_runs_bridge")`). Inclut le **gate de validation** (comparaison ancien vs nouveau, accord PO) avant tout teardown. Collecteur + `curated_dbx_workflow_*` DLT restent **intacts**.

## Files to create/modify

- UPDATE packages/dcm-databricks-pipeline/pipelines/dlt_03_gold_layer.py — +2 vues-pont `_wf_runs_bridge` / `_wf_task_runs_bridge` (lecture `spark.read.table("it.<schema>.curated_dbx_lakeflow_*")`, mapping SQL) ; re-source les 8 gold vers les vues-pont
- UPDATE packages/dcm-databricks-pipeline/tests/ (test_dlt_workflow.py ou équivalent) — source = reshaping system tables ; assertions grain/mapping

## Acceptance Criteria

- [x] Reshaping par `GROUP BY` : `start_time = min(period_start_time)`, `end_time = max(period_end_time)` **si** `bool_and(period_end_time IS NOT NULL)` (sinon NULL), état/attributs via `max_by(col, period_start_time)` — [datamapping.md §0](../../../docs/spike/migration_from_collector_to_sys_table/datamapping.md).
- [x] Grain garanti : 1 ligne par `(cloud_provider, account_id, workspace_id, workflow_id, run_id)` (et `+ task_id`) — `quickstart.md` §2, 0 doublon ; **jamais** `qualify row_number()` comme mécanisme principal. **DEVIATION assumée** : `source_lz_id` retiré de la grain/PK/FK (colonne + FK `dim_landing_zone` supprimées) — aucune résolution `workspace_id -> LZ` fiable n'existe sur le chemin d'ingestion system tables ; `account_id` remplace ce rôle dans la grain (cohérent avec `gold_dbx_compute`).
- [x] Mapping `status` (CASE SQL §3) et `trigger_type` (CASE §4) reproduisent la sémantique collecteur ; valeurs inconnues loguées, jamais inventées.
- [x] Champs perdus = **NULL** (queue/setup/execution/cleanup/schedule_lag, `workspace_name`) ; dégradés conformes ([contracts/gold-workflow-contract.md](../contracts/gold-workflow-contract.md)) : `error_message`=`termination_code`+court, `creator_user_name`=`creator_id`, `cluster_instance_id`=`element_at(compute_ids,1)`, `run_page_url` reconstruit, `retry_count` dérivé.
- [x] Les 8 tables gold gardent nom + schéma DDL ; aucune colonne retirée (hors `source_lz_id`, cf. déviation ci-dessus — FK `dim_landing_zone` supprimée, non remplacée).
- [x] Vues nommées `_wf_*_bridge` (distinctes des anciennes tables → coexistence sans collision).
- [ ] **Gate** : `quickstart.md` §3 exécuté en dev (volumétrie/success_rate/percentiles alignés), écarts expliqués par la latence, **validation PO** des champs perdus consignée.
- [x] Aucune durée négative ; `end_time` NULL ⇒ `status='running'`.
- [x] ruff + mypy : aucune nouvelle erreur introduite (dette pré-existante du package inchangée).

## Tests

- `pytest packages/dcm-databricks-pipeline/tests/ -q` (tests DLT workflow)
- `quickstart.md` §2 (grain/reshaping) + §3 (gate comparaison)

## Out of scope

- Suppression de l'ancien flux (T003) — cette PR **ne supprime rien**.
- Backend/Frontend (T004/T005).

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass + gate quickstart §3 validé (accord PO consigné)
- [ ] No files outside `packages/dcm-databricks-pipeline`
- [ ] Diff reviewable (vues-pont + re-sourcing gold + tests)
- [ ] Sub-spec checkboxes reviewed
- [ ] Jira Story lists **Git branch** name

## Notes

- Le reshaping agrégeant vit dans le fichier gold (`dlt_03`) → conforme P12 (agrégations sur Gold, curated reste fidèle).
- Rollback trivial tant que le gate n'est pas passé : re-pointer `dlt.read` sur l'ancienne `curated_dbx_workflow_runs`.
- Vérifier que job wheel (schéma system_tables) et DLT gold visent le **même** `it.ba_data_connect_monitoring__{env}` (sinon FQN explicite dans la vue-pont).
