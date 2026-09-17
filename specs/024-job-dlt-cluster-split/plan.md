# Implementation Plan: Séparation compute Job cluster / DLT vs All-purpose

**Branch**: `dataeng/024-…` → `backend/024-…` → `frontend/024-…` | **Date**: 2026-09-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/024-job-dlt-cluster-split/spec.md`
· Spike: [docs/spike/job-dlt-cluster-separation/proposition.md](../../docs/spike/job-dlt-cluster-separation/proposition.md)

**Réf. socle réutilisé** :
- [`pipelines/gold_dbx_compute/job_cluster_cost_daily.py`](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/job_cluster_cost_daily.py) — **modèle de référence** du rollup à maille métier : résolution `cluster_id → job_id` via `curated_dbx_lakeflow_job_task_run_timeline.compute` (`INNER JOIN` volontaire, clé de merge null-safe), `jobs_as_of` (`change_time < period_start + INTERVAL 1 DAY`), avertissement anti-double-comptage avec `cluster_cost_daily`.
- [`pipelines/gold_dbx_compute/job_cluster_cost_rolling.py`](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/job_cluster_cost_rolling.py) — **modèle exact** du `*_rolling` DLT : `anchor`/`windows`/`latest_attrs`/`agg`, `cost_usd_prev_window`, `RANK()`, filtre `cost_usd <> 0 OR cost_usd_prev_window <> 0`.
- [`pipelines/gold_dbx_compute/cluster_cost_rolling.py`](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_cost_rolling.py) — CTE `daily` où s'injecte le filtre `cluster_type = 'ALL_PURPOSE'` (la colonne `cluster_type` y est déjà lue).
- [`pipelines/gold_dbx_compute/cluster_governance.py`](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_governance.py) — `governance_applies = (cluster_type = 'ALL_PURPOSE')` **existe déjà** ; il reste à borner le snapshot lui-même aux `ALL_PURPOSE` (décision C2).
- [`pipelines/gold_dbx_compute/forecast.py`](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/forecast.py) — `WHERE cluster_type != 'JOB'` sur les 2 passes CLUSTER (cost/dbu + cpu), passe `job_cost_and_dbu_forecast` déjà présente ; point d'ajout de la passe `pipeline_cost_and_dbu_forecast` + généralisation de l'exclusion à PIPELINE.
- [`pipelines/gold_dbx_compute/specs.py`](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py) — `GoldAggregationSpec`, `GOLD_SPECS`, `ROLLING_WINDOWS`, `TOP_COST_RANK_THRESHOLD`, `GOLD_JOB_CLUSTER_COST_*` : point d'ajout des `GOLD_PIPELINE_COST_*` (jamais modifier une entrée existante, cf. merge-strategy 012).
- [`pipelines/system_tables/specs.py`](../../packages/dcm-databricks-pipeline/pipelines/system_tables/specs.py) — bloc `Workflow : Jobs/Lakeflow` (l.370-466) + registre `SPECS` (l.624) : modèle `IngestionSpec` pour ajouter `system.lakeflow.pipelines`.
- [`app/api/services/compute_metrics_clusters.py`](../../packages/dcm-backend/app/api/services/compute_metrics_clusters.py) — `cluster_type` n'est aujourd'hui qu'un `column_filter` optionnel ; il devient un prédicat dur `ALL_PURPOSE`. **Modèle** des nouveaux services job/pipeline (fenêtre, `_window_*`, `_normalize_prev_cost`).
- [`app/api/services/compute_metrics_warehouses.py`](../../packages/dcm-backend/app/api/services/compute_metrics_warehouses.py) — **modèle** d'un service compute à maille non-cluster branché sur une famille `*_rolling` dédiée.
- [`src/app-routes.ts`](../../packages/dcm-frontend/src/app-routes.ts) (`/databricks/cluster`, `/databricks/sql-warehouse`), [`src/config/navigation.ts`](../../packages/dcm-frontend/src/config/navigation.ts) (groupe Compute), [`src/config/role-permissions.ts`](../../packages/dcm-frontend/src/config/role-permissions.ts) (`page:databricks`), [`src/lib/databricks/routes.ts`](../../packages/dcm-frontend/src/lib/databricks/routes.ts) (`PREDEFINED_WINDOW_ROUTES`), [`src/pages/ComputeClusters.tsx`](../../packages/dcm-frontend/src/pages/ComputeClusters.tsx) — modèle de page Compute.

## Summary

Trois branches filles, une par domaine, en cascade stricte **DataEng → Backend → Frontend**.
La branche DataEng est elle-même séquencée en 4 PR pour rester en petits diffs.

**T001 — DataEng (4 PR séquentielles).**

1. **T001a — purge des tables de liste.** Injecter `WHERE cluster_type = 'ALL_PURPOSE'`
   dans la CTE `daily` de `cluster_cost_rolling.py` et `cluster_efficiency_rolling.py`
   (la colonne `cluster_type` y est déjà projetée), et borner le snapshot
   `cluster_governance.py` aux `ALL_PURPOSE` (au-delà de `governance_applies`, décision
   C2 — la gouvernance des éphémères est abandonnée). `forecast.py` : généraliser
   `cluster_type != 'JOB'` en `cluster_type NOT IN ('JOB', 'PIPELINE')` sur les 2 passes
   CLUSTER (cost/dbu + cpu). Aucune table nouvelle, aucune source nouvelle : purge pure.
   Les `*_daily` restent **inchangées** (elles portent tous les types — sources des rollups
   job/pipeline et du forecast).

2. **T001b — ingestion `system.lakeflow.pipelines`.** Ajouter `CURATED_LAKEFLOW_PIPELINES`
   / `SOURCE_LAKEFLOW_PIPELINES` / `LAKEFLOW_PIPELINES_SPEC` (IngestionSpec SCD, calquée
   sur `LAKEFLOW_JOBS_SPEC`) et l'entrée `"lakeflow_pipelines"` du registre `SPECS`.
   Fournit `pipeline_name` (fallback `dlt_pipeline_id`). Prérequis du nom lisible DLT.

3. **T001c — rollup DLT.** Créer `pipeline_cost_daily.py` (grain
   `(cloud_provider, workspace_id, dlt_pipeline_id, period_start)`) et
   `pipeline_cost_rolling.py` (grain `+ window_days`), miroirs exacts des builders job.
   Enregistrer `GOLD_PIPELINE_COST_DAILY` / `_ROLLING` (specs + merge keys) et câbler
   l'`entrypoint.py`. **Anti-double-comptage** : rollup des mêmes lignes de facturation
   que `cluster_cost_daily` restreint `cluster_type = 'PIPELINE'` — jamais sommé avec.

4. **T001d — forecast/reco PIPELINE.** Ajouter la passe `ai_forecast`
   `pipeline_cost_and_dbu_forecast` (source `pipeline_cost_daily`, `object_type = 'PIPELINE'`,
   métriques `cost_usd` + `dbu_quantity` uniquement — décision C4). `recommendations.py` :
   aucune règle nouvelle au grain pipeline (gouvernance abandonnée, pas d'efficacité DLT) —
   la seule garantie est que le grain CLUSTER n'émet plus de reco éphémère, déjà acquise
   par la purge T001a (les `*_rolling` cluster ne contiennent plus que `ALL_PURPOSE`).

**T002 — Backend.** Durcir `cluster_type = 'ALL_PURPOSE'` en prédicat dur sur les services
cluster (liste + gouvernance), et exposer **deux** familles compute jusqu'ici sans endpoint :
`compute_metrics_jobs.py` (grain `job_id`, lit `gold_dbx_compute_job_cluster_cost_rolling`)
et `compute_metrics_pipelines.py` (grain `dlt_pipeline_id`, lit
`gold_dbx_compute_pipeline_cost_rolling`), calqués sur `compute_metrics_warehouses.py`.
Étendre le forecast/reco à `object_type = PIPELINE`. Schémas dcm-commons associés.

**T003 — Frontend.** Nav Compute à 3 onglets : la page Clusters existante (`ComputeClusters`,
`/databricks/cluster`) purgée de fait par le backend, plus **deux pages neuves**
`ComputeJobs` (`/databricks/job-compute`) et `ComputePipelines` (`/databricks/pipeline-compute`),
chacune branchée sur son endpoint via un hook TanStack Query et un client central, avec
forecast/reco par famille. Entrées `navigation.ts` + `role-permissions.ts` + allowlists
`routes.ts` / `focus-routes.ts`.

### Amendement 2026-09-09 — second lot, même cascade DataEng → Backend → Frontend

T001–T003 livrées, les pages Jobs / Pipelines n'ont que 2 sous-onglets et des lignes inertes.
Trois tasks supplémentaires apportent l'efficacité et le drill-down à ces deux grains.

**T004 — DataEng (2 PR séquentielles).**

1. **T004a — efficacité job.** Créer `job_efficiency_daily.py` (grain
   `(cloud_provider, workspace_id, job_id, period_start)`) et `job_efficiency_rolling.py`
   (`+ window_days`) par agrégation de `gold_dbx_compute_cluster_efficiency_daily` filtré
   `cluster_type = 'JOB'`, avec la résolution `cluster_id → job_id` **déjà écrite** dans
   `job_cluster_cost_daily.py` (CTE `job_clusters`) — **à factoriser en helper partagé**,
   pas à recopier. Enregistrer les 4 entrées `specs.py` et câbler `entrypoint.py`.
2. **T004b — efficacité pipeline.** Idem pour `cluster_type = 'PIPELINE'`. La résolution
   `cluster_id → dlt_pipeline_id` est **tranchée par R7** (mesurée le 2026-09-09) : couples
   distincts depuis `curated_dbx_billing_usage`, 99,84 % de couverture, unicité vérifiée, et
   accord sans divergence avec `system.lakeflow.pipeline_update_timeline` sur 61 826 clusters.
   Même source que le coût, donc pas d'attribution contradictoire possible.

**T005 — Backend.** `compute_metrics_jobs.py` / `compute_metrics_pipelines.py` gagnent
`fetch_jobs_efficiency` / `fetch_pipelines_efficiency`, `fetch_job_detail` /
`fetch_pipeline_detail` (blocs `cost` + `efficiency`, **sans** `governance`) et les tendances
`cost-trend` (depuis `*_cost_daily`) / `uptime-trend` (depuis `*_efficiency_daily`). Les
helpers `_uptime_delta_pct` / `_idle_delta_pts` descendent de `compute_metrics_clusters.py`
vers `compute_metrics_common.py`. **Piège d'ordre de déclaration** : `/jobs/efficiency` doit
précéder `/jobs/{job_id}`, sinon le segment variable avale `efficiency`.

**T006 — Frontend.** `ComputeCostGrainTabKey` passe à
`'overview' | 'cost' | 'efficiency'` (`compute-cost-tabs.tsx`, docstring à corriger : elle
affirme aujourd'hui que ces grains n'ont pas de signal d'utilisation en gold). `ComputeJobs`
et `ComputePipelines` gagnent le sous-onglet Efficiency (colonnes + KPI cards) et
`onRowClick` sur les 3 tableaux, ouvrant `ComputeJobDrawer` / `ComputePipelineDrawer`
(neufs, calqués sur `compute-cluster-drawer.tsx` moins le bloc gouvernance).

## Technical Context

**Language/Version**: Python 3.12 (pipeline + backend), TypeScript 5 / React 18 (frontend).

**Primary Dependencies**: aucune nouvelle dans les trois packages. Pipeline : `pyspark` +
`pipelines/common/` (writers `merge_into_table`, `IngestionSpec`) ; `ai_forecast` via
Statement Execution (`databricks.sdk`) déjà en place dans `forecast.py`. Backend : FastAPI
+ `DatabricksWarehousePool`. Frontend : React Query + composants `compute-*`.

**Storage**: Unity Catalog `it.ba_data_connect_monitoring__<env>` (dev `__d`, prod `__p`).
Tables **écrites** neuves : `curated_dbx_lakeflow_pipelines`,
`gold_dbx_compute_pipeline_cost_daily`, `gold_dbx_compute_pipeline_cost_rolling` ; puis, par
l'amendement (T004) : `gold_dbx_compute_job_efficiency_daily`/`_rolling` et
`gold_dbx_compute_pipeline_efficiency_daily`/`_rolling`. Tables
**modifiées** (filtre `ALL_PURPOSE`) : `gold_dbx_compute_cluster_cost_rolling`,
`..._cluster_efficiency_rolling`, `..._cluster_governance`. Table **modifiée** (nouvelle
projection PIPELINE) : `gold_dbx_compute_forecast_daily`. Tables **lues** par le backend
après T002 : `..._cluster_*_rolling`/`_governance` (ALL_PURPOSE), `..._job_cluster_cost_rolling`,
`..._pipeline_cost_rolling`, `..._recommendations`, `..._forecast_daily`, `dim_dbx_workspace`.

**Testing**: pipeline → `pytest` avec `FakeSpark` (assertions sur le SQL généré, aucune
JVM ; cf. `tests/gold_dbx_compute/test_job_cluster_cost.py`, `test_forecast.py`,
`tests/system_tables/`). Backend → `pytest` (`tests/test_compute_metrics_services.py`,
`tests/test_compute_metrics_routes.py`). Frontend → `vitest` + fixtures MSW
(`src/test/fixtures/compute-*.ts`).

**Target Platform**: Databricks Jobs (wheel task) pour T001 — `job_dcm_system_tables.yml`
(ingestion) et `job_dcm_gold_dbx_compute.yml` (gold) ; API FastAPI et SPA React pour le reste.

**Project Type**: multi-package — 3 branches filles, une par package.

**Performance Goals**: la page Clusters cesse de matérialiser/servir des centaines de
`cluster_id` éphémères (le filtre `ALL_PURPOSE` s'applique **en gold**, pas au runtime API).
`pipeline_cost_rolling` est une lecture d'une ligne par `(dlt_pipeline_id, window_days)`,
comme le module job. `ai_forecast` gagne une 6ᵉ passe (PIPELINE), bornée par
`FORECAST_OBSERVED_LOOKBACK_DAYS` comme les autres.

**Constraints**:
- **Clé de merge jamais NULL** : le rollup DLT groupe par `dlt_pipeline_id` ; toute ligne
  de facturation PIPELINE sans `dlt_pipeline_id` résolvable est **exclue** (jamais fusionnée
  en une ligne `NULL` corrompue — même piège null-safe que `job_id` dans `job_cluster_cost_daily`).
- **Anti-double-comptage** : `pipeline_cost_daily` est un rollup des mêmes lignes de
  facturation que `cluster_cost_daily` (`cluster_type = 'PIPELINE'`) ; les deux ne se
  somment jamais. Vérifié par SC-003 (égalité des sommes `cost_usd`).
- **Maintenance DLT incluse** (C3) : le coût des clusters `PIPELINE_MAINTENANCE` est rattaché
  au `dlt_pipeline_id` parent. C'est la contrainte qui pilote le choix de source du rollup
  (cf. Research R2 / Complexity) : la source retenue doit couvrir maintenance **et** update
  pour que SC-003 tienne.
- **`cluster_type = 'ALL_PURPOSE'` en prédicat dur** côté backend : plus un `column_filter`
  optionnel qui, non fourni, laissait fuiter JOB/PIPELINE (cause racine de la pollution).
- **Forecast PIPELINE = `cost_usd` + `dbu_quantity` seulement** (C4) : pas de `cpu_util_p95_pct`
  (pas de table d'efficacité au grain pipeline — hors scope), miroir exact du grain JOB.
- **Gouvernance des éphémères abandonnée** (C2) : `cluster_governance` ne liste plus que les
  `ALL_PURPOSE` ; aucun rollup gouvernance au grain `job_id` / `dlt_pipeline_id`.
- Backend continue de ne lire que du gold + dimensions (`rg "curated_dbx" app/api/services/`
  reste vide) — frontière médaillon.

Contraintes ajoutées par l'amendement (T004–T006) :

- **`cluster_efficiency_daily` reste non filtrée** : c'est la source de T004. Le filtre
  `ALL_PURPOSE` de T001a ne borne que le `_rolling`. Un futur filtre sur le `daily`
  supprimerait l'efficacité job/pipeline — à écrire dans le docstring des nouveaux builders.
- **Percentiles jamais moyennés** : `cpu_util_p95_pct` / `mem_util_p95_pct` au grain stable
  sont recalculés depuis les histogrammes sommés (`sum_histograms_sql` +
  `percentile_from_histogram_sql`). Les moyennes et `idle_pct` sont pondérés par
  `uptime_hours`. Même règle que `cluster_efficiency_rolling`.
- **`LEFT JOIN prev_agg` avec `window_days` dans la condition** : l'omettre multiplie chaque
  ligne de sortie par le nombre de fenêtres (4). Piège déjà commenté dans le builder cluster.
- **Pas de `is_zombie` au grain éphémère** (R8) : la colonne serait `false` partout et se
  lirait comme un contrôle qui passe. Ne pas la produire plutôt que la produire vide.
- **Population efficacité ⊂ population coût** : les pipelines serverless n'ont pas de
  `node_timeline`. L'écart est mesuré (SC-005) et documenté, jamais comblé par une valeur par
  défaut (P9). Côté UI, bloc `efficiency` absent → « — », pas `0`.
- **Aucun bloc gouvernance** dans les détails job/pipeline (C2 inchangé) : clé absente du
  payload, pas `null`.

**Scale/Scope**: T001a = 4 builders modifiés + tests. T001b = `system_tables/specs.py`
(+1 spec, +1 entrée registre) + 1 fichier de tests. T001c = 2 builders neufs
(`pipeline_cost_daily.py`, `pipeline_cost_rolling.py`) + `specs.py` (+2 specs) +
`entrypoint.py` + 2 fichiers de tests. T001d = `forecast.py` (+1 passe) + tests. T002 =
3 services (clusters durci, 2 neufs) + 1 module de routes + dcm-commons (schémas job/pipeline)
+ 2 fichiers de tests. T003 = 2 pages neuves + hooks + client + types + nav/perm/allowlists
+ fixtures + tests. **T004** = 4 builders neufs + 1 helper de résolution factorisé +
`specs.py` (+4 specs) + `entrypoint.py` + 2 fichiers de tests. **T005** = 2 services étendus
(6 `fetch_*` neufs) + `compute_metrics_common.py` + 6 routes + dcm-commons + 2 fichiers de
tests. **T006** = 1 composant partagé modifié (`compute-cost-tabs`), 2 tiroirs neufs, 2 pages
étendues, hooks/client/types/fixtures + tests.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principe | Statut | Justification |
|---|---|---|
| P1 Test-First & Code Quality (NON-NEGOTIABLE) | ✅ PASS | Tests avant code : SQL généré (purge, rollup DLT, forecast, ingestion), services + routes (backend), rendu + hooks (frontend). Gates lint/types/tests par package. |
| P2 Simplicité, Explicitness & Versioning | ✅ PASS | Le rollup DLT **réutilise** le patron job (mêmes CTE, mêmes helpers `rolling_windows_array_sql`, `ROLLING_WINDOWS`, `TOP_COST_RANK_THRESHOLD`). Les helpers de fenêtre backend descendent dans `compute_metrics_common.py` plutôt que d'être dupliqués sur job + pipeline. |
| P3 Self-Documenting Code | ✅ PASS | `pipeline_cost_*` reçoivent `column_comments` + docstrings sur le *pourquoi* : exclusion `dlt_pipeline_id NULL`, anti-double-comptage, inclusion maintenance, source retenue. Le commentaire existant de `cluster_type` (specs.py) décrit déjà PIPELINE. |
| P4 Fail Fast, Fail Loud | ✅ PASS | `dlt_pipeline_id` NULL → ligne exclue (jamais de clé NULL). Backend : `object_type` inconnu → 422. Écart pré-existant des `fetch_*` (soft-fail) non introduit ici. |
| P5 Architecture explicite & modularité | ✅ PASS | Purge et rollup **en gold** ; le backend continue de lire uniquement gold + `dim_dbx_workspace`. `pipeline_name` résolu en gold (via curated ingéré), jamais en lecture curated côté API. |
| P6 Idempotency by Design | ✅ PASS | `pipeline_cost_*` héritent des `merge_keys` explicites ; `*_rolling` = snapshots complets rejouables. Ingestion pipelines = SCD idempotente (`LAKEFLOW_PIPELINES_MERGE_KEYS`). |
| P7/P8 Secrets Management (NON-NEGOTIABLE) | ✅ PASS | Aucun secret touché. Déploiement pipeline via bundle + OAuth (`databricks auth login`) — jamais de PAT. |
| P9 No Fake Data in Production (NON-NEGOTIABLE) | ✅ PASS | `pipeline_name` vient du curated réel (`system.lakeflow.pipelines`), fallback `dlt_pipeline_id`, jamais inventé. Coût DLT = vraies lignes de facturation. Fixtures cantonnées à `src/test/`. |
| P10 Observability & Traceability | ⚠️ NOTE | `logging` stdlib côté pipeline/backend — écart pré-existant et uniforme, non introduit ici. |
| P11 Naming Conventions | ✅ PASS | `pipeline_cost_daily`/`_rolling`, `curated_dbx_lakeflow_pipelines`, `dlt_pipeline_id`, `object_type = 'PIPELINE'` : mêmes conventions que job/warehouse. `CheckEffect`/`StandardCheck` non concernés. |
| P12 Medallion — Aggregations on Gold Only | ✅ PASS | Cœur du plan : purge et rollup sont des agrégations gold ; l'API les lit, ne recalcule rien. Le forecast lit les `*_daily` gold, jamais le curated. |
| P13 Immutable Raw Layer | N/A | Pas de couche Raw dans ce flux. |
| P14 Schema Versioning | N/A | Tables gold/curated hors `MetricPayload`. |
| P15 API Contract Stability | ⚠️ NOTE | **Ajouts** : endpoints job-compute et pipeline-compute, `object_type = PIPELINE` sur forecast/reco. **Changement de comportement assumé et tracé** : la liste clusters ne renvoie plus JOB/PIPELINE (but explicite de la feature) — les cartes cliquables/liens éventuels vers un `cluster_id` éphémère doivent pointer vers les nouvelles pages job/pipeline. |
| P16 Frontend Quality | ✅ PASS | 2 pages typées calquées sur `ComputeClusters`, client central + hooks TanStack Query, états vides réutilisés, tests vitest + fixtures MSW. |

**Verdict** : PASS. Deux `⚠️ NOTE` (P10 pré-existant, P15 rupture assumée et tracée),
aucune sur un principe NON-NEGOTIABLE.

### Constitution Check — amendement (T004–T006)

Seuls les principes dont la lecture change sont réévalués ; les autres sont inchangés.

| Principe | Statut | Justification |
|---|---|---|
| P1 Test-First (NON-NEGOTIABLE) | ✅ PASS | Tests avant code aux 3 niveaux : SQL généré des 4 builders (pondération, histogrammes, jointure `prev_agg` avec `window_days`), services + routes (dont l'ordre `efficiency` avant `{id}` et le 404), rendu des 3 onglets + clic → tiroir + `efficiency` absente → « — ». |
| P2 Simplicité & réutilisation | ✅ PASS | Les 4 builders réutilisent `sum_histograms_sql` / `percentile_from_histogram_sql` / `rolling_windows_array_sql` ; la résolution `cluster_id → job_id` est **factorisée** depuis `job_cluster_cost_daily` au lieu d'être recopiée ; `_uptime_delta_pct` / `_idle_delta_pts` descendent en commun. |
| P3 Self-Documenting | ✅ PASS | Docstrings sur le *pourquoi* : pourquoi pas de `is_zombie`, pourquoi les p95 viennent des histogrammes, pourquoi `cluster_efficiency_daily` ne doit pas être filtrée, pourquoi `uptime-trend` ≠ `lifetime-trend`. |
| P4 Fail Fast | ✅ PASS | Clé de merge NULL exclue (jamais fusionnée) ; id hors périmètre → 404, pas un 200 vide ; `window_days` hors énumération → 422. |
| P9 No Fake Data (NON-NEGOTIABLE) | ✅ PASS | Un grain sans efficacité mesurable **n'a pas de ligne** et l'UI affiche « — » ; aucune valeur par défaut, aucun `0` de complaisance. L'écart de population est mesuré (SC-005), pas comblé. |
| P12 Medallion | ✅ PASS | Les 4 agrégations sont en gold ; l'API lit et ne recalcule que des deltas de présentation (déjà le cas au grain cluster). |
| P15 API Contract Stability | ✅ PASS | **Additif seulement** : 6 routes neuves, aucune réponse existante modifiée. `ComputeCostGrainTabKey` gagne une valeur (union élargie, type interne au frontend). |
| P16 Frontend Quality | ✅ PASS | Tiroirs typés calqués sur le patron existant, hooks TanStack Query, fixtures MSW, fermeture clavier héritée du composant tiroir. |

**Verdict amendement** : PASS. Le dernier point factuel ouvert (**R7**, couverture du mapping
DLT) a été mesuré en dev le 2026-09-09 → billing-direct. Plus aucun point ouvert.

## Project Structure

### Documentation

```
specs/024-job-dlt-cluster-split/
├── spec.md
├── plan.md              ← ce fichier
├── research.md          ← décisions de conception (R1…R9, toutes tranchées)
├── data-model.md        ← tables gold/curated neuves + colonnes + contrats de réponse
├── quickstart.md        ← déploiement dev (ingestion → gold) + contrôles d'acceptation SQL
├── merge-strategy.md    ← ordre de merge des branches filles (3 + 3 de l'amendement)
├── contracts/           ← formes de réponse des endpoints job-compute / pipeline-compute
├── intake.json
├── domain-scope.json
├── checklists/requirements.md
├── tasks.md
└── stories/             ← T001…T006
```

### Code — fichiers touchés

**T001 — `packages/dcm-databricks-pipeline`**

```
pipelines/system_tables/
├── specs.py                              (M) T001b: +SOURCE/CURATED_LAKEFLOW_PIPELINES, +LAKEFLOW_PIPELINES_SPEC, +registre SPECS
pipelines/gold_dbx_compute/
├── cluster_cost_rolling.py               (M) T001a: WHERE cluster_type = 'ALL_PURPOSE' dans CTE daily
├── cluster_efficiency_rolling.py         (M) T001a: idem
├── cluster_governance.py                 (M) T001a: snapshot borné aux ALL_PURPOSE (au-delà de governance_applies)
├── forecast.py                           (M) T001a: exclusion PIPELINE du grain CLUSTER ; T001d: passe pipeline_cost_and_dbu_forecast
├── pipeline_cost_daily.py                (N) T001c: rollup grain (cloud_provider, workspace_id, dlt_pipeline_id, period_start)
├── pipeline_cost_rolling.py              (N) T001c: rollup grain + window_days (miroir job_cluster_cost_rolling)
├── specs.py                              (M) T001c: +GOLD_PIPELINE_COST_DAILY/_ROLLING, specs + merge keys, GOLD_SPECS
├── recommendations.py                    (M) T001d: (si nécessaire) confirmer exclusion éphémère du grain CLUSTER
└── entrypoint.py                         (M) T001c: câblage des 2 builders pipeline + source curated pipelines
tests/system_tables/
└── test_specs.py / test_ingest.py        (M) T001b
tests/gold_dbx_compute/
├── test_cluster_cost_rolling.py          (M) T001a
├── test_cluster_efficiency_rolling.py    (M) T001a
├── test_cluster_governance.py            (M) T001a
├── test_forecast.py                      (M) T001a + T001d
├── test_pipeline_cost.py                 (N) T001c
└── test_entrypoint.py                    (M) T001c
```

**T002 — `packages/dcm-backend` (+ `dcm-commons`)**

```
app/api/services/
├── compute_metrics_common.py     (M) helpers de fenêtre partagés (descendus de _clusters si dupliqués)
├── compute_metrics_clusters.py   (M) cluster_type = 'ALL_PURPOSE' en prédicat dur (liste + governance)
├── compute_metrics_jobs.py       (N) grain job_id, lit gold_dbx_compute_job_cluster_cost_rolling
├── compute_metrics_pipelines.py  (N) grain dlt_pipeline_id, lit gold_dbx_compute_pipeline_cost_rolling
└── compute_metrics_forecast.py   (M) object_type = PIPELINE accepté (selon module existant)
app/api/routes/
└── compute_metrics.py            (M) routes /compute/jobs*, /compute/pipelines*, forecast object_type=PIPELINE
tests/
├── test_compute_metrics_services.py (M)
└── test_compute_metrics_routes.py   (M)
packages/dcm-commons/…             (M) schémas de réponse job-compute / pipeline-compute
```

**T003 — `packages/dcm-frontend`**

```
src/pages/
├── ComputeClusters.tsx           (M) (au besoin) libellé onglet « All-purpose », liens éphémères repointés
├── ComputeJobs.tsx               (N) page compute jobs (grain job_id)
└── ComputePipelines.tsx          (N) page compute pipelines DLT (grain dlt_pipeline_id)
src/api/dcmApiClient.ts           (M) getComputeJobs*/getComputePipelines* + types de réponse
src/hooks/
├── useComputeJobsQueries.ts      (N)
├── useComputePipelinesQueries.ts (N)
└── query-keys.ts                 (M) clés + normalisation des params job/pipeline
src/config/navigation.ts          (M) entrées Compute : All-purpose / Jobs / Pipelines
src/config/role-permissions.ts    (M) page:databricks pour les 2 routes neuves
src/lib/databricks/routes.ts      (M) PREDEFINED_WINDOW_ROUTES (+ les 2 routes si fenêtrées)
src/lib/databricks/focus-routes.ts(M) allowlist /databricks/** si widgets cliquables
src/app-routes.ts                 (M) 2 routes lazy vers les pages neuves
src/types/api.ts                  (M) types job-compute / pipeline-compute
src/test/fixtures/                (N) compute-jobs.ts, compute-pipelines.ts
```

**T004 — `packages/dcm-databricks-pipeline`** (amendement)

```
pipelines/gold_dbx_compute/
├── job_cluster_cost_daily.py             (M) T004a: extraire la CTE job_clusters en helper réutilisable
├── sql_helpers.py                        (M) T004a: helper de résolution cluster_id → job_id (ou module dédié)
├── job_efficiency_daily.py               (N) T004a: grain (cloud_provider, workspace_id, job_id, period_start)
├── job_efficiency_rolling.py             (N) T004a: grain + window_days (miroir cluster_efficiency_rolling)
├── pipeline_efficiency_daily.py          (N) T004b: grain (…, dlt_pipeline_id, period_start) — mapping billing-direct (R7)
├── pipeline_efficiency_rolling.py        (N) T004b: grain + window_days
├── specs.py                              (M) T004: +4 GOLD_*_EFFICIENCY_*, specs + merge keys, GOLD_SPECS
└── entrypoint.py                         (M) T004: câblage des 4 builders (après cluster_efficiency_daily)
tests/gold_dbx_compute/
├── test_job_efficiency.py                (N) T004a
├── test_pipeline_efficiency.py           (N) T004b
└── test_entrypoint.py                    (M) T004
```

**T005 — `packages/dcm-backend` (+ `dcm-commons`)** (amendement)

```
app/api/services/
├── compute_metrics_common.py     (M) _uptime_delta_pct / _idle_delta_pts descendus de _clusters
├── compute_metrics_clusters.py   (M) importe les helpers descendus (aucun changement de comportement)
├── compute_metrics_jobs.py       (M) +fetch_jobs_efficiency, fetch_job_detail, fetch_job_cost_trend, fetch_job_uptime_trend
└── compute_metrics_pipelines.py  (M) idem au grain dlt_pipeline_id
app/api/routes/
└── compute_metrics.py            (M) 6 routes ; /…/efficiency DÉCLARÉES AVANT /…/{id}
tests/
├── test_compute_metrics_services.py (M)
└── test_compute_metrics_routes.py   (M) dont un test d'ordre de routes (efficiency ≠ id)
packages/dcm-commons/…             (M) schémas efficiency / detail / trend job & pipeline
```

**T006 — `packages/dcm-frontend`** (amendement)

```
src/components/domain/compute/
├── compute-cost-tabs.tsx             (M) ComputeCostGrainTabKey += 'efficiency' ; docstring corrigé
├── compute-job-drawer.tsx            (N) calqué sur compute-cluster-drawer, sans bloc gouvernance
└── compute-pipeline-drawer.tsx       (N) idem au grain dlt_pipeline_id
src/pages/
├── ComputeJobs.tsx                   (M) onglet Efficiency + onRowClick sur les 3 tables + tiroir
└── ComputePipelines.tsx              (M) idem
src/api/dcmApiClient.ts               (M) efficiency / detail / cost-trend / uptime-trend × 2 familles
src/hooks/
├── useComputeJobsQueries.ts          (M) +useComputeJobsEfficiencyData, useComputeJobDetail, trends
├── useComputePipelinesQueries.ts     (M) idem
└── query-keys.ts                     (M) clés des nouvelles requêtes
src/types/api.ts                      (M) types efficiency / detail / trend job & pipeline
src/test/fixtures/compute-jobs.ts     (M) + fixtures efficiency / detail / trends
src/test/fixtures/compute-pipelines.ts(M) idem
src/pages/ComputeJobs.test.tsx        (M) 3 onglets, clic → tiroir, efficiency absente → « — »
src/pages/ComputePipelines.test.tsx   (M) idem
```

## Phase 0 — Research

Décisions consignées dans [research.md](./research.md). **R2 et R7 ont toutes deux été
tranchées par la mesure en dev du 2026-09-09**, l'une et l'autre vers une source billing-direct
(R2 pour le coût, R7 pour le mapping d'efficacité DLT). Aucune décision de conception ne reste
en suspens.

| # | Question | Décision (à valider) |
|---|----------|----------------------|
| R1 | Filtre `ALL_PURPOSE` en gold ou côté backend ? | **En gold** (T001a), dans la CTE `daily` des rollups et le snapshot governance. Le backend ajoute quand même le prédicat dur (défense en profondeur, décision C2), mais la table ne matérialise plus l'éphémère. |
| R2 | Source du rollup DLT garantissant SC-003 **et** l'inclusion maintenance (C3) ? | **À mesurer**. Deux options : (A) agréger `curated_dbx_billing_usage` filtré `usage_metadata.dlt_pipeline_id IS NOT NULL` (pas de lignée, mais échoue SC-003 si les lignes `PIPELINE_MAINTENANCE` ne portent pas `dlt_pipeline_id`) ; (B) rollup de `cluster_cost_daily` (`cluster_type='PIPELINE'`) + résolution `cluster_id → dlt_pipeline_id` via `usage_metadata` (garantit SC-003 par construction, comme le JOB via `job_task_run_timeline`). **Recommandé : mesurer si les lignes maintenance portent `dlt_pipeline_id`** ; si oui → A (plus simple), sinon → B avec coalesce `dlt_pipeline_id`/parent de `dlt_maintenance_id`. |
| R3 | Grain DLT `dlt_pipeline_id` vs `dlt_update_id` ? | `dlt_pipeline_id` (le pipeline), symétrique au choix `job_id` plutôt que `job_run_id`. Déjà acté (Assumptions spec). |
| R4 | `system.lakeflow.pipelines` : SCD (versions) ou snapshot ? | SCD calquée sur `LAKEFLOW_JOBS_SPEC` (1 ligne par version), `pipeline_name` résolu « as of » `period_start` comme `job_name` (`change_time < period_start + INTERVAL 1 DAY`). |
| R5 | Forecast PIPELINE : quelles métriques ? | `cost_usd` + `dbu_quantity` (C4). Pas de `cpu_util_p95_pct` (pas de table efficacité au grain pipeline). Exclusion de PIPELINE du grain CLUSTER généralisée depuis `!= 'JOB'`. |
| R6 | Frontend : pages séparées ou onglets internes ? | 2 pages neuves routées (`ComputeJobs`, `ComputePipelines`) + entrées nav, cohérent avec la séparation `ComputeClusters` / `ComputeSqlWarehouses` existante (pas d'onglets internes cross-grain). |
| R7 | Comment résoudre `cluster_id → dlt_pipeline_id` pour l'efficacité DLT ? | **TRANCHÉE 2026-09-09 → option A (billing-direct).** Couples distincts `(cluster_id, dlt_pipeline_id)` depuis `curated_dbx_billing_usage`. Mesuré : 0 violation d'unicité, 5029/5037 clusters AWS et 4/4 Azure résolus (99,84 %), et **0 désaccord sur 61 826 clusters** contre la source documentée `system.lakeflow.pipeline_update_timeline` (`pipeline_id` + `compute.cluster_id`). Retenue plutôt que cette dernière parce qu'elle couvre **les deux clouds** (`system.lakeflow` n'est lisible que côté AWS) et qu'elle est **la même source que le coût**, ce qui interdit une attribution contradictoire. Option B (parsing du nom) reste **rejetée** malgré 0 désaccord mesuré : contrat non documenté. Résidu : 8 clusters AWS exclus par `INNER JOIN`, documenté en SC-005. |
| R8 | Quelles métriques d'efficacité au grain éphémère ? | Jeu **adapté** : moyennes pondérées `uptime_hours`, p95 recalculés depuis les histogrammes, `uptime_hours` cumulé, `cluster_count` ajouté (nombre de runs agrégés). **Sans** `is_zombie`, `cluster_name`, `cluster_type` ni gouvernance. |
| R9 | Un tiroir générique ou un par grain ? | **Un par grain** (`compute-job-drawer`, `compute-pipeline-drawer`), comme cluster/warehouse aujourd'hui. Seul vrai changement partagé : `ComputeCostGrainTabKey` += `'efficiency'`. |

## Phase 1 — Design

- [data-model.md](./data-model.md) — schéma de `curated_dbx_lakeflow_pipelines`,
  `gold_dbx_compute_pipeline_cost_daily`/`_rolling` (colonnes + formules + `column_comments`),
  filtre `ALL_PURPOSE` sur les 3 tables cluster, nouvelle projection PIPELINE du forecast,
  et formes de réponse des endpoints job-compute / pipeline-compute.
- [contracts/](./contracts/) — payloads des routes `/compute/jobs*` et `/compute/pipelines*`
  et de la route forecast avec `object_type=PIPELINE`.
- [quickstart.md](./quickstart.md) — déploiement dev **dans l'ordre** : ingestion pipelines
  (T001b) → gold purge (T001a) → gold rollup DLT (T001c/d) → contrôles SQL (SC-001/002/003)
  → vérification HTTP des endpoints.

### Ordre d'exécution imposé

```
DataEng : T001a (purge) ─┐
          T001b (ingest) ─┼─► déploiement dev + SC-001/002/003 ─► T002 (API) ─► T003 (UI)
          T001c (rollup) ─┤
          T001d (fcst)   ─┘
```

T001a est indépendante et livrable en premier (débloque la purge visuelle dès que le backend
durcit le filtre). T001c dépend de T001b (`pipeline_name`) et alimente T001d. T002 lit les
tables que T001c/d créent ; T003 consomme les endpoints de T002.

Second lot (amendement), même cascade, après T003 :

```
DataEng : T004a (efficacité job) ────┐
          T004b (efficacité DLT) ────┴─► déploiement dev + SC-004/005 ─► T005 (API) ─► T006 (UI)
```

Les deux volets de T004 sont livrables : le mapping `cluster_id → job_id` existait déjà, et
celui du DLT est tranché par R7 (billing-direct, mesuré le 2026-09-09). T005 lit les 4 tables
de T004 ; T006 consomme les 6 routes de T005.

## Complexity Tracking

| Écart | Pourquoi c'est nécessaire | Alternative rejetée |
|---|---|---|
| Nouveau rollup DLT `pipeline_cost_*` (2 builders + 2 specs) | Les clusters PIPELINE sont éphémères (`cluster_id` neuf par update) : sans rollup au grain stable `dlt_pipeline_id`, le forecast et la liste sont inexploitables — même problème que JOB, déjà résolu par un rollup | Filtrer PIPELINE de la liste sans le remonter à une maille stable : on perdrait toute visibilité coût DLT (régression fonctionnelle, pas une simplification) |
| Ingestion `system.lakeflow.pipelines` (T001b) séparée | Le `dlt_pipeline_id` seul n'est pas lisible en UI ; le nom n'existe que dans cette table système, absente du registre curated | Afficher l'`dlt_pipeline_id` brut : lisible par une machine, pas par un FinOps — le fallback id reste, mais le nom est la valeur ajoutée |
| Source du rollup DLT laissée en R2 (mesure) plutôt que figée | L'inclusion maintenance (C3) et SC-003 se contredisent si les lignes `PIPELINE_MAINTENANCE` ne portent pas `dlt_pipeline_id` : seule la mesure en dev tranche entre A (simple) et B (lignée) | Figer l'option A sans mesure : risque d'échec SC-003 en revue et de coût maintenance perdu (contredit C3) |
| Deux pages front neuves plutôt que des onglets dans ComputeClusters | Les 3 familles ont des grains différents (`cluster_id`/`job_id`/`dlt_pipeline_id`) et des colonnes différentes ; les empiler dans une page casserait le typage par grain et la logique de fenêtre | Onglets internes partageant un tableau : forcerait un modèle de ligne polymorphe, à rebours de la séparation `ComputeClusters`/`ComputeSqlWarehouses` déjà en place |
| `cluster_type` durci en prédicat backend **en plus** du filtre gold | Défense en profondeur (C2) : même si une future table gold réintroduisait de l'éphémère, l'API ne le servirait pas ; coût nul (un `WHERE` de plus) | Se reposer sur le seul filtre gold : un régresseur silencieux côté pipeline rouvrirait la pollution sans garde-fou API |
| 4 tables gold d'efficacité neuves (T004) plutôt qu'un calcul à la volée côté API | P12 : les agrégations vivent en gold. Recalculer les p95 depuis les histogrammes au runtime API sur 90 jours × N clusters éphémères par job serait lent et hors frontière médaillon | Exposer `cluster_efficiency_daily` filtré `JOB`/`PIPELINE` tel quel : renverrait le grain éphémère, c'est-à-dire exactement le problème que cet Epic supprime |
| Jeu de colonnes **différent** du grain cluster (R8) plutôt que miroir exact | `is_zombie` serait `false` partout à ce grain : une colonne toujours verte se lit comme un contrôle qui passe, pas comme un contrôle absent — pire qu'une colonne manquante | Miroir exact « pour l'uniformité » : ferait entrer un faux signal en production (P9 / P4) |
| 2 tiroirs neufs plutôt qu'un tiroir générique paramétré | Le patron « un tiroir par grain » existe déjà (cluster, warehouse) et ses sections sont factorisées ; généraliser imposerait de réécrire les 4 tiroirs pour un gain nul sur cette itération | Tiroir unique polymorphe : refonte de code livré et testé, hors du périmètre demandé |
| `uptime-trend` au lieu de `lifetime-trend` (nom divergent de l'homologue cluster) | « Durée de vie » n'a pas de sens sur un cluster détruit à chaque run ; la grandeur suivie est l'uptime cumulé du job/pipeline | Réutiliser `lifetime-trend` par symétrie : nom qui décrit mal ce que la série mesure |

## Progress Tracking

- [x] Constitution Check initial — PASS
- [x] Phase 0 — Research documentée (R1…R6 ; R2 tranchée par la mesure du 2026-09-09 → option A)
- [x] Phase 1 — Design (data-model, contracts, quickstart)
- [x] Constitution Check après design — PASS (inchangé)
- [x] Tasks générées
- [x] T001a purge implémentée + vérifiée en dev (SC-001)
- [x] T001b ingestion pipelines implémentée + vérifiée en dev
- [x] T001c rollup DLT implémenté + vérifié en dev (SC-002 / SC-003 résiduel documenté)
- [x] T001d forecast/reco PIPELINE implémenté + vérifié en dev
- [x] T002 implémentée + vérifiée en dev
- [x] T003 implémentée

Amendement 2026-09-09 (efficacité + drill-down job/pipeline) :

- [x] Spec amendée (session de clarifications, US4–US6, FR-011…FR-018, SC-004…SC-006)
- [x] Phase 0 — Research additionnelle (R7 **tranchée par mesure**, R8, R9)
- [x] Phase 1 — Design additionnel (data-model, contracts, quickstart §6–8, merge-strategy)
- [x] Constitution Check de l'amendement — PASS (aucun point ouvert)
- [x] Tasks T004/T005/T006 générées + stories rédigées
- [ ] Stories Jira T004/T005/T006 créées (`/speckit.dcm.dispatch`) — clés à reporter dans
      `tasks.md` et dans les 3 en-têtes de story
- [x] **R7 mesurée en dev** (2026-09-09) — mapping billing-direct, 99,84 % de couverture
- [ ] T004a efficacité job implémentée + vérifiée en dev (SC-004)
- [ ] T004b efficacité pipeline implémentée + vérifiée en dev (SC-004 / SC-005)
- [ ] T005 implémentée + vérifiée en dev
- [ ] T006 implémentée (SC-006)
