# Contrats API — clusters sur fenêtres glissantes

Base : `/api/v1/compute-metrics`. Les paramètres de scope existants
(`workspace_id`, `workspace_ids`, `cloud_provider`, `source_lz_id`, `source_lz_ids`,
`page`, `page_size`) sont **inchangés** sur tous les endpoints.

## Paramètre commun aux 3 vues de liste

| Paramètre | Type | Défaut | Validation |
|---|---|---|---|
| `window_days` | int | `1` | `IntEnum ClusterWindowDays{1, 7, 30, 90}` → 422 hors liste |

La validation passe par un `IntEnum` et non par `Query(enum=[…])`, qui ne documente que
l'OpenAPI sans rien rejeter (mesuré : `window_days=5` → 200). Détail en
[research.md](../research.md) R4.

`period_start` / `period_end` restent acceptés (compatibilité des appelants) mais
**n'ont plus d'effet** sur les vues de liste : les tables `*_rolling` sont ancrées sur
`as_of_date`. Ils continuent de délimiter les tendances par cluster.

## Bloc `window` — présent dans les 3 réponses de liste

```json
{
  "window": {
    "window_days": 7,
    "from_date": "2026-08-29",
    "to_date": "2026-09-04"
  }
}
```

`from_date` = `window_start`, `to_date` = `as_of_date`, lus dans la ligne gold. Le bloc
`period` existant est conservé pour ne pas casser les appelants ; il porte la même paire
de dates.

## `GET /clusters/overview`

Réponse (structure inchangée, `items` enrichis) :

```json
{
  "kpis": {
    "total_cost_usd": 12345.67,
    "cost_delta_pct": -8.4,
    "active_clusters": 42,
    "zombie_count": 3,
    "open_recommendations": 11
  },
  "items": [
    {
      "cloud_provider": "azure",
      "workspace_id": "1234567890",
      "workspace_name": "dbw-analytics-prd",
      "cluster_id": "0101-…",
      "cluster_name": "etl-main",
      "cluster_type": "ALL_PURPOSE",
      "owner": "…",
      "cost_usd": 812.4,
      "cost_usd_prev_window": 902.1,
      "cost_delta_pct": -9.9,
      "uptime_hours": 118.5,
      "uptime_hours_prev_window": 121.0,
      "uptime_hours_delta_pct": -2.1,
      "utilization_status": "OVER",
      "cpu_util_p95_pct": 22.7,
      "idle_pct": 41.2,
      "severity": "LOW"
    }
  ],
  "window": { "window_days": 7, "from_date": "2026-08-29", "to_date": "2026-09-04" },
  "period": { "start": "2026-08-29", "end": "2026-09-04" }
}
```

KPI recalculés sur la fenêtre : `total_cost_usd = SUM(cost_usd)`,
`cost_delta_pct` depuis `SUM(cost_usd_prev_window)`,
`active_clusters = SUM(CASE WHEN cost_usd > 0 THEN 1 ELSE 0 END)`,
`zombie_count = COUNT(is_zombie)`. `open_recommendations` est inchangé.

`active_clusters` n'est **pas** `COUNT(*)` : `cluster_cost_rolling` matérialise aussi les
clusters facturés uniquement sur la fenêtre **précédente**
(`WHERE cost_usd <> 0 OR cost_usd_prev_window <> 0` dans le builder), qu'un `COUNT(*)`
compterait comme actifs aujourd'hui.

**Champs ajoutés** : `workspace_name`, `cost_usd_prev_window`, `cost_delta_pct`,
`uptime_hours_prev_window`, `uptime_hours_delta_pct`.
**Champ retiré** : aucun.

## `GET /clusters/cost`

Filtres existants conservés : `search`, `sku_group`, `sort=cost_desc|name|rank`.

```json
{
  "items": [
    {
      "cloud_provider": "azure",
      "workspace_id": "1234567890",
      "workspace_name": "dbw-analytics-prd",
      "cluster_id": "0101-…",
      "cluster_name": "etl-main",
      "cluster_type": "ALL_PURPOSE",
      "owner": "…",
      "cost_center": "…",
      "sku_group": "ALL_PURPOSE_COMPUTE",
      "dbu_quantity": 1420.5,
      "dbu_cost": 0.572,
      "cost_usd": 812.4,
      "cost_usd_prev_window": 902.1,
      "cost_delta_pct": -9.9,
      "cost_rank": 3,
      "is_top_cost": true
    }
  ],
  "total": 42, "page": 1, "page_size": 25,
  "window": { … }, "period": { … }
}
```

**Champs ajoutés** : `workspace_name`, `dbu_cost`, `cost_usd_prev_window`.
**Champs retirés** : `cost_usd_prev_day` (n'a pas de sens à la maille fenêtre — la table
rolling ne le porte pas), `ba_name` (absent de `cluster_cost_rolling` ; vérifié non rendu
par le front, seul `types/api.ts` le déclare), `period_start` (la table rolling ne le porte
pas non plus : la fenêtre est décrite par le bloc `window`, pas par une date de ligne).

