# feature : Pages Cluster sur les fenêtres glissantes `gold_dbx_compute_*_rolling`

**Feature Branch**: `022-cluster-rolling-windows` — branches filles `{domain}/022-cluster-rolling-windows`
**Work Type**: feature
**Priority**: P2
**Created**: 2026-09-04

**Input**: adapte le front et le back pour prendre en compte les tables rolling de gold_dbx_compute :
Cluster page — un filtre par plage : daily, last_7d, last_30, Last_90. Filtre date : les plages sont statiques (1j, 7j, 30j, ou 90j), afficher les plages « from_date » « to_date ».
Overview : une ligne par cluster, la valeur la plus récente. Indicateurs : Workspace_name, Cluster_name, Cluster_type, $Cost, $Cost_previous_period, Lifetime, Lifetime_previous_period, Utilization, Governance.
Cost → Workspace_name, Cluster_name, Cluster_type, $Cost, $Cost_previous_period, SKU, DBU_cost, DBU.
Efficiency → Workspace_name, Cluster_name, Cluster_type, driver_node_type, worker_node_type, Autoscaling, min_node max_node, Lifetime, Lifetime_previous_period, IDLE, IDLE_previous_period, avg_cpu_usage, P95_cpu_usage, avg_memory_usage, P95_memory_usage, STATUS, RECOMMENDED NODE, EST. SAVINGS.
Governance → laisser intacte.
Détail par Cluster : garder le format actuel en ajoutant les détails tech du cluster (driver_node_type, worker_node_type, Autoscaling, min_node max_node) + remplacer l'existant par un graphe COST TREND (≈90 DAYS) (histogramme) où on peut suivre point à point les coûts par jour, semaine et mois, et un graphe Lifetime TREND (≈90 DAYS) suivable de la même manière.

## Clarifications

### Session 2026-09-04

- Q: La plage sélectionnée remplace-t-elle le sélecteur de période libre du header sur la page Cluster ? → A: **Oui**. Les tables `*_rolling` sont des snapshots « as of » le dernier jour disponible (`as_of_date`) : une période libre n'a aucun effet sur elles. Le sélecteur de plage pilote `window_days` ; les filtres de scope (workspace, cloud provider, LZ) restent actifs et inchangés.
- Q: `from_date` / `to_date` sont-ils calculés côté front ? → A: **Non**, ils sont lus tels quels dans la réponse API (`window_start` / `as_of_date` du gold) — l'utilisateur voit la période réellement couverte par la donnée, pas une plage théorique calculée depuis `today` qui mentirait dès qu'un run est en retard.
- Q: `Governance` dans l'Overview = quelle valeur ? → A: **`severity`** (`HIGH`/`MEDIUM`/`LOW`, `NULL` = conforme), rendu en badge. C'est déjà la colonne remontée par l'Overview actuel (`app/api/services/compute_metrics_clusters.py:202`) et `gold_dbx_compute_cluster_governance` n'en porte qu'une par cluster — pas d'agrégation à inventer.
- Q: `Utilization` dans l'Overview = quelle valeur ? → A: **`utilization_status`** (`OVER`/`OPTIMAL`/`UNDER`), adossé à `cpu_util_p95_pct` pour l'ordre de tri et l'infobulle. Là aussi c'est le comportement actuel (`compute_metrics_clusters.py:197-201`) ; les pourcentages détaillés restent dans l'onglet Efficiency.

## Domain Scope

Depuis `intake.json` — « In scope » = lecture autorisée, « Ticket » = reçoit une Story.

| Domaine | In scope | Ticket Story | Packages |
|---------|----------|--------------|----------|
| Frontend | ✅ | ✅ | packages/dcm-frontend |
| Backend | ✅ | ✅ | packages/dcm-backend |
| DataEng | ✅ | ✅ | packages/dcm-databricks-pipeline |
| DevOps | ❌ | ❌ | — |
| QA | ❌ | ❌ | — |

## Ticket Plan

| Stories Jira | 3 |
|---|---|
| Mode | one_per_domain |
| Domaines avec ticket | dataeng, backend, frontend |

## Contexte

Le pipeline produit depuis sa création des fenêtres glissantes 1/7/30/90 jours
(`gold_dbx_compute_cluster_cost_rolling`, `..._efficiency_rolling`,
`..._reliability_rolling`) : une ligne par cluster et par fenêtre, avec la fenêtre
précédente déjà calculée pour le coût (`cost_usd_prev_window`, `cost_delta_pct`) et les
percentiles recalculés depuis les histogrammes quotidiens — un p95 quotidien n'étant pas
moyennable.

