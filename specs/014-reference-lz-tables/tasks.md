# Tasks: Tables référentiel `dim_reference_landing_zone_dbx_workspace` & `dim_reference_landing_zone_business_application`

**Input**: Design documents from `/specs/014-reference-lz-tables/` (plan.md, spec.md, research.md, data-model.md, quickstart.md)

**Tests**: P1 (constitution, NON-NEGOTIABLE) impose des tests pytest avec la tâche — inclus dans la sub-spec (fakes partagés `tests/conftest.py`, sans JVM, même pattern que `tests/system_tables/`).

**Organization**: DCM ticket plan = **single_domain** (`intake.json.ticket_plan`, 1 Story → `dataeng ×1`). 1 task = 1 Jira Story = 1 branche = 1 sub-spec. Détail d'exécution dans `stories/T001-*.md` (ce fichier = index).

## Format: `[ID] [P?] Domain Description → sub-spec`

- **[P]** : parallélisable (fichiers disjoints, pas de dépendance sur une tâche incomplète).
- Domaines : dataeng (seul domaine de ce ticket plan).

## Tasks

- [x] T001 DataEng Nouveau module d'ingestion `pipelines/reference_lz/` (job wheel-task, MERGE idempotent) pour `dim_reference_landing_zone_dbx_workspace` (AWS ⊎ Azure) + `dim_reference_landing_zone_business_application` (Azure seule) + 2 primitives génériques `dedupe_by_key`/`filter_null_or_empty_key` dans `pipelines/common/transforms.py` → [stories/T001-reference-lz-ingestion.md](stories/T001-reference-lz-ingestion.md)

## Dependencies & Execution Order

- **T001** — aucune dépendance (nouveau module isolé, aucune table/pipeline existant modifié). Seule tâche du ticket plan (`single_domain`, 1 Story).

## Implementation Strategy

### MVP (T001 seul)

1. Primitives génériques `pipelines/common/transforms.py` (`dedupe_by_key`, `filter_null_or_empty_key`) — testées isolément (`tests/common/test_transforms.py`).
2. Module `pipelines/reference_lz/` (`specs.py` → `ingest.py` → `entrypoint.py`), réutilisant les primitives du socle (`read_native_source`, `read_azure_batches`, `append_to_staging`, `merge_into_curated`) + les 2 nouvelles primitives.
3. Ressource bundle `resources/job_dcm_reference_lz.yml` (`for_each_task` sur les 2 tables).
4. Validation dev via `quickstart.md` (déploiement + requêtes SC-001 à SC-006).

## Notes

- Pas de phase Setup/Foundational dédiée : le package `dcm-databricks-pipeline` est déjà scaffoldé, le socle `pipelines/common/` déjà en production (`system_tables`).
- Pas de `merge-strategy.md` : ticket plan mono-domaine, mono-tâche, aucun fichier partagé avec un autre développeur en parallèle sur cette feature.
- Polish (ruff/mypy zéro-warning, run complet `quickstart.md`) plié dans le « Before PR » de T001, pas une phase séparée.