## `GET /clusters/efficiency`

Filtres existants conservés : `utilization_status` (dont la valeur spéciale `ZOMBIE`),
`is_zombie`.

```json
{
  "items": [
    {
      "cloud_provider": "azure",
      "workspace_id": "1234567890",
      "workspace_name": "dbw-analytics-prd",
      "cluster_id": "0101-…",
      "cluster_name": "etl-main",
      "cluster_type": "ALL_PURPOSE",
      "driver_node_type": "Standard_DS4_v2",
      "worker_node_type": "Standard_DS3_v2",
      "autoscale_enabled": true,
      "autoscale_min_workers": 2,
      "autoscale_max_workers": 8,
      "configured_worker_count": null,
      "uptime_hours": 118.5,
      "uptime_hours_prev_window": 121.0,
      "uptime_hours_delta_pct": -2.1,
      "idle_pct": 41.2,
      "idle_pct_prev_window": 38.0,
      "idle_pct_delta_pts": 3.2,
      "cpu_util_avg_pct": 12.1,
      "cpu_util_p95_pct": 22.7,
      "mem_util_avg_pct": 31.0,
      "mem_util_p95_pct": 44.9,
      "worker_count_avg": 3.2,
      "worker_count_max": 8,
      "autoscale_oscillation": 14,
      "is_zombie": false,
      "utilization_status": "OVER",
      "recommended_node_type": "Standard_DS2_v2",
      "rightsizing_reco": "Reduire vers Standard_DS2_v2",
      "estimated_savings_usd": 203.1
    }
  ],
  "total": 42, "page": 1, "page_size": 25,
  "window": { … }, "period": { … }
}
```

**Champs ajoutés** : `workspace_name`, `cluster_name`, `autoscale_enabled`,
`autoscale_min_workers`, `autoscale_max_workers`, `configured_worker_count`,
`uptime_hours_prev_window`, `uptime_hours_delta_pct`, `idle_pct_prev_window`,
`idle_pct_delta_pts`.
**Champ retiré** : `active_hours` (conservé en base, non demandé par l'onglet — la
colonne reste dans la table gold).

`cluster_name` et `worker_count_max` cohabitent avec `autoscale_max_workers` :
`worker_count_max` est le **maximum observé** par minute sur la fenêtre,
`autoscale_max_workers` la **borne configurée**.

Un cluster éteint sur **toute** la fenêtre est absent de cet onglet : la table efficiency
ne matérialise pas de ligne sans jour allumé (`WHERE uptime_hours > 0`, filtre
pré-existant). Il reste listé sur l'Overview, qui pivote sur la table de coût — avec
`uptime_hours` et `uptime_hours_prev_window` à `null`.

## `GET /clusters/governance` — inchangé

Aucun changement : ni paramètre, ni requête, ni réponse. `window_days` n'est **pas**
ajouté (la table `cluster_governance` est un snapshot sans notion de fenêtre).

## `GET /clusters/{cluster_id}`

Structure inchangée (`cost`, `efficiency`, `governance`, `period`) **plus le bloc `window`**,
identique à celui des vues de liste — le détail est lu pour une fenêtre donnée, il doit
pouvoir la légender. Les blocs `cost` et `efficiency` proviennent désormais des tables
`*_rolling` pour la fenêtre demandée (`window_days`), donc portent tous les champs ci-dessus
— y compris les 4 colonnes d'autoscaling qui alimentent le bloc « caractéristiques
techniques » du détail, `dbu_cost`, et les deux deltas dérivés
(`uptime_hours_delta_pct`, `idle_pct_delta_pts`).

`GET /clusters/governance` n'a **pas** de bloc `window` : sa table est un snapshot.

## `GET /clusters/{cluster_id}/cost-trend` — inchangé

`period_start`, `period_end`, `granularity=day|week|month`. Continue de lire
`gold_dbx_compute_cluster_cost_daily`.

## `GET /clusters/{cluster_id}/lifetime-trend` — nouveau

Mêmes paramètres et même forme que `cost-trend`, sur
`gold_dbx_compute_cluster_efficiency_daily` :

```json
{
  "items": [
    { "bucket": "2026-09-01", "uptime_hours": 21.4, "idle_pct": 38.2 }
  ],
  "period": { "start": "2026-06-07", "end": "2026-09-04" },
  "granularity": "day"
}
```

- `uptime_hours` : `SUM(uptime_hours)` par bucket (additif).
- `idle_pct` : moyenne pondérée par `uptime_hours` sur le bucket — **pas** une moyenne
  simple des pourcentages quotidiens, qui donnerait le même poids à un jour allumé
  20 heures et à un jour allumé 20 minutes.
- `idle_pct` vaut `null` — pas `0` — si aucun jour du bucket ne porte de mesure : un `0 %`
  se lirait comme un cluster occupé en permanence.
- Buckets vides absents de la série (comme `cost-trend`), le front gère la discontinuité.
- Pas de `window_days` sur les deux tendances : elles servent une série sur
  `period_start`/`period_end`, ce qu'une table `*_rolling` ne peut pas faire (R6).
