# Implementation Plan: Migration domaine `workflow` — collecteur → system tables `system.lakeflow.*`

**Branch**: `spec/migrate_dcm_workflow_from_collector_to_sys_table` | **Date**: 2026-08-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/013-workflow-sys-tables-migration/spec.md`

**Réf. spike** : [`docs/spike/migration_from_collector_to_sys_table/`](../../docs/spike/migration_from_collector_to_sys_table/) — source de vérité data-model / mapping / impact / étapes (code-vérifié).

**Réf. précédent** : [`specs/012-compute-metrics-ingestion/plan.md`](../012-compute-metrics-ingestion/plan.md) — a étendu le socle d'ingestion `pipelines/system_tables/` (Job PySpark wheel, MERGE idempotent, watermark, backfill 30 j). On réutilise exactement ce socle pour les 3 nouvelles tables `curated_dbx_lakeflow_*`.

## Summary

Remplacer la source de données du domaine `workflow` (observabilité Jobs/Workflows Databricks, epic 009) : passer du collecteur `DatabricksWorkflowCollector` (API REST Jobs 2.2 → raw → curated DLT) aux **system tables Unity Catalog** `system.lakeflow.jobs` / `job_run_timeline` / `job_task_run_timeline`.

L'approche, **en 2 temps** (clarif. Q2), préserve intégralement le **contrat GOLD** (`gold_dbx_workflow_*` × 8, schéma + noms + routes API inchangés) :

1. **CURATED fidèle** — 3 `IngestionSpec` ajoutées au registre `system_tables/specs.py` produisant `curated_dbx_lakeflow_{jobs,job_run_timeline,job_task_run_timeline}` (aucune transformation, MERGE idempotent, watermark).
2. **Vues-pont DLT** — 2 vues de reshaping (`_wf_runs_bridge`, `_wf_task_runs_bridge`, **nommées séparément** des anciennes tables) reproduisant le schéma des anciennes `curated_dbx_workflow_runs` / `_task_runs`, alimentées par agrégation `GROUP BY` du timeline (jamais `qualify row_number()`). Les 8 fonctions gold re-sourcent `dlt.read("curated_dbx_workflow_runs")` → `dlt.read("_wf_runs_bridge")`.
3. **Gate de validation** — comparaison gold ancien vs nouveau sur période commune, collecteur + `curated_dbx_workflow_*` DLT laissés **intacts** jusqu'à validation PO.
4. **Teardown** (PR destructive séparée, post-gate) — retrait `'workflow'` de `valid_domain`, suppression section 9 DLT curated, collecteur `databricks_workflows.py`, modèles `WorkflowRunMetric`/`WorkflowTaskRun`, enums `MetricDomain.WORKFLOW`/`WorkflowRunStatus`/`WorkflowTriggerType` (mapping 100 % SQL, clarif. Q4).
5. **Back/Front NULL-safe** — tolérance aux champs devenus NULL (queue/lag/exec, `workspace_name`, `error_message` réduit), colonne « Attente » masquée par défaut (clarif. Q3), fraîcheur exposée via champ `as_of` réel (clarif. Q5).

## Technical Context

**Language/Version**: Python 3.12 (`>=3.12,<3.13`, borne haute wheels numpy/pandas — cf. `pyproject.toml`), PySpark ; Backend FastAPI 3.12 ; Frontend React 18 + TypeScript.

**Primary Dependencies**: `pyspark>=3.5`, `delta-spark>=3.1`, `databricks-sql-connector==4.2.6` (lecture Azure cross-tenant via SQL Warehouse — même voie que `system.billing`/`system.access`), `azure-identity==1.20.0` (SP OAuth M2M). **Aucune nouvelle dépendance** : le socle `pipelines/common/` (readers, writers `merge_into_curated`, transforms, incremental, models) et `pipelines/system_tables/` sont réutilisés tels quels. Backend : `asyncpg` + Pydantic existants. Frontend : TanStack Query + client API central existants.

**Storage**: Databricks Unity Catalog Delta, `it.ba_data_connect_monitoring__{env}` (dev `__d`, prod `__p`, jamais codé en dur — vars bundle `catalog`/`schema`). Source system tables `system.lakeflow.*` (niveau compte, lues via le SP existant). Pas de synchro Lakebase dans cet Epic.

**Testing**: pytest + pytest-asyncio + chispa (assertions DataFrame Spark) + pytest-cov ; Vitest (frontend) ; ruff + mypy zéro warning (gate CI). Arborescences tests miroir des packages.

**Target Platform**: Databricks Jobs — Job wheel `dcm_system_tables` (curated, cron `0 0 3 * * ?`) + pipeline DLT gold (vues-pont + agrégats). Backend ECS Fargate ; Frontend S3 + CloudFront.

**Project Type**: Multi-package — `packages/dcm-databricks-pipeline` (curated specs + vues-pont + teardown DLT), `packages/dcm-azure-collector` (teardown collecteur), `packages/dcm-commons` (teardown modèles/enums), `packages/dcm-backend` (NULL-safe + `as_of`), `packages/dcm-frontend` (NULL-safe + bandeau fraîcheur).

**Performance Goals**: Rafraîchissement quotidien best-effort (pas de SLA horaire). Latence system tables (quelques heures) assumée et exposée (`as_of`) — pas de « live » temps réel sur `concurrency_1min`/runs `running`. Mémoire driver bornée par le sizing par lots Azure (`AZURE_BATCH_*`) : les 3 nouvelles tables calibrées par largeur de ligne (`job_run_timeline`/`job_task_run_timeline` = timelines étroites → lot large ; `jobs` = maps/tags → lot nested).

**Constraints**: MERGE idempotent 0 doublon au re-run (`merge_into_curated`) ; **reshaping par agrégation `GROUP BY`, jamais `qualify row_number()`** sur les timelines (fausserait `start_time`) — `min(period_start_time)` / `max(period_end_time)` conditionné à `bool_and(period_end_time IS NOT NULL)` / `max_by(col, period_start_time)` ; échec d'accès LZ/workspace ⇒ échec global (fail fast, `max_retries: 0`) ; backfill initial 30 j (clarif. Q1, réutilise `INITIAL_BACKFILL_DAYS = 30`) ; **jamais de donnée fictive** — champ indisponible = `NULL` ; contrat GOLD et routes API **non cassés** (colonnes conservées, valeurs NULL, ajout additif `as_of`).

**Scale/Scope**: 3 tables curated + 2 vues-pont DLT ; 8 tables gold re-sourcées (schéma inchangé) ; 1 collecteur + 2 modèles + 3 enums supprimés ; ~3 services backend + 1 page front (Lakeflow/Jobs N1/N2/N3) rendus NULL-safe. Multi-cloud Azure + AWS via `cloud_provider` (clé anti-collision).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principe | Statut | Justification |
|---|---|---|
| P1 Test-First & Code Quality (NON-NEGOTIABLE) | ✅ PASS | Tests pytest/chispa (curated specs + vues-pont reshaping), tests backend (NULL/`as_of`), Vitest front (fixtures NULL, rendu « n/d ») ; ruff/mypy zéro warning. TDD requis sur le chemin no-fake-data (reshaping). |
| P2 Simplicité, Explicitness (semver + migration) | ✅ PASS | Réutilisation intégrale du socle (`merge_into_curated`, `IngestionSpec`) plutôt qu'un nouveau framework ; migration explicite en 2 temps avec gate (pas de big bang). Ajout `as_of` = minor additif backward-compat. |
| P5 Architecture explicite & modularité | ✅ PASS | Vues-pont isolent le reshaping ; aucune dépendance croisée nouvelle ; **aucun appel cross-LZ** (system tables lues au niveau compte via le SP existant). |
| P6 Idempotency by Design | ✅ PASS | Curated via `merge_into_curated` (MERGE sur clés métier + watermark) ; vues-pont déterministes (GROUP BY). Re-run = 0 doublon (FR, SC). |
| P7/P8 Secrets Management (NON-NEGOTIABLE) | ✅ PASS | Aucun nouveau secret : réutilise le secret scope Databricks existant (SP Azure OAuth M2M) déjà câblé dans `system_tables/entrypoint.py`. Nouveau `GRANT SELECT ON system.lakeflow` = prérequis infra (moindre privilège), pas de secret en code. |
| P9 No Fake Data in Production (NON-NEGOTIABLE) | ✅ PASS | Champs perdus restent **NULL** (jamais 0/valeur inventée) — FR-011, front « n/d ». Gold calculé sur vraies system tables. `as_of` reflète la vraie latence. |
| P10 Observability & Traceability | ⚠️ NOTE | `dcm-databricks-pipeline` utilise `logging` stdlib (pas `structlog` JSON) — écart pré-existant uniforme sur le package, non introduit ici ; on reste cohérent avec `system_tables/` en place. Backend/collector conservent `structlog`. |
| P11 Naming Conventions | ✅ PASS | `curated_dbx_lakeflow_*` (préfixe `dbx`, aligné `curated_dbx_*` existant) ; vues-pont `_wf_*_bridge` (privées, distinctes des anciennes tables — clarif. Q2) ; gold `gold_dbx_workflow_*` inchangé. Aucun nom `Cluster`/`Compliance` legacy introduit. |
| P12 Medallion — Aggregations on Gold Only | ✅ PASS | Les 3 curated restent **fidèles source** (no transform, no join). Le reshaping agrégeant (`GROUP BY`, `count`, `min`/`max`) vit dans les **vues-pont DLT situées dans `dlt_03_gold_layer.py`** (couche Gold) — conforme : les agrégations métier sont sur Gold, pas sur Curated. |
| P13 Immutable Raw Layer | ✅ PASS | Le nouveau flux **bypasse la couche Raw** (system tables = source, comme feature 012). Le retrait de `'workflow'` de `valid_domain` (teardown) supprime une entrée d'un flux abandonné, sans muter d'historique raw existant. |
| P14 Schema Versioning | ✅ PASS | Contrat GOLD versionné inchangé ; colonnes perdues conservées au schéma (NULL) → pas de breaking. `as_of` = ajout additif. |
| P15 API Contract Stability | ✅ PASS | Aucune route supprimée, aucun champ retiré des réponses ; ajout du champ `as_of` (additif). Champs deviennent nullable — types Pydantic `... | None` (à vérifier/aligner). |
| P16 Frontend Quality | ✅ PASS | Colonnes NULL-safe (« n/d », jamais 0), colonne « Attente » masquée par défaut, bandeau fraîcheur ; `app-routes.ts` inchangé ; tests Vitest mis à jour. |

Aucune violation nécessitant une entrée en Complexity Tracking.

### Post-Design Re-check (après Phase 1)

`research.md`, `data-model.md`, `contracts/` et `quickstart.md` n'introduisent aucune nouvelle dépendance, aucun nouveau secret, aucune agrégation hors couche Gold, et respectent le contrat GOLD + les 5 décisions de clarification. **Constitution Check reconfirmé : PASS**.

## Project Structure

### Documentation (this feature)

```text
specs/013-workflow-sys-tables-migration/
├── plan.md              # This file (/speckit.plan)
├── research.md          # Phase 0 output — décisions techniques (system.lakeflow, reshaping, gate)
├── data-model.md        # Phase 1 output — curated_dbx_lakeflow_* + vues-pont + gold (inchangé)
├── quickstart.md        # Phase 1 output — exécution & validation dev
├── contracts/           # Phase 1 output
│   ├── gold-workflow-contract.md   # schémas gold conservés + colonnes NULL
│   └── api-freshness-contract.md   # champ as_of, NULL-tolérance Pydantic, /workspaces
├── spec.md              # Feature spec (clarifiée)
├── intake.json / domain-scope.json
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit.tasks — NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
packages/dcm-databricks-pipeline/
├── pipelines/
│   ├── system_tables/
│   │   ├── specs.py                 # EXTENDED (Story 1) — +3 IngestionSpec lakeflow + entrées SPECS/SPEC_KEYS
│   │   ├── ingest.py / entrypoint.py# reused as-is (génériques)
│   ├── dlt_03_gold_layer.py         # EXTENDED (Story 2) — +2 vues-pont _wf_*_bridge ; 8 gold re-sourcées ; (Story 3 teardown : rien ici)
│   ├── dlt_02_curated_layer.py      # MODIFIED (Story 3 teardown) — suppr. §9 workflow (_stg_dbx_workflow*, curated_dbx_workflow_runs/_task_runs, rejects)
│   ├── dlt_01_raw_layer.py          # MODIFIED (Story 3 teardown) — retrait 'workflow' de valid_domain
│   └── common/                      # REUSED as-is
├── resources/
│   └── job_dcm_system_tables.yml    # EXTENDED (Story 1) — +3 clés dans for_each.inputs (aligné SPEC_KEYS)
└── tests/
    ├── system_tables/               # EXTENDED (Story 1) — test_specs.py (+3 specs), idempotence
    └── (dlt) test_dlt_workflow.py   # MODIFIED (Story 2) — source = reshaping system tables

