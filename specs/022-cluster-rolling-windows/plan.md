# Implementation Plan: Pages Cluster sur les fenêtres glissantes `gold_dbx_compute_*_rolling`

**Branch**: `dataeng/022-cluster-rolling-windows` → `backend/022-…` → `frontend/022-…` | **Date**: 2026-09-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/022-cluster-rolling-windows/spec.md`

**Réf. socle réutilisé** :
- [`pipelines/gold_dbx_compute/cluster_cost_rolling.py`](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_cost_rolling.py) — **modèle de référence** pour la fenêtre précédente : lecture élargie à `2 * window_days`, découpe par `CASE WHEN period_start > as_of_date - window_days`, `cost_usd_prev_window` + `cost_delta_pct`.
- [`pipelines/gold_dbx_compute/cluster_efficiency_rolling.py`](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_efficiency_rolling.py) — CTE `anchor` / `windows` / `latest_attrs` / `agg`, moyennes pondérées par `uptime_hours`, percentiles depuis histogrammes.
- [`app/api/services/compute_metrics_clusters.py`](../../packages/dcm-backend/app/api/services/compute_metrics_clusters.py) — 6 fonctions `fetch_*`, `try/except` + soft-fail, requêtes paramétrées `?`, pagination.
- [`app/api/services/compute_metrics_common.py`](../../packages/dcm-backend/app/api/services/compute_metrics_common.py) — `_scope_where`, `_resolve_period`, `_previous_period`, `_row_to_dict`, `_empty_page`.
- [`src/components/domain/compute/compute-data-table.tsx`](../../packages/dcm-frontend/src/components/domain/compute/compute-data-table.tsx) — table générique déjà utilisée par les 4 onglets.

## Summary

Trois livrables, dans cet ordre imposé (chacun consomme le précédent) :

1. **T001 DataEng** — enrichir `gold_dbx_compute_cluster_efficiency_daily` du `cluster_name` (absent des deux tables efficiency alors que les trois onglets l'affichent) et de la configuration d'autoscaling du cluster (`autoscale_enabled`, `autoscale_min_workers`, `autoscale_max_workers`, `configured_worker_count`), lus dans la CTE `clusters_as_of` qui joint **déjà** `curated_dbx_compute_clusters` pour les types de node — aucune nouvelle source. Puis, dans `..._efficiency_rolling`, propager ces 4 colonnes via `latest_attrs` et ajouter la fenêtre précédente (`uptime_hours_prev_window`, `idle_pct_prev_window`) par une CTE `prev_agg` dédiée jointe en `LEFT JOIN` — plutôt qu'en élargissant la CTE `agg` existante, ce qui obligerait à re-conditionner ses 13 agrégats et risquerait de casser les métriques en place. Les deux tables sont ensuite **migrées** : type élargi en place sur la quotidienne, `DROP`/recréation de la rolling, puis backfill `full_refresh` en run ponctuel hors job (le commit `b102155` fait passer `active_hours` de `bigint` à `decimal` et `MERGE WITH SCHEMA EVOLUTION` ajoute des colonnes mais ne convertit pas les types). Supprimer la quotidienne — décision R3 initiale — est à éviter : la reconstruction complète qui en découle dépasse le timeout du job (cf. [research.md](./research.md) R3 révisé et [quickstart.md](./quickstart.md) §2).

2. **T002 Backend** — brancher les 3 vues de liste des clusters sur `*_cost_rolling` / `*_efficiency_rolling` avec un paramètre `window_days ∈ {1, 7, 30, 90}` validé par FastAPI (`Query(enum=…)`), exposer `window_days` / `from_date` / `to_date` (lus dans `window_start` / `as_of_date`, pas recalculés), joindre `dim_dbx_workspace` pour `workspace_name`, dériver `dbu_cost = cost_usd / dbu_quantity`, et ajouter `/clusters/{cluster_id}/lifetime-trend` construit sur le même patron que `cost-trend` (granularité `day|week|month` déjà en place). `fetch_clusters_governance` **n'est pas touchée**.

3. **T003 Frontend** — remplacer, sur la page Cluster, la période libre du header par un sélecteur de 4 plages statiques affichant `from_date → to_date` issus de l'API, étendre les colonnes des onglets Overview / Cost / Efficiency, et refondre le détail cluster : bloc de caractéristiques techniques + histogramme `COST TREND (≈90 DAYS)` et courbe `Lifetime TREND (≈90 DAYS)`, chacun avec un commutateur jour / semaine / mois.

## Technical Context

**Language/Version**: Python 3.12 (pipeline + backend), TypeScript 5 / React 18 (frontend).

**Primary Dependencies**: aucune nouvelle, dans les trois packages. Pipeline : `pyspark` + `pipelines/common/`. Backend : FastAPI + `DatabricksWarehousePool` existant. Frontend : React Query + les composants `compute-*` en place ; les deux graphes sont dessinés en SVG inline comme l'actuel `compute-cost-trend-chart.tsx` (aucune librairie de charting à introduire).

**Storage**: Unity Catalog `it.ba_data_connect_monitoring__<env>` (dev `__d`, prod `__p`). Tables écrites : `gold_dbx_compute_cluster_efficiency_daily`, `..._efficiency_rolling`. Tables lues par le backend : `..._cluster_cost_rolling`, `..._cluster_efficiency_rolling`, `..._cluster_governance` (inchangée), `..._cluster_cost_daily` et `..._cluster_efficiency_daily` (tendances par cluster uniquement), `dim_dbx_workspace`.

**Testing**: pipeline → `pytest` avec `FakeSpark` (assertions sur le SQL généré, aucune JVM), `.venv/bin/python -m pytest`. Backend → `pytest` (`tests/test_compute_metrics_services.py`, `tests/test_compute_metrics_routes.py`). Frontend → `vitest` + fixtures MSW (`src/test/fixtures/compute-clusters.ts`).

**Target Platform**: Databricks Jobs (wheel task, job `job_dcm_gold_dbx_compute.yml`) pour T001 ; API FastAPI et SPA React pour T002/T003.

**Project Type**: multi-package — 3 branches filles, une par package.

**Performance Goals**: les vues de liste passent d'une agrégation à la volée sur N jours de `*_daily` à une lecture d'une ligne par cluster dans `*_rolling` → moins de travail côté warehouse, pas d'objectif chiffré. Les tendances par cluster restent bornées à ≈90 jours.

**Constraints**:
- `uptime_hours_prev_window` / `idle_pct_prev_window` **`NULL` et non `0`** en l'absence de fenêtre précédente (`LEFT JOIN` sans `COALESCE`) — un `0` s'afficherait comme une chute de 100 %.
- `window_days` strictement dans `{1, 7, 30, 90}` : une valeur hors liste est rejetée (422), jamais rabattue silencieusement.
- La jointure `dim_dbx_workspace` **enrichit** : `LEFT JOIN`, jamais `INNER` (un workspace absent de la dimension ne doit pas faire disparaître ses clusters).
- Onglet Governance strictement inchangé (contrat, requête, rendu).
- Aucune agrégation métier nouvelle côté backend : ce qui est agrégeable est agrégé en gold (P12).

**Scale/Scope**: T001 = 2 builders + `specs.py` (commentaires de colonnes) + 2 fichiers de tests ; T002 = 1 service (~+250 lignes), 1 module de routes, 2 fichiers de tests ; T003 = 1 page, 1 hook, 3 composants (dont 1 nouveau graphe), 1 fixture, 2 fichiers de tests.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principe | Statut | Justification |
|---|---|---|
| P1 Test-First & Code Quality (NON-NEGOTIABLE) | ✅ PASS | Tests écrits avant le code dans les 3 stories : SQL généré (pipeline), services + routes (backend), rendu + interactions (frontend). Gates lint/types/tests par package. |
| P2 Simplicité, Explicitness & Versioning | ✅ PASS | Aucune nouvelle dépendance ni framework. `prev_agg` en CTE séparée plutôt qu'une réécriture des 13 agrégats existants. `window_days` est un entier validé par une énumération explicite. |
| P3 Self-Documenting Code | ✅ PASS | Les 6 nouvelles colonnes gold reçoivent un `column_comment` avec leur formule ; les commentaires ne portent que le *pourquoi* (ex. pourquoi `NULL` et non `0`). |
| P4 Fail Fast, Fail Loud | ⚠️ NOTE | `window_days` invalide → 422 immédiat. Mais les `fetch_*` conservent leur `try/except` + soft-fail (retour vide, `logger.exception`) : comportement **pré-existant** et uniforme sur toute la page Compute, non introduit ici. |
| P5 Architecture explicite & modularité | ✅ PASS | Frontière médaillon respectée : le backend ne lit que du gold et des dimensions. Le pipeline reste seul à toucher curated. |
| P6 Idempotency by Design | ✅ PASS | Les 2 tables gardent leur `MERGE` sur `merge_keys` inchangées ; les nouvelles colonnes sont déterministes pour un état source donné. Le `DROP` + run `full` de migration est rejouable (gold intégralement dérivable). |
| P7/P8 Secrets Management (NON-NEGOTIABLE) | ✅ PASS | Aucun secret touché. Déploiement pipeline via bundle et OAuth (`databricks auth login`) — **jamais** de PAT. |
| P9 No Fake Data in Production (NON-NEGOTIABLE) | ✅ PASS | Les 6 colonnes dérivent de données réelles. Les fixtures ajoutées restent cantonnées à `src/test/`. Une comparaison impossible se rend « non disponible », pas remplie d'une valeur inventée. |
| P10 Observability & Traceability | ⚠️ NOTE | `logging` stdlib côté pipeline/backend (pas de JSON structuré) — écart pré-existant et uniforme, non introduit ici. |
| P11 Naming Conventions | ✅ PASS | `*_prev_window` reprend la convention déjà posée par `cost_usd_prev_window`. `autoscale_*` évite la collision avec `worker_count_max`, qui désigne déjà le **maximum observé** par minute et non une borne de configuration. |
| P12 Medallion — Aggregations on Gold Only | ✅ PASS | C'est le cœur de la feature : la fenêtre précédente et la moyenne pondérée sont calculées en gold, pas dans l'API. |
| P13 Immutable Raw Layer | N/A | Aucune couche Raw dans ce flux. |
| P14 Schema Versioning | N/A | Tables gold hors `MetricPayload`. |
| P15 API Contract Stability | ⚠️ NOTE | `window_days`, `from_date`, `to_date` et 6 champs sont **ajoutés** ; `period_start`/`period_end` restent acceptés (ignorés par les vues de liste, toujours utilisés par les tendances). Seule rupture assumée : les vues de liste renvoient désormais la fenêtre du gold et non la période demandée — inhérent à la demande (« les plages sont statiques »), tracée en Complexity Tracking. |
| P16 Frontend Quality | ✅ PASS | Composants typés, réutilisation de `compute-data-table` et des états vides existants, tests vitest. |

**Verdict** : PASS. Trois `⚠️ NOTE`, toutes sur des écarts pré-existants ou explicitement tracés, aucune sur un principe NON-NEGOTIABLE.

## Project Structure

### Documentation

```
specs/022-cluster-rolling-windows/
├── spec.md
├── plan.md              ← ce fichier
├── research.md           ← décisions techniques (Phase 0)
├── data-model.md         ← colonnes gold ajoutées + contrat de lecture
├── contracts/
│   └── compute-clusters-rolling.md   ← formes de requête/réponse API
├── quickstart.md         ← déploiement + vérification dev de T001
├── intake.json
├── domain-scope.json
└── checklists/requirements.md
```

### Code — fichiers touchés

```
packages/dcm-databricks-pipeline/            # T001
├── pipelines/gold_dbx_compute/
│   ├── cluster_efficiency_daily.py          # + 4 colonnes autoscaling (CTE clusters_as_of)
│   ├── cluster_efficiency_rolling.py        # + 4 colonnes propagées, + CTE prev_agg
│   └── specs.py                             # column_comments des 6 nouvelles colonnes
└── tests/gold_dbx_compute/
    ├── test_cluster_efficiency_daily.py
    └── test_cluster_efficiency_rolling.py

