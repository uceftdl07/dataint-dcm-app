# Implementation Plan: Remplacer `dim_landing_zone` par une vue union

**Branch**: `021-dim-landing-zone-view` | **Date**: 2026-09-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/021-dim-landing-zone-view/spec.md`

## Summary

Transformer la dimension `dim_landing_zone` — aujourd'hui **table streaming DLT SCD1** — en **vue Unity Catalog** qui unifie deux périmètres de LZ (celles collectées par DCM + les workspaces référentiels `dim_dbx_workspace`), enrichie par le référentiel Business Application, avec `lz_id` recalculé et déduplication par `subscription_or_account_id`.

Trois changements dans `packages/dcm-databricks-pipeline` :

1. **Renommer** la table DLT `dim_landing_zone` → `dim_landing_zone_collector` (mécanique SCD1 / `apply_changes` inchangée).
2. **Supprimer** les 7 contraintes FK `fk_gold_*_lz … REFERENCES … dim_landing_zone (lz_id)` des tables gold (une vue ne peut pas être cible de FK).
3. **Créer** un module dédié `pipelines/gold_landing_zone/` produisant, via une **tâche wheel** (`CREATE OR REPLACE VIEW`), la vue `dim_landing_zone` — SQL généré par une fonction pure `build_dim_landing_zone_view_sql(catalog, schema)` unit-testable sans cluster.

L'approche **mire feature 020** (`pipelines/gold_dbx_workspace/` : `view.py` pure fn + `entrypoint.py` wheel + job DAB), seul précédent de vue du pipeline.

## Technical Context

**Language/Version**: Python 3.12 (package `dcm-databricks-pipeline`)
**Primary Dependencies**: PySpark / Databricks (DLT pour la couche gold existante, Spark SQL pour la vue), `uv` packaging
**Storage**: Unity Catalog — `it.ba_data_connect_monitoring__<env>` (catalog/schema via `named_parameters` du job, jamais codés en dur)
**Testing**: `pytest` (string-based sur le builder SQL pur ; pas d'exécution Spark en CI)
**Target Platform**: Databricks serverless (tâche wheel) + pipeline DLT existant
**Project Type**: Data pipeline (DataEng mono-package)
**Performance Goals**: dimension faible cardinalité ; vue recalculée à la lecture — acceptable, pas de SLA de matérialisation
**Constraints**: le builder SQL doit rester une fonction pure (pas d'I/O), catalog/schema paramétrés
**Scale/Scope**: 1 module nouveau (3 fichiers) + 1 job DAB + édition de `dlt_03_gold_layer.py` (rename + suppression FK) + tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principe | Statut | Note |
|----------|--------|------|
| P7 — pas de données mockées en prod | ✅ | Vraies tables UC uniquement |
| P8 — pas de secret hardcodé | ✅ | Aucun secret ; catalog/schema via params job |
| P9 — pas d'appel cross-LZ | ✅ | Lecture intra-lakehouse |
| Python 3.12 strict | ✅ | Nouveau module pur, typé |
| Ruff zéro warning | ✅ | Nouveau module clean ; édition DLT jugée sur le baseline existant (module DLT `dlt_0*.py` déjà non-ruff/mypy conforme par nature — `spark` implicite, décorateurs `@dlt.table` non typés — cf. repo memory ; CI ne lance que pytest) |
| Tests obligatoires | ✅ | `tests/gold_landing_zone/test_view.py` + mise à jour `tests/test_dlt_03_gold_layer.py` |
| Imports absolus | ✅ | `from pipelines.gold_landing_zone…` |
| P11 — nommage table | ✅ | Vue `dim_landing_zone` cohérente avec `dim_dbx_workspace` (préfixe `dim_` déjà admis) |

Voir **Complexity Tracking** pour les 2 écarts assumés (tâche wheel hors DLT, `DROP TABLE` de migration).

## Project Structure

### Documentation (this feature)

```text
specs/021-dim-landing-zone-view/
├── spec.md              # Spec (+ Clarifications C1–C4)
├── plan.md              # Ce fichier
├── research.md          # Phase 0 — décisions techniques
├── data-model.md        # Phase 1 — contrat de la vue + table collector + FK
├── quickstart.md        # Phase 1 — validation dev
├── intake.json / domain-scope.json
└── tasks.md             # Phase 2 (/speckit.tasks — PAS créé ici)
```

### Source Code (repository root)

```text
packages/dcm-databricks-pipeline/
├── pipelines/
│   ├── dlt_03_gold_layer.py            # ÉDITÉ : rename dim_landing_zone→_collector,
│   │                                   #         3× dlt.read(...), suppression 7 FK
│   └── gold_landing_zone/              # NOUVEAU module (mirror gold_dbx_workspace)
│       ├── __init__.py
│       ├── view.py                     # build_dim_landing_zone_view_sql(catalog, schema) -> str
│       └── entrypoint.py               # DROP TABLE IF EXISTS + CREATE OR REPLACE VIEW (wheel)
├── resources/
│   └── job_dcm_gold_landing_zone.yml   # NOUVEAU job wheel serverless (cron aval)
├── pyproject.toml                      # ÉDITÉ : [project.scripts] dcm-gold-landing-zone
├── databricks.yml                      # ÉDITÉ : override pause_status dev/dev_local
└── tests/
    ├── gold_landing_zone/test_view.py  # NOUVEAU : assertions string-based
    └── test_dlt_03_gold_layer.py       # ÉDITÉ : dlt.read → dim_landing_zone_collector, FK absentes
