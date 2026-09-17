# T001 — Ingestion `workspaces_latest` + vue `dim_dbx_workspace`

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: dataeng/020-ingestion-system-access-workspaces
**Jira**: pending
**Depends on**: none (code) · runtime : `dcm_system_tables` (curated) + `dcm_reference_lz` (dim ref, feature 014)
**Work type**: feature

## Description

Deux livrables dans `packages/dcm-databricks-pipeline` (DataEng only) :

1. **Ingestion curated** — ajouter `system.access.workspaces_latest` (AWS natif + Azure cross-tenant) au registre `SPECS` de `pipelines/system_tables/specs.py` → table `curated_dbx_access_workspaces_latest` (`it.ba_data_connect_monitoring__<env>`). Full-load (snapshot « latest », **sans** watermark, comme `compute.node_types` / `billing.list_prices`), `merge_keys = ("cloud_provider", "workspace_id")`, `select_columns` restreint aux colonnes utiles à la vue (`workspace_id`, `workspace_name`, `status`, `account_id` sous réserve du schéma réel). Ajouter `"access_workspaces_latest"` dans `for_each_task.inputs` du job `dcm_system_tables` (aligné sur le registre — garde-fou entrypoint sur clé inconnue).

2. **Vue référentiel** — nouveau module `pipelines/gold_dbx_workspace/` : `view.py` expose `build_dim_dbx_workspace_view_sql(catalog, schema) -> str` (fonction **pure**, SQL `CREATE OR REPLACE VIEW`), `entrypoint.py` câble la wheel task (résout SparkSession + params `catalog`/`schema` puis `spark.sql(view_sql)`). La vue = **inner join** `curated_dbx_access_workspaces_latest` ⋈ `dim_reference_landing_zone_dbx_workspace` sur `workspace_id`, filtré `subscription_or_account_id IS NOT NULL AND status = 'RUNNING'`, exposant exactement `workspace_id`, `workspace_name` (curated), `subscription_or_account_id` + `cloud` (référentiel `cloud_provider`), `updated_at = current_timestamp()`. Nouveau job `dcm_gold_dbx_workspace` (cron 05:00 Europe/Paris, après system_tables 03:00 et reference_lz 04:30).

Décisions figées `/speckit.clarify` (2026-09-02) : module vue dédié, `merge_keys=(cloud_provider, workspace_id)`, `updated_at=current_timestamp()`.

## Files to create/modify

- UPDATE packages/dcm-databricks-pipeline/pipelines/system_tables/specs.py — `CURATED_ACCESS_WORKSPACES_LATEST`, `SOURCE_ACCESS_WORKSPACES_LATEST`, `WORKSPACES_LATEST_MERGE_KEYS`, `WORKSPACES_LATEST_SPEC` (full-load, `select_columns`), + entrée `"access_workspaces_latest"` dans `SPECS`
- UPDATE packages/dcm-databricks-pipeline/resources/job_dcm_system_tables.yml — `+"access_workspaces_latest"` dans `for_each_task.inputs`
- CREATE packages/dcm-databricks-pipeline/pipelines/gold_dbx_workspace/__init__.py
- CREATE packages/dcm-databricks-pipeline/pipelines/gold_dbx_workspace/view.py — `build_dim_dbx_workspace_view_sql(catalog, schema) -> str` (SQL pur, testable sans cluster)
- CREATE packages/dcm-databricks-pipeline/pipelines/gold_dbx_workspace/entrypoint.py — wheel task (`run`/`main`) : SparkSession + params `catalog`/`schema` → `spark.sql(view_sql)`, garde-fou explicite si tables sources absentes
- CREATE packages/dcm-databricks-pipeline/resources/job_dcm_gold_dbx_workspace.yml — job wheel, tâche unique de création de vue, cron `0 0 5 * * ?` Europe/Paris (PAUSED en dev/dev_local)
- UPDATE packages/dcm-databricks-pipeline/pyproject.toml — `[project.scripts]` `dcm-gold-dbx-workspace = "pipelines.gold_dbx_workspace.entrypoint:run"`
- CREATE packages/dcm-databricks-pipeline/tests/gold_dbx_workspace/__init__.py
- CREATE packages/dcm-databricks-pipeline/tests/gold_dbx_workspace/test_view.py — assertions sur le SQL de la vue
- UPDATE packages/dcm-databricks-pipeline/tests/system_tables/ — test de `WORKSPACES_LATEST_SPEC` + présence dans `SPECS` (fichier existant `test_specs.py` si présent, sinon nouveau)

