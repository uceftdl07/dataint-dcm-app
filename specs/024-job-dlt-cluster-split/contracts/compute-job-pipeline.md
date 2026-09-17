# Contracts — endpoints compute job & pipeline (T002)

Formes de réponse des routes neuves. Calquées sur `compute_metrics_warehouses` (pagination
serveur, fenêtre glissante `window_days ∈ {1,7,30,90}`, `from_date`/`to_date` dérivés).

## `GET /api/v1/databricks/compute/jobs/overview` (+ `/cost`)

Grain `job_id`. Source gold : `gold_dbx_compute_job_cluster_cost_rolling`.

```jsonc
{
  "items": [
    {
      "cloud_provider": "azure",
      "workspace_id": "1234567890",
      "job_id": "987654321",
      "job_name": "daily_ingestion",          // fallback: job_id
      "cluster_count": 12,
      "dbu_quantity": 340.5,
      "cost_usd": 512.30,
      "cost_usd_prev_window": 480.10,
      "cost_delta_pct": 6.7,
      "cost_rank": 3,
      "is_top_cost": true,
      "window_days": 30,
      "window_start": "2026-08-10",
      "as_of_date": "2026-09-08"
    }
  ],
  "page": 1, "page_size": 25, "total": 42
}
```

## `GET /api/v1/databricks/compute/pipelines/overview` (+ `/cost`)

Grain `dlt_pipeline_id`. Source gold : `gold_dbx_compute_pipeline_cost_rolling`.

```jsonc
{
  "items": [
    {
      "cloud_provider": "aws",
      "workspace_id": "2233445566",
      "dlt_pipeline_id": "a1b2c3d4-...",
      "pipeline_name": "bronze_to_silver",     // fallback: dlt_pipeline_id
      "cluster_count": 8,
      "dbu_quantity": 210.0,
      "cost_usd": 305.00,
      "cost_usd_prev_window": 290.00,
      "cost_delta_pct": 5.2,
      "cost_rank": 5,
      "is_top_cost": false,
      "window_days": 30,
      "window_start": "2026-08-10",
      "as_of_date": "2026-09-08"
    }
  ],
  "page": 1, "page_size": 25, "total": 17
}
```

## `GET /api/v1/databricks/compute/forecast?object_type=PIPELINE`

Séries `cost_usd` et `dbu_quantity` uniquement (C4). Même forme que `object_type=JOB`,
`object_id = dlt_pipeline_id`.

## Notes contractuelles

- `cost_usd_prev_window` ≤ 0 → `null` (« pas de comparaison », pas « gratuit »), aligné sur
  la convention warehouse/cluster.
- `window_days` hors `{1,7,30,90}` → 422 (IntEnum, pas rabattement silencieux).
- Schémas Pydantic dans `dcm-commons` (réponses partagées backend/typage).

---

# Contracts — amendement 2026-09-09 : efficacité & drill-down (T005)

Calqués sur les routes cluster homologues (`/clusters/efficiency`, `/clusters/{cluster_id}`,
`/clusters/{cluster_id}/cost-trend`, `/clusters/{cluster_id}/lifetime-trend`).

## `GET /api/v1/databricks/compute/jobs/efficiency`

Grain `job_id`. Source gold : `gold_dbx_compute_job_efficiency_rolling`.

```jsonc
{
  "items": [
    {
      "cloud_provider": "azure",
      "workspace_id": "1234567890",
      "job_id": "987654321",
      "job_name": "daily_ingestion",           // fallback: job_id
      "cluster_count": 12,                     // runs agrégés dans la fenêtre
      "cpu_util_avg_pct": 38.4,
      "cpu_util_p95_pct": 71.2,
      "mem_util_avg_pct": 44.1,
      "mem_util_p95_pct": 68.9,
      "cpu_wait_avg_pct": 3.2,
      "idle_pct": 21.5,
      "idle_pct_prev_window": 18.0,            // null si fenêtre précédente vide
      "idle_pct_delta_pts": 3.5,               // POINTS, pas pour cent
      "uptime_hours": 46.8,                    // cumulé sur tous les runs
      "uptime_hours_prev_window": 41.0,        // null si fenêtre précédente vide
      "uptime_hours_delta_pct": 14.1,
      "active_hours": 36.7,
      "worker_count_avg": 4.2,
      "worker_count_max": 8,
      "autoscale_enabled": true,
      "autoscale_min_workers": 2,
      "autoscale_max_workers": 8,
      "configured_worker_count": null,
      "driver_node_type": "Standard_D8ds_v5",
      "worker_node_type": "Standard_D8ds_v5",
      "utilization_status": "OPTIMAL",          // OVER | OPTIMAL | UNDER
      "recommended_node_type": "Standard_D4ds_v5",
      "rightsizing_reco": null,
      "estimated_savings_usd": 0.0,
      "window_days": 30,
      "window_start": "2026-08-10",
      "as_of_date": "2026-09-08"
    }
  ],
  "page": 1, "page_size": 25, "total": 31
}
```

**Pas de champ `is_zombie`** (R8) : à ce grain le signal serait `false` partout et se lirait
comme un contrôle qui passe, alors qu'il n'a pas de sens.

## `GET /api/v1/databricks/compute/pipelines/efficiency`

Identique, `job_id`/`job_name` remplacés par `dlt_pipeline_id`/`pipeline_name`. Source gold :
`gold_dbx_compute_pipeline_efficiency_rolling`.

