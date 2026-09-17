# Feature Specification: Compute Metrics Exposition (UI)

**Feature Branch**: `015-compute-metrics-exposition`
**Work Type**: feature
**Priority**: P1
**Created**: 2026-08-25

**Input**: Exposer dans DCM l'interface de monitoring Compute Metrics — 3 pages filles sous `Databricks > Compute` (Clusters, SQL Warehouses, Recommandations & Forecast) — alimentée par les tables gold produites par `012-compute-metrics-ingestion`, conformément aux maquettes fonctionnelles dans `maquette/compute-metrics-exposition/`.

**Maquettes de référence** :
- `maquette/compute-metrics-exposition/dcm-compute-clusters.html` + `Compute_Clusters_Spec.md`
- `maquette/compute-metrics-exposition/dcm-compute-warehouses.html` + `Compute_Warehouses_Spec.md`
- `maquette/compute-metrics-exposition/dcm-compute-recommendations-forecast.html` + `Compute_Recommendations_Forecast_Spec.md`

**Prérequis Epic** : `specs/012-compute-metrics-ingestion` (tables gold Delta — contrat dans `specs/012-compute-metrics-ingestion/contracts/gold-tables-contract.md`).

---

## Domain Scope

| Domaine | In scope | Ticket Story | Packages |
|---------|----------|--------------|----------|
| Frontend | ✅ | ✅ (T002, T003, T004 — 1 page / ticket) | packages/dcm-frontend |
| Backend | ✅ | ✅ (T001) | packages/dcm-backend, packages/dcm-commons |
| DataEng | ✅ lecture | ❌ | gold tables — livrées par Epic 012 |
| DevOps | ❌ | ❌ | — |
| QA | ❌ | ❌ | — |

## Ticket Plan

| Stories Jira | 4 |
| Mode | custom — 1 Backend + 3 Frontend (1 page = 1 ticket) |
| Domaines avec ticket | Backend, Frontend |

| ID | Domain | Summary | Merge order |
|----|--------|---------|-------------|
| T001 | Backend | API exposition gold compute (clusters, warehouses, recommendations, forecast) | 1 |
| T002 | Frontend | Page Compute Clusters | 2 (after T001) |
| T003 | Frontend | Page Compute SQL Warehouses | 3 (after T001) |
| T004 | Frontend | Page Recommendations & Forecast + nav badge | 4 (after T001) |

Branches attendues : `backend/015-compute-metrics-api`, `frontend/015-compute-clusters-warehouses-ui`, `frontend/015-compute-warehouses-ui`, `frontend/015-compute-reco-forecast-ui`.

## Dependency Analysis

| # | Besoin | Domaine | Résolution | Preuve |
|---|--------|---------|------------|--------|
| 1 | Tables gold `gold_dbx_compute_*` peuplées | DataEng | **Différé** — prérequis Epic 012 ; soft-fail + empty-state UI/API | `specs/012-compute-metrics-ingestion/spec.md` |
| 2 | Routes API sur gold compute | Backend | **Ticket T001** — à créer | `packages/dcm-backend/app/api/routes/clusters.py` expose `GET /api/v1/compute` (legacy `curated_compute_metrics`) — aucune route `gold_dbx_compute_*` |
| 3 | Pages Compute placeholder | Frontend | **Tickets T002/T003/T004** — 1 page / ticket | `app-routes.ts` : ComingSoon |
| 4 | Nav Compute 3e enfant + badge reco | Frontend | **Ticket T004** | `navigation.ts` — groupe Compute sans « Recommandations & Forecast » |
| 5 | Table `warehouse_slow_queries` (sous-vue Requêtes à investiguer) | DataEng | **Différé / conditionnel** — hors contrat 012 actuel | Maquette §2 Warehouses ; absent du spike et du contrat gold 012 |

**Règle soft-fail** (alignée 011-dbx-workflow-job-metrics) : si les gold tables sont vides ou indisponibles, l'API retourne des listes vides / 404 contrôlé et l'UI affiche un empty-state explicite — **aucune donnée DEMO ni mock permanent en prod**.

---

## Prerequisites

