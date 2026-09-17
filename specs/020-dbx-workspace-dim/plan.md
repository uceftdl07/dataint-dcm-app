# Implementation Plan: Dimension `dim_dbx_workspace` (curated `workspaces_latest` + vue référentiel)

**Branch**: `dataeng/020-dbx-workspace-dim` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/020-dbx-workspace-dim/spec.md`

**Réf. socle réutilisé** :
- [`pipelines/system_tables/`](../../packages/dcm-databricks-pipeline/pipelines/system_tables/) — ingestion générique `system.*` → curated (lecture native AWS + connecteur SQL cross-tenant Azure, staging + `MERGE INTO` idempotent, job wheel `for_each_task`). On y **ajoute** une `IngestionSpec` pour `system.access.workspaces_latest`.
- [`pipelines/reference_lz/`](../../packages/dcm-databricks-pipeline/pipelines/reference_lz/) — produit la table jointe `dim_reference_landing_zone_dbx_workspace` (feature 014, job wheel `dcm_reference_lz`, cron 04:30).

## Summary

Deux livrables dans `packages/dcm-databricks-pipeline` (DataEng only) :

1. **Ingestion curated** — ajouter `system.access.workspaces_latest` (AWS natif + Azure cross-tenant) au registre `SPECS` de `pipelines/system_tables/specs.py` → table `curated_dbx_access_workspaces_latest` dans `it.ba_data_connect_monitoring__<env>`. Full-load (snapshot « latest », **sans** watermark, comme `compute.node_types` / `billing.list_prices`), `merge_keys = (cloud_provider, workspace_id)`, projection restreinte aux colonnes utiles à la vue (`workspace_id`, `workspace_name`, `status`, + `account_id` si présent). Une seule ligne à ajouter dans `for_each_task.inputs` du job `dcm_system_tables`.

2. **Vue référentiel** — nouveau module `pipelines/gold_dbx_workspace/` (entrypoint wheel) exécutant `spark.sql("CREATE OR REPLACE VIEW dim_dbx_workspace AS …")` : **inner join** `curated_dbx_access_workspaces_latest` ⋈ `dim_reference_landing_zone_dbx_workspace` sur `workspace_id`, filtré `subscription_or_account_id IS NOT NULL AND status = 'RUNNING'`. Colonnes exposées : `workspace_id`, `workspace_name` (curated), `subscription_or_account_id` + `cloud` (référentiel, depuis `cloud_provider`), `updated_at = current_timestamp()`. Nouveau job `dcm_gold_dbx_workspace` (wheel task) ordonnancé **après** `dcm_system_tables` (curated) **et** `dcm_reference_lz` (dim ref).

Aucune nouvelle dépendance, aucun nouveau secret : réutilisation intégrale de `pipelines/common/` et du secret scope Databricks existant. Décisions figées par `/speckit.clarify` (session 2026-09-02) : matérialisation via module dédié, `merge_keys=(cloud_provider, workspace_id)`, `updated_at=current_timestamp()`.

## Technical Context

**Language/Version**: Python 3.12 (`>=3.12,<3.13`), PySpark ; aucun autre package touché (pas de backend/frontend, cf. Domain Scope).

**Primary Dependencies**: Aucune nouvelle. Ingestion réutilise `pipelines/common/` (`readers`, `writers.merge_into_curated`, `transforms`) + le générique `ingest_system_table()`. La vue n'utilise que `spark.sql` (aucune lib tierce). `databricks-sql-connector` / `azure-identity` déjà présents (mêmes secrets que `system_tables`).

**Storage**: Databricks Unity Catalog, `it.ba_data_connect_monitoring__<env>` (dev `__d`). Source ingestion : `system.access.workspaces_latest` (AWS natif + Azure cross-tenant). Sources de la vue : `curated_dbx_access_workspaces_latest` (nouvelle) + `dim_reference_landing_zone_dbx_workspace` (existante). La vue est un objet Unity Catalog `VIEW` (pas de stockage matérialisé).

**Testing**: pytest + fakes partagés `tests/conftest.py` (`FakeSpark`, `FakeDataFrame`), sans JVM. ruff + mypy scoped. Nouveau `tests/system_tables/` (assertion de la nouvelle `IngestionSpec` : source/curated/merge_keys/full-load/select_columns) + nouveau `tests/gold_dbx_workspace/` (test du SQL de la vue : présence du inner join, des filtres `status='RUNNING'`/`subscription_or_account_id IS NOT NULL`, des 5 colonnes projetées, du `current_timestamp()`).

**Target Platform**: Databricks Jobs (serverless, wheel task). (1) tâche `access_workspaces_latest` ajoutée au `for_each` du job existant `dcm_system_tables`. (2) nouveau job `dcm_gold_dbx_workspace` (wheel `dcm-gold-dbx-workspace`), cron **05:00 Europe/Paris** (après `dcm_system_tables` 03:00 et `dcm_reference_lz` 04:30) — ou chaîné via `run_job_task` dans l'orchestrateur maître (cf. research.md §4).

**Project Type**: Mono-package — `packages/dcm-databricks-pipeline` uniquement (DataEng only ✅).

**Performance Goals**: Rafraîchissement quotidien best-effort, pas de SLA. `workspaces_latest` = petite table snapshot (une ligne par workspace) → pas de contrainte de lot Azure (valeur globale du job suffit). La vue est calculée à la lecture (aucun coût d'ingestion).

**Constraints**: MERGE idempotent 0 doublon au re-run (`merge_keys=(cloud_provider, workspace_id)`, SC-001) ; full-load sans watermark ; inner join strict (workspaces non appariés exclus) ; filtres `status='RUNNING'` + `subscription_or_account_id IS NOT NULL` portés par la vue (SC-002) ; jamais de donnée fictive (P9) — projection fidèle source, aucun enrichissement inventé.

**Scale/Scope**: 1 nouvelle `IngestionSpec` + 1 ligne `inputs` (job system_tables), 1 nouveau module `pipelines/gold_dbx_workspace/` (2 fichiers : entrypoint + SQL builder), 1 nouvelle ressource bundle `job_dcm_gold_dbx_workspace.yml`, 1 entrée `[project.scripts]`, 2 dossiers/fichiers de tests. Aucun impact backend/frontend/collectors.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principe | Statut | Justification |
|---|---|---|
| P1 Test-First & Code Quality (NON-NEGOTIABLE) | ✅ PASS | Tests de la nouvelle `IngestionSpec` (`tests/system_tables/`) + tests du SQL de la vue (`tests/gold_dbx_workspace/`), fakes sans JVM ; ruff/mypy scoped zéro warning. |
| P2 Simplicité, Explicitness & Versioning | ✅ PASS | Réutilise le générique `ingest_system_table()` (une simple entrée de registre) ; la vue est un `CREATE OR REPLACE VIEW` idempotent, pas de nouveau framework ; aucune table existante modifiée. |
| P3 Self-Documenting Code | ✅ PASS | Noms explicites (`CURATED_ACCESS_WORKSPACES_LATEST`, `build_dim_dbx_workspace_view_sql`) ; commentaires réservés au *why* (choix full-load, filtres de la vue). |
| P4 Fail Fast, Fail Loud | ✅ PASS | `entrypoint` du module vue : erreur explicite si les tables sources n'existent pas ; `for_each_task` remonte l'échec par table sans l'avaler. |
| P5 Architecture explicite & modularité | ✅ PASS | Module vue isolé `pipelines/gold_dbx_workspace/`, aucune dépendance croisée nouvelle ; lecture cross-tenant via le connecteur existant (même mécanisme que `system_tables`), aucun appel cross-LZ direct. |
| P6 Idempotency by Design | ✅ PASS | Ingestion : `MERGE` par `(cloud_provider, workspace_id)`. Vue : `CREATE OR REPLACE VIEW` (rejouable), résultat déterministe pour un état source donné. |
| P7/P8 Secrets Management (NON-NEGOTIABLE) | ✅ PASS | Aucun nouveau secret : réutilise le secret scope Databricks existant (SP Azure OAuth M2M) déjà câblé pour `system_tables`. La vue ne lit que des tables Unity Catalog (aucun secret). |
| P9 No Fake Data in Production (NON-NEGOTIABLE) | ✅ PASS | Curated = projection fidèle de `system.access.workspaces_latest` ; vue = inner join filtré des données réelles, aucune valeur inventée. |
| P10 Observability & Traceability | ⚠️ NOTE | `logging` stdlib (pas `structlog` JSON) — écart pré-existant uniforme sur `dcm-databricks-pipeline` (déjà noté sur `system_tables`/`reference_lz`), non introduit ici. |
| P11 Naming Conventions | ⚠️ NOTE | La vue est préfixée `dim_` (pas `gold_`) — cohérent avec l'usage dimensionnel (`dim_landing_zone`, `dim_reference_landing_zone_dbx_workspace` déjà en place) et avec le nom demandé dans le spec (contrat de données). Écart volontaire, documenté en Complexity Tracking. |
| P12 Medallion — Aggregations on Gold Only | ✅ PASS | Ingestion curated : aucune agrégation (fidèle source). La vue vit au niveau gold (jointure/filtre référentiel), aucune agrégation métier (pas de SUM/AVG/COUNT). |
| P13 Immutable Raw Layer | N/A | Pas de couche Raw dans ce flux — lecture directe d'une system table (comme le reste de `system_tables`). |
| P14 Schema Versioning | N/A | Table `system.*` hors `MetricPayload` — `schema_version` non applicable (mêmes conventions que les autres curated `system_tables`). |
| P15 API Contract Stability | N/A | Aucune route API exposée dans cette Epic (Out of scope). |
| P16 Frontend Quality | N/A | Aucun impact frontend (Out of scope). |

**P11 (NOTE)** est la seule justification à documenter en Complexity Tracking (écart de nommage `dim_` vs `gold_`, non bloquant).

### Post-Design Re-check (après Phase 1)

`research.md` (5 décisions, dont les 3 du `/speckit.clarify` du 2026-09-02), `data-model.md` (1 curated + 1 vue) et `quickstart.md` n'introduisent aucune nouvelle dépendance, aucun nouveau secret, aucune agrégation métier hors couche gold, et respectent les 3 décisions de clarification (module vue dédié, `merge_keys`, `updated_at`). **Constitution Check reconfirmé : PASS** (P11 reste une NOTE à valider en revue).

## Project Structure

### Documentation (this feature)

```text
specs/020-dbx-workspace-dim/
├── plan.md              # This file (/speckit.plan)
├── research.md          # Phase 0 — socle réutilisé, choix full-load, filtres vue, ordonnancement, updated_at
├── data-model.md        # Phase 1 — curated_dbx_access_workspaces_latest + vue dim_dbx_workspace
├── quickstart.md        # Phase 1 — exécution & validation dev
├── contracts/           # vide — aucune interface externe (pas d'API/UI dans cette Epic)
├── spec.md              # Feature spec (clarifiée — 3 Q/R intégrées)
├── intake.json / domain-scope.json
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit.tasks — PAS créé par /speckit.plan)
```

### Source Code (repository root)

```text
packages/dcm-databricks-pipeline/
├── pipelines/
│   ├── system_tables/
│   │   └── specs.py                       # MODIFIED — +CURATED_ACCESS_WORKSPACES_LATEST, +SOURCE_ACCESS_WORKSPACES_LATEST,
│   │                                      #   +WORKSPACES_LATEST_MERGE_KEYS, +WORKSPACES_LATEST_SPEC, +entrée dans SPECS
│   └── gold_dbx_workspace/                # NEW module
│       ├── __init__.py
│       ├── view.py                        # build_dim_dbx_workspace_view_sql(catalog, schema) → str (CREATE OR REPLACE VIEW …)
│       └── entrypoint.py                  # wheel task : résout SparkSession + params (catalog/schema) puis spark.sql(view_sql)
├── resources/
│   ├── job_dcm_system_tables.yml          # MODIFIED — +"access_workspaces_latest" dans for_each_task.inputs
│   └── job_dcm_gold_dbx_workspace.yml     # NEW — job wheel, tâche unique de création de vue, cron 05:00 Europe/Paris
├── pyproject.toml                         # MODIFIED — +[project.scripts] dcm-gold-dbx-workspace = "pipelines.gold_dbx_workspace.entrypoint:run"
└── tests/
    ├── system_tables/                     # EXTENDED — test de WORKSPACES_LATEST_SPEC (source/curated/merge_keys/full-load/select_columns) + présence dans SPECS
    └── gold_dbx_workspace/                # NEW — test_view.py (inner join, filtres status/subscription_or_account_id, 5 colonnes, current_timestamp)
