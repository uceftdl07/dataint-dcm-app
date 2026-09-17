# Spike — Séparation compute Job cluster / DLT vs All-purpose

> Branche : `feat/job-cluster_and_serverless_management`
> Objet : dépolluer la page Compute Clusters des clusters éphémères (JOB, DLT), agréger
> leur coût à la maille métier stable (`job_id`, `dlt_pipeline_id`) et corriger
> forecast/recommandations qui ne supportent pas ces types.
> Références code : [gold_dbx_compute](../../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/) ·
> [compute_metrics_clusters.py](../../../packages/dcm-backend/app/api/services/compute_metrics_clusters.py) ·
> [compute_datamapping.md](../compute-metrics-definition/compute_datamapping.md)

---

## 1. Constat — état réel du code (moitié déjà fait)

Le pipeline **sépare déjà** les job clusters, mais **seulement côté FinOps forecast**,
pas côté pages liste. D'où la pollution.

Ce qui existe :

- `cluster_type` dérivé de `system.compute.clusters.cluster_source` dans
  [`sql_helpers.cluster_type_case_expr`](../../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/sql_helpers.py) :
  - `JOB` → `JOB` (éphémère, recréé à chaque exécution)
  - `UI` / `API` → `ALL_PURPOSE` (persistant)
  - `PIPELINE` / `PIPELINE_MAINTENANCE` → **`PIPELINE`** (DLT / Lakeflow — déjà une catégorie identifiée)
  - autre → `OTHER`
- Rollup FinOps `gold_dbx_compute_job_cluster_cost_daily` + `_rolling` au grain **`job_id`**
  ([`job_cluster_cost_daily.py`](../../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/job_cluster_cost_daily.py)).
- Forecast ([`forecast.py`](../../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/forecast.py))
  **exclut déjà** `cluster_type = 'JOB'` du grain CLUSTER (série dégénérée à 1 point,
  inexploitable par `ai_forecast`) et projette `JOB` via le rollup `job_id`.

Ce qui **manque** (= la pollution constatée) :

- Les tables lues par les **pages liste** — `cluster_cost_rolling`,
  `cluster_efficiency_rolling`, `cluster_governance` — **ne filtrent PAS `cluster_type`**.
  JOB **et** PIPELINE y restent → page Clusters polluée + reco produites au grain cluster
  éphémère (inutiles, cluster recréé au run suivant).
- Backend [`compute_metrics_clusters.py`](../../../packages/dcm-backend/app/api/services/compute_metrics_clusters.py) :
  `cluster_type` n'existe qu'en **filtre optionnel**, jamais appliqué par défaut.
- **DLT n'a AUCUN rollup** — les clusters `PIPELINE` éphémères polluent exactement comme
  les JOB avant leur rollup.

---

## 2. Réponse : DLT = même problème que Job cluster ?

**Oui, même problème, grain d'agrégation différent.**

| | Job cluster | DLT / pipeline cluster |
|---|---|---|
| `cluster_source` | `JOB` | `PIPELINE` / `PIPELINE_MAINTENANCE` |
| `cluster_id` | éphémère (recréé / run) | éphémère (recréé / update) |
| Clé stable d'agrégation | `job_id` | **`dlt_pipeline_id`** |
| Résolution de la clé | lineage `job_task_run_timeline.compute` (cluster → job) | **direct** : `billing_usage.usage_metadata.dlt_pipeline_id` (natif, aucun lineage) |
| Source du nom | `lakeflow_jobs.name` ∪ `job_run_timeline.run_name` | `system.lakeflow.pipelines.name` |

Différence clé : **le DLT est plus simple** — `billing_usage.usage_metadata.dlt_pipeline_id`
porte déjà la clé stable, pas besoin du détour lineage qu'exige le JOB.

---

## 3. Stratégie : 3 familles de compute, 3 grains

```
system.compute.clusters.cluster_source
        │
        ├── UI / API          → ALL_PURPOSE   grain = cluster_id        (persistant)  → page "Clusters"
        ├── JOB               → JOB           grain = job_id            (éphémère)    → page "Jobs compute"
        └── PIPELINE(_MAINT)  → PIPELINE      grain = dlt_pipeline_id   (éphémère)    → page "Pipelines (DLT) compute"
```

**Principe** : `cluster_id` n'est une clé viable QUE pour `ALL_PURPOSE`. Pour `JOB` et
`PIPELINE`, agréger sur la clé métier stable.

Trois mouvements :

1. **Purger les pages cluster** → `cluster_*_rolling` / `governance` / reco filtrent
   `cluster_type = 'ALL_PURPOSE'` (JOB déjà exclu du forecast, à généraliser aux 3 tables + reco).
2. **Symétriser le DLT sur le JOB** → nouvelles tables `gold_dbx_compute_pipeline_cost_daily`
   + `_rolling` au grain `dlt_pipeline_id`, calquées sur `job_cluster_cost_*`.
3. **Forecast / reco** → ajouter `object_type = 'PIPELINE'` à côté de `JOB` et `CLUSTER`.

---

## 4. Data model cible

⭐ = nouvelle · ✅ = existe · 🔧 = à filtrer `ALL_PURPOSE`