- **Small branches / small PRs** : T001 (backend global), T002/T003/T004 (1 page frontend par ticket) — QA page par page.
- Epic `012-compute-metrics-ingestion` mergé ou tables gold disponibles en dev (minimum pour tests d'intégration).
- Intake confirmé (`intake.json`, `domain-scope.json`).
- Maquettes HTML validées UX/PO pour les interactions filtres (seuils marqués « à valider PO » dans les specs maquette).
- Résoudre le statut de `warehouse_slow_queries` avant implémentation de la 4e sous-vue Warehouses (voir Clarifications).

---

## Navigation & Information Architecture

```
Databricks
  Overview
  Jobs & Pipelines
  ▸ Compute                    (collapsible — pas de page racine cliquable)
      Clusters                 → /databricks/cluster              (T002)
      SQL Warehouses           → /databricks/sql-warehouse          (T003)
      Recommandations & Forecast → /databricks/compute/recommendations (T004, badge = count OPEN)
  FinOps
  Usage Data Product
```

### Règles UX nav

1. **Compute** est un groupe dépliable (pattern existant nav v2 — cf. `navigation.ts`).
2. Labels : **Clusters**, **SQL Warehouses**, **Recommandations & Forecast** — pas de ALL CAPS.
3. Badge nav sur « Recommandations & Forecast » = nombre de recommandations `status='OPEN'` (clusters + warehouses).
4. Chaque page fille affiche une secondary nav / tabs pour ses sous-vues.
5. Filtres globaux topbar (LZ · cloud provider · workspace · plage dates 30j/90j/6m/1an) — communs aux 3 pages, cohérents avec le header DCM existant.

---

## User Scenarios & Testing

### User Story 1 — API gold compute disponible (Priority: P1) — **Backend T001**

En tant que développeur frontend / consommateur API, je veux des endpoints REST paginés et filtrables sur les tables gold compute, afin d'alimenter les 3 pages UI sans requêtes SQL directes côté navigateur.

**Why this priority** : Bloquant pour toute l'exposition UI ; aucune route gold n'existe aujourd'hui.

**Independent Test** : Appeler les nouvelles routes avec un token valide et des filtres LZ/workspace/date → réponses JSON typées, pagination, empty-state si tables vides.

**Acceptance Scenarios** :

1. **Given** des lignes existent dans `gold_dbx_compute_cluster_cost_daily`, **When** `GET /api/v1/databricks/compute/clusters/cost` avec `period_start`/`period_end` et scope LZ, **Then** la réponse contient les colonnes du contrat gold (cost_usd, dbu_quantity, cost_delta_pct, cost_rank…) filtrées par le scope utilisateur.
2. **Given** les tables gold sont vides, **When** tout endpoint compute metrics est appelé, **Then** HTTP 200 avec `{ items: [], total: 0 }` (pas d'erreur 500).
3. **Given** un utilisateur sans accès à une LZ, **When** il filtre sur cette LZ, **Then** la réponse exclut les données (filtre `_lz_filter` existant).
4. **Given** une requête avec filtres locaux (ex. `utilization_status=OVER`, `sku_group=Photon`), **When** le paramètre est supporté par l'endpoint, **Then** le filtrage est appliqué **côté serveur** (pas de fetch massif + filtre client en prod).

**Endpoints minimum (preview)** :

| Groupe | Tables gold source | Usage UI |
|--------|-------------------|----------|
| Clusters — cost | `gold_dbx_compute_cluster_cost_daily` | Overview, Cost, drawer trend |
| Clusters — efficiency | `gold_dbx_compute_cluster_efficiency_daily` | Overview, Efficiency |
| Clusters — governance | `gold_dbx_compute_cluster_governance` | Overview, Governance, drawer |
| Warehouses — cost | `gold_dbx_compute_warehouse_cost_daily` | Overview, Cost, drawer trend |
| Warehouses — query perf | `gold_dbx_compute_warehouse_query_performance_daily` | Overview, Query performance |
| Recommendations | `gold_dbx_compute_recommendations` | KPI reco, table, drawer, badge nav |
| Forecast | `gold_dbx_compute_forecast_daily` | Widget forecast (5 métriques) |
| Slow queries | `warehouse_slow_queries` | Sous-vue Requêtes à investiguer — **si table disponible** |

Granularité drawer (Jour/Semaine/Mois) : endpoint trend avec param `granularity=day|week|month` — agrégation SQL (`date_trunc`), pas de ré-agrégation frontend depuis le grain journalier brut.

---

### User Story 2 — Page Compute Clusters (Priority: P1) — **Frontend T002**

En tant que Data Platform Lead / FinOps / Data Engineer, je veux la page `Databricks > Compute > Clusters` avec 4 sous-vues (Overview, Cost, Efficiency, Governance), afin de monitorer coût, efficience et conformité des clusters sans quitter DCM.

**Why this priority** : Premier pilier métier Clusters ; remplace le placeholder ComingSoon.

**Independent Test** : Naviguer vers `/databricks/cluster` → vérifier les 4 tabs, KPI cards, tableaux, filtres locaux et drawer détail conformes à la maquette.

**Acceptance Scenarios** :

1. **Given** la page Clusters est chargée, **When** l'utilisateur ouvre l'onglet Overview, **Then** les KPI (Coût total Δ%, Clusters actifs, Zombies, Reco ouvertes) et le tableau agrégé s'affichent selon `Compute_Clusters_Spec.md` §2.
2. **Given** l'onglet Cost, **When** l'utilisateur saisit une recherche texte + filtre SKU + tri coût, **Then** le tableau se met à jour (paramètres API) et un message empty-state apparaît si aucun résultat.
3. **Given** l'onglet Efficiency, **When** l'utilisateur active la pill « Zombie », **Then** seuls les clusters `is_zombie=true` sont listés.
4. **Given** l'onglet Governance, **When** l'utilisateur combine pills « Tags manquants » + « DBR obsolète », **Then** le filtre ET logique s'applique comme en maquette §8.
5. **Given** un clic sur une ligne, **When** le drawer s'ouvre, **Then** fiche identité, KPIs, sparkline coût 90j (granularité Semaine par défaut), recommandations liées + CTA vers page Reco & Forecast.
6. **Given** les données gold sont indisponibles, **When** la page charge, **Then** empty-state explicite sans crash.

**Sous-vues V1** (cf. maquette) :

| Sous-vue | KPI cards | Filtres locaux |
|----------|-----------|----------------|
| Overview | Coût total, Clusters actifs, Zombies, Reco ouvertes | — |
| Cost | Coût période, DBU, Top coûteux | recherche, sku_group, tri |
| Efficiency | CPU/Mem p95, Zombies, Économies estimées | statut util. (+ pill Zombie) |
| Governance | Tags manquants, DBR obs., Sans auto-stop, Sévérité haute | sévérité, pills tags/DBR/auto-stop |

**Hors V1** (ne pas afficher placeholder grisé) : sous-vue Reliability, timeline événements drawer — cf. maquette §4.

---

### User Story 3 — Page Compute SQL Warehouses (Priority: P1) — **Frontend T003**

En tant que PO Data / FinOps / Data Eng, je veux la page `Databricks > Compute > SQL Warehouses` avec 4 sous-vues (Overview, Cost, Query performance, Requêtes à investiguer), afin de monitorer coût et performance SQL des warehouses.

**Why this priority** : Second pilier métier ; ticket dédié pour QA page par page (patterns UI partagés avec T002).

**Independent Test** : Naviguer vers `/databricks/sql-warehouse` → vérifier tabs, KPI, filtres, drawer ; bandeau sensibilité sur sous-vue Requêtes à investiguer.

**Acceptance Scenarios** :

1. **Given** la page SQL Warehouses, **When** l'utilisateur consulte Query performance, **Then** KPI (failure rate, latence p95, queue p95, spill) et filtres pills « Avec échecs » / « Avec spill » + seuil latence fonctionnent (seuils PO — cf. Clarifications).
2. **Given** la sous-vue Requêtes à investiguer, **When** des lignes existent, **Then** le texte SQL n'est **jamais** affiché ; seul un lien « Ouvrir » vers le query profile natif Databricks est proposé ; colonnes Raison (badge) et error_message restent distinctes.
3. **Given** la table `warehouse_slow_queries` est absente, **When** la page charge, **Then** la sous-vue Requêtes à investiguer est masquée (3 sous-vues visibles) — pas de tab grisé « Bientôt disponible ».
4. **Given** un clic warehouse, **When** le drawer s'ouvre, **Then** fiche (Taille, Auto-stop), KPIs, trend coût, requêtes à investiguer liées, reco + CTA Forecast.

**Hors V1** : sous-vue Utilization (warehouse_utilization_daily) — cf. maquette §4.

---

### User Story 4 — Page Recommandations & Forecast (Priority: P1) — **Frontend T004**

En tant que FinOps / Data Eng, je veux la page transverse `Recommandations & Forecast` listant les 9 règles actives V1 et les projections prédictives, afin de prioriser les actions d'optimisation clusters + warehouses.

**Why this priority** : Vue agrégée ; badge nav ; lien retour depuis drawers Clusters/Warehouses.

**Independent Test** : Naviguer vers `/databricks/compute/recommendations` → KPI reco, table filtrable, mini-drawer, widget forecast 5 métriques.

**Acceptance Scenarios** :

1. **Given** la page Reco & Forecast, **When** elle charge, **Then** KPI (Reco ouvertes, Économies potentielles, Résolues 30j, Sévérité haute) reflètent `gold_dbx_compute_recommendations`.
2. **Given** le tableau recommandations, **When** l'utilisateur combine filtres object_type + catégorie + sévérité, **Then** filtre ET logique ; empty-state si aucun match.
3. **Given** un clic ligne reco, **When** le mini-drawer s'ouvre, **Then** résumé + CTA « Ouvrir la fiche cluster|warehouse complète → » vers la page fille correspondante.
4. **Given** le widget Forecast, **When** l'utilisateur change de métrique, **Then** les 5 métriques V1 sont disponibles : `cost_usd`, `dbu_quantity`, `cpu_util_p95_pct`, `query_count`, `queue_time_p95_ms` — graphique historique + prévision + bande confiance.
5. **Given** des reco OPEN existent, **When** l'utilisateur consulte la nav, **Then** le badge sur « Recommandations & Forecast » affiche le count OPEN.

**9 règles actives V1** : cf. `Compute_Recommendations_Forecast_Spec.md` §2.3 (5 cluster + 4 warehouse ; règle #10 warehouse UNDER = V2).

---

## Out of scope (this Epic)

| Élément | Domaine | Raison |
|---------|---------|--------|
| Ingestion / pipelines gold | DataEng | Epic 012 |
| Sous-vue Clusters Reliability + timeline événements | Frontend + DataEng | `curated_dbx_access_audit` — chantier V2 |
| Sous-vue Warehouses Utilization | Frontend + DataEng | `warehouse_utilization_daily` — chantier V2 |
| 10e règle reco warehouse UNDER | DataEng + Frontend | Dépend utilization V2 |
| Règle cluster UNDER (sous-dimensionné) | PO + DataEng | Point ouvert maquette §3 — angle mort ou 6e règle |
| Migration / suppression API legacy `GET /api/v1/compute` | Backend | Page `/clusters` legacy hors scope — coexistence |
| DevOps (API GW routes) | DevOps | Hors scope si routes backend standard suffisent |

---

## Work Breakdown (preview)

| ID | Domain | Summary | Ticket |
|----|--------|---------|--------|
| T001 | Backend | Routes API gold compute + serializers + tests + contrats OpenAPI | ✅ |
| T002 | Frontend | Page Clusters (4 sous-vues, drawer, filtres) | ✅ |
| T003 | Frontend | Page SQL Warehouses (sous-vues, drawer, filtres) | ✅ |
| T004 | Frontend | Page Reco & Forecast + badge nav | ✅ |
| — | DataEng | Tables gold + warehouse_slow_queries | ❌ Epic 012 / extension |

---

## Requirements

### Functional Requirements

- **FR-001** : Le système MUST exposer des endpoints REST authentifiés pour lire les tables gold compute documentées dans le contrat 012, avec filtrage scope LZ/workspace/date.
- **FR-002** : Les pages `/databricks/cluster` et `/databricks/sql-warehouse` MUST remplacer les placeholders ComingSoon par l'UI maquette (4 sous-vues chacune).
- **FR-003** : La page `/databricks/compute/recommendations` MUST afficher recommandations + forecast conformément à la maquette dédiée.
- **FR-004** : Les filtres locaux documentés dans les specs maquette (§8 de chaque page) MUST être implémentés via paramètres API (prod) — la logique JS maquette sert de référence comportementale uniquement.
- **FR-005** : Le drawer détail (cluster/warehouse) MUST inclure trend coût avec granularité Jour/Semaine/Mois (défaut Semaine), agrégée côté backend.
- **FR-006** : La sous-vue Requêtes à investiguer MUST masquer le `statement_text` et proposer uniquement un lien externe query profile Databricks.
- **FR-007** : Le badge nav Reco MUST refléter `count(status='OPEN')` sur `gold_dbx_compute_recommendations`.
- **FR-008** : En absence de données gold, l'UI MUST afficher un empty-state — jamais de crash ni données fictives en prod.
- **FR-009** : Les CTAs cross-pages (drawer → Reco & Forecast ; mini-drawer reco → fiche cluster/warehouse) MUST naviguer vers les routes définies en § Navigation.
- **FR-010** : Aucune sous-vue V2 (Reliability, Utilization) MUST apparaître grisée « Bientôt disponible » — masquée jusqu'à livraison data.

### Non-Functional Requirements

- **NFR-001** : Pagination serveur sur les tableaux (pas de chargement unbounded multi-MB).
- **NFR-002** : Respect permissions LZ existantes (`get_allowed_lz_ids`).
- **NFR-003** : Accessibilité WCAG 2.2 AA — tabs, drawers, filtres keyboard-navigables.
- **NFR-004** : Labels UI en anglais (harmonisation frontend DCM) sauf libellés métier validés PO.

---

## Success Criteria

- **SC-001** : Les 3 routes Compute Metrics sont accessibles depuis la nav Databricks pour un utilisateur autorisé.
- **SC-002** : Chaque sous-vue V1 affiche KPI + tableau conformes à la maquette HTML (revue UX sign-off).
- **SC-003** : Les filtres locaux produisent le même résultat que la maquette JS sur un jeu de test backend fixe.
- **SC-004** : Empty-state gracieux quand gold tables vides (dev/staging pré-012).
- **SC-005** : Badge nav reco = count API OPEN (écart 0).
- **SC-006** : Widget forecast expose les 5 métriques V1 (correction maquette initiale 3→5).
- **SC-007** : Aucune régression sur routes legacy `/clusters` (page Computes existante).

---

## Clarifications

### Session 2026-08-25

- Q: Plan tickets ? → A: **4 Stories** — T001 Backend global + T002 Clusters + T003 SQL Warehouses + T004 Reco & Forecast (1 page = 1 ticket, QA page par page — PO 2026-08-25).
- Q: Consolidation puis re-split ? → A: Retour PO — tester page par page ; DCINT-268 Clusters, DCINT-269 Warehouses (réouvert), DCINT-270 Reco.
- Q: Priorité ? → A: P1 (suite directe exposition des gold tables 012).
- Q: Seuils filtres Query performance (« Avec échecs » ≥ 1 % failure rate, « Avec spill » > 0) ? → A: **[NEEDS CLARIFICATION]** — valeurs maquette par défaut ; validation PO/Data Eng avant implémentation réelle.
- Q: Mini-drawer reco vs drawer complet objet sur page Reco ? → A: **[NEEDS CLARIFICATION]** — maquette choisit mini-drawer + redirect ; alternative drawer complet à valider revue UX.
- Q: Table `warehouse_slow_queries` absente du contrat 012 ? → A: Sous-vue masquée si indisponible ; extension DataEng ou spec amend 012 si requis pour V1 complet.

---

## Assumptions

- Epic 012 livre les tables gold listées dans `gold-tables-contract.md` avant merge T002 en staging.
- Les routes backend suivent le pattern existant Databricks (`packages/dcm-backend/app/api/routes/databricks.py` ou module dédié `compute_metrics.py`).
- Réutilisation composants DCM existants : MetricCard, MetricGrid, Content layout, header workspace filter, TanStack Query.
- `warehouse_slow_queries` sera ajoutée au pipeline DataEng ou reportée — la page Warehouses reste livrable avec 3 sous-vues minimum.
- Le widget Forecast consomme `gold_dbx_compute_forecast_daily` (méthode `ai_forecast` — pas de recalcul front).
- Les liens « Ouvrir query profile » construisent une URL workspace Databricks à partir de `workspace_id` + `statement_id` (pattern à confirmer avec l'équipe plateforme).

---

## Edge Cases

- Workspace filter header actif → toutes les pages Compute respectent le scope (comme Dashboard inactive cluster widget).
- LZ onboardée sans workspaces Databricks → empty-state « No workspaces in scope ».
- Recommandation OPEN sur un cluster supprimé entre deux runs gold → ligne orpheline avec statut résolu ou flag « object not found » (soft handling).
- Forecast sans historique suffisant (< 7 jours) → graphique partiel ou message explicite.
- Utilisateur sans permission compute → pages gated (aligner `role-permissions.ts`).

---

## References

- Maquettes : `maquette/compute-metrics-exposition/`
- Ingestion gold : `specs/012-compute-metrics-ingestion/`
- Contrat tables : `specs/012-compute-metrics-ingestion/contracts/gold-tables-contract.md`
- Spike data model : `docs/spike/compute-metrics-definition/`
- Pattern nav fullstack : `specs/011-dbx-workflow-job-metrics/spec.md`
