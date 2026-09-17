# T001 — Ingestion `dim_reference_landing_zone_dbx_workspace` & `dim_reference_landing_zone_business_application`

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: dataeng/014-reference-lz-tables
**Jira**: pending
**Depends on**: none
**Work type**: feature

## Description

Créer le nouveau module d'ingestion `pipelines/reference_lz/` (job wheel-task, pas DLT — même socle que `pipelines/system_tables/`) qui alimente 2 tables gold de référentiel dans `it.ba_data_connect_monitoring__<env>` :

1. `dim_reference_landing_zone_dbx_workspace` — union AWS (lecture native `egress_firewall_aws.workspace_inventory`) + Azure (connecteur cross-tenant `egress_firewall.workspace_inventory`), renommage par cloud vers `subscription_or_account_id`.
2. `dim_reference_landing_zone_business_application` — source Azure unique (`catalog_badsdataeng_dev.ref_dcm.ref_ba_lz`), renommage direct `lz_id` → `subscription_or_account_id` (pas de jointure de résolution).

Ajoute aussi 2 primitives génériques réutilisables à `pipelines/common/transforms.py` : `dedupe_by_key` (déduplication déterministe avant MERGE, FR-009) et `filter_null_or_empty_key` (exclusion + log des lignes à clé NULL/vide, FR-011). L'isolation d'échec par table/source (FR-010) est obtenue par construction via `for_each_task` (pas de code applicatif dédié).

## Files to create/modify

