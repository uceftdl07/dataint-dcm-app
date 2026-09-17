# Implementation Plan: Ingestion Compute Metrics (Curated + Gold)

**Branch**: `012-compute-metrics-ingestion` | **Date**: 2026-08-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/012-compute-metrics-ingestion/spec.md`

**Réf. spike** : [`docs/spike/compute-metrics-definition/`](../../docs/spike/compute-metrics-definition/) (data model + mapping, mis à jour avec la convention `gold_dbx_compute_*`).

**Réf. précédent** : [`specs/010-databricks-usage-finops-curated/plan.md`](../010-databricks-usage-finops-curated/plan.md) — a livré le socle d'ingestion `pipelines/system_tables/` (Job PySpark, no DLT) et les 5 premières tables `curated_dbx_*`, dont `curated_dbx_compute_clusters`/`curated_dbx_compute_node_timeline` déjà réutilisées ici.

## Summary

Étendre le socle d'ingestion `pipelines/system_tables/` existant avec 3 nouvelles tables curated (warehouses, warehouse_events, node_types), puis construire un **nouveau module Job PySpark** `pipelines/gold_dbx_compute/` qui agrège quotidiennement ces tables curated (+ celles déjà existantes : `curated_dbx_compute_clusters`, `curated_dbx_billing_usage`, `curated_dbx_query_history`, etc.) en 9 tables gold (4 clusters + 3 warehouses + 2 transverses réactif/prédictif), suivant la convention de nommage `gold_dbx_compute_*` / `gold_dbx_compute_warehouse_*` actée en clarification. Aucune DLT, aucune modification du pipeline collecteur SQS existant (`dlt_01/02/03_layer.py`) : approche disjointe, alignée sur la décision technique de la feature 010 (E5).

## Technical Context

**Language/Version**: Python 3.12 (`>=3.12,<3.13`, borne haute imposée par les wheels numpy/pandas — cf. `pyproject.toml`), PySpark

**Primary Dependencies**: `pyspark>=3.5`, `delta-spark>=3.1`, `databricks-sql-connector==4.2.6` (lecture Azure cross-tenant via SQL Warehouse, réutilisé tel quel), `azure-identity==1.20.0` (SP OAuth M2M, réutilisé). **Aucune nouvelle dépendance** requise pour cet Epic — le socle `pipelines/common/` (readers, writers, transforms, incremental, models) est entièrement réutilisé.

**Storage**: Databricks Unity Catalog Delta tables, `it.ba_data_connect_monitoring__{env}` (dev `__d`, prod `__p`, jamais codé en dur — vars bundle `catalog`/`schema`). Pas de synchronisation Lakebase PostgreSQL dans cet Epic (hors scope — cf. spec.md "Out of scope").

**Testing**: pytest + pytest-asyncio + chispa (assertions DataFrame Spark) + pytest-cov ; ruff + mypy zéro warning (gate CI). Arborescence tests miroir de `pipelines/` (convention existante du package).

**Target Platform**: Databricks Jobs (environnement serverless, Databricks Asset Bundle `databricks.yml` + `resources/*.yml`), planification cron quotidienne (`quartz_cron_expression`).

**Project Type**: Projet unique — package `packages/dcm-databricks-pipeline` (extension du plugin existant `pipelines/system_tables/` + nouveau plugin `pipelines/gold_dbx_compute/`, tous deux consommant le socle générique `pipelines/common/`).

**Performance Goals**: Rafraîchissement quotidien best-effort, sans SLA horaire strict (cf. Clarifications spec.md). Mémoire driver bornée via le sizing existant des lots Azure (`AZURE_BATCH_*`), à calibrer pour les 3 nouvelles tables curated selon leur largeur/volumétrie (même méthode que les tables existantes).

**Constraints**: MERGE idempotent (0 doublon au re-run — réutilise `merge_into_curated`) ; échec d'accès à une LZ/workspace ⇒ échec de l'intégralité du run (fail fast global, `max_retries: 0`, pas de swallow d'exception) ; backfill initial 30 jours pour la couche curated (réutilise la constante existante `INITIAL_BACKFILL_DAYS = 30` de `system_tables/specs.py`) ; couche gold `*_daily` calculée en **full** au premier run puis en **incrémental (fenêtre 3 jours, watermark `period_start`)** ensuite (FR-018, cf. research.md R9) ; périmètre multi-cloud Azure + AWS via `cloud_provider` (réutilise le pattern AWS natif + Azure JDBC existant) ; convention de nommage `gold_dbx_compute_*` / `gold_dbx_compute_warehouse_*` (préfixe `dbx` pour distinguer du domaine `compute` générique DLT existant `gold_compute_utilization`).

**Scale/Scope**: 3 nouvelles tables curated + 9 nouvelles tables gold (4 clusters + 3 warehouses + 2 transverses), multi-LZ / multi-cloud (Azure + AWS), grain jour × objet compute (cluster ou warehouse).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principe | Statut | Justification |
|---|---|---|
| P1 Test-First & Code Quality | ✅ PASS | Tests pytest/chispa planifiés en miroir de `pipelines/gold_dbx_compute/` (mêmes conventions que `tests/system_tables/`) ; ruff/mypy zéro warning (gate CI existant). |
| P2 Simplicité, Explicitness | ✅ PASS | Réutilisation du socle générique existant (`merge_into_curated`, `IngestionSpec`-like specs) plutôt qu'un nouveau framework ; pas de DLT ajouté (YAGNI — la feature 010 a déjà tranché ce point, E5). |
| P5 Architecture explicite & modularité | ✅ PASS | Nouveau plugin `pipelines/gold_dbx_compute/` séparé de `system_tables/` et de `dlt_*` (aucune dépendance croisée) ; pas d'appel cross-LZ direct (system tables lues au niveau compte via le SP existant, jamais LZ→LZ). |
| P6 Idempotency by Design | ✅ PASS | Toutes les écritures (curated ET gold) passent par `merge_into_curated` (MERGE sur clés métier) — FR-014. |
| P7/P8 Secrets Management (NON-NEGOTIABLE) | ✅ PASS | Aucun nouveau secret : réutilise le secret scope Databricks existant (SP Azure OAuth M2M) déjà câblé dans `entrypoint.py`. |
| P9 No Fake Data (NON-NEGOTIABLE) | ✅ PASS | Toutes les tables gold sont calculées à partir de vraies system tables Databricks (curated réel) — FR-014, SC-006. |
| P11 Naming Conventions | ✅ PASS | `curated_dbx_*` (déjà conforme) ; nouvelles tables gold `gold_dbx_compute_*`/`gold_dbx_compute_warehouse_*` — FR-015, tranché en clarification (Q2). |
| P12 Aggregations on Gold Only | ✅ PASS | Les 3 nouvelles tables curated restent fidèles source (no transform, no join — pattern `system_tables` existant) ; toutes les agrégations (SUM/AVG/percentile/rank) sont dans `pipelines/gold_dbx_compute/`. |
| P13 Immutable Raw Layer | N/A | Aucune couche Raw dans cet Epic (les system tables Databricks sont la source, pas un volume d'ingestion). |
| P10 Observability & Traceability | ⚠️ NOTE | Le package `dcm-databricks-pipeline` utilise `logging` stdlib (pas `structlog` JSON) de façon uniforme sur tout le pipeline existant — écart pré-existant, non introduit par cet Epic ; on reste cohérent avec le module `system_tables/` déjà en place plutôt que d'introduire une divergence de logging au sein du même package. |

Aucune violation nécessitant une entrée dans Complexity Tracking.

### Post-Design Re-check (après Phase 1)

`data-model.md`, `contracts/gold-tables-contract.md` et `quickstart.md` ne introduisent aucune nouvelle dépendance, aucun nouveau secret, aucune agrégation en dehors de la couche Gold, et respectent la convention de nommage tranchée (R2). **Constitution Check reconfirmé : PASS** — aucun changement de posture après le design de Phase 1.

## Project Structure

### Documentation (this feature)

```text
specs/012-compute-metrics-ingestion/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
packages/dcm-databricks-pipeline/
├── pipelines/
│   ├── system_tables/                 # EXTENDED (Story 1 / T001)
│   │   ├── specs.py                   # + WAREHOUSES_SPEC, WAREHOUSE_EVENTS_SPEC, NODE_TYPES_SPEC + entrées SPECS/SPEC_KEYS
│   │   ├── ingest.py                  # reused as-is (générique, aucune modif)
│   │   └── entrypoint.py              # reused as-is (générique, aucune modif)
│   ├── gold_dbx_compute/              # NEW (Stories 2-4 / T002-T004)
│   │   ├── __init__.py
│   │   ├── specs.py                   # registre des agrégations gold : source curated -> table gold, grain, clés ; watermark_column="period_start", initial_mode="full", incremental_lookback_days=3 (FR-018, research.md R9)
│   │   ├── cluster_metrics.py         # T002 — gold_dbx_compute_cluster_{cost,efficiency,reliability}_daily + governance
│   │   ├── warehouse_metrics.py       # T003 — gold_dbx_compute_warehouse_{cost,utilization,query_performance}_daily
│   │   ├── recommendations.py         # T004 — gold_dbx_compute_recommendations (moteur de règles réactif)
│   │   ├── forecast.py                # T004 — gold_dbx_compute_forecast_daily (ai_forecast)
│   │   └── entrypoint.py              # point d'entrée wheel (python_wheel_task), miroir de system_tables/entrypoint.py
│   └── common/                        # REUSED as-is: readers, writers (merge_into_curated), transforms, incremental, models
├── resources/
│   ├── job_dcm_system_tables.yml      # EXTENDED: `inputs` du for_each_task += 3 nouvelles clés de table
│   └── job_dcm_gold_dbx_compute.yml   # NEW: Job Databricks quotidien orchestrant les tâches gold_dbx_compute
└── tests/
    ├── system_tables/                 # EXTENDED: test_specs.py (+3 specs) ; test_ingest.py/test_entrypoint.py reused (génériques)
    └── gold_dbx_compute/               # NEW: test_specs.py, test_cluster_metrics.py, test_warehouse_metrics.py, test_recommendations.py, test_forecast.py
```

**Structure Decision**: Projet unique (pas de frontend/backend dans cet Epic). Extension du plugin existant `pipelines/system_tables/` pour les 3 nouvelles tables curated (Story 1), et création d'un nouveau plugin `pipelines/gold_dbx_compute/` pour les 9 tables gold (Stories 2-4), tous deux consommant le socle partagé `pipelines/common/` sans le modifier. Aucune table DLT (`dlt_01/02/03_layer.py`) touchée — pipeline disjoint, conformément à la décision E5 de la feature 010.

## Complexity Tracking

Aucune violation de la constitution à justifier (cf. Constitution Check ci-dessus — tout PASS ou N/A).