packages/dcm-azure-collector/        # Story 3 teardown
├── azure_collector/collectors/databricks_workflows.py   # DELETED
├── azure_collector/collectors/__init__.py               # MODIFIED — retrait import/export
├── azure_collector/main.py / config.py                  # MODIFIED — retrait "databricks_workflows"
├── .github/azure-collector-deploy-targets.json          # MODIFIED — retrait enabled_collectors (dev+prod)
└── tests/test_databricks_workflows_collector.py         # DELETED

packages/dcm-commons/                # Story 3 teardown
├── dcm_commons/models/workflow.py                       # DELETED (WorkflowRunMetric, WorkflowTaskRun)
├── dcm_commons/models/__init__.py                       # MODIFIED — retrait imports/exports
├── dcm_commons/models/enums.py                          # MODIFIED — suppr. MetricDomain.WORKFLOW, WorkflowRunStatus, WorkflowTriggerType (clarif. Q4)
└── tests/test_workflow.py                               # DELETED

packages/dcm-backend/                # Story 4 — NULL-safe + as_of
├── app/api/services/lakeflow_jobs.py       # MODIFIED — tolérance NULL (queue/lag/exec, workspace_name, error_message)
├── app/api/services/lakeflow_overview.py   # MODIFIED — as_of (min(_ingested_at)) exposé
├── app/api/routes/databricks.py            # MODIFIED — /workspaces : repli tags/id (gold/curated NULL)
└── tests/ (test_lakeflow_*, test_databricks_workspaces.py)  # MODIFIED — fixtures NULL

packages/dcm-frontend/               # Story 5 — NULL-safe + fraîcheur
├── Lakeflow/Jobs (N1/N2/N3)                # MODIFIED — colonnes NULL-safe, « Attente » masquée, tooltip cron retiré, bandeau as_of
└── *.test.tsx                              # MODIFIED — fixtures NULL, rendu « n/d »
```

**Structure Decision**: Multi-package. Cœur DataEng dans `packages/dcm-databricks-pipeline` (extension additive du socle `system_tables/` pour la curated ; vues-pont + re-sourcing dans le gold DLT ; teardown DLT). Teardown transverse (collecteur, modèles, enums) dans `dcm-azure-collector` + `dcm-commons`. NULL-safety applicative dans `dcm-backend` + `dcm-frontend`. Le contrat GOLD reste le point pivot stable : aucune table gold, route API, ni écran ne disparaît.

## Complexity Tracking

Aucune violation de la constitution à justifier (cf. Constitution Check — tout PASS, N/A, ou NOTE pré-existante non introduite par cet Epic).
