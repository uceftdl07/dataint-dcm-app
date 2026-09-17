Feature Specification: Ingestion Compute Metrics (Curated + Gold)

**Feature Branch**: `012-compute-metrics-ingestion`
**Work Type**: feature
**Priority**: P1
**Created**: 2026-08-12

**Input**: En se basant sur le spike `docs/spike/compute-metrics-definition/` (data model + mapping), construire dans DCM les flux d'ingestion des data models Compute (clusters + SQL Warehouses), depuis les system tables Databricks jusqu'aux tables curated et gold, prêts à être consommés par une interface de monitoring qui affichera ces métriques aux end users.

## Clarifications

### Session 2026-08-12

- Q: Quel périmètre cloud pour l'ingestion compute (curated + gold) de cet Epic ? → A: Azure + AWS — même périmètre que le reste de DCM (`cloud_provider` discrimine les lignes).
- Q: Comment traiter la collision de nommage entre le domaine `compute` générique existant (`gold_compute_utilization`) et les nouvelles tables gold du spike ? → A: Suivre la convention `gold_<source>_<domain>_<metric>` (ex. `gold_dbx_workflow_tasks`) ; les nouvelles tables sont préfixées `gold_dbx_compute_*` / `gold_dbx_compute_warehouse_*` pour les distinguer explicitement du domaine `compute` générique existant. Le spike (`docs/spike/compute-metrics-definition/`) a été mis à jour en conséquence.
- Q: Y a-t-il un SLA de fraîcheur précis pour les tables gold quotidiennes ? → A: Best-effort quotidien — pas de SLA horaire strict pour cet Epic (alignement sur les autres pipelines gold DCM existants).
- Q: Comment gérer un échec d'accès aux system tables pour une LZ/workspace donnée pendant un run multi-LZ ? → A: Un échec sur une LZ fait échouer tout le run — aucune donnée partielle n'est publiée (fail fast global, pas d'isolation par LZ).
- Q: Quelle fenêtre de backfill initial pour les nouvelles tables curated/gold à l'activation de cet Epic ? → A: Backfill de 30 jours à l'activation (couvre le besoin minimal du socle prédictif dès la mise en production).

## Domain Scope

| Domaine | In scope | Ticket Story | Packages |
|---------|----------|--------------|----------|
| Frontend | ❌ | ❌ | — |
| Backend | ❌ | ❌ | — |
| DataEng | ✅ | ✅ | packages/dcm-databricks-pipeline |
| DevOps | ❌ | ❌ | — |
| QA | ❌ | ❌ | — |

## Ticket Plan

| Stories Jira | 5 |
| Mode | custom (découpage par sous-lot DataEng) |
| Domaines avec ticket | DataEng |

| # | Slug | Titre |
|---|------|-------|
| 1 | `curated-compute-system-tables` | Curated system tables compute (warehouses, warehouse_events, node_types) |
| 2 | `gold-compute-clusters` | Gold clusters — cost, efficiency/rightsizing, reliability, governance |
| 3 | `gold-warehouses` | Gold SQL warehouses — cost, utilization/rightsizing, query performance |
| 4 | `gold-compute-transverse` | Gold transverse réactif — recommendations |
| 5 | `gold-compute-forecast` | Gold transverse prédictif — forecast_daily (SQL Warehouse natif) *(amendé 2026-08-27, scindé de #4)* |

## Dependency Analysis

| Besoin | Domaine | Résolution |
|--------|---------|------------|
| Exposition API backend + affichage UI monitoring des nouvelles gold tables compute | Backend / Frontend | **Différé** — hors scope de cet Epic. Aucune route backend n'existe aujourd'hui sur ces futures tables gold (vérifié par recherche dans `packages/dcm-backend`). Un Epic distinct exposera ces données une fois les tables gold disponibles et stabilisées. |

## User Scenarios & Testing

### User Story 1 - Curated system tables compute disponibles (Priority: P1)

En tant qu'ingénieur data / pipeline DCM, je veux que les system tables Databricks `system.compute.warehouses`, `system.compute.warehouse_events` et `system.compute.node_types` soient collectées et matérialisées dans des tables curated idempotentes, alignées sur les tables curated déjà existantes (`curated_dbx_compute_clusters`, `curated_dbx_compute_node_timeline`), afin que les couches gold puissent s'appuyer sur une base fiable et à jour pour clusters ET warehouses.

**Why this priority**: Sans ces 3 tables curated, aucune des tables gold Warehouses ni certains enrichissements clusters (node_types) ne peuvent être calculés. C'est le socle bloquant des 3 autres stories.

**Independent Test**: Lancer le pipeline curated sur un environnement de test ; vérifier que les 3 nouvelles tables curated existent, contiennent des lignes cohérentes avec les system tables sources, et que les runs successifs (merge idempotent sur la clé documentée) ne dupliquent pas les lignes ni ne perdent l'historique SCD (`warehouses`), l'append (`warehouse_events`) ou le référentiel (`node_types`).

**Acceptance Scenarios**:

1. **Given** des lignes existent dans `system.compute.warehouses` pour un workspace donné, **When** le pipeline curated s'exécute, **Then** `curated_dbx_compute_warehouses` contient une ligne par `(cloud_provider, account_id, workspace_id, warehouse_id, change_time)` avec `delete_time` NULL pour les warehouses actifs.
2. **Given** un nouvel événement `system.compute.warehouse_events` apparaît, **When** le pipeline curated s'exécute à nouveau, **Then** l'événement est ajouté à `curated_dbx_compute_warehouse_events` sans duplication des événements déjà ingérés (curated fidèle source, aucune colonne dérivée/inventée : la source n'expose pas de colonne date dédiée, seulement `event_time`).
3. **Given** un `node_type` référencé par un cluster ou warehouse n'existe pas encore dans `curated_dbx_compute_node_types`, **When** le pipeline curated tourne, **Then** la ligne référentiel est créée avec `gpu_count` renseigné (0 si absent en source).

---

### User Story 2 - Gold Clusters : coût, efficience, fiabilité, gouvernance (Priority: P1)

En tant que Data Platform Lead / FinOps ou Data Engineer, je veux disposer de tables gold journalières par cluster (coût, utilisation CPU/mémoire, fiabilité, conformité) calculées automatiquement à partir des tables curated, afin qu'une interface de monitoring puisse ensuite afficher ces métriques sans recalcul côté consommateur.

**Why this priority**: C'est le premier des deux piliers métier (Clusters) de la feature ; il matérialise la majorité des indicateurs FinOps + rightsizing attendus par le spike.

**Independent Test**: Exécuter le job gold sur des données curated de test couvrant plusieurs jours et clusters ; interroger `gold_dbx_compute_cluster_cost_daily`, `gold_dbx_compute_cluster_efficiency_daily`, `gold_dbx_compute_cluster_reliability_daily` et `gold_dbx_compute_cluster_governance`, et vérifier que chaque ligne respecte le grain documenté et les règles de dérivation (ex. `utilization_status`, `cost_rank`).

**Acceptance Scenarios**:

1. **Given** de l'usage `curated_dbx_billing_usage` rattaché à un `cluster_id` sur une journée, **When** le job gold s'exécute, **Then** `gold_dbx_compute_cluster_cost_daily` contient une ligne `(cloud_provider, workspace_id, cluster_id, period_start)` avec `dbu_quantity`, `cost_usd`, `cost_delta_pct` vs J-1, et `cost_rank`/`is_top_cost` cohérents avec le classement **global** (tous clusters, toutes LZ confondues) ce jour-là — pas de `source_lz_id` sur cette table (aucun mapping `workspace_id → lz_id` fiable, cf. T002 sub-spec Notes).
2. **Given** un cluster avec `cpu_util_p95_pct < 40` et `mem_util_p95_pct < 50` sur une journée, **When** le job gold calcule `gold_dbx_compute_cluster_efficiency_daily`, **Then** `utilization_status = 'OVER'` et une `rightsizing_reco` + `estimated_savings_usd` sont renseignés.
3. **Given** un cluster sans tag `owner` ni `cost_center`, **When** le job gold calcule `gold_dbx_compute_cluster_governance`, **Then** `has_owner_tag = false`, `has_cost_center_tag = false`, et `recommended_action`/`severity` reflètent la règle de priorité documentée (tag manquant > DBR obsolète > oversize).

---

### User Story 3 - Gold SQL Warehouses : coût, utilisation, performance requêtes (Priority: P2)

En tant que Data Platform Lead / FinOps ou Analyste SQL, je veux disposer de tables gold journalières par warehouse (coût, utilisation/rightsizing, performance des requêtes), afin que l'interface de monitoring puisse restituer ces indicateurs pour la page SQL Warehouses.

**Why this priority**: Second pilier métier de la feature ; dépend des tables curated warehouses/warehouse_events livrées par la Story 1, d'où une priorité légèrement inférieure à la Story 2 (clusters, socle déjà partiellement en place).

**Independent Test**: Exécuter le job gold sur des données curated de test couvrant plusieurs warehouses ; interroger `gold_dbx_compute_warehouse_cost_daily`, `gold_dbx_compute_warehouse_utilization_daily`, `gold_dbx_compute_warehouse_query_performance_daily` et vérifier grain, dérivations (`idle_pct`, `failure_rate_pct`, `utilization_status`) et jointures (`curated_dbx_compute_warehouses`, `curated_dbx_query_history`).

**Acceptance Scenarios**:

1. **Given** des requêtes exécutées sur un warehouse durant une journée, **When** le job gold s'exécute, **Then** `gold_dbx_compute_warehouse_cost_daily` contient `query_count`, `cost_usd`, `cost_per_query_usd` cohérents avec `curated_dbx_query_history` et `curated_dbx_billing_usage` filtré sur `warehouse_id`.
2. **Given** un warehouse RUNNING sans requête active sur une large part de la journée, **When** le job gold calcule `gold_dbx_compute_warehouse_utilization_daily`, **Then** `idle_pct` est élevé, `utilization_status = 'OVER'`, et `estimated_savings_usd` reflète le pourcentage idle appliqué au coût du jour.
3. **Given** des requêtes en échec ou en spill sur un warehouse, **When** le job gold calcule `gold_dbx_compute_warehouse_query_performance_daily`, **Then** `failure_rate_pct` et `spill_query_count` reflètent fidèlement les statuts/`spilled_local_bytes` source, avec `latency_p50/p95/p99_ms` et `queue_time_p95_ms` calculés par percentile.

---

### User Story 4 - Socle transverse réactif/prédictif : recommendations + forecast (Priority: P3)

> **Amendé (2026-08-27, mis à jour 2026-08-31)** : cette story couvrait à l'origine `recommendations` (T004) ET `forecast_daily` (désormais **T005**, cf. [stories/T005-gold-compute-forecast.md](stories/T005-gold-compute-forecast.md)). Le contenu ci-dessous décrit toujours les deux volets pour la cohérence du récit métier ; la scission technique (T004 = recommendations, T005 = forecast, exécuté en `python_wheel_task` via l'API Statement Execution contre un SQL Warehouse Pro/Serverless — même trame que les autres builders gold du module, décision documentée dans T005) est documentée dans `tasks.md` et les deux sub-specs. Le scénario 2 ci-dessous (forecast) est désormais la responsabilité de T005.

En tant que Data Platform Lead / Gouvernance, je veux un socle transverse unifiant les recommandations d'optimisation (réactif) et les projections (prédictif) sur clusters et warehouses, afin que l'interface de monitoring puisse afficher une liste d'actions priorisées et des tendances anticipées sans dupliquer la logique de calcul par page.

**Why this priority**: Valeur ajoutée transverse qui consolide les Stories 2 et 3 ; dépend de leur disponibilité (les gold `*_daily` alimentent les recommandations et le forecast), d'où la priorité la plus basse du lot mais reste dans le même Epic pour livrer un socle cohérent.

**Independent Test**: Exécuter les jobs `gold_dbx_compute_recommendations` et `gold_dbx_compute_forecast_daily` sur un historique gold de test couvrant plusieurs jours ; vérifier l'unicité de `recommendation_id`, la présence de `severity`/`personas`/`status`, et que `gold_dbx_compute_forecast_daily` produit des lignes par `(object_type, object_id, metric_name, horizon_date)` avec bornes `lower_bound ≤ predicted_value ≤ upper_bound`.

**Acceptance Scenarios**:

1. **Given** un cluster détecté `is_zombie = true` un jour donné, **When** le job recommendations s'exécute, **Then** une ligne `gold_dbx_compute_recommendations` de `category = 'RIGHTSIZING'` (ou catégorie appropriée) est créée/maintenue avec `first_seen_date`/`last_seen_date` mis à jour et `status = 'OPEN'` tant que la condition persiste.
2. **Given** un historique gold journalier suffisant (≥ N jours) pour un objet compute, **When** le job forecast s'exécute, **Then** `gold_dbx_compute_forecast_daily` produit une projection pour au moins les métriques `cost_usd` et `cpu_util_p95_pct`/`idle_pct` selon l'objet, avec une méthode `ai_forecast` tracée.
3. **Given** une recommandation précédemment ouverte dont la condition ne se reproduit plus, **When** le job recommendations tourne à nouveau, **Then** son `status` passe à `RESOLVED` (ou n'est plus régénérée en `OPEN`).

## Out of scope (this Epic)

- **Exposition API backend** des nouvelles tables gold compute (routes `dcm-backend`) — dépendance identifiée en Dependency Analysis, différée à un Epic ultérieur.
- **Interface de monitoring / pages UI** (Clusters, SQL Warehouses) affichant ces métriques aux end users — mentionnée comme finalité métier mais hors scope technique de cet Epic (aucun package Frontend en scope).
- **Sync Lakebase PostgreSQL** des nouvelles tables gold (au-delà de ce qui existe déjà, ex. `gold_compute_summary_sync`) — à traiter avec l'Epic d'exposition backend, une fois le contrat de lecture (API ou sync) confirmé.

## Work Breakdown (preview)

| ID | Domain | Summary | Ticket |
|----|--------|---------|--------|
| T001 | DataEng | Curated system tables compute (warehouses, warehouse_events, node_types) | ✅ |
| T002 | DataEng | Gold clusters (cost, efficiency, reliability, governance) daily | ✅ |
| T003 | DataEng | Gold warehouses (cost, utilization, query performance) daily | ✅ |
| T004 | DataEng | Gold transverse réactif (recommendations) | ✅ |
| T005 | DataEng | Gold transverse prédictif (forecast_daily, SQL Warehouse natif) | ⏳ |
| — | Backend | Exposition API des gold tables compute | ❌ hors Epic |
| — | Frontend | Pages monitoring Clusters / SQL Warehouses | ❌ hors Epic |

## Requirements

### Functional Requirements

- **FR-001**: Le système DOIT ingérer `system.compute.warehouses` dans une table curated idempotente (merge SCD sur `cloud_provider, account_id, workspace_id, warehouse_id, change_time`, watermark `change_time`), conservant `delete_time` pour distinguer les warehouses actifs des supprimés.
- **FR-002**: Le système DOIT ingérer `system.compute.warehouse_events` dans une table curated en append idempotent (clé `cloud_provider, account_id, workspace_id, warehouse_id, event_time, event_type`, watermark `event_time`), fidèle source (pas de colonne dérivée : la source n'expose pas de colonne date dédiée, `event_time` sert aussi de watermark, table non partitionnée).
- **FR-003**: Le système DOIT ingérer `system.compute.node_types` dans une table curated référentiel (clé `cloud_provider, account_id, node_type`), avec `gpu_count` normalisé à 0 quand absent en source.
- **FR-004**: Le système DOIT calculer quotidiennement `gold_dbx_compute_cluster_cost_daily` au grain `(cloud_provider, workspace_id, cluster_id, period_start)`, incluant coût $, DBU, delta J-1, classement (`cost_rank`, `is_top_cost`) global par jour (pas de `source_lz_id` sur cette table — cf. FR-013 exception documentée).
- **FR-005**: Le système DOIT calculer quotidiennement `gold_dbx_compute_cluster_efficiency_daily`, incluant utilisation CPU/mémoire (moyenne + p95), idle %, statut de dimensionnement (`utilization_status`) et recommandation de rightsizing avec économie estimée.
- **FR-006**: Le système DOIT calculer quotidiennement `gold_dbx_compute_cluster_reliability_daily`, incluant démarrages, latence de démarrage moyenne, terminaisons inattendues et configuration d'auto-termination.
- **FR-007**: Le système DOIT maintenir `gold_dbx_compute_cluster_governance` en snapshot du dernier état connu par cluster, incluant conformité des tags, version DBR, sur-dimensionnement et action recommandée avec sévérité.
- **FR-008**: Le système DOIT calculer quotidiennement `gold_dbx_compute_warehouse_cost_daily` au grain `(cloud_provider, source_lz_id, workspace_id, warehouse_id, period_start)`, incluant coût $, DBU, nombre de requêtes et coût par requête.
- **FR-009**: Le système DOIT calculer quotidiennement `gold_dbx_compute_warehouse_utilization_daily`, incluant heures RUNNING vs actives, idle %, ratio actif/allumé, événements de scaling et statut de dimensionnement avec économie estimée.
- **FR-010**: Le système DOIT calculer quotidiennement `gold_dbx_compute_warehouse_query_performance_daily`, incluant latences p50/p95/p99, temps de file d'attente, taux d'échec, spill, cache hit et volumes scannés.
- **FR-011**: Le système DOIT maintenir un socle `gold_dbx_compute_recommendations` unifiant les recommandations actionnables (FinOps, Rightsizing, Fiabilité, Gouvernance) pour clusters et warehouses, avec statut de cycle de vie (`OPEN`/`ACK`/`RESOLVED`) et dates de première/dernière détection.
- **FR-012**: Le système DOIT maintenir un socle `gold_dbx_compute_forecast_daily` produisant des projections journalières (valeur prédite + bornes) pour les métriques clés coût/utilisation/volume/queue, tracées avec la méthode de calcul utilisée.
- **FR-013**: Toutes les nouvelles tables curated et gold DOIVENT porter `cloud_provider` et `source_lz_id` (ou équivalent LZ) afin de rester cohérentes multi-cloud/multi-LZ avec le reste du modèle DCM, sans appel cross-LZ direct. Le périmètre cloud de cet Epic couvre Azure ET AWS (cf. Clarifications).
- **FR-014**: Les jobs d'ingestion et de calcul gold DOIVENT être idempotents et rejouables (ré-exécution sans duplication ni perte de données) et s'appuyer exclusivement sur des données réelles issues des system tables Databricks — jamais de données mockées.
- **FR-015**: Les tables gold introduites par cet Epic DOIVENT suivre la convention de nommage `gold_<source>_<domain>_<metric>` avec le préfixe `dbx` (ex. `gold_dbx_compute_cluster_cost_daily`), afin de les distinguer explicitement du domaine `compute` générique déjà existant (`gold_compute_utilization`) et de rester cohérentes avec le reste du référentiel medallion DCM.
- **FR-016**: Si l'accès aux system tables échoue pour une LZ/workspace donnée pendant un run, le job DOIT faire échouer l'intégralité du run (fail fast global) plutôt que de publier des données partielles ou d'ignorer silencieusement la LZ en échec.
- **FR-017**: À l'activation initiale de chaque nouvelle table curated/gold, le système DOIT backfiller un historique de 30 jours à partir des system tables Databricks (qui conservent nativement cet historique), avant de basculer en rafraîchissement quotidien incrémental.
- **FR-018**: Pour les tables gold journalières (`*_daily`, clusters et warehouses), le tout premier calcul DOIT couvrir l'intégralité de l'historique curated disponible (full, ≥ 30 jours — cf. FR-017) ; les calculs suivants DOIVENT se limiter à une fenêtre incrémentale de 3 jours (`period_start` comme colonne de watermark), permettant d'absorber les corrections tardives sans recalculer tout l'historique à chaque run.

### Key Entities

- **curated_dbx_compute_warehouses**: État SCD des SQL warehouses (config, taille, scaling, tags).
- **curated_dbx_compute_warehouse_events**: Journal d'événements de cycle de vie/scaling d'un warehouse.
- **curated_dbx_compute_node_types**: Référentiel des types de nœuds de calcul (capacité CPU/mémoire/GPU).
- **gold_dbx_compute_cluster_cost_daily / efficiency_daily / reliability_daily / governance**: Agrégats et snapshot journaliers par cluster couvrant coût, efficience, fiabilité, conformité.
- **gold_dbx_compute_warehouse_cost_daily / utilization_daily / query_performance_daily**: Agrégats journaliers par warehouse couvrant coût, utilisation, performance des requêtes.
- **gold_dbx_compute_recommendations**: Fait unifié des recommandations actionnables (réactif) par objet compute.
- **gold_dbx_compute_forecast_daily**: Série de projections (prédictif) par objet compute et métrique.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% des system tables compute listées dans le spike (warehouses, warehouse_events, node_types) sont disponibles sous forme de tables curated interrogeables, en plus des 2 déjà existantes (clusters, node_timeline).
- **SC-002**: Pour chaque jour où des données sources existent, une ligne gold est produite pour chaque cluster/warehouse actif sur les 7 tables gold journalières définies (4 clusters + 3 warehouses), sans écart de grain par rapport au modèle du spike.
- **SC-003**: Les jobs d'ingestion et de calcul gold peuvent être ré-exécutés sur une même période sans provoquer de duplication de lignes ni de perte d'historique (vérifié par un jeu de données de test rejoué 2 fois).
- **SC-004**: Le socle de recommandations identifie automatiquement au moins les 4 catégories métier du spike (FinOps, Rightsizing, Fiabilité, Gouvernance) sur un jeu de données de test couvrant des cas de chaque catégorie.
- **SC-005**: Le socle prédictif produit des projections journalières exploitables (bornes cohérentes, valeur dans l'intervalle) pour au moins les métriques coût et utilisation, sur un historique de test d'au moins 14 jours.
- **SC-006**: Les données produites sont exclusivement issues de vraies system tables Databricks (aucune donnée fictive), conformément aux règles absolues du projet.
- **SC-007**: Après activation, chaque nouvelle table curated/gold contient au moins 30 jours d'historique backfillé, et les runs suivants complètent quotidiennement cet historique en best-effort (sans SLA horaire strict).
- **SC-008**: Un run simulant une LZ/workspace inaccessible échoue intégralement (aucune ligne gold/curated partielle publiée pour ce run) et l'échec est visible dans les logs/alertes, conformément à P4 (Fail Fast, Fail Loud).

## Assumptions

- L'historique de données brutes nécessaire au calcul du prédictif (`gold_dbx_compute_forecast_daily`) est disponible nativement via les system tables Databricks sur une profondeur suffisante pour couvrir le backfill de 30 jours requis par FR-017.
- Le référentiel `dim_landing_zone` existe déjà et peut être joint pour dériver `ba_name`/`source_lz_id` sur les nouvelles tables gold, sans modification de son schéma.
- Les tables curated déjà existantes (`curated_dbx_compute_clusters`, `curated_dbx_compute_node_timeline`, `curated_dbx_billing_usage`, `curated_dbx_billing_list_prices`, `curated_dbx_query_history`) ne nécessitent aucune évolution de schéma pour supporter ce nouveau socle gold ; elles sont réutilisées telles quelles.
- Le calcul prédictif s'appuie sur la fonctionnalité native `ai_forecast` (ou équivalent Databricks) déjà éprouvée sur d'autres domaines DCM — pas de nouvelle librairie ML à évaluer dans le cadre de cet Epic.
- L'exposition backend/API et l'affichage frontend de ces données sont volontairement hors scope de cet Epic (cf. Out of scope) ; le contrat des tables gold documenté ici sert de base au futur Epic d'exposition.
- Aucun SLA horaire strict n'est requis pour la disponibilité quotidienne des tables gold (best-effort) ; un SLA formel pourra être introduit plus tard si le futur Epic d'exposition l'exige.
- Le backfill initial (30 jours) est réalisable dans les limites de rétention des system tables Databricks pour tous les workspaces/LZ concernés (Azure et AWS).
- La fenêtre incrémentale de 3 jours (FR-018) est suffisante pour absorber le délai de correction/late-arrival des données curated amont ; si ce délai s'avère plus long en production, la fenêtre pourra être ajustée sans changement de modèle (paramètre de configuration).