**Aucun consommateur ne les lit.** Les pages Cluster interrogent uniquement les tables
`*_daily` sur une période libre `period_start`/`period_end` choisie dans le header. Deux
conséquences : l'utilisateur ne peut pas comparer « les 7 derniers jours » à la semaine
précédente sans lire deux écrans, et l'application recalcule à la volée des agrégats que
le gold matérialise déjà (moyennes pondérées par le temps allumé, percentiles depuis
histogrammes) — donc plus lentement et avec un risque d'écart de définition.

Le besoin : sur la page Cluster, choisir une plage parmi 1, 7, 30 ou 90 jours, voir la
période réellement couverte, et pour chaque cluster la valeur de la fenêtre **et** celle
de la fenêtre précédente côte à côte. Puis, sur un cluster donné, suivre ses coûts et son
temps allumé sur ≈90 jours point par point, par jour, semaine ou mois.

## Dependency Analysis

Constats de la vérification code (Q6 de l'intake) et décision retenue.

| Besoin | Domaine requis | Preuve (fichier) | Résolution |
|--------|----------------|------------------|------------|
| Lecture des tables `*_rolling` | backend | `rg -l "rolling" packages/dcm-backend/app` → aucun résultat ; `app/api/services/compute_metrics_clusters.py:38-41` ne cite que les tables `*_daily` | ticket Backend (T002) |
| Paramètre de plage `window_days` | backend | `rg -n "window_days\|window_start\|as_of_date" packages/dcm-backend/app` → aucun résultat ; les 6 routes clusters prennent `period_start`/`period_end` (`app/api/routes/compute_metrics.py:153-358`) | ticket Backend (T002) |
| `workspace_name` par cluster | backend | `dim_dbx_workspace(workspace_id, workspace_name)` déjà jointe dans `app/api/routes/databricks.py:316-328` et `app/api/routes/projects.py:557`, jamais dans le service clusters | ticket Backend (T002) |
| Tendance `Lifetime` par cluster | backend | seul `/clusters/{cluster_id}/cost-trend` existe (`app/api/routes/compute_metrics.py:358`) | ticket Backend (T002) |
| Granularité jour / semaine / mois | — | déjà en place : `granularity=day\|week\|month` (`app/api/routes/compute_metrics.py:374`, service `compute_metrics_clusters.py:652-696`), déjà transmise par le front (`src/hooks/useComputeClustersQueries.ts:243-264`) | aucun besoin |
| Histogramme (barres) pour la tendance de coût | frontend | `src/components/domain/compute/compute-cost-trend-chart.tsx` dessine une **polyline** (sparkline), pas des barres | ticket Frontend (T003) |
| `Lifetime_previous_period`, `IDLE_previous_period` | dataeng | `pipelines/gold_dbx_compute/cluster_efficiency_rolling.py` n'a aucune colonne `*_prev_window` ; seul `cluster_cost_rolling.cost_usd_prev_window` existe | `add_dataeng_ticket` → T001 |
| `Autoscaling`, `min_node`, `max_node` | dataeng | le modèle expose `autoscale_min`/`autoscale_max` (`dcm_commons/models/compute.py:70-75`, `src/types/api.ts:420`) mais la requête de `GET /compute` ne les sélectionne pas (`app/api/routes/clusters.py:162-181`) → toujours `null`. Seul `curated_dbx_compute_clusters.min_autoscale_workers`/`max_autoscale_workers` porte l'information | `add_dataeng_ticket` → T001 |

**Pourquoi le gold et pas le backend** pour les deux derniers besoins : `cluster_efficiency_daily`
joint déjà `curated_dbx_compute_clusters` (CTE `clusters_as_of`, pour `driver_node_type` /
`worker_node_type`) — l'autoscaling y est à portée de `SELECT`. Le faire côté backend
obligerait le service compute-metrics, qui ne lit aujourd'hui que du gold et des
dimensions, à requêter du curated. Et la fenêtre précédente côté backend dupliquerait la
moyenne pondérée par `uptime_hours` du rolling, avec un risque d'écart de définition avec
le gold. Enfin `gold_dbx_compute_cluster_efficiency_rolling` doit **de toute façon** être
recréée : `active_hours` passe de `bigint` à `decimal` dans le commit `b102155`, et
`MERGE WITH SCHEMA EVOLUTION` ajoute des colonnes mais ne convertit pas les types. La
migration est donc déjà payée.

## Prerequisites

- **Small branches / small PRs** : trois branches filles, une par package
  (`dataeng/022-…`, `backend/022-…`, `frontend/022-…`), chacune limitée à son package.
- Intake + domain scope confirmés (`intake.json` / `domain-scope.json`).
- Dépendances bloquantes de Dependency Analysis résolues : le gap `dataeng` reçoit la
  Story T001, ordonnancée **avant** T002 (le backend lit les colonnes qu'elle produit).
- `[NEEDS CLARIFICATION]` : aucun ouvert — les deux questions de scope (`Governance`,
  `Utilization` de l'Overview) sont tranchées sur le comportement existant (cf.
  Clarifications).
- **Migration T001** : `gold_dbx_compute_cluster_efficiency_daily` et
  `..._efficiency_rolling` sont à recréer (`DROP` + run `full`, le gold étant
  intégralement dérivable) — changement de type de `active_hours` du commit `b102155`
  cumulé aux nouvelles colonnes. À faire en dev **puis** en prod avant T002.
- Les tables `*_rolling` doivent être peuplées dans le catalogue lu par le backend
  (`it.ba_data_connect_monitoring__d` en dev) avant de brancher le front.

## User stories

### User Story 1 — Fenêtre précédente et autoscaling exposés en gold (Priority: P1)

Story **DataEng** (T001). En tant que consommateur des tables gold, je veux que
`gold_dbx_compute_cluster_efficiency_rolling` porte, pour chaque cluster et chaque
fenêtre, le temps allumé et le taux d'inactivité de la **fenêtre précédente**, ainsi que
la configuration d'autoscaling du cluster — de la même manière que
`cluster_cost_rolling` porte déjà `cost_usd_prev_window`.

**Why this priority** : bloque T002 et T003 — quatre indicateurs demandés n'existent
nulle part aujourd'hui.
**Independent Test** : `pytest` sur les builders (`FakeSpark`, assertions sur le SQL
généré), puis contrôle des colonnes et de la cohérence `uptime_hours_prev_window` vs.
`uptime_hours` de la fenêtre précédente sur le catalogue de dev.

**Acceptance Scenarios**

1. **Given** un cluster avec 60 jours d'historique quotidien, **When**
   `cluster_efficiency_rolling` est reconstruite, **Then** la ligne `window_days = 30`
   porte `uptime_hours_prev_window` égal à la somme de `uptime_hours` sur
   `[as_of_date - 59, as_of_date - 30]` et `idle_pct_prev_window` égal à la moyenne
   d'`idle_pct` pondérée par `uptime_hours` sur cette même fenêtre.
2. **Given** un cluster sans aucun jour dans la fenêtre précédente (créé récemment),
   **When** la table est reconstruite, **Then** `uptime_hours_prev_window` et
   `idle_pct_prev_window` sont `NULL` — jamais `0`, qui se lirait comme « allumé zéro
   heure » au lieu de « pas de comparaison possible ».
3. **Given** un cluster en autoscaling 2→8 workers, **When** les tables efficiency
   quotidienne et glissante sont reconstruites, **Then** elles exposent
   `autoscale_enabled = true`, `autoscale_min_workers = 2`, `autoscale_max_workers = 8`
   au dernier état connu du cluster.
4. **Given** un cluster à taille fixe, **When** les tables sont reconstruites, **Then**
   `autoscale_enabled = false` et les bornes sont `NULL`.

### User Story 2 — API des clusters par fenêtre glissante (Priority: P1)

Story **Backend** (T002). En tant que page Cluster, je veux demander une plage
(1, 7, 30 ou 90 jours) et recevoir, par cluster, les indicateurs de la fenêtre, ceux de
la fenêtre précédente, le nom du workspace, et les bornes réelles de la période couverte.

**Why this priority** : sans elle le front n'a aucune donnée à afficher.
**Independent Test** : tests de routes et de services (`tests/test_compute_metrics_routes.py`,
`tests/test_compute_metrics_services.py`), puis appel manuel des endpoints sur le dev.

**Acceptance Scenarios**

1. **Given** `window_days = 7`, **When** j'appelle `/clusters/overview|cost|efficiency`,
   **Then** la réponse porte `window_days`, `from_date` (= `window_start`) et `to_date`
   (= `as_of_date`) lus dans le gold, et une seule ligne par cluster.
2. **Given** une valeur de `window_days` hors de {1, 7, 30, 90}, **When** j'appelle un de
   ces endpoints, **Then** la requête est rejetée (422) plutôt que silencieusement
   ramenée à une autre fenêtre.
3. **Given** un cluster dont le `workspace_id` est absent de `dim_dbx_workspace`, **When**
   je liste les clusters, **Then** la ligne reste présente avec `workspace_name` à `null`
   — la jointure enrichit, elle ne filtre pas.
4. **Given** un cluster avec `dbu_quantity = 0` ou `null`, **When** je demande l'onglet
   Cost, **Then** `dbu_cost` est `null` et non une division par zéro.
5. **Given** un `cluster_id` et une granularité `week`, **When** j'appelle la tendance de
   `Lifetime` sur ≈90 jours, **Then** je reçois une série de points agrégés par semaine
   sur la même forme de réponse que `cost-trend` (`items`, `period`, `granularity`).
6. **Given** l'onglet Governance, **When** je l'appelle, **Then** son contrat de réponse
   et ses données sont inchangés.

### User Story 3 — Page Cluster par plage, avec tendances par cluster (Priority: P2)

Story **Frontend** (T003). En tant qu'utilisateur FinOps, je veux choisir une plage sur
la page Cluster, voir la période couverte, comparer chaque cluster à sa période
précédente, et ouvrir un cluster pour suivre ses coûts et son temps allumé sur ≈90 jours.

**Why this priority** : livre la valeur utilisateur, mais dépend de T002.
**Independent Test** : vitest + fixtures MSW (`src/test/fixtures/compute-clusters.ts`) sur
`ComputeClusters.tsx` et le drawer.

**Acceptance Scenarios**

1. **Given** la page Cluster, **When** elle s'ouvre, **Then** un sélecteur propose
   `Daily`, `Last 7d`, `Last 30d`, `Last 90d` — quatre plages statiques, aucun choix de
   dates libre — et la période couverte est affichée sous la forme `from_date → to_date`.
2. **Given** une plage sélectionnée, **When** je change d'onglet
   (Overview / Cost / Efficiency / Governance), **Then** la plage est conservée.
3. **Given** l'onglet Overview, **When** il s'affiche, **Then** chaque ligne porte
   Workspace, Cluster, Type, $Cost, $Cost période précédente, Lifetime, Lifetime période
   précédente, Utilization et Governance.
4. **Given** l'onglet Efficiency, **When** il s'affiche, **Then** chaque ligne porte les
   types de node driver/worker, l'autoscaling avec ses bornes min/max, Lifetime et IDLE
   avec leur période précédente, CPU et mémoire (moyenne et p95), le statut, le node
   recommandé et l'économie estimée.
5. **Given** un cluster ouvert en détail, **When** le panneau s'affiche, **Then** il
   conserve son format actuel, ajoute les caractéristiques techniques du cluster, et
   présente un histogramme `COST TREND (≈90 DAYS)` et une courbe `Lifetime TREND
   (≈90 DAYS)`, chacun avec un sélecteur jour / semaine / mois et une valeur lisible
   point par point.
6. **Given** un cluster sans donnée sur la plage choisie, **When** son détail s'ouvre,
   **Then** l'état vide existant est affiché — pas de graphe vide ni de `NaN`.

## Acceptance Criteria

1. **Given** la page Cluster branchée sur les `*_rolling`, **When** je sélectionne les
   4 plages successivement, **Then** chaque onglet affiche les indicateurs demandés et la
   période couverte, sans requête sur les tables `*_daily` pour les vues de liste.
2. **Given** l'onglet Governance, **When** la feature est livrée, **Then** son
   comportement est identique à avant (aucune régression, contrat inchangé).
3. Gates des trois packages verts (lint → types → tests → build).

## Out of scope (cet Epic)

- `gold_dbx_compute_cluster_reliability_rolling` (démarrages, terminaisons inattendues,
  auto-termination) : produite et disponible, mais aucun indicateur demandé ne s'y
  rattache.
- Pages Warehouses : elles gardent leur période libre et leurs tables `*_daily`.
- Page `Clusters.tsx` héritée (`GET /api/v1/compute` sur `curated_compute_metrics`) :
  non touchée, y compris ses champs `autoscale_min`/`autoscale_max` jamais peuplés.
- Recalcul historique des fenêtres précédentes au-delà de la profondeur disponible dans
  `cluster_efficiency_daily`.

## Work Breakdown (preview)

| ID | Domain | Summary | Ticket |
|----|--------|---------|--------|
| T001 | DataEng | `uptime_hours_prev_window`, `idle_pct_prev_window`, `cluster_name` et l'autoscaling (`autoscale_enabled`, `autoscale_min_workers`, `autoscale_max_workers`, `configured_worker_count`) exposés par `cluster_efficiency_daily` / `_rolling`, + migration des deux tables | ✅ |
| T002 | Backend | Services et routes clusters sur les `*_rolling` : paramètre `window_days`, `from_date`/`to_date` dans la réponse, `workspace_name` depuis `dim_dbx_workspace`, `dbu_cost`, tendance `Lifetime` | ✅ |
| T003 | Frontend | Sélecteur de plage + période affichée, colonnes des onglets Overview / Cost / Efficiency, détail cluster : specs techniques, histogramme COST TREND et courbe Lifetime TREND (≈90 j, jour/semaine/mois) | ✅ |

## Requirements & Success Criteria

**Exigences fonctionnelles**

- **FR-001** : la page Cluster propose exactement quatre plages statiques — 1, 7, 30 et
  90 jours — et aucune saisie de dates libre.
- **FR-002** : la période réellement couverte est affichée (`from_date` → `to_date`) et
  provient de la donnée (`window_start` / `as_of_date`), pas d'un calcul depuis `today`.
- **FR-003** : les vues de liste rendent **une ligne par cluster**, celle de la fenêtre
  demandée au dernier `as_of_date` disponible.
- **FR-004** : Overview expose Workspace_name, Cluster_name, Cluster_type, $Cost,
  $Cost_previous_period, Lifetime, Lifetime_previous_period, Utilization, Governance.
- **FR-005** : Cost expose Workspace_name, Cluster_name, Cluster_type, $Cost,
  $Cost_previous_period, SKU, DBU_cost, DBU.
- **FR-006** : Efficiency expose Workspace_name, Cluster_name, Cluster_type,
  driver_node_type, worker_node_type, Autoscaling, min_node/max_node, Lifetime,
  Lifetime_previous_period, IDLE, IDLE_previous_period, avg/P95 CPU, avg/P95 mémoire,
  STATUS, RECOMMENDED NODE, EST. SAVINGS.
- **FR-007** : Governance est inchangée (contrat, requête, rendu).
- **FR-008** : le détail d'un cluster conserve son format et ajoute driver_node_type,
  worker_node_type, Autoscaling, min_node/max_node.
- **FR-009** : le détail d'un cluster présente un histogramme `COST TREND (≈90 DAYS)` et
  une courbe `Lifetime TREND (≈90 DAYS)`, chacun consultable par jour, semaine et mois,
  et remplace les visuels de tendance actuels.
- **FR-010** : une comparaison impossible (pas de fenêtre précédente, `dbu_quantity`
  nulle, workspace inconnu) se rend comme « non disponible », jamais comme `0`, `NaN` ou
  une erreur.

**Critères de succès**

- **SC-001** : les 4 plages × 4 onglets sont consultables sur le dev, avec la période
  couverte affichée et cohérente avec `window_start`/`as_of_date` du gold.
- **SC-002** : aucun indicateur des trois onglets n'est vide faute de colonne source
  (les 4 gaps de Dependency Analysis sont couverts par T001).
- **SC-003** : les vues de liste n'interrogent plus les tables `*_daily` (les `*_daily`
  ne servent plus qu'aux tendances par cluster).
- **SC-004** : `Lifetime_previous_period` et `IDLE_previous_period` d'une fenêtre de N
  jours sont égaux aux valeurs de la fenêtre courante décalée de N jours, sur un
  échantillon de clusters du dev.

## Assumptions

- `DBU_cost` est le coût unitaire par DBU, soit `cost_usd / dbu_quantity` — le gold ne
  porte pas de tarif par SKU.
- `Lifetime` désigne `uptime_hours` (temps allumé), et `IDLE` le pourcentage
  `idle_pct` déjà calculé en gold.
- « la valeur la plus récente » de l'Overview signifie la ligne au dernier `as_of_date`
  écrit dans la table, pas une valeur temps réel.
- Les tables `*_rolling` étant des snapshots « as of » le dernier jour disponible, le
  sélecteur de période libre du header n'a pas d'effet sur la page Cluster et cède la
  place au sélecteur de plage ; les filtres de scope (workspace, cloud, LZ) restent
  appliqués.
- Les tendances par cluster (≈90 jours, jour/semaine/mois) restent servies par les tables
  `*_daily`, seule source d'une série temporelle continue — les `*_rolling` ne portent
  qu'un point par fenêtre.
- L'onglet Efficiency ne liste que les clusters allumés au moins une fois pendant la
  fenêtre (`WHERE uptime_hours > 0`, filtre pré-existant de la table). Un cluster éteint
  sur toute la fenêtre reste visible sur l'Overview via la table de coût, avec ses colonnes
  `Lifetime` rendues « non disponible ». Cf. [data-model.md](./data-model.md).
