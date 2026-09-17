# Implementation Plan: Tables référentiel `dim_reference_landing_zone_dbx_workspace` & `dim_reference_landing_zone_business_application`

**Branch**: `dataeng/014-reference-lz-tables` | **Date**: 2026-08-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/014-reference-lz-tables/spec.md`

**Réf. socle réutilisé** : [`pipelines/system_tables/`](../../packages/dcm-databricks-pipeline/pipelines/system_tables/) — même architecture (lecture native AWS + connecteur SQL cross-tenant Azure, staging + `MERGE INTO` idempotent, job wheel-task `for_each_task`), étendue ici pour 2 tables référentiel dont les sources divergent par colonne (pas de schéma identique AWS/Azure).

## Summary

Créer 2 tables gold de référentiel dans `it.ba_data_connect_monitoring__<env>` :

1. `dim_reference_landing_zone_dbx_workspace` — mapping workspace Databricks ↔ compte/subscription cloud, alimenté par union des tables AWS (`egress_firewall_aws.workspace_inventory`, lecture native) et Azure (`egress_firewall.workspace_inventory`, connecteur cross-tenant).
2. `dim_reference_landing_zone_business_application` — mapping Business Application ↔ compte/subscription cloud, alimenté par la vue Azure unique `ref_ba_lz` (renommage direct `lz_id` → `subscription_or_account_id`, sans jointure de résolution).

Nouveau module `pipelines/reference_lz/` (`specs.py`, `ingest.py`, `entrypoint.py`) et job `resources/job_dcm_reference_lz.yml` (`for_each_task` sur les 2 tables), calqués sur `pipelines/system_tables/` mais avec une orchestration bespoke (pas le générique `ingest_system_table()`) car les 2 sources `workspace_inventory` divergent sur le nom de colonne d'identifiant de compte et `ref_ba_lz` n'a pas d'équivalent AWS. Full-load MERGE à chaque run (FR-005), avec 3 garde-fous issus de `/speckit.clarify` : déduplication déterministe avant MERGE (FR-009), isolation d'échec par tâche via `for_each_task` (FR-010), et filtrage des lignes à clé NULL/vide (FR-011) — ces 2 dernières primitives (`dedupe_by_key`, `filter_null_or_empty_key`) sont ajoutées à `pipelines/common/transforms.py` pour être réutilisables par d'autres specs futures.

## Technical Context

**Language/Version**: Python 3.12 (`>=3.12,<3.13`), PySpark ; aucun autre package touché (pas de backend/frontend dans cette Epic, cf. Domain Scope).

**Primary Dependencies**: Aucune nouvelle dépendance. Réutilisation intégrale de `pipelines/common/` (`readers.read_native_source` / `read_azure_batches`, `writers.append_to_staging` / `merge_into_curated`, `transforms.enrich_with_envelope` + 2 nouvelles fonctions `dedupe_by_key`/`filter_null_or_empty_key`, `runtime` pour le debug local Databricks Connect) — `databricks-sql-connector`, `azure-identity` déjà présents (mêmes secrets/scope `dcm-secret-scope` que `pipelines/system_tables/`).

**Storage**: Databricks Unity Catalog Delta, `it.ba_data_connect_monitoring__<env>` (dev `__d`), `TBLPROPERTIES ('quality'='gold', 'delta.enableChangeDataFeed'='true')`. Sources : `` `onedatalake-ppd-internal`.egress_firewall_aws.workspace_inventory `` (AWS natif), `` `onedatalake-ppd-internal`.egress_firewall.workspace_inventory `` et `` `catalog_badsdataeng_dev`.`ref_dcm`.`ref_ba_lz` `` (Azure, cross-tenant).

**Testing**: pytest + fakes partagés `tests/conftest.py` (`FakeSpark`, `FakeDataFrame` étendu avec `withColumnRenamed`), sans JVM — même pattern que `tests/system_tables/`. ruff + mypy zéro warning. Nouveau dossier `tests/reference_lz/` (`test_specs.py`, `test_ingest.py`, `test_entrypoint.py`) + tests des 2 nouvelles primitives dans `tests/common/test_transforms.py`.

**Target Platform**: Databricks Jobs — nouveau job wheel `dcm_reference_lz` (compute serverless, `for_each_task`, cron quotidien 04:30 Europe/Paris — après `dcm_system_tables` à 03:00, avant l'heure de bureau).

**Project Type**: Mono-package — `packages/dcm-databricks-pipeline` uniquement (DataEng only, cf. Domain Scope ✅).

**Performance Goals**: Rafraîchissement quotidien best-effort, pas de SLA horaire. Tables petites (référentiel, pas de séries temporelles) — pas de contrainte de lot Azure particulière (`AZURE_BATCH_NARROW`/valeur globale du job suffit, pas de colonnes larges type `request_params`).

**Constraints**: MERGE idempotent 0 doublon au re-run (FR-007, SC-001/SC-002) ; mode full-load, pas de watermark (FR-005) ; déduplication déterministe avant MERGE (FR-009) ; isolation d'échec par table/source, pas de blocage global (FR-010) ; exclusion + log des lignes à clé NULL/vide (FR-011) ; jamais de donnée fictive (P9) — les 2 sources sont interrogées telles quelles, aucun enrichissement inventé.

**Scale/Scope**: 2 tables gold, 1 nouveau module pipeline (3 fichiers), 1 nouvelle ressource bundle, 2 nouvelles primitives génériques dans `pipelines/common/transforms.py`, 1 dossier de tests. Aucun impact backend/frontend/collectors.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principe | Statut | Justification |
|---|---|---|
| P1 Test-First & Code Quality (NON-NEGOTIABLE) | ✅ PASS | `tests/reference_lz/` (specs/ingest/entrypoint) + tests des 2 nouvelles primitives `transforms.py`, fakes partagés sans JVM ; ruff/mypy zéro warning. |
| P2 Simplicité, Explicitness & Versioning | ✅ PASS | Réutilisation du socle `pipelines/common/` plutôt qu'un nouveau framework ; pas de breaking change (nouvelles tables, aucune existante modifiée). |
| P3 Self-Documenting Code | ✅ PASS | Noms explicites (`dedupe_by_key`, `filter_null_or_empty_key`, `ingest_dbx_workspace`, `ingest_business_application`) ; commentaires réservés au *why* (cf. pattern déjà en place dans `system_tables/specs.py`). |
| P4 Fail Fast, Fail Loud | ✅ PASS | Garde-fou `entrypoint.main` (config Azure requise pour `business_application`, FR-004) ; exclusions NULL (FR-011) et déduplication (FR-009) loggées explicitement, jamais silencieuses ; `for_each_task` remonte l'échec par tâche (FR-010) sans l'avaler. |
| P5 Architecture explicite & modularité | ✅ PASS | Nouveau module `pipelines/reference_lz/` isolé, aucune dépendance croisée nouvelle ; aucun appel cross-LZ (lecture cross-tenant via le connecteur existant, même mécanisme que `system_tables`). |
| P6 Idempotency by Design | ✅ PASS | `merge_into_curated` (MERGE par clé métier) ; `dedupe_by_key` rend le choix de ligne déterministe run après run (condition nécessaire à l'idempotence en présence de doublons source, FR-009). |
| P7/P8 Secrets Management (NON-NEGOTIABLE) | ✅ PASS | Aucun nouveau secret : réutilise le secret scope Databricks existant (`dcm-secret-scope`, SP Azure OAuth M2M) déjà câblé pour `system_tables`. |
| P9 No Fake Data in Production (NON-NEGOTIABLE) | ✅ PASS | Les 2 tables reflètent fidèlement les sources réelles (`workspace_inventory`, `ref_ba_lz`) — aucune valeur inventée ; lignes à clé invalide **exclues** (pas remplacées par une valeur factice, FR-011). |
| P10 Observability & Traceability | ⚠️ NOTE | `pipelines/reference_lz/` utilise `logging` stdlib (pas `structlog` JSON) — écart pré-existant uniforme sur `dcm-databricks-pipeline` (déjà noté sur `system_tables`), non introduit ici. |
| P11 Naming Conventions | ⚠️ NOTE | Tables référentiel préfixées `dim_` (pas `raw_`/`curated_`/`gold_`) — cohérent avec un usage de type "table de référence/dimension" hors flux medallion classique (pas de couche raw/curated en amont, source = référentiel externe direct). Écart documenté et volontaire (pas un flux métrique medallion), à confirmer en revue si une convention `dim_reference_*` doit être ajoutée formellement à P11. |
| P12 Medallion — Aggregations on Gold Only | ✅ PASS | Aucune agrégation métier (SUM/AVG/COUNT) : fidèle source, renommage de colonnes uniquement. `dedupe_by_key` utilise `row_number()` pour la **déduplication/ordering**, explicitement permis par P12 (pas un calcul de métrique). |
| P13 Immutable Raw Layer | N/A | Pas de couche Raw dans ce flux — lecture directe des sources référentiel (comme `system_tables`, cf. research.md §1). |
| P14 Schema Versioning | N/A | Tables de référentiel hors `MetricPayload` — pas de `schema_version` applicable (mêmes conventions que les tables `system.*` déjà en place). |
| P15 API Contract Stability | N/A | Aucune route API exposée dans cette Epic (Out of scope). |
| P16 Frontend Quality | N/A | Aucun impact frontend dans cette Epic (Out of scope). |

**P11 (NOTE)** est la seule justification à documenter en Complexity Tracking (pas une violation bloquante, un écart de nommage à faire valider).

### Post-Design Re-check (après Phase 1)

`research.md` (6 décisions, dont 3 issues du `/speckit.clarify` du 2026-08-20 : dédup FR-009, isolation FR-010, filtrage NULL FR-011), `data-model.md` (2 entités + primitives `dedupe_by_key`/`filter_null_or_empty_key`) et `quickstart.md` n'introduisent aucune nouvelle dépendance, aucun nouveau secret, aucune agrégation hors couche Gold, et respectent les 4 décisions de clarification (spelling, dédup, isolation, NULL). **Constitution Check reconfirmé : PASS** (P11 reste une NOTE à valider en revue, pas un blocage).

## Project Structure

### Documentation (this feature)

```text
specs/014-reference-lz-tables/
├── plan.md              # This file (/speckit.plan)
├── research.md          # Phase 0 output — socle réutilisé, dédup/isolation/filtrage NULL, test strategy
├── data-model.md         # Phase 1 output — 2 entités + primitives dedupe_by_key/filter_null_or_empty_key
├── quickstart.md         # Phase 1 output — exécution & validation dev
├── contracts/            # vide — aucune interface externe exposée (pas d'API/UI dans cette Epic)
├── spec.md               # Feature spec (clarifiée — 4 questions/réponses intégrées)
├── intake.json / domain-scope.json
├── checklists/requirements.md
└── tasks.md              # Phase 2 (/speckit.tasks — NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
packages/dcm-databricks-pipeline/
├── pipelines/
│   ├── reference_lz/                  # NEW module
│   │   ├── __init__.py
│   │   ├── specs.py                   # Constantes tables/colonnes source, merge_keys (pas d'IngestionSpec générique — schémas divergents)
│   │   ├── ingest.py                  # ingest_dbx_workspace() (AWS + Azure), ingest_business_application() (Azure seul)
│   │   └── entrypoint.py              # Point d'entrée wheel task (--table), garde-fou azure_config requis pour business_application
│   ├── common/
│   │   └── transforms.py              # EXTENDED — +dedupe_by_key(df, key_columns), +filter_null_or_empty_key(df, *key_columns)
├── resources/
│   └── job_dcm_reference_lz.yml       # NEW — job wheel, for_each_task sur les 2 tables, cron 04:30 Europe/Paris
├── pyproject.toml                     # MODIFIED — +[project.scripts] dcm-reference-lz = "pipelines.reference_lz.entrypoint:run"
└── tests/
    ├── reference_lz/                  # NEW — test_specs.py, test_ingest.py, test_entrypoint.py (fakes tests/conftest.py)
    └── common/test_transforms.py      # EXTENDED — tests dedupe_by_key / filter_null_or_empty_key