| Table | Grain | Statut | Usage |
|---|---|---|---|
| `gold_dbx_compute_cluster_cost_daily` | cluster_id | ✅ garde tous les types (source de vérité par cluster) | source des rollups |
| `gold_dbx_compute_cluster_cost_rolling` | cluster_id + window | 🔧 filtre `ALL_PURPOSE` | page Clusters |
| `gold_dbx_compute_cluster_efficiency_rolling` | cluster_id + window | 🔧 filtre `ALL_PURPOSE` | page Clusters |
| `gold_dbx_compute_cluster_governance` | cluster_id | 🔧 filtre `ALL_PURPOSE` | page Clusters |
| `gold_dbx_compute_job_cluster_cost_daily` | job_id | ✅ | page Jobs compute |
| `gold_dbx_compute_job_cluster_cost_rolling` | job_id + window | ✅ | page Jobs compute |
| `gold_dbx_compute_pipeline_cost_daily` | **dlt_pipeline_id** | ⭐ | page Pipelines compute |
| `gold_dbx_compute_pipeline_cost_rolling` | dlt_pipeline_id + window | ⭐ | page Pipelines compute |
| `gold_dbx_compute_forecast_daily` | (object_type, object_id, metric) | 🔧 + `PIPELINE` | forecast |
| `gold_dbx_compute_recommendations` | (object_type, object_id) | 🔧 exclure JOB/PIPELINE du grain CLUSTER | reco |

Schéma `gold_dbx_compute_pipeline_cost_daily` (miroir de `job_cluster_cost_daily`) :

```
cloud_provider, workspace_id, dlt_pipeline_id, period_start   -- PK / merge key
pipeline_name          -- system.lakeflow.pipelines.name (dernier change_time <= jour)
cluster_count          -- COUNT(DISTINCT cluster_id) du pipeline ce jour
dbu_quantity, cost_usd -- SUM
cost_usd_prev_day, cost_delta_pct
cost_rank, is_top_cost
_generated_at
```

---

## 5. Mapping — nouveau (DLT)

`gold_dbx_compute_pipeline_cost_daily` :

| Cible gold | Source | Transformation |
|---|---|---|
| `dlt_pipeline_id` | `billing_usage.usage_metadata.dlt_pipeline_id` | clé de groupe (filtre `IS NOT NULL`) |
| `pipeline_name` | `curated_dbx_lakeflow_pipelines.name` (⚠️ à ingérer — cf. §7) | join dernier `change_time` ≤ jour ; à défaut `dlt_pipeline_id` |
| `cluster_count` | `usage_metadata.cluster_id` | `COUNT(DISTINCT cluster_id)` |
| `dbu_quantity` / `cost_usd` | `usage_quantity` × prix effectif | `SUM` (même join `list_prices` que `cluster_cost_daily`) |
| `cost_usd_prev_day` / `cost_delta_pct` | self-join J-1 | idem `job_cluster_cost_daily` |
| `cost_rank` / `is_top_cost` | dérivé | `RANK() OVER (PARTITION BY source_lz_id, period_start ORDER BY cost_usd DESC)` |

Deux options de source :

- **Option A (recommandée)** : agréger **directement** `curated_dbx_billing_usage` filtré
  `usage_metadata.dlt_pipeline_id IS NOT NULL`, groupé par `dlt_pipeline_id`. Aucun lineage —
  plus propre que le chemin JOB.
- Option B : rollup de `cluster_cost_daily` (`cluster_type = 'PIPELINE'`) via lineage
  cluster → pipeline. Inutilement complexe, pas de table lineage dédiée. **À écarter.**

> **Anti-double-comptage** (déjà documenté pour JOB) : `pipeline_cost_daily` et
> `job_cluster_cost_daily` sont des **rollups** des mêmes lignes de facturation que
> `cluster_cost_daily`. Ne jamais les sommer entre elles.

---

## 6. Impact backend / frontend

- **Backend** : `cluster_type = 'ALL_PURPOSE'` en prédicat **dur** (pas filtre optionnel)
  dans `fetch_clusters_*`. Nouveaux services `pipeline_cost` / `overview` calqués sur les
  services `job`. Forecast / reco : accepter `object_type = PIPELINE`.
- **Frontend** : nav Compute → 3 sous-onglets **All-purpose clusters** / **Jobs compute** /
  **Pipelines (DLT) compute** (précédent : onglet Jobs). `FORECAST_METRICS` / labels :
  ajouter la dimension pipeline.

---

## 7. Dette à lever (prérequis DLT)

`curated_dbx_lakeflow_pipelines` (← `system.lakeflow.pipelines`) **n'est pas dans le socle
d'ingestion** (`system_tables/specs.py` inputs) → pas de `pipeline_name`. Sans ça, DLT
fonctionne mais affiche l'`id` brut.

> Le grain `dlt_pipeline_id` lui-même vient de `billing_usage` (déjà ingéré) — le rollup
> **coût** marche même sans le nom. L'ingestion de `system.lakeflow.pipelines` n'est donc
> requise que pour l'affichage lisible.

---

## 8. Séquencement suggéré

1. **T1 (quick win, gros impact visuel)** — filtre `ALL_PURPOSE` sur les 3 tables cluster
   liste + reco/forecast. Purge la page immédiatement, aucune table nouvelle.
2. **T2** — ingest `system.lakeflow.pipelines` → `curated_dbx_lakeflow_pipelines`.
3. **T3** — `pipeline_cost_daily` + `_rolling` (option A, miroir du module job).
4. **T4** — forecast / reco `object_type = PIPELINE`.
5. **T5** — services backend + nav frontend 3 onglets.