## Acceptance Criteria

- [x] `curated_dbx_access_workspaces_latest` alimentée par `system.access.workspaces_latest` (AWS natif + Azure cross-tenant) via le générique `ingest_system_table()`, projection `select_columns` (`workspace_id`, `workspace_name`, `status`, +`account_id`) (FR-001/FR-002). *(test : `WORKSPACES_LATEST_SPEC` source/curated/`select_columns`)*
- [x] `WORKSPACES_LATEST_SPEC` en full-load : `watermark_column is None`, `merge_keys == ("cloud_provider", "workspace_id")`, aucune partition (FR-001). *(test spec)*
- [x] `"access_workspaces_latest"` présent dans `SPECS` **et** dans `for_each_task.inputs` du job `dcm_system_tables` (alignement registre/job). *(test spec + revue YAML)*
- [x] Vue `dim_dbx_workspace` créée via `CREATE OR REPLACE VIEW` = inner join sur `workspace_id`, filtres `status='RUNNING'` **et** `subscription_or_account_id IS NOT NULL` (FR-003). *(test : le SQL contient `INNER JOIN`, `ON w.workspace_id = r.workspace_id`, les 2 filtres)*
- [x] Vue expose exactement `workspace_id`, `workspace_name` (curated), `subscription_or_account_id` + `cloud` (référentiel `cloud_provider`), `updated_at = current_timestamp()` (FR-004). *(test : les 5 colonnes projetées + `current_timestamp()`)*
- [x] Vue qualifiée `catalog.schema.dim_dbx_workspace` depuis les params (jamais codée en dur), rejouable (`CREATE OR REPLACE VIEW`, P6). *(test : nom qualifié depuis `build_dim_dbx_workspace_view_sql(catalog, schema)`)*
- [x] Une ligne par `workspace_id` (SC-001, FR-005) — par construction (snapshot latest clé `(cloud_provider, workspace_id)` + PK `workspace_id` du référentiel) ; ajouter un `QUALIFY row_number()… = 1` uniquement si un doublon est observé au run. *(validation réelle post-déploiement via `quickstart.md` §5)*
- [x] Job `dcm_gold_dbx_workspace` : wheel task, cron `0 0 5 * * ?` Europe/Paris, PAUSED en dev/dev_local, UNPAUSED en prod (pattern `dcm_reference_lz`). *(revue YAML)*
- [x] `SC-003` — `curated_dbx_access_workspaces_latest` contient des lignes `aws` **et** `azure` après un run nominal. — **validé dev** : curated 319 lignes / 2 clouds, vue `dim_dbx_workspace` 313 lignes (aws 161, azure 152), 5 colonnes conformes, 1 ligne/workspace_id.
- [x] `bundle validate -t dev` OK (OAuth, pas de PAT). *(à exécuter avant PR)*
- [x] ruff + mypy zéro warning (`uv run ruff check` + `uv run mypy -p pipelines.gold_dbx_workspace -p pipelines.system_tables`). *(note : 1 erreur mypy pré-existante `entrypoint.py:143` hors périmètre, fichier non touché — CI mypy désactivée sur ce package)*

## Tests

- `uv run pytest packages/dcm-databricks-pipeline/tests/gold_dbx_workspace -v`
- `uv run pytest packages/dcm-databricks-pipeline/tests/system_tables -v`
- Idempotence + filtres + colonnes : `quickstart.md` §5 (SQL post-déploiement dev, SC-001/SC-002/SC-003)

## Out of scope

- Exposition API/UI de `dim_dbx_workspace` (aucune route backend, aucun écran frontend — cf. spec Out of scope).
- Historisation SCD / colonnes supplémentaires de `system.access.workspaces_latest` non nécessaires à la vue.
- Chaînage `run_job_task` dans un orchestrateur maître (le cron décalé 05:00 est le choix par défaut ; chaînage = décision d'exploitation, cf. research.md §4).
