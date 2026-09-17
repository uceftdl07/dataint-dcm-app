# T001 — Curated fidèle `system.lakeflow.*` (3 IngestionSpec)

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: dataeng/013-curated-lakeflow-system-tables
**Jira**: [DCINT-238](https://tdf.atlassian.net/browse/DCINT-238)
**Depends on**: none
**Work type**: technique

## Description

Étendre le socle d'ingestion `pipelines/system_tables/` avec 3 nouvelles tables curated **fidèles source** (aucune transformation, MERGE idempotent, watermark) lisant `system.lakeflow.jobs`, `system.lakeflow.job_run_timeline` et `system.lakeflow.job_task_run_timeline`. PR **additive** (zéro risque) : elle ne touche ni le gold, ni le collecteur. Réutilise `merge_into_curated`, `IngestionSpec`, l'enveloppe socle et le backfill 30 j existants.

## Files to create/modify

- UPDATE packages/dcm-databricks-pipeline/pipelines/system_tables/specs.py — 3 `IngestionSpec` (`curated_dbx_lakeflow_jobs`, `curated_dbx_lakeflow_job_run_timeline`, `curated_dbx_lakeflow_job_task_run_timeline`) + clés merge + watermark + entrées `SPECS`/`SPEC_KEYS`
- UPDATE packages/dcm-databricks-pipeline/resources/job_dcm_system_tables.yml — +3 clés dans `for_each.inputs` (alignées `SPEC_KEYS`)
- UPDATE packages/dcm-databricks-pipeline/tests/system_tables/test_specs.py — assertions registre (+3 specs, clés/watermark/partition)

## Acceptance Criteria

- [ ] Les 3 `IngestionSpec` déclarent les clés de merge, watermark et partition de [data-model.md §1](../data-model.md) (ex. run_timeline : merge `(cloud_provider, account_id, workspace_id, job_id, run_id, period_start_time)`, watermark `period_start_time`, partition `date(period_start_time)`).
- [ ] `SPECS` et `SPEC_KEYS` incluent les 3 nouvelles clés ; `job_dcm_system_tables.yml` `for_each.inputs` est aligné (sinon garde-fou entrypoint lève une erreur).
- [ ] Backfill initial borné à 30 j via `INITIAL_BACKFILL_DAYS` (aucune nouvelle constante).
- [ ] Aucune transformation/join/agrégation dans ces specs (fidèle source — P12).
- [ ] Re-run idempotent : 0 doublon sur la clé de merge (`quickstart.md` §1).
- [ ] ruff + mypy zéro warning.

## Tests

- `pytest packages/dcm-databricks-pipeline/tests/system_tables/ -q`
- Idempotence : `quickstart.md` §1 (contrôle `GROUP BY … HAVING count > 1` = 0 ligne)

## Out of scope

- Vues-pont / gold (T002).
- Suppression de l'ancien flux collecteur (T003).

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass (`pytest tests/system_tables/`)
- [ ] No files outside `packages/dcm-databricks-pipeline`
- [ ] Diff stays reviewable (registre + YAML + tests seulement)
- [ ] Sub-spec checkboxes reviewed
- [ ] Jira Story lists **Git branch** name

## Notes

- Réf. schémas exacts : [data-model.md §1](../data-model.md), [spike datamodel_curated_gold.md §1](../../../docs/spike/migration_from_collector_to_sys_table/datamodel_curated_gold.md).
- Prérequis infra (hors code) : `GRANT SELECT ON SCHEMA system.lakeflow` au SP (cf. spec Prerequisites) — vérifier avant run dev.
- Calibrage lot Azure par largeur : `jobs` → `AZURE_BATCH_NESTED` (maps/tags) ; timelines → lot large (lignes étroites).

### ⚠️ `curated_dbx_lakeflow_job_task_run_timeline` déjà ingérée (branche `dataeng/012-gold-compute-clusters`, fix idle_pct/active_hours)

`system.lakeflow.job_task_run_timeline` est **déjà ingérée** dans `pipelines/system_tables/specs.py` sous ce nom exact (`CURATED_LAKEFLOW_JOB_TASK_RUN_TIMELINE`/`LAKEFLOW_JOB_TASK_RUN_TIMELINE_SPEC`, clé registre `"lakeflow_job_task_run_timeline"`), livrée dans le cadre d'un fix sur `gold_dbx_compute_cluster_efficiency_daily` (epic 012, T002) — voir PR #188. **Réutiliser cette spec existante, ne pas en recréer une deuxième** pour `job_task_run_timeline` (double ingestion de la même system table = coût inutile). Il reste à ajouter uniquement `curated_dbx_lakeflow_jobs` et `curated_dbx_lakeflow_job_run_timeline` pour ce T001.

**Correction de schéma** (vérifié en prod via `DESCRIBE TABLE system.lakeflow.job_task_run_timeline`, warehouse `fcc5098720414937`, 2026-08-18) : il n'existe **PAS** de colonne `task_run_id` sur cette table, contrairement à ce que suppose ce doc/`spec.md`/`data-model.md` (clé merge `task_run_id, period_start_time`). La colonne réelle est `run_id` — qui EST déjà l'identifiant du run de tâche sur cette table précise (nom trompeur, à ne pas confondre avec `run_id` de `job_run_timeline` qui désigne le run de JOB). Clé de merge réellement utilisée par la spec déjà en place : `(cloud_provider, account_id, workspace_id, job_id, run_id, task_key, period_start_time)`. À corriger dans `spec.md`/`data-model.md` de cette epic avant implémentation du reste de T001.
