# T002 — API clusters par fenêtre glissante

**Domain**: backend
**Package**: packages/dcm-backend
**Branch**: `backend/022-api-clusters-par-fenetre-glissante`
**Jira**: not dispatched (dispatch non exécuté sur cette feature)
**Depends on**: T001 (colonnes gold peuplées en dev)
**Work type**: feature

## Description

Les 6 endpoints clusters de `/api/v1/compute-metrics` agrègent aujourd'hui les tables
`*_daily` à la volée sur une période libre. Cette task les branche sur
`gold_dbx_compute_cluster_cost_rolling` et `..._cluster_efficiency_rolling` avec un
paramètre `window_days ∈ {1, 7, 30, 90}`, expose la période réellement couverte
(`from_date` = `window_start`, `to_date` = `as_of_date`, lues dans la donnée et non
recalculées depuis `today`), joint `dim_dbx_workspace` pour `workspace_name`, dérive
`dbu_cost = cost_usd / dbu_quantity`, et ajoute
`GET /clusters/{cluster_id}/lifetime-trend` sur le patron de `cost-trend`.

`fetch_clusters_governance` n'est pas touchée : `cluster_governance` est un snapshot sans
notion de fenêtre.

## Files to create/modify

- UPDATE `packages/dcm-backend/app/api/services/compute_metrics_clusters.py`
- UPDATE `packages/dcm-backend/app/api/routes/compute_metrics.py`
- UPDATE `packages/dcm-backend/tests/test_compute_metrics_services.py`
- UPDATE `packages/dcm-backend/tests/test_compute_metrics_routes.py`

## Sub-tasks

- [ ] Tests d'abord : `window_days` invalide → 422 ; workspace absent de la dimension →
      ligne conservée avec `workspace_name` `null` ; `dbu_quantity` nul ou `0` → `dbu_cost`
      `null` ; fenêtre précédente `NULL` → delta `null` ; Governance inchangée.
- [ ] Constantes de tables : ajouter `_COST_ROLLING`, `_EFFICIENCY_ROLLING` ; conserver
      `_COST_DAILY` / `_EFFICIENCY_DAILY` pour les tendances par cluster.
- [ ] `window_days: int = Query(default=1, enum=[1, 7, 30, 90])` sur overview / cost /
      efficiency / détail. Pas de repli silencieux sur 1.
- [ ] `fetch_clusters_overview` : pivot `cost_rolling`, `LEFT JOIN efficiency_rolling` sur
      les 3 clés **+ `window_days`**, `LEFT JOIN cluster_governance`, `LEFT JOIN
      dim_dbx_workspace`. KPI recalculés depuis les sommes de la fenêtre.
- [ ] `fetch_clusters_cost` : `+ workspace_name`, `+ dbu_cost` (`NULLIF(dbu_quantity, 0)`),
      `+ cost_usd_prev_window` ; `ba_name` et `cost_usd_prev_day` disparaissent (absents du
      rolling ; `ba_name` vérifié non rendu par le front).
- [ ] `fetch_clusters_efficiency` : `+ workspace_name`, `+ cluster_name`, les 4 colonnes
      d'autoscaling, `uptime_hours_prev_window` / `idle_pct_prev_window` et leurs deltas.
- [ ] Bloc `window` (`window_days`, `from_date`, `to_date`) dans les 3 réponses de liste ;
      `period` conservé pour ne pas casser les appelants.
- [ ] `fetch_cluster_detail` : blocs `cost` et `efficiency` depuis les tables rolling pour
      la fenêtre demandée, y compris les caractéristiques techniques.
- [ ] `fetch_cluster_lifetime_trend` + route `/clusters/{cluster_id}/lifetime-trend` :
      `SUM(uptime_hours)` par bucket, `idle_pct` en moyenne **pondérée par `uptime_hours`**
      — une moyenne simple donnerait le même poids à un jour allumé 20 h et à un jour
      allumé 20 min.
- [ ] Gates : `pytest`, `ruff`, `mypy`.

## Acceptance Criteria

- [ ] `window_days ∈ {1, 7, 30, 90}` accepté ; toute autre valeur → 422.
- [ ] Les 3 vues de liste renvoient une ligne par cluster et le bloc `window` avec
      `from_date`/`to_date` égaux à `window_start`/`as_of_date` du gold.
