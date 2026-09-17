# T001 — Purge liste `ALL_PURPOSE` + rollup DLT + ingest `pipelines` + forecast/reco PIPELINE

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: `dataeng/024-purge-liste-all-purpose-rollup-dlt`
**Jira**: [DCINT-326](https://tdf.atlassian.net/browse/DCINT-326) (Epic [DCINT-325](https://tdf.atlassian.net/browse/DCINT-325))
**Depends on**: rien (T001a) ; interne : T001a → T001b → T001c → T001d
**Work type**: feature

## Description

Producteur du socle gold des 3 familles de compute. Trois effets :

1. **Purge** — les tables gold liste (`cluster_cost_rolling`, `cluster_efficiency_rolling`,
   `cluster_governance`) ne gardent que `cluster_type = 'ALL_PURPOSE'`, ce qui vide la page
   Clusters des `cluster_id` éphémères JOB/PIPELINE (SC-001).
2. **Rollup DLT** — nouveau couple `gold_dbx_compute_pipeline_cost_daily` / `_rolling` au
   grain stable `dlt_pipeline_id`, **miroir exact** du module job (`job_cluster_cost_*`).
   Prérequis : ingérer `system.lakeflow.pipelines` pour le `pipeline_name` lisible.
3. **Forecast / reco** — le grain CLUSTER exclut désormais JOB **et** PIPELINE ; le forecast
   projette `object_type = 'PIPELINE'` depuis le rollup DLT (coût + DBU seulement, C4).

Séquencé en **4 PR** pour rester en petits diffs (Prerequisites spec) :
`T001a purge → T001b ingest pipelines → T001c rollup DLT → T001d forecast/reco`.

## Point ouvert bloquant T001c — R2 (mesure dev obligatoire)

Avant d'écrire `pipeline_cost_daily`, **mesurer en dev** si les lignes `PIPELINE_MAINTENANCE`
de `billing_usage` portent `usage_metadata.dlt_pipeline_id` (requête [quickstart.md](../quickstart.md) §0) :

- **Option A** (FR-002) — agréger `curated_dbx_billing_usage` filtré `dlt_pipeline_id IS NOT
  NULL`. Simple, mais **échoue SC-003** si la maintenance ne porte qu'un `dlt_maintenance_id`.
- **Option B** — rollup `cluster_cost_daily` filtré `cluster_type = 'PIPELINE'` + résolution
  `cluster_id → dlt_pipeline_id` via `usage_metadata`. Garantit SC-003.

Ne pas fabriquer le choix. Le trancher sur la donnée, tracer la mesure dans la story.

## Files to create/modify

### T001a — purge liste
- UPDATE `pipelines/gold_dbx_compute/cluster_cost_rolling.py` — `WHERE cluster_type = 'ALL_PURPOSE'` dans la CTE `daily`
- UPDATE `pipelines/gold_dbx_compute/cluster_efficiency_rolling.py` — idem CTE `daily`
- UPDATE `pipelines/gold_dbx_compute/cluster_governance.py` — borner le snapshot à `ALL_PURPOSE`
- UPDATE `pipelines/gold_dbx_compute/forecast.py` — grain CLUSTER `cluster_type != 'JOB'` → `NOT IN ('JOB','PIPELINE')` (2 passes)
- UPDATE `tests/gold_dbx_compute/test_cluster_cost_rolling.py`, `test_cluster_efficiency_rolling.py`, `test_cluster_governance.py`, `test_forecast.py`

### T001b — ingest system.lakeflow.pipelines
- UPDATE `pipelines/system_tables/specs.py` — bloc « Workflow : Jobs/Lakeflow » : `CURATED_LAKEFLOW_PIPELINES`, `SOURCE_LAKEFLOW_PIPELINES = "system.lakeflow.pipelines"`, `LAKEFLOW_PIPELINES_MERGE_KEYS`, `LAKEFLOW_PIPELINES_SPEC` (SCD, calqué sur `LAKEFLOW_JOBS_SPEC`) ; ajouter `"lakeflow_pipelines"` au registry `SPECS`
- UPDATE tests d'ingestion correspondants

### T001c — rollup DLT (grain dlt_pipeline_id)
- CREATE `pipelines/gold_dbx_compute/pipeline_cost_daily.py` — `build_pipeline_cost_daily(...)`, grain `(cloud_provider, workspace_id, dlt_pipeline_id, period_start)`, miroir de `job_cluster_cost_daily.py`
- CREATE `pipelines/gold_dbx_compute/pipeline_cost_rolling.py` — `build_pipeline_cost_rolling(...)`, +`window_days`, miroir de `job_cluster_cost_rolling.py`
- UPDATE `pipelines/gold_dbx_compute/specs.py` — `GOLD_PIPELINE_COST_DAILY`/`_ROLLING`, `PIPELINE_COST_DAILY_MERGE_KEYS`, `PIPELINE_COST_ROLLING_MERGE_KEYS`, specs, entrées `GOLD_SPECS`, `__all__`
- UPDATE `pipelines/gold_dbx_compute/entrypoint.py` — câbler les 2 builders
- CREATE `tests/gold_dbx_compute/test_pipeline_cost.py`
- UPDATE `tests/gold_dbx_compute/test_entrypoint.py`

### T001d — forecast/reco PIPELINE
- UPDATE `pipelines/gold_dbx_compute/forecast.py` — CTE `pipeline_cost_and_dbu_forecast` (object_type `'PIPELINE'`, lit `pipeline_cost_daily`, **cost_usd + dbu_quantity seulement**), UNION ALL des blocs
- UPDATE `pipelines/gold_dbx_compute/recommendations.py` — vérifier que les règles GOVERNANCE restent gated `governance_applies` (ALL_PURPOSE) ; aucune reco au grain éphémère
- UPDATE `tests/gold_dbx_compute/test_forecast.py`, `test_recommendations.py`

## Sub-tasks

### T001a — purge liste
- [x] **Tests d'abord** (`FakeSpark`, SQL généré) : `cluster_cost_rolling` / `_efficiency_rolling` portent `cluster_type = 'ALL_PURPOSE'` dans la CTE `daily` ; `forecast.py` grain CLUSTER filtre `NOT IN ('JOB','PIPELINE')` sur les 2 passes cost_and_dbu / cpu_util.
- [x] `cluster_cost_rolling.py` : injecter le filtre dans la CTE `daily` (projette déjà `cluster_type`).
- [x] `cluster_efficiency_rolling.py` : idem.
- [x] `cluster_governance.py` : borner le snapshot à `governance_applies = (cluster_type = 'ALL_PURPOSE')` (déjà présent) — s'assurer que la table matérialisée ne contient plus que ALL_PURPOSE.
- [x] `forecast.py` : généraliser `cluster_type != 'JOB'` → `NOT IN ('JOB','PIPELINE')` (2 passes CLUSTER).
- [x] Gates : `pytest`, `ruff check pipelines tests`, `mypy pipelines --explicit-package-bases`.
- [x] Déploiement dev + contrôle **SC-001** ([quickstart.md](../quickstart.md) §2).
- [x] **Purge one-shot (migration, 1×/env)** — le filtre source n'élague pas les lignes JOB/PIPELINE déjà matérialisées (`cluster_cost_rolling`/`_efficiency_rolling` en MERGE upsert pur ; `cluster_governance` a un delete-not-matched gated par `SNAPSHOT_ABSENT_ROW_GRACE_DAYS`). Rejouer par env, une fois, après déploiement : `DELETE FROM gold_dbx_compute_cluster_{cost_rolling,efficiency_rolling,governance} WHERE cluster_type <> 'ALL_PURPOSE'`. Définitif car les `cluster_id` éphémères ne réapparaissent jamais dans la source filtrée. Dev : ✅ (−1 989 647 / −739 782 / −5 421 311, tables = `ALL_PURPOSE` uniquement).

### T001b — ingest pipelines
- [x] **Tests d'abord** : `LAKEFLOW_PIPELINES_SPEC` en SCD, merge keys sur l'id de pipeline + `change_time`, présent dans `SPECS`.
- [x] `system_tables/specs.py` : ajouter le bloc calqué sur `LAKEFLOW_JOBS_SPEC` ; `for_each` du job `dcm_system_tables` aligné (17→18 clés).
- [x] Gates + ingestion dev : `curated_dbx_lakeflow_pipelines` peuplé, `name` non nul mesuré ([quickstart.md](../quickstart.md) §1). Dev : ✅ (67 186 lignes, 22 358 `pipeline_id` distincts, 2 clouds, 0 `name` null).

### T001c — rollup DLT
- [x] **R2 tranché en dev** — mesure §0 (2026-09-09, warehouse fcc5098720414937 sur `system.billing.usage`) : `(dlt_pipeline_id NOT NULL, maintenance NULL)` = 1 605 588 lignes ; `(pipeline NOT NULL, maintenance NOT NULL)` = 12 345 ; **aucune ligne `(pipeline NULL, maintenance NOT NULL)`** → toute ligne de maintenance porte `dlt_pipeline_id`. Règle research.md R2 → **Option A** (billing-direct filtré `usage_metadata.dlt_pipeline_id IS NOT NULL`, groupé par `dlt_pipeline_id` ; maintenance capturée car elle porte le pipeline_id parent — pas de résolution `cluster_id → dlt_pipeline_id`).
- [x] **Tests d'abord** : grain `(cloud_provider, workspace_id, dlt_pipeline_id, period_start)` ; unicité par `dlt_pipeline_id × window` ; `pipeline_name` résolu (fallback `dlt_pipeline_id`) ; maintenance rattachée au pipeline parent (C3).
- [x] `pipeline_cost_daily.py` + `pipeline_cost_rolling.py` : miroir des builders job.
- [x] `specs.py` + `entrypoint.py` : registry + câblage.
- [x] Gates + déploiement dev : **SC-002** (unicité) et **SC-003** (Σ vs `cluster_cost_daily` PIPELINE) ([quickstart.md](../quickstart.md) §3).
  - **SC-002 ✅** : `gold_dbx_compute_pipeline_cost_rolling` GROUP BY `dlt_pipeline_id, window_days` HAVING count>1 → **0 doublon**.
  - **SC-003 — écart attendu, documenté (résidu de conception, PAS un bug)** : Σ `pipeline_cost_daily` = **384 364,80 USD** vs Σ `cluster_cost_daily` WHERE `cluster_type='PIPELINE'` = **172 016,55 USD** → delta **+212 348,25 USD (+123 %)**. Cause : la voie billing-direct (Option A) capte le **DLT serverless** — 46 % du DBU pipeline (2 166 842 lignes, 459 690 DBU, `usage_metadata.cluster_id IS NULL`) — que la voie cluster-source (`cluster_type='PIPELINE'`, adossée aux clusters classiques) **ne peut structurellement pas voir**. Le delta **valide** Option A (mesure de coût pipeline plus complète). Résidu conservé et documenté ; on garde Option A.
  - **Débloquage gold job** : le run gold échouait sur `gold_recommendations` à cause d'un **comment de colonne orphelin `cluster_type`** dans `RECOMMENDATIONS_COLUMN_COMMENTS` (leftover de #247 / DCINT-311 — colonne retirée du builder par décision produit mais comment + test laissés). Retiré ici (comment + `test_recommendations_column_comments_document_cluster_type`) ; repair-run → run gold **TERMINATED SUCCESS**.

### T001d — forecast/reco PIPELINE
- [x] **Tests d'abord** : `object_type = 'PIPELINE'` projeté depuis `pipeline_cost_daily` sur `cost_usd` + `dbu_quantity` uniquement ; pas de passe efficacité PIPELINE (`test_pipeline_cost_and_dbu_are_forecast_together_from_pipeline_cost_daily`, `test_object_key_groups...`, `test_output_is_unpivoted...`).
- [x] `forecast.py` : CTE `pipeline_cost_and_dbu_forecast` (grain `dlt_pipeline_id`, `array('cost_usd','dbu_quantity')`, params `global_floor=0`, borne `observed_lower_bound`, **pas** de filtre `cluster_type`) + 2 `UNION ALL 'PIPELINE'` ; param `pipeline_cost_daily_table` threadé `render_forecast_query`/`build_compute_forecast`/`entrypoint`. `job_dcm_gold_forecast.yml` : 5→6 tables source + description.
- [x] `recommendations.py` : **inchangé** — le rule engine ne lit que cluster (ALL_PURPOSE) + warehouse, jamais `pipeline_cost_*` → aucune reco au grain pipeline. Verrou : `test_recommendations_never_target_pipeline_ephemeral_grain`.
- [x] Gates + déploiement dev : ruff clean, **614 pytest pass** ; job `dcm_gold_forecast` **TERMINATED SUCCESS** (run 7453166992622). **Contrôle forecast PIPELINE ✅** (contrôle local de T001d — à ne pas confondre avec le `SC-004` de la spec, ajouté plus tard par l'amendement) : `gold_dbx_compute_forecast_daily` contient `object_type='PIPELINE'` = **19 592 lignes × 2 métriques** (`cost_usd`/`dbu_quantity`, 2 500 pipelines), **aucun `cpu_util_p95_pct` PIPELINE** ; grain CLUSTER = ALL_PURPOSE only (JOB/PIPELINE projetés séparément via leur rollup stable).

## Notes

- **Anti-double-comptage** : `pipeline_cost_daily`, `job_cluster_cost_daily`,
  `cluster_cost_daily (ALL_PURPOSE)` agrègent des sous-ensembles **disjoints** par
  `cluster_type` des mêmes lignes billing — ne jamais les sommer.
- `PIPELINE_MAINTENANCE` est déjà classé `PIPELINE` par `cluster_type_case_expr` — pas de
  cas spécial de classification, seulement le rattachement du coût au `dlt_pipeline_id` parent.