```

**Structure Decision**: Mono-package `packages/dcm-databricks-pipeline`. Nouveau module isolé `pipelines/reference_lz/` (ne modifie aucun module `system_tables`/DLT existant) ; seule extension partagée : 2 primitives génériques ajoutées à `pipelines/common/transforms.py` (réutilisables par de futures specs ayant le même besoin de dédup/filtrage NULL avant MERGE). Une seule branche fille (`dataeng/014-reference-lz-tables`, cf. Prerequisites) — changement focalisé, petite PR.

## Complexity Tracking

| Écart | Pourquoi nécessaire | Alternative plus simple rejetée |
|---|---|---|
| P11 (NOTE) — préfixe `dim_` hors convention `raw_`/`curated_`/`gold_` | Ces tables sont des référentiels/dimensions alimentés directement depuis une source externe (pas de flux medallion raw→curated→gold) — le préfixe `dim_` signale ce statut particulier, cohérent avec le vocabulaire dimensionnel (`dim_landing_zone` déjà mentionné dans les Assumptions du spec). | Renommer en `gold_dbx_reference_*` pour coller strictement à P11 — rejeté : masquerait le fait qu'il n'y a ni raw ni curated pour ces tables, information utile pour un futur lecteur du catalog. À valider explicitement en revue (Design Authority si jugé nécessaire). |
