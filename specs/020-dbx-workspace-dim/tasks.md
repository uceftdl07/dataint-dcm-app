# Tasks: Dimension `dim_dbx_workspace` (curated `workspaces_latest` + vue référentiel)

**Input**: Design documents from `/specs/020-dbx-workspace-dim/` (plan.md, spec.md, research.md, data-model.md, quickstart.md)

**Tests**: P1 (constitution, NON-NEGOTIABLE) impose des tests pytest avec la tâche — inclus dans la sub-spec (fakes partagés `tests/conftest.py`, sans JVM, même pattern que `tests/system_tables/`).

**Organization**: DCM ticket plan = **single_domain** (`intake.json.ticket_plan`, 1 Story → `dataeng ×1`). 1 task = 1 Jira Story = 1 branche = 1 sub-spec. Détail d'exécution dans `stories/T001-*.md` (ce fichier = index).

## Format: `[ID] [P?] Domain Description → sub-spec`

- **[P]** : parallélisable (fichiers disjoints, pas de dépendance sur une tâche incomplète).
- Domaines : dataeng (seul domaine de ce ticket plan).

## Tasks

- [x] T001 DataEng Ingestion `system.access.workspaces_latest` (AWS+Azure) → `curated_dbx_access_workspaces_latest` via `SPECS` de `pipelines/system_tables/` + nouveau module `pipelines/gold_dbx_workspace/` créant la vue `dim_dbx_workspace` (inner join filtré avec `dim_reference_landing_zone_dbx_workspace`) + job wheel + tests → [stories/T001-dbx-workspace-dim.md](stories/T001-dbx-workspace-dim.md)

## Dependencies & Execution Order

- **T001** — aucune dépendance de code (nouvelle `IngestionSpec` additive + nouveau module isolé). Dépendance **runtime** : la vue nécessite `curated_dbx_access_workspaces_latest` (produit par le job `dcm_system_tables`) et `dim_reference_landing_zone_dbx_workspace` (job `dcm_reference_lz`, feature 014). Seule tâche du ticket plan (`single_domain`, 1 Story).

## Implementation Strategy

### MVP (T001 seul)

1. Ingestion : ajouter `WORKSPACES_LATEST_SPEC` (full-load, `merge_keys=(cloud_provider, workspace_id)`) au registre `SPECS` de `pipelines/system_tables/specs.py` + `"access_workspaces_latest"` dans `for_each_task.inputs` du job `dcm_system_tables`. Test dans `tests/system_tables/`.
2. Vue : nouveau module `pipelines/gold_dbx_workspace/` — `view.py` (`build_dim_dbx_workspace_view_sql(catalog, schema)` pur) + `entrypoint.py` (câblage wheel : résout SparkSession + params puis `spark.sql`). Test string-based dans `tests/gold_dbx_workspace/`.
3. Ressource bundle `resources/job_dcm_gold_dbx_workspace.yml` (wheel task, cron 05:00 Europe/Paris) + entrée `[project.scripts]`.
4. Validation dev via `quickstart.md` (déploiement + requêtes SC-001 à SC-003).

## Notes

- Pas de phase Setup/Foundational dédiée : le package `dcm-databricks-pipeline` est déjà scaffoldé, le socle `pipelines/common/` + `system_tables` déjà en production.
- Pas de `merge-strategy.md` : ticket plan mono-domaine, mono-tâche, aucun fichier partagé avec un autre développeur en parallèle sur cette feature.
- Polish (ruff/mypy zéro-warning, run complet `quickstart.md`) plié dans le « Before PR » de T001, pas une phase séparée.
