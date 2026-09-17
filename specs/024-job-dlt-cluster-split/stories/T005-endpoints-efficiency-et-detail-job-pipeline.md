# T005 — Endpoints efficiency + détail + tendances (job & pipeline DLT)

**Domain**: backend
**Package**: packages/dcm-backend (+ packages/dcm-commons)
**Branch**: `backend/024-endpoints-efficiency-detail-tendances`
**Jira**: à créer (`/speckit.dcm.dispatch`) — Epic [DCINT-325](https://tdf.atlassian.net/browse/DCINT-325)
**Depends on**: T004 (4 tables gold d'efficacité déployées et vérifiées en dev)
**Work type**: feature

## Description

Amendement du 2026-09-09. Exposer, aux grains stables `job_id` et `dlt_pipeline_id`, ce que la
page All-purpose expose déjà au grain `cluster_id` : l'efficacité en liste, le détail d'un
élément, et ses tendances. Six routes neuves, deux services étendus, **aucune réponse
existante modifiée**.

| Route | Source gold | Sert |
|---|---|---|
| `GET /compute/jobs/efficiency` | `gold_dbx_compute_job_efficiency_rolling` | sous-onglet Efficiency |
| `GET /compute/pipelines/efficiency` | `gold_dbx_compute_pipeline_efficiency_rolling` | idem |
| `GET /compute/jobs/{job_id}` | `job_cluster_cost_rolling` + `job_efficiency_rolling` | tiroir |
| `GET /compute/pipelines/{dlt_pipeline_id}` | `pipeline_cost_rolling` + `pipeline_efficiency_rolling` | tiroir |
| `GET …/{id}/cost-trend` | `*_cost_daily` | tendance coût ≈90 j |
| `GET …/{id}/uptime-trend` | `*_efficiency_daily` | tendance uptime ≈90 j |

Payloads détaillés : [contracts/compute-job-pipeline.md](../contracts/compute-job-pipeline.md)
(section « amendement »).

## Files to create/modify

- UPDATE `app/api/services/compute_metrics_common.py` — accueillir `_uptime_delta_pct` et
  `_idle_delta_pts`, **descendus** de `compute_metrics_clusters.py` (pas dupliqués)
- UPDATE `app/api/services/compute_metrics_clusters.py` — importer les helpers descendus
  (aucun changement de comportement attendu)
- UPDATE `app/api/services/compute_metrics_jobs.py` — `fetch_jobs_efficiency`,
  `fetch_job_detail`, `fetch_job_cost_trend`, `fetch_job_uptime_trend` ; `__all__` étendu ;
  constantes de tables `_EFFICIENCY_ROLLING` / `_EFFICIENCY_DAILY`
- UPDATE `app/api/services/compute_metrics_pipelines.py` — les 4 homologues au grain
  `dlt_pipeline_id`
- UPDATE `app/api/routes/compute_metrics.py` — 6 routes ; **`/jobs/efficiency` et
  `/pipelines/efficiency` déclarées AVANT `/jobs/{job_id}` / `/pipelines/{dlt_pipeline_id}`**
- UPDATE `packages/dcm-commons/…` — schémas de réponse efficiency / detail / trend des 2 familles
- UPDATE `tests/test_compute_metrics_services.py`
- UPDATE `tests/test_compute_metrics_routes.py`

### Écarts constatés à l'implémentation

1. **Les tests ont atterri dans `tests/test_compute_metrics_jobs.py` et
   `tests/test_compute_metrics_pipelines.py`**, pas dans `test_compute_metrics_services.py` /
   `test_compute_metrics_routes.py` nommés ci-dessus : ces deux fichiers par grain existaient
   déjà depuis T003 et portent le harnais (`_settings()`, constantes de tables). Un troisième
   emplacement aurait séparé les tests d'efficacité de ceux de coût du **même** grain.
2. **Une ligne de plus dans `compute_metrics_warehouses.py`** : `fetch_warehouse_cost_trend`
   portait une 4ᵉ copie inline de la whitelist `day`/`week`/`month`, remplacée par le `_grain`
   descendu dans `common`. Iso-comportement, mais hors périmètre annoncé.
3. **`_grain` et `_round_pct` ont été descendus en plus** de `_uptime_delta_pct` /
   `_idle_delta_pts` : mêmes duplications, même raison (P2).
4. `packages/dcm-commons/dcm_commons/schemas/__init__.py` est aussi à modifier — il
   ré-exporte nommément chaque schéma.

## Sub-tasks

- [x] **Tests d'abord** :
      - `/jobs/efficiency` renvoie le grain `job_id` avec `job_name`, **sans** `is_zombie` ;
      - `/pipelines/efficiency` renvoie le grain `dlt_pipeline_id` avec `pipeline_name` ;
      - `/jobs/{job_id}` sur un id hors périmètre → **404**, pas un 200 vide ;
      - le détail porte `cost` + `efficiency` et **aucune clé `governance`** (absente, pas `null`) ;
      - `efficiency: null` quand le grain n'a pas de ligne d'efficacité — le détail reste servi ;
      - `uptime-trend` pondère `idle_pct` par `uptime_hours` et rend `null` (jamais `0`) sur un
        bucket non mesuré ;
      - **ordre des routes** : `GET /compute/jobs/efficiency` n'est pas résolu comme
        `/{job_id}` avec `job_id = "efficiency"` (test dédié, le piège est réel — le fichier le
        commente déjà pour `filter-options`) ;
      - `window_days` hors `{1,7,30,90}` → 422.
- [x] Descendre `_uptime_delta_pct` / `_idle_delta_pts` dans `compute_metrics_common.py` et les
      réutiliser aux 3 grains (P2 : pas de troisième copie).
- [x] `compute_metrics_jobs.py` : 4 `fetch_*`, calqués sur les homologues cluster
      (`fetch_clusters_efficiency`, `fetch_cluster_detail`, `fetch_cluster_cost_trend`,
      `fetch_cluster_lifetime_trend`), pagination serveur + recherche + tri comme `fetch_jobs_cost`.
- [x] `compute_metrics_pipelines.py` : les 4 homologues.
- [x] `compute_metrics.py` : 6 routes, périmètre appliqué par `_common_scope_kwargs` /
      `_scope_where` sans exception (y compris sur les tendances) ; `granularity` en
      `day`/`week`/`month`.
- [x] Schémas `dcm-commons` (réponses partagées backend/typage).
- [x] Gates : `pytest`, `ruff check`, `mypy`.
- [x] Vérification dev : chaque route appelée sur données réelles (AWS + Azure), le 404 et le
      cas `efficiency: null` observés pour de vrai, pas seulement en test.

## Vérification dev (2026-09-09)

App FastAPI réelle en processus (ASGITransport) sur le pool Databricks de dev — OAuth SPN,
`it.ba_data_connect_monitoring__d`, snapshot `as_of_date = 2026-09-09`. Les 4 tables T004 sont
peuplées sur les 4 fenêtres (job efficiency : 1152 / 2359 / 4846 / 6580 lignes).

| Contrôle | Résultat observé |
|---|---|
| `/jobs/efficiency?window_days=30` | AWS `total=1576`, Azure `total=3270`, fenêtre `2026-08-11 → 2026-09-09` |
| `/pipelines/efficiency?window_days=30` | AWS `total=172`, Azure `total=2` |
| Colonnes interdites (R8) | `is_zombie`, `cluster_name`, `cluster_type` absentes des items des 2 grains |
| Deltas | uptime en **%** (`+102,9`, `+18,0`), idle en **points** (`+7,7`, `−17,6`) ; `null` quand la fenêtre précédente est `NULL` |
| Ordre des routes | `/jobs/efficiency` et `/pipelines/efficiency` répondent une **liste** (`items` présent, `cost`/`efficiency` absents) — le segment variable ne les avale pas |
| Tris | `savings_desc` → 924,76 USD en tête ; `uptime` → 2940 h en tête ; `name` → ordre alphabétique |
| Détail | 7 clés, **`governance` absente**, `cost` + `efficiency` renseignés, `window` + `period` cohérents |
| `cost-trend?granularity=week` | 5 buckets hebdo, pas de clé `window` |
| `uptime-trend` | 30 buckets journaliers, `idle_pct` pondéré arrondi à 0,1 |
| 404 | `Job not found` / `Pipeline not found` sur un id inconnu |
| **`efficiency: null` réel** | job `953514147920842` (azure, 2,84 USD facturés) et pipeline `05e63a07-be8b-4500-8c5b-8cc60d25f594` (aws, **941,47 USD facturés**) → `200`, `cost` renseigné, `efficiency: null` |

Trois observations, aucune bloquante :

- **Le résidu SC-005 n'est pas cantonné aux petits grains** : le pipeline sans efficacité le plus
  coûteux pèse 941 USD sur la fenêtre 30 j (DLT serverless, aucune ligne `node_timeline`). T006
  doit afficher « — » sur ces lignes, et surtout ne pas les masquer : ce sont des coûts réels.
- `cluster_count` diffère entre `cost` (1024) et `efficiency` (1030) pour le même job — sources
  distinctes (facturation vs `node_timeline`), attendu, à ne pas réconcilier dans l'UI.
- `idle_pct: 100.00000000000001` traverse jusqu'au payload (ε de T001, non clampé sciemment).
  L'affichage devant arrondir, c'est sans effet visible.

**Périmètre projet** : sous l'utilisateur dev de `auth_disabled`, les 6 routes renvoient
`total=0` — mais `/clusters/cost`, `/clusters/efficiency`, `/jobs/cost` et `/pipelines/cost`,
déjà livrées, aussi. C'est le périmètre projet vide de cet utilisateur, partagé par
`_common_scope_kwargs`, pas un défaut de T005 ; la vérification ci-dessus a donc été faite avec
le périmètre non restreint d'un platform admin.

## Notes

- **`uptime-trend`, pas `lifetime-trend`** : « durée de vie » n'a pas de sens sur un cluster
  détruit à la fin de chaque run — la grandeur suivie est l'uptime **cumulé** du job/pipeline.
  Divergence de nommage assumée avec l'homologue cluster, tracée en Complexity Tracking.
- **Pas de bloc gouvernance** (C2 inchangé) : la clé est **absente** du payload, pas à `null` —
  `null` se lirait « gouvernance mesurée et vide ».
- **Soft-fail conservé** : les `fetch_*` renvoient vide / `None` plutôt que 500 quand une table
  gold manque, comme le reste du module (écart pré-existant, non aggravé ici).
- **Frontière médaillon** : lecture gold + `dim_dbx_workspace` uniquement. Le contrôle exact
  est `rg "curated_dbx" app/api/services/compute_metrics_*.py` → vide (vérifié). Élargi à tout
  `app/api/services/`, il remonte `lakeflow_overview.py`, antérieur et hors 024.
- La population de `/…/efficiency` est **plus petite** que celle de `/…/cost` (couverture
  `node_timeline`, DLT serverless) : ce n'est pas un bug de pagination, et ça n'appelle aucun
  remplissage par défaut.