packages/dcm-backend/                        # T002
├── app/api/services/compute_metrics_clusters.py   # rolling + window_days + workspace_name + dbu_cost + lifetime trend
├── app/api/routes/compute_metrics.py              # Query(window_days), route lifetime-trend
└── tests/
    ├── test_compute_metrics_services.py
    └── test_compute_metrics_routes.py

packages/dcm-frontend/                       # T003
├── src/pages/ComputeClusters.tsx                  # sélecteur de plage + colonnes des onglets
├── src/pages/ComputeClusters.test.tsx
├── src/hooks/useComputeClustersQueries.ts         # window_days, lifetime-trend
├── src/types/api.ts                               # types des réponses enrichies
├── src/components/domain/compute/
│   ├── compute-cluster-drawer.tsx                 # specs techniques + 2 graphes
│   ├── compute-cost-trend-chart.tsx               # + variante histogramme
│   └── compute-trend-chart.tsx                    # nouveau : graphe générique jour/semaine/mois
└── src/test/fixtures/compute-clusters.ts
```

## Phase 0 — Research

Décisions et alternatives écartées : [research.md](./research.md). Résumé des 6 décisions :

| # | Décision | Alternative écartée |
|---|---|---|
| R1 | Fenêtre précédente via une CTE `prev_agg` en `LEFT JOIN` | Élargir la CTE `agg` à `2 * window_days` comme `cluster_cost_rolling` — imposerait de conditionner 13 agrégats existants |
| R2 | `autoscale_enabled = min_autoscale_workers IS NOT NULL AND max_autoscale_workers IS NOT NULL` ; bornes `NULL` si désactivé, + `configured_worker_count` | `COALESCE(min_autoscale_workers, worker_count)` — afficherait une plage d'autoscaling là où aucune n'est configurée |
| R3 | Migration par `DROP TABLE` + run `full` des 2 tables efficiency | `delta.enableTypeWidening` + `ALTER COLUMN` — conserve l'historique mais le gold est intégralement dérivable, donc coût inutile |
| R4 | `window_days` en `Query(..., enum=[1, 7, 30, 90])` | Chaîne `range=last_7d` — dupliquerait un mapping libellé → jours des deux côtés |
| R5 | `from_date`/`to_date` lus dans le gold (`window_start`/`as_of_date`) | Calcul depuis `today` côté front — mentirait dès qu'un run de pipeline est en retard |
| R6 | Tendances par cluster servies par les tables `*_daily` | Les servir depuis `*_rolling` — impossible : une seule ligne par fenêtre, pas de série |

## Phase 1 — Design

- Colonnes gold ajoutées, types et formules : [data-model.md](./data-model.md).
- Paramètres et formes de réponse des 6 endpoints clusters : [contracts/compute-clusters-rolling.md](./contracts/compute-clusters-rolling.md).
- Déploiement et vérification de T001 sur le dev : [quickstart.md](./quickstart.md).

### Ordre d'exécution imposé

```
T001 (gold)  ──► déploiement dev + vérification des 6 colonnes ──► T002 (API) ──► T003 (UI)
```

T002 ne démarre qu'une fois les tables enrichies **peuplées en dev** : sinon ses tests
passent sur des colonnes qui n'existent pas encore et l'API échoue au premier appel réel.

## Complexity Tracking

| Écart | Pourquoi il est assumé |
|---|---|
| Les vues de liste ignorent `period_start`/`period_end` | Demande explicite : « les plages sont statiques (1j, 7j, 30j, ou 90j) ». Les tables `*_rolling` sont des snapshots ancrés sur `as_of_date` ; honorer une période libre exigerait de relire les `*_daily`, c'est-à-dire de ne pas faire la feature. Les paramètres restent acceptés pour ne pas casser les appelants. |
| 4 colonnes de configuration d'autoscaling plutôt que 2 | `autoscale_min_workers`/`autoscale_max_workers` seules laisseraient la cellule « min_node max_node » vide pour tous les clusters à taille fixe — la majorité de la population en dev. `configured_worker_count` la remplit sans inventer de plage. |
| `soft-fail` conservé sur les `fetch_*` | Comportement pré-existant de toute la page Compute ; le changer sortirait du périmètre et modifierait le contrat des 12 autres endpoints. |

## Progress Tracking

- [x] Phase 0 — Research (`research.md`)
- [x] Phase 1 — Design (`data-model.md`, `contracts/`, `quickstart.md`)
- [x] Constitution Check — PASS
- [x] Phase 2 — `tasks.md` + 3 `stories/` + `merge-strategy.md` (`dcm-parse-tasks.sh` exit 0, 0 warning)
- [x] T001 implémentée, déployée et vérifiée en dev (run `436955739280464` `SUCCESS`, les 5
      contrôles de `quickstart.md` §4 verts)
- [x] T002 implémentée, et vérifiée au niveau HTTP contre la donnée dev sur les 4 fenêtres —
      2 défauts trouvés et corrigés, 82 tests verts
- [ ] T003 implémentée (tests verts) — reste à vérifier dans le navigateur