- CREATE packages/dcm-databricks-pipeline/pipelines/reference_lz/__init__.py
- CREATE packages/dcm-databricks-pipeline/pipelines/reference_lz/specs.py — constantes tables/colonnes source, merge_keys (pas d'`IngestionSpec` générique — schémas AWS/Azure divergents sur `dim_reference_landing_zone_dbx_workspace`)
- CREATE packages/dcm-databricks-pipeline/pipelines/reference_lz/ingest.py — `ingest_dbx_workspace()` (AWS natif + Azure staging/MERGE), `ingest_business_application()` (Azure seul, `azure_config` requis)
- CREATE packages/dcm-databricks-pipeline/pipelines/reference_lz/entrypoint.py — point d'entrée wheel task (`--table`), garde-fou config Azure requise pour `business_application` (FR-004)
- UPDATE packages/dcm-databricks-pipeline/pipelines/common/transforms.py — `dedupe_by_key(df, key_columns)`, `filter_null_or_empty_key(df, *key_columns)`
- CREATE packages/dcm-databricks-pipeline/resources/job_dcm_reference_lz.yml — job wheel, `for_each_task` sur les 2 tables, cron `0 30 4 * * ?` Europe/Paris
- UPDATE packages/dcm-databricks-pipeline/pyproject.toml — `[project.scripts]` `dcm-reference-lz = "pipelines.reference_lz.entrypoint:run"`
- CREATE packages/dcm-databricks-pipeline/tests/reference_lz/test_specs.py
- CREATE packages/dcm-databricks-pipeline/tests/reference_lz/test_ingest.py
- CREATE packages/dcm-databricks-pipeline/tests/reference_lz/test_entrypoint.py
- UPDATE packages/dcm-databricks-pipeline/tests/common/test_transforms.py — tests `dedupe_by_key` / `filter_null_or_empty_key`

## Acceptance Criteria

- [x] `dim_reference_landing_zone_dbx_workspace` créée avec les colonnes/PK de [data-model.md](../data-model.md) — `TBLPROPERTIES ('quality'='gold', 'delta.enableChangeDataFeed'='true')` (FR-001). *(table créée via le `merge_into_curated` partagé, même socle que `system_tables` — TBLPROPERTIES portées par ce writer commun, non modifié par T001)*
- [x] `dim_reference_landing_zone_dbx_workspace` alimentée par union AWS + Azure, renommage par cloud (`aws_account_id`/`subscription_id` → `subscription_or_account_id`) (FR-002). *(tests `test_ingest_dbx_workspace_aws_only_renames_and_merges` + `test_ingest_dbx_workspace_azure_batches_stage_then_merge`)*
- [x] `dim_reference_landing_zone_business_application` créée avec les colonnes/PK de [data-model.md](../data-model.md) (FR-003).
- [x] `dim_reference_landing_zone_business_application` alimentée depuis `ref_ba_lz`, renommage direct `lz_id` → `subscription_or_account_id` (FR-004). *(tests `test_ingest_business_application_stages_batches_then_merges` + `test_business_application_spec_uses_azure_only_source`)*
- [x] Chargement full-load (pas de watermark), MERGE par clé métier à chaque run (FR-005). *(test `test_no_watermark_full_load_semantics`)*
- [x] `updated_at` renseigné au timestamp du run, identique pour toutes les lignes d'un même run (FR-006).
- [x] Aucun doublon sur la PK après re-run consécutif (FR-007, SC-001/SC-002/SC-004). *(par construction : `dedupe_by_key` + `MERGE INTO` sur `merge_keys` — validation réelle post-déploiement via `quickstart.md` §4)*
- [x] Architecture alignée `pipelines/system_tables/` (module wheel-task, pas DLT) (FR-008).
- [x] `dedupe_by_key` : si la source contient des doublons de clé dans un run, une seule ligne déterministe est conservée par clé — pas d'échec `multiple source rows matched` (FR-009, SC-005). *(tests `test_dedupe_by_key_orders_by_all_remaining_columns_and_drops_helper_column` + `test_dedupe_by_key_uses_constant_order_when_key_is_all_columns`)*
- [x] `for_each_task` isole l'échec par table/source — une panne Azure sur une table ne bloque pas les autres itérations du run (FR-010). *(vérifié dans `resources/job_dcm_reference_lz.yml` : `for_each_task` avec 2 itérations indépendantes)*
- [x] `filter_null_or_empty_key` : lignes à clé NULL/vide exclues du MERGE, nombre exclu loggué (FR-011, SC-006). *(tests `test_filter_null_or_empty_key_excludes_and_logs_when_rows_removed` + variantes)*
- [x] Garde-fou `entrypoint.main` : erreur explicite si `dim_reference_landing_zone_business_application` sélectionnée sans config Azure. *(test `test_main_raises_when_business_application_selected_without_azure_config`)*
- [ ] `dim_reference_landing_zone_dbx_workspace` contient au moins une ligne `cloud_provider='aws'` et une ligne `cloud_provider='azure'` après un run nominal (SC-003). — **non vérifiable en local** (nécessite un run réel sur cluster Databricks contre les sources AWS/Azure) ; à valider via `quickstart.md` §4 après déploiement dev.
- [x] ruff + mypy zéro warning. *(`uv run ruff check` + `uv run mypy -p pipelines.common -p pipelines.reference_lz` : 0 erreur)*

## Tests

- `uv run pytest packages/dcm-databricks-pipeline/tests/reference_lz -v`
- `uv run pytest packages/dcm-databricks-pipeline/tests/common/test_transforms.py -v`
- Idempotence + dédoublonnage + NULL : `quickstart.md` §2 (unitaire) et §4 (SQL post-déploiement dev, SC-001/SC-002/SC-003)

## Out of scope

- Exposition API/UI de ces référentiels (aucune route backend, aucun écran frontend — cf. spec Out of scope).
- Résolution/enrichissement `landing_zone_id` via jointure vers `dim_landing_zone` — design abandonné (cf. note de re-intake dans `spec.md`).

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass (`pytest tests/reference_lz/ tests/common/test_transforms.py`)
- [ ] No files outside `packages/dcm-databricks-pipeline`
- [ ] Diff stays reviewable (module + primitives + job YAML + tests seulement)
- [ ] Sub-spec checkboxes reviewed
- [ ] Jira Story lists **Git branch** name (not a commit SHA)

## Notes

- Réf. schémas/pseudocode exacts : [data-model.md](../data-model.md) (2 entités + primitives dédup/filtrage).
- Réf. décisions techniques : [research.md](../research.md) (§1-3 socle réutilisé, §4-6 clarify Q2/Q3/Q4, §7 test strategy).
- 4 clarifications intégrées dans [spec.md](../spec.md) `## Clarifications` (spelling, dédup, isolation, NULL) — aucune ambiguïté bloquante restante.
- `dedupe_by_key`/`filter_null_or_empty_key` sont génériques (`pipelines/common/`) — réutilisables par de futures specs, à ne pas dupliquer localement dans `reference_lz/`.