- [ ] Aucune requête des vues de liste ne touche `*_cluster_cost_daily` ni
      `*_cluster_efficiency_daily` (SC-003) ; ces tables ne servent plus qu'aux tendances.
- [ ] `dim_dbx_workspace` en `LEFT JOIN` : un `workspace_id` absent de la dimension ne fait
      pas disparaître ses clusters.
- [ ] `dbu_cost` est `null` si `dbu_quantity` est nul ou vaut `0` — pas de division par zéro.
- [ ] `uptime_hours_delta_pct` est `null` si la fenêtre précédente est `NULL` ou nulle ;
      `idle_pct_delta_pts` est un écart en **points**.
- [ ] `/clusters/{cluster_id}/lifetime-trend` renvoie la même forme que `cost-trend`
      (`items`, `period`, `granularity`) pour `day|week|month`.
- [ ] `GET /clusters/governance` : réponse et requête identiques à avant (test de
      non-régression).
- [ ] Le service ne lit que du gold et des dimensions — jamais de `curated_*` (P5/P12).

## Tests

```bash
cd packages/dcm-backend
uv run pytest tests/test_compute_metrics_services.py tests/test_compute_metrics_routes.py
uv run pytest
uv run ruff check app tests
uv run mypy app
```

Puis appel réel sur le dev pour les 4 valeurs de `window_days`.

## Out of scope

- Pages Warehouses : conservent leur période libre et leurs tables `*_daily`.
- `GET /api/v1/compute` de `routes/clusters.py` (page héritée) et ses champs
  `autoscale_min`/`autoscale_max` jamais peuplés.
- `reliability_rolling`.
- Remplacer le `try/except` + soft-fail des `fetch_*` : comportement pré-existant commun
  aux 15 endpoints compute, le changer sortirait du périmètre.

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside `packages/dcm-backend`
- [ ] Diff stays reviewable
- [ ] Sub-spec checkboxes reviewed
- [ ] T001 vérifiée en dev avant de démarrer

## Notes

- Formes de requête et de réponse endpoint par endpoint :
  [contracts/compute-clusters-rolling.md](../contracts/compute-clusters-rolling.md).
- Graphe de jointure et champs dérivés : [data-model.md](../data-model.md).
- `window_days` en entier plutôt qu'un libellé `last_7d` : [research.md](../research.md) R4.
- Tendances conservées sur les `*_daily` : R6 — une table `*_rolling` n'a qu'un point par
  fenêtre, elle ne peut pas alimenter une série de ≈90 points.

### Vérifiée en dev — 2 défauts trouvés hors des tests unitaires

Les 7 endpoints ont été interrogés **au niveau HTTP** (ASGI + vrai pool + donnée dev) sur
les 4 fenêtres. Détail des 2 défauts et de leur correction : [tasks.md](../tasks.md),
section « Les 2 défauts que la vérification de T002 a révélés ». En résumé :

1. `Decimal` → chaîne JSON, parce que l'annotation `-> dict[str, Any]` des routes sert de
   `response_model` à FastAPI. Corrigé dans `_json_safe` (`compute_metrics_common.py`).
2. `cost_usd_prev_window` à `0` au lieu de `NULL`, ce qui violait P9 de T003. Corrigé par
   `_normalize_prev_cost` (`compute_metrics_clusters.py`).

La leçon vaut pour la suite : un test unitaire qui construit ses lignes avec des `float`
Python ne peut pas voir le premier défaut, et un mock qui renvoie `None` pour la fenêtre
précédente ne peut pas voir le second. Les 4 tests de régression ajoutés utilisent donc des
`Decimal`, et l'un d'eux vérifie l'octet de sortie **après** passage par Pydantic.

Également établi par cette vérification, et à ne pas retenter : `ClusterWindowDays(IntEnum)`
est la seule forme qui donne 200 sur 1/7/30/90 et 422 partout ailleurs (0, 5, 14, 365, -7,
`abc` vérifiés) ; `/clusters/governance` ne porte bien aucun bloc `window` ; les tendances
non plus, et elles tolèrent un `window_days` parasite.