```

**Structure Decision** : DataEng mono-package. Le nouveau module `pipelines/gold_landing_zone/` isole la vue (dépend de 3 tables produites par 3 jobs distincts — collector DLT, `dcm_gold_dbx_workspace`, `dcm_reference_lz`), exactement comme `pipelines/gold_dbx_workspace/`.

## Phase 0 — Research

Voir [research.md](research.md). Décisions clés :
- **R1** Vue via tâche wheel `CREATE OR REPLACE VIEW` (pas DLT) — la vue croise des tables DLT et non-DLT.
- **R2** Migration : `DROP TABLE IF EXISTS dim_landing_zone` avant `CREATE VIEW` — l'ancienne table DLT physique bloque sinon la création de la vue homonyme.
- **R3** `dlt.read("dim_landing_zone")` interne (cost/standard_check/security) → `dlt.read("dim_landing_zone_collector")` : ces agrégats DLT lisent la table du pipeline, pas la vue externe.
- **R4** Colonnes héritées (`environment`, `region`, `owner_team`, `onboarded_at`) portées via l'union (NULL castés côté `dim_dbx_workspace`).
- **R5** Ordonnancement : job vue en aval de `dcm_system_tables`, `dcm_reference_lz`, `dcm_gold_dbx_workspace` et de la pipeline gold DLT.

## Phase 1 — Design

Voir [data-model.md](data-model.md) (contrat vue 10 colonnes, table collector, liste des 7 FK supprimées) et [quickstart.md](quickstart.md) (validation dev).

## Complexity Tracking

| Écart | Pourquoi nécessaire | Alternative rejetée |
|-------|---------------------|---------------------|
| Tâche wheel `CREATE OR REPLACE VIEW` hors DLT | La vue croise `dim_landing_zone_collector` (DLT), `dim_dbx_workspace` (vue non-DLT) et `dim_reference_landing_zone_business_application` (non-DLT) ; `dlt.read` ne voit que les datasets du pipeline | Vue DLT `@dlt.view` — impossible de lire des tables hors pipeline ; inliner dans un job existant — couple mal 3 ordonnancements |
| `DROP TABLE IF EXISTS dim_landing_zone` (migration one-off) | Après le rename, l'ancienne table DLT physique subsiste en UC sous le nom `dim_landing_zone` et bloque `CREATE OR REPLACE VIEW dim_landing_zone` (conflit type table/vue) | Laisser le rename seul — la création de vue échouerait ; renommer la vue — casse la substitution transparente voulue (clarif C2) |