```

**Structure Decision**: Mono-package `packages/dcm-databricks-pipeline`. L'ingestion réutilise le socle générique `system_tables` (une entrée de registre + une ligne `inputs`, aucun code d'orchestration nouveau). La vue vit dans un module isolé `pipelines/gold_dbx_workspace/` (aucun module existant modifié hormis les 2 fichiers de config `specs.py` / `job_dcm_system_tables.yml`). Une seule branche fille (`dataeng/020-dbx-workspace-dim`) — changement focalisé, petite PR.

## Complexity Tracking

| Écart | Pourquoi nécessaire | Alternative plus simple rejetée |
|---|---|---|
| P11 (NOTE) — vue préfixée `dim_` hors convention `raw_`/`curated_`/`gold_` | Nom imposé par le spec (contrat de données consommé en aval) et cohérent avec le vocabulaire dimensionnel déjà en place (`dim_landing_zone`, `dim_reference_landing_zone_dbx_workspace`). | Renommer en `gold_dbx_workspace` pour coller à P11 — rejeté : casserait le contrat de nommage attendu par les consommateurs et l'homogénéité des `dim_*`. À valider en revue. |
| Nouveau module pour un simple `CREATE VIEW` | Le pipeline n'a aucun précédent de vue ; isoler la logique (SQL builder testable + entrypoint câblage) évite de polluer `system_tables`/`gold_dbx_compute` et rend le SQL unit-testable sans cluster. | Inliner le `spark.sql` dans l'entrypoint `reference_lz` — rejeté : la vue dépend AUSSI du curated produit par le job `system_tables` (couplage d'ordonnancement mal placé) et mélangerait deux responsabilités. |