Population **plus petite** que `/pipelines/cost` : les pipelines serverless n'ont pas de
`node_timeline`, donc pas d'efficacité (R7). Ce n'est pas une erreur de pagination.

## `GET /api/v1/databricks/compute/jobs/{job_id}` (et `/pipelines/{dlt_pipeline_id}`)

```jsonc
{
  "cloud_provider": "azure",
  "workspace_id": "1234567890",
  "job_id": "987654321",
  "cost": { /* ligne de jobs/cost pour la fenêtre, ou null */ },
  "efficiency": { /* ligne de jobs/efficiency pour la fenêtre, ou null */ },
  "window": { "window_days": 30, "window_start": "2026-08-10", "as_of_date": "2026-09-08" },
  "period": { "from_date": "2026-08-10", "to_date": "2026-09-08" }
}
```

- **Pas de clé `governance`** — ni `null` : absente du payload (C2, la gouvernance n'existe
  pas à ce grain).
- `efficiency: null` est un cas **normal** (couverture `node_timeline`), pas une erreur : le
  détail reste servi avec son bloc `cost`.
- Grain inconnu du périmètre du caller → **404** (`Job not found` / `Pipeline not found`),
  jamais un corps vide en 200 — aligné sur `/clusters/{cluster_id}`.

## `GET …/jobs/{job_id}/cost-trend` (et `/pipelines/{dlt_pipeline_id}/cost-trend`)

Source gold : `*_cost_daily`. **Pas de `window_days`** : une tendance est une série sur la
période, que les `*_rolling` ne peuvent pas servir (un point par fenêtre).

```jsonc
{
  "items": [{ "bucket": "2026-09-01", "cost_usd": 18.42, "dbu_quantity": 12.5 }],
  "period": { "from_date": "2026-06-11", "to_date": "2026-09-08" },
  "granularity": "day"                          // day | week | month
}
```

## `GET …/jobs/{job_id}/uptime-trend` (et `/pipelines/{dlt_pipeline_id}/uptime-trend`)

Source gold : `*_efficiency_daily`. `idle_pct` **pondéré par `uptime_hours`** dans chaque
bucket, et `null` (jamais `0`) sur un bucket non mesuré.

```jsonc
{
  "items": [{ "bucket": "2026-09-01", "uptime_hours": 2.4, "idle_pct": 17.3 }],
  "period": { "from_date": "2026-06-11", "to_date": "2026-09-08" },
  "granularity": "day"
}
```

Nommée `uptime-trend` et non `lifetime-trend` (son homologue cluster) : « durée de vie » n'a
pas de sens sur un cluster détruit à la fin de chaque run — la grandeur suivie est l'uptime
cumulé du job/pipeline. Divergence de nommage assumée, pas un oubli.

## Notes contractuelles — amendement

- **Ordre de déclaration des routes** : `/jobs/efficiency` et `/pipelines/efficiency`
  **doivent** être déclarées **avant** `/jobs/{job_id}` / `/pipelines/{dlt_pipeline_id}`,
  sinon le segment variable avale `efficiency` comme un identifiant. Le fichier porte déjà
  ce commentaire pour `filter-options` — même piège.
- Toutes les routes restent en **soft-fail** (retour vide / `None`, jamais 500 sur absence de
  table gold), conforme aux `fetch_*` existants.
- Le périmètre (`allowed_lz_ids`, `allowed_workspace_ids`, `cloud_provider`, …) est appliqué
  par `_common_scope_kwargs` / `_scope_where` sans exception, y compris sur les tendances.

## Amendement T008 — `compute_kind` sur les routes de coût pipeline

Les deux tables `gold_dbx_compute_pipeline_cost_daily` / `_rolling` portent désormais
`compute_kind` (`CLASSIC` / `SERVERLESS`, jamais `null`) **dans leur grain** : sans filtre, un
pipeline mixte apparaît **deux fois** et `cost_rank` repart à 1 pour chaque forme.

- Les routes de **coût** pipeline (`/pipelines/overview` — lignes *et* KPI —, `/pipelines/cost`,
  le détail et `/pipelines/{id}/cost-trend`) filtrent `compute_kind = 'CLASSIC'` : la page IHM
  est celle des *clusters* DLT. Le champ est servi dans le payload (`"compute_kind": "CLASSIC"`).
- **Non filtrées** : `/pipelines/efficiency` et `/pipelines/{id}/uptime-trend`, qui lisent
  `*_efficiency_*` — déjà 100 % classiques par construction (source `node_timeline`), et sans
  colonne `compute_kind`. La note « population plus petite que `/pipelines/cost` » ci-dessus
  perd donc sa cause principale : les deux populations sont désormais comparables, l'écart
  résiduel n'étant plus que la couverture `node_timeline`.
- `forecast?object_type=PIPELINE` reste **une série par pipeline, toutes formes confondues**
  (agrégation explicite côté gold) : `object_id` ne porte pas `compute_kind` et la réponse est
  inchangée.
- Doc antérieure à corriger le jour où l'on y retouche : le champ `cluster_count` de l'exemple
  `/pipelines/overview` (T002) n'existe dans aucune des deux tables pipeline — le grain est le
  pipeline, pas le cluster. Hors périmètre T008, signalé sans le modifier.
