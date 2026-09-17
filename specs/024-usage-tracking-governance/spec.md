# feature : Tracking d'usage — Usage des tables UC & Gouvernance

**Feature Branch**: `024-usage-tracking-governance` — branches filles `{domain}/024-usage-tracking-governance`
**Work Type**: feature
**Priority**: P1
**Created**: 2026-09-10

**Input**: « je veux lancer les spec sur le module tracking d'usage » — module à 2 pages exposant les 8 tables gold `gold_dbx_usage_*` livrées par la feature 019 : **Usage des tables UC** (vue d'ensemble + 3 vues) et **Gouvernance & Recommandations** (2 onglets). Spécifications draft déjà rédigées et challengées contre le code livré dans `maquette/tracking-usage-tables-uc/spec-tracking-usage-usage-tables-uc.md` et `maquette/tracking-usage-tables-uc/spec-gouvernance-recommandations.md`, avec mockups HTML de référence dans le même dossier.

## Domain Scope

Depuis `intake.json` — « In scope » = lecture autorisée, « Ticket » = reçoit une Story.

| Domaine | In scope | Ticket Story | Packages |
|---------|----------|--------------|----------|
| Frontend | ✅ | task T003 | packages/dcm-frontend |
| Backend | ✅ | task T002 | packages/dcm-backend, packages/dcm-commons |
| DataEng | ✅ | task T001 | packages/dcm-databricks-pipeline (histogramme de latence uniquement) |
| DevOps | ❌ | ❌ | — |
| QA | ❌ | ❌ | — |

Les trois domaines partagent **une seule Story Jira et une seule branche** (cf. Ticket
Plan) : la colonne « Ticket Story » désigne donc la task, pas une Story distincte.

## Ticket Plan

| Stories Jira | 1 |
|---|---|
| Mode | custom — **écart assumé** à la convention 1-domaine-1-ticket |
| Domaines couverts | dataeng, backend, frontend |
| Branche | `dataeng/024-usage-tracking-governance` (**unique**) |

Une seule Story Jira et une seule branche portent les **3 tasks** (T001 DataEng,
T002 Backend, T003 Frontend), exécutées **séquentiellement** sur cette même branche.
Chaque task est terminée et cochée avant que la suivante ne démarre.

**Écart assumé, décidé par l'équipe pour la vélocité** : la convention DCM prévoit
1 domaine = 1 Story = 1 branche = 1 PR. Ici la PR unique touche trois packages
(`dcm-databricks-pipeline`, `dcm-backend`, `dcm-frontend`), ce qui alourdit la revue —
cf. Prerequisites. Conséquence opérationnelle : le dispatch crée 1 Epic + 1 Story, et non
trois.

La task DataEng est **strictement bornée** à l'ajout d'un histogramme de latence sur
`gold_dbx_usage_table_query_performance_daily` (cf. Clarifications). Les 8 tables gold
existantes ne sont ni renommées, ni re-grainées, ni modifiées autrement.

## Contexte

Le module « Tracking d'usage » n'a aujourd'hui aucune exposition applicative : les 8
tables gold (`gold_dbx_usage_table_daily`, `table_popularity_daily`, `consumer_daily`,
`table_query_performance_daily`, `table_catalog`, `table_governance`, `recommendations`,
`forecast_daily`) sont livrées et alimentées par le pipeline (feature 019,
`packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/`), mais aucun endpoint API ni
aucune page frontend ne les lit. La page frontend existante `DataProductUsage.tsx` /
l'endpoint `data_product_usage.py` consomment une table différente
(`gold_data_product_usage`, feature antérieure) et ne sont pas concernés par cet Epic.

Objectif : donner aux personas Gouvernance (GOV), propriétaires de tables (OWN), FinOps
(FIN), Data Engineering (DE) et Analystes (AN) une vue exploitable de l'usage des tables
Unity Catalog (popularité, consommateurs, coût, fraîcheur, prévisions) et de leur
gouvernance (registre, cycle de vie, recommandations actionnables), sans naviguer entre
plus de 2 pages.

**Périmètre retenu à l'intake (Q6)** : le périmètre complet des deux specs draft, **à
l'exception** des points explicitement bloqués ou en attente de décision produit :

- **Exclu** — filtre consommateur `GENIE` (spec Usage, FR7) : bloqué côté Data
  Engineering, `consumer_type` n'a aujourd'hui aucune valeur `GENIE` en gold.
- **Exclu** — action d'acquittement des recommandations (spec Gouvernance, FR8) : le
  pipeline ne connaît que `OPEN`/`RESOLVED` et réécrit `status` à chaque run ; pas de
  `PATCH` applicatif dans cet Epic.
- **Exclu** — rattachement des lignes `recommendations.object_type = 'CONSUMER'` au
  filtre catalogue/schéma/table (spec Gouvernance, FR5/FR9) : ces lignes n'ont pas de
  colonne catalogue, elles restent visibles indépendamment du filtre table actif (voir
  Assumptions).
- **Exclu** — persistance des filtres communs lors de la navigation Usage → Gouvernance
  (spec Usage, FR9) : reporté, chaque page repart de filtres par défaut.

## Clarifications

### Session 2026-09-10

- Q: Quelle stratégie de pagination pour les listes (Par table, Par consommateur,
  Registre Gouvernance, Recommandations) ? → A: Pagination serveur classique
  (`page`/`page_size`, tri serveur).
- Q: Quelle période par défaut au premier chargement des 2 pages ? → A: Aucun défaut
  côté API — `period` (start/end) est un paramètre obligatoire ; le Frontend envoie une
  valeur par défaut (90 jours, cohérent avec le bouton 90d actif du mockup).
- Q: Comment gérer une table gold `gold_dbx_usage_*` absente ou pas encore alimentée ?
  → A: Réutiliser le pattern existant de `data_product_usage.py` (détection
  `[TABLE_OR_VIEW_NOT_FOUND]`, code d'erreur explicite par table).
- Q: Le sélecteur « Tous les clouds » du bandeau des mockups fait-il partie des
  filtres communs de cet Epic ? → A: Non — retiré, même traitement que les filtres
  Workspace/LZ (FR-010).
- Q: Quel tri par défaut pour la vue Par table et le Registre Gouvernance ? → A:
  Par table = `request_count` décroissant ; Registre Gouvernance = `severity`
  décroissante.

### Session 2026-09-10 (2) — arbitrages de conception

- Q: Faut-il ajouter `workspace_id` aux tables gold pour rendre le scope RBAC
  exprimable ? → A: **Non**. Une table Unity Catalog appartient à un `catalog.schema`,
  pas à un workspace ; `table_catalog`, `table_governance` et `recommendations` n'ont
  aucune notion de workspace, donc la page Gouvernance resterait non scopable dans tous
  les cas. Les 2 pages sont réservées au scope non restreint
  (`require_unrestricted_scope`), précédent `unity_catalog.py`. L'axe de scope
  sémantiquement correct serait le **catalogue**, mais aucun mapping projet → catalogue
  n'existe : Epic distinct si l'audience doit être élargie.
- Q: Faut-il un calcul par défaut au chargement des pages ? → A: **Non**. Le bandeau de
  période global reste affiché (cohérence avec les autres pages Databricks) mais aucune
  requête datée ne part tant que l'utilisateur n'a pas cliqué **Appliquer**. Les
  endpoints snapshot (registre, KPI gouvernance, recommandations) n'ont pas de période
  mais attendent le même geste (amendement du 2026-09-15, cf. FR-017). Rend caduque la
  question 30 j vs 90 j : il n'y a plus de période par défaut du tout.
- Q: Comment obtenir un P95 de latence correct sur une période arbitraire ? → A: Story
  **DataEng** ajoutant un histogramme de latence par (table, jour) sur
  `gold_dbx_usage_table_query_performance_daily`. Les compteurs de buckets sont
  additionnables sur une période quelconque, d'où un P95 interpolé sans rescanner
  `curated_dbx_query_history`. Écartés : `MAX` des P95 quotidiens (approximatif) et une
  agrégation backend sur le curated (viole P12 et coûteux à chaque affichage).

## Dependency Analysis

Constats de la vérification code (Q6 de l'intake) et décision retenue.

| Besoin | Domaine requis | Preuve (fichier) | Résolution |
|--------|----------------|-------------------|------------|
| P95 de latence sur une période arbitraire | dataeng | `gold_dbx_usage_table_query_performance_daily` ne stocke qu'un `percentile_approx` quotidien ; un P95 de période n'en est pas recalculable | Story DataEng (T001) — histogramme de latence |
| Exposer les 8 tables `gold_dbx_usage_*` via API | backend | `rg gold_dbx_usage_table_daily packages/dcm-backend` → aucune occurrence ; `data_product_usage.py` sert une table différente (`gold_data_product_usage`) | Story Backend (T002), après merge de T001 |
| 2 pages frontend (Usage des tables UC, Gouvernance & Recommandations) | frontend | `DataProductUsage.tsx` consomme l'ancienne API, aucune page/hook ne référence `gold_dbx_usage_*` | Story Frontend (T003), après merge de T002 |

## Prerequisites

- **Branche unique, PR unique** : `dataeng/024-usage-tracking-governance` porte les trois
  tasks. Écart assumé à la règle « small branches / small PRs » (cf. Ticket Plan) —
  compensation attendue : **commits séparés par task**, dans l'ordre T001 → T002 → T003,
  pour que la revue puisse se lire par étapes plutôt que comme un diff unique.
- **Séquencement** : T002 ne démarre qu'une fois T001 terminée **et la table gold
  rafraîchie** ; T003 ne démarre qu'une fois T002 terminée. Une seule task ouverte à la
  fois.
- Intake + domain scope confirmés (`intake.json` / `domain-scope.json`).
- Aucune dépendance bloquante non résolue : les trois besoins identifiés en Dependency
  Analysis ont chacun leur task.
- `[NEEDS CLARIFICATION]` : aucun marqueur restant dans cette spec — les points
  initialement `[NEEDS DECISION PO]` des specs draft ont été tranchés comme hors scope
  (cf. Contexte et Assumptions) plutôt que laissés en clarification bloquante.

## User stories

### User Story 1 — Rendre le P95 de latence calculable sur une période (Priority: P1)

En tant que pipeline gold, je veux stocker par (table, jour) la répartition des durées de
requête en buckets de latence, afin qu'un P95 puisse être reconstitué sur une période
quelconque en additionnant les compteurs, sans rescanner les statements bruts.

**Why this priority** : bloquant pour la colonne latence de la Story Backend, et seule
façon d'obtenir un P95 de période sans violer P12 (agrégations métier en Gold uniquement).

**Independent Test** : sur une fenêtre de test, comparer le P95 interpolé depuis les
buckets additionnés au `percentile_approx` calculé directement sur
`curated_dbx_query_history` pour les mêmes (table, période) — l'écart doit rester dans la
largeur du bucket.

**Acceptance Scenarios**

1. **Given** des statements de durées connues sur 3 jours, **When** le job gold tourne,
   **Then** la somme des compteurs de buckets d'une (table, jour) égale son `query_count`.
2. **Given** les buckets de 3 jours consécutifs, **When** on les additionne bucket à
   bucket, **Then** le P95 interpolé est celui de la période, pas une moyenne des P95
   quotidiens.
3. **Given** une (table, jour) sans requête, **When** le job tourne, **Then** les
   compteurs sont absents ou nuls, jamais un P95 fabriqué.
4. **Given** un run répété sur la même fenêtre, **When** le MERGE rejoue, **Then** les
   compteurs sont inchangés (idempotence, P6).

### User Story 2 — Exposer l'usage et la gouvernance des tables UC via API (Priority: P1)

En tant que service Backend, je veux exposer les données des 8 tables gold
`gold_dbx_usage_*` via des endpoints REST filtrables (période, catalogue, schéma,
table(s)) afin que le frontend puisse construire les pages Usage des tables UC et
Gouvernance & Recommandations sans logique d'agrégation dupliquée côté client.

**Why this priority** : bloquant pour la Story Frontend — aucune page ne peut être
construite sans ces endpoints.

**Independent Test** : appeler chaque endpoint (`/api/v1/uc-usage/overview`,
`/api/v1/uc-usage/tables`, `/api/v1/uc-usage/tables/{table_full_name}/top-consumers`,
`/api/v1/uc-usage/consumers`, `/api/v1/uc-usage/finops/*`, `/api/v1/uc-usage/governance/*`,
`/api/v1/uc-usage/recommendations`, `/api/v1/uc-usage/attention`) via des tests pytest sur des
fixtures représentatives des 8 tables gold, et vérifier que la réponse respecte les
règles d'agrégation documentées dans les specs draft (SUM vs COUNT DISTINCT, pas de
moyenne de P95, NULL préservé pour `data_written_bytes`/forecast absent, etc.).

**Acceptance Scenarios**

1. **Given** des lignes `gold_dbx_usage_table_popularity_daily` sur une période donnée,
   **When** j'appelle `GET /api/v1/uc-usage/tables?period_start=…&period_end=…`, **Then** je reçois une ligne par
   table avec `request_count` et `estimated_cost_usd` sommés sur la période, `latency_p95_ms`
   recalculé par `percentile_approx`, et `failure_rate_pct` recalculé (`SUM(failed)/SUM(total)`,
   jamais une moyenne de pourcentages quotidiens).
2. **Given** une table sans ligne dans `gold_dbx_usage_forecast_daily` (aucune activité sur
   14 jours), **When** j'appelle l'endpoint FinOps coût par table, **Then** la colonne
   forecast retourne `null` (jamais `0`).
3. **Given** `gold_dbx_usage_recommendations.status = 'RESOLVED'` pour une ligne,
   **When** j'appelle `GET /api/v1/uc-usage/recommendations`, **Then** cette ligne n'apparaît pas
   (filtre `status = 'OPEN'` par défaut, pas de déduplication par `(object_id, category)`).
4. **Given** un filtre `catalog`/`schema`/`tables[]`, **When** j'appelle
   `GET /api/v1/uc-usage/governance/registry`, **Then** seules les tables correspondantes sont
   retournées, avec `owner = null` explicite (pas de chaîne vide) quand le tag UC `owner`
   est absent.

### User Story 3 — Consulter l'usage et la gouvernance des tables UC (Priority: P1)

En tant qu'utilisateur Gouvernance / propriétaire de table / FinOps / analyste, je veux
consulter, depuis 2 pages accessibles par le menu Databricks, l'usage détaillé des tables
Unity Catalog et leur état de gouvernance, afin d'identifier les tables à risque, les
consommateurs coûteux et les recommandations actionnables sans naviguer entre plusieurs
outils.

**Why this priority** : valeur utilisateur finale du module ; dépend entièrement de la
Story 2 livrée.

**Independent Test** : avec l'API de la Story 1 disponible (ou mockée via MSW pendant le
développement), naviguer sur les 2 pages, changer les filtres communs et vérifier que
chaque vue/onglet se met à jour ; vérifier absence de régression sur les tests Vitest des
composants concernés.

**Acceptance Scenarios**

1. **Given** la page Usage des tables UC, **When** elle s'ouvre, **Then** aucune requête
   de données n'est émise : un écran d'accueil invite à choisir un périmètre puis à
   cliquer **Appliquer**, et aucune mesure — pas même un top 3 de recommandations — n'est
   affichée avant (FR-001 et FR-017, amendés le 2026-09-15).
2. **Given** un périmètre et une période choisis, **Appliquer** cliqué, **When** les
   données arrivent, **Then** la Vue d'ensemble affiche 6 KPI, 3 tendances prédictives
   intitulées **« +7j »** (jamais « +14j ») et 1 carte Volume écrit marquée comme
   observée.
3. **Given** la vue Par table, **When** je déplie une ligne, **Then** je vois le top 5
   consommateurs de cette table triés par coût, sans pagination.
4. **Given** la vue FinOps, **When** une table n'a pas de ligne de forecast, **Then**
   la cellule affiche un tiret, jamais `0` ou `$0`.
5. **Given** l'onglet Gouvernance, **When** la page s'ouvre, **Then** aucun endpoint de
   données n'est appelé : la page demande un périmètre puis **Appliquer**, comme Usage des
   tables UC (FR-017, amendé le 2026-09-15). **When** un périmètre est appliqué, **Then**
   le registre et les KPI se chargent ; quand le tag UC `owner` est absent, la colonne
   Owner affiche explicitement « Non renseigné ».
6. **Given** l'onglet Recommandations, **When** je filtre par catégorie, **Then** seules
   les recommandations `status = 'OPEN'` de cette catégorie s'affichent, triées par
   `severity` décroissante (HIGH > MEDIUM > LOW).
7. **Given** les filtres Workspace/LZ/Cloud du bandeau (mockup initial), **When** la page
   est livrée, **Then** ces filtres sont absents.

## Acceptance Criteria

1. **Given** les scénarios ci-dessus, **When** les 2 Stories sont mergées, **Then**
   toutes les valeurs affichées correspondent aux colonnes réelles des 8 tables gold
   (pas de `cost_usd`/`table_catalog`/`table_schema`, pas d'horizon « +14j »).
2. Gates du package verts (lint → types → tests → build) pour `dcm-backend` et
   `dcm-frontend`.

## Out of scope (cet Epic)

Tous les domaines in-scope (DataEng, Backend, Frontend) ont une task ; aucun n'est laissé
de côté. La task DataEng est bornée à **deux changements** — l'histogramme de latence
(FR-020) et la purge des tables éphémères (FR-024, ajoutée le 2026-09-17) : les 8 tables
gold existantes ne sont ni renommées, ni re-grainées, et `workspace_id` n'est **pas** ajouté
(cf. Clarifications). Aucune colonne n'est ajoutée aux faits journaliers pour FR-024 : la
purge supprime des lignes, elle n'en enrichit aucune. Les exclusions fonctionnelles (Genie, acquittement,
filtre CONSUMER, persistance de filtres inter-pages) sont documentées dans **Contexte** et
**Assumptions**.

## Work Breakdown (preview)

Trois tasks, **une seule Story Jira et une seule branche**
`dataeng/024-usage-tracking-governance`, exécutées dans cet ordre.

| ID | Domain | Summary | Ordre |
|----|--------|---------|-------|
| T001 | DataEng | Histogramme de latence par (table, jour) sur `gold_dbx_usage_table_query_performance_daily`, rendant le P95 reconstituable sur période arbitraire (FR-020) ; puis purge des tables éphémères des 5 tables gold de grain table (FR-024) | 1 |
| T002 | Backend | Endpoints `/api/v1/uc-usage/*` (overview, par table, top-consumers, par consommateur, FinOps, gouvernance, recommandations, points d'attention) sur les 8 tables `gold_dbx_usage_*` | 2 — après T001 et rafraîchissement de la table gold |
| T003 | Frontend | 2 pages — Usage des tables UC (vue d'ensemble + 3 vues) et Gouvernance & Recommandations (2 onglets), filtres communs catalogue/schéma/table(s) | 3 — après T002 |

## Requirements & Success Criteria

### Usage des tables UC

- **FR-001** : Une fois le périmètre appliqué (FR-017), la page ouvre sur une section Vue
  d'ensemble (6 KPI, 3 tendances prédictives à horizon **7 jours** lues depuis
  `gold_dbx_usage_forecast_daily`, 1 carte Volume écrit observée depuis
  `gold_dbx_usage_table_daily.data_written_bytes` sans conversion des `NULL` en 0).

  *Amendement du 2026-09-15* — la rédaction initiale ajoutait un bloc « Points
  d'attention » (top 3 recommandations `status='OPEN'` triées par `severity`) affiché
  **sans** période appliquée. Bloc **retiré de l'UI sur demande utilisateur** dans
  `7490304`, quand l'écran d'accueil a pris la place du contenu pré-Appliquer : un top 3
  de tout le patrimoine contredisait le principe « l'utilisateur choisit d'abord son
  périmètre ». Côté backend, `GET /attention` et le champ `attention` de `/overview`
  restent livrés et testés (T002) : aucune page ne les consomme aujourd'hui.
- **FR-002** : Trois vues accessibles par tabbar sous la Vue d'ensemble — Par table
  (défaut), Par consommateur, FinOps — sans rechargement des filtres communs au switch.
- **FR-003** : Les filtres catalogue/schéma/table(s) sont communs aux trois vues ; le
  filtre table restreint la vue Par consommateur par intersection (au moins une table
  lue) et la vue FinOps par filtre direct.
- **FR-004** : Vue Par table — drill-down (top 5 consommateurs triés par coût, sans
  pagination) et fraîcheur lue depuis `freshness_lag_hours` + `freshness_basis` (mention
  « estimation » quand `freshness_basis = table_altered`). Tri par défaut :
  `request_count` décroissant (popularité), avant toute sélection utilisateur.
- **FR-005** : Vue Par consommateur — classement recalculé côté API sur la période
  sélectionnée (`SUM(estimated_cost_usd)` décroissant), pas une lecture brute de
  `consumer_rank` (colonne non fiable sur une période multi-jours et non partitionnée
  par `cloud_provider`) ; 5 premiers mis en avant par un badge de rang.
- **FR-006** : Vue FinOps — KPI de coût agrégé, coût moyen/requête libellé comme
  minorant potentiel (dénominateur `request_count`, `costed_request_count` non exposé à
  ce grain), top table coûteuse, tableau coût par table avec colonne Forecast **+7j**
  (tiret si absence de ligne de prévision).
- **FR-022** : La latence P95 affichée est celle de la **période sélectionnée**,
  reconstituée par interpolation sur les buckets de latence additionnés (FR-020) — ni
  une moyenne des P95 quotidiens, ni un `MAX` du pire jour.
- **FR-007** : Recherche texte libre par nom (table ou consommateur selon la vue
  active ; sans effet sur la vue FinOps déjà filtrée par le multi-select table).
- **FR-008** : Toutes les occurrences `cost_usd`/`table_catalog`/`table_schema` du
  mockup sont corrigées en `estimated_cost_usd`/`catalog`/`schema` dans l'API et l'UI.
- **FR-009** : Tooltip/footnote sur `estimated_cost_usd` mentionnant
  `cost_attribution_method = equal_parts_fallback` et `cost_basis` quand il diffère de
  `warehouse_prorata`.
- **FR-010** : Les filtres Workspace/LZ du bandeau (mockup) sont retirés — aucune des 8
  tables gold ne porte `workspace_id`.
- **FR-019** : Le sélecteur cloud (« Tous les clouds ») du bandeau des mockups n'est
  pas repris pour ce module — même traitement que FR-010 : retiré, aucun paramètre
  `cloud_provider` sur les endpoints `/api/v1/uc-usage/*`. Les données aws et azure
  restent agrégées ensemble sur toutes les vues.
- **FR-020** : `gold_dbx_usage_table_query_performance_daily` porte, par (table, jour),
  la répartition des durées de requête en buckets de latence à bornes fixes. Les
  compteurs sont **additionnables** sur une période quelconque, ce dont l'API déduit un
  P95 par interpolation. La somme des compteurs d'une (table, jour) égale son
  `query_count` ; une (table, jour) sans requête ne produit aucun P95 fabriqué.

### Gouvernance & Recommandations

- **FR-011** : Deux onglets — Gouvernance (défaut) et Recommandations — partageant les
  filtres communs catalogue/schéma/table(s) ; ce filtre s'applique aux recommandations
  via jointure `object_id = table_full_name` uniquement pour `object_type = 'DATA_PRODUCT'`.
- **FR-012** : Onglet Gouvernance — KPI (tables inutilisées, périmées mais lues,
  critiques) et registre des tables (owner affiché « Non renseigné » si le tag UC est
  absent ; dernière opération limitée aux valeurs réelles `createTable`/`deleteTable`/
  `updateTables` ; fan-out aval ; statut dérivé du mot-clé `recommended_action`
  (`archiver`/`documenter`/`surveiller`/NULL) + `severity`, jamais un texte libre). Tri
  par défaut : `severity` décroissante, avant toute sélection utilisateur.
- **FR-013** : Onglet Recommandations — KPI High/Medium/Total ouvertes (`status='OPEN'`),
  filtre par catégorie (liste fermée : LIFECYCLE, FRESHNESS, GOVERNANCE, RELIABILITY,
  FINOPS), liste triée par `severity` décroissante sans déduplication par
  `(object_id, category)` (une ligne `RESOLVED` reste en base, une réouverture crée une
  nouvelle ligne).
- **FR-014** : Le KPI « gain estimé » est libellé comme ne couvrant que la catégorie
  LIFECYCLE « inutilisée » (`estimated_savings_usd` est `NULL` pour les 4 autres
  catégories).
- **FR-015** : La sévérité est normalisée à l'affichage entre les deux onglets
  (`HIGH`/`MEDIUM`/`LOW` côté recommandations vs `high`/`medium`/`low` côté
  `table_governance`) par un mapping insensible à la casse, pas un composant de badge
  partagé sans normalisation.

- **FR-016** : Les 4 endpoints de liste (Par table, Par consommateur, Registre
  Gouvernance, Recommandations) sont paginés côté serveur (`page`/`page_size`, tri
  serveur) — aucun ne retourne la liste complète en un seul appel. Le drill-down top 5
  consommateurs (FR-004) reste un `LIMIT 5` non paginé, hors de cette règle.
- **FR-017** : `period` (date de début / date de fin) est un paramètre **obligatoire**
  sur tous les endpoints `/api/v1/uc-usage/*` qui en dépendent — aucune valeur par défaut
  côté API (rejet explicite si absent). Côté UI, **aucune requête de données n'est
  déclenchée au chargement**, datée ou non : le bandeau de période global reste affiché
  pour la cohérence avec les autres pages Databricks, mais rien ne part tant que
  l'utilisateur n'a pas choisi un périmètre (catalogue, schéma ou tables) et cliqué
  **Appliquer**. Les endpoints snapshot (registre, KPI gouvernance, recommandations) n'ont
  pas de période mais sont soumis au même geste, sur les **deux** pages. Seul
  `/filters/options` part au chargement : c'est lui qui peuple le sélecteur de périmètre.

  *Amendement du 2026-09-15* — la rédaction initiale faisait charger les endpoints
  snapshot immédiatement. La page Gouvernance s'ouvrait donc sur l'état de tous les
  catalogues, là où Usage des tables UC demandait déjà un périmètre : deux entrées
  opposées pour deux pages voisines. Le périmètre est désormais obligatoire des deux
  côtés, ce qui supprime aussi le balayage du registre entier à chaque ouverture.
  Conséquence assumée : plus d'analyse « tous les catalogues » sans une option explicite,
  qui n'existe pas aujourd'hui.
- **FR-018** : Si une table gold `gold_dbx_usage_*` est absente (erreur
  `[TABLE_OR_VIEW_NOT_FOUND]`), l'endpoint concerné renvoie un code d'erreur explicite
  (même pattern que `data_product_usage_table_missing` dans `data_product_usage.py`),
  jamais une 500 générique ni une réponse vide indistincte d'une période sans données.
- **FR-023** : Les tables supprimées de Unity Catalog sont **exclues par défaut** de toute
  l'analyse, et incluses sur demande explicite. Contrat gelé par la spec 027 :
  [027 · api-include-deleted.md](../027-usage-table-deleted-flag/contracts/api-include-deleted.md).
  - API : `include_deleted` (booléen, défaut `false`) sur les **18** routes de
    `/api/v1/uc-usage/*` qui portent une clé table ; `GET /consumers` et
    `GET /charts/consumers` en sont **exemptes** — de grain consommateur, elles n'ont
    aucune table à filtrer. L'exclusion s'applique **avant** agrégation, par anti-jointure
    sur `gold_dbx_usage_table_catalog` (le drapeau n'est pas dénormalisé sur les faits
    journaliers : le MERGE glissant de 3 jours le figerait), ou par
    `NOT COALESCE(is_deleted, false)` là où la table porte elle-même le drapeau. Aucun KPI,
    graphique ni total de pagination ne compte donc une table que sa liste n'affiche pas.
  - Réponses de grain table (`/tables`, `/finops/cost-by-table`, `/governance/registry`,
    `/details`, `/tables/{t}/top-consumers`, `/filters/options`) : trois champs de cycle de
    vie **toujours présents** — `is_deleted` (jamais nul), `deleted_at`, `lifecycle_state`
    ∈ `ACTIVE|DELETED|UNKNOWN`. Les lignes de grain recommandation (`/recommendations`,
    `/attention`) ne les portent pas : leur `object_id` n'est pas toujours une table.
  - UI : une case **« Include deleted tables »** dans le bloc de périmètre, aux côtés de
    catalogue / schéma / tables, sur les **2** pages. Décochée par défaut, elle part avec
    le même clic sur **Appliquer** que le reste du périmètre (FR-017) — rien ne se
    recharge à la coche. Seul `/filters/options` l'écoute immédiatement : sans cela, une
    table supprimée ne pourrait jamais être cochée dans le sélecteur. Une ligne supprimée
    est marquée avec **sa date de suppression** dans les trois tableaux de grain table et
    dans le tiroir d'historique — sans la date, elle se lirait comme une ligne vide.

  *Amendement du 2026-09-16* — exigence **ajoutée** après la livraison de T001–T003 : la
  spec 027 a introduit `is_deleted` dans `gold_dbx_usage_table_catalog`, et sans ce filtre
  les 2 pages comptaient encore des tables qui n'existent plus. Écarts assumés : le libellé
  de la case est en **anglais** (« Include deleted tables ») comme toute la copie UI, là où
  le contrat 027 le cite en français ; et l'OpenAPI documente le **paramètre** mais pas les
  trois champs de réponse — ce routeur ne déclare aucun `response_model` (ses 20 routes
  renvoient `dict[str, Any]`), ce qui n'a pas été changé pour une seule exigence.
- **FR-024** : Une table **éphémère** — créée puis supprimée dans l'heure, d'après les
  événements DDL de `system.access.audit` — n'est **jamais** présentée comme un objet
  gouverné : ni ligne au registre `gold_dbx_usage_table_catalog`, ni ligne de faits
  journaliers, ni ligne dans le snapshot de gouvernance. Une table de travail détruite le
  jour même n'a pas d'owner à réclamer, pas de fraîcheur à surveiller et pas d'action de
  gouvernance à recommander : la faire figurer noie les tables réelles.
  - Le pipeline gold **purge** les 5 tables porteuses de la clé de table — registre, faits
    journaliers, popularité, performance de requête, snapshot de gouvernance — après
    l'écriture de chaque run. Purger le seul registre serait pire que ne rien faire :
    l'exclusion en aval lit la **présence** d'une ligne `is_deleted` au registre, pas
    l'absence de ligne, donc une éphémère retirée du seul registre réapparaîtrait comme une
    table **vivante** dans les 2 pages.
  - Trois conditions **cumulatives**, toutes nécessaires : la table est absente de Unity
    Catalog aujourd'hui, **et** son dernier événement DDL audité est une suppression,
    **et** sa durée de vie auditée est inférieure au seuil. Une table dont l'audit ne dit
    pas l'âge n'est jamais purgée — l'inconnu est traité comme « a vécu assez longtemps ».
  - Trois tables restent **hors** périmètre, et pour des raisons distinctes : le grain
    consommateur (aucune clé de table à purger), les recommandations (elles se soignent
    seules en passant à `RESOLVED`), et les prévisions (leur seuil d'observation minimale
    exclut déjà toute table de moins d'une semaine).

  *Amendement du 2026-09-17* — exigence **ajoutée** après la livraison de FR-023. Le
  correctif de plan des recommandations (T002 étape 6) a montré que le registre issu de la
  spec 027 marquait supprimée la quasi-totalité de ses lignes : le catalogue accumulait des
  tables temporaires que rien n'avait jamais eu l'intention de gouverner. Le drapeau
  `is_deleted` de FR-023 reste nécessaire — une table suivie puis supprimée doit être
  reconnaissable — mais il ne doit pas servir à masquer des objets qui n'auraient jamais dû
  être enregistrés.
- **FR-021** : Les 2 pages sont accessibles au seul **scope non restreint** : le routeur
  est protégé par `require_unrestricted_scope` et les routes frontend sont mappées sur
  `page:unity-catalog`. Motif : aucune des 8 tables gold ne porte `source_lz_id` ni
  `workspace_id`, et une table Unity Catalog n'appartient pas à un workspace — aucun
  filtrage par lignes n'est exprimable.

### Success Criteria

- **SC-001** : Un utilisateur Gouvernance identifie les tables inutilisées et critiques
  du catalogue sans quitter la page Gouvernance.
- **SC-002** : Un propriétaire de table identifie le top 5 des consommateurs d'une table
  donnée en au plus 2 interactions (ouverture de page + clic sur la ligne).
- **SC-003** : Un utilisateur FinOps consulte le coût agrégé et sa projection à 7 jours
  sans changer de page.
- **SC-004** : 100 % des libellés d'horizon affichés à l'écran correspondent à l'horizon
  réel des données sources (7 jours) — aucune occurrence de « +14j » ne subsiste.
- **SC-005** : Aucune métrique de volume ou de prévision absente n'est affichée comme
  zéro (`NULL` reste distinct de `0` dans toute la chaîne API → UI).
- **SC-006** : Case « Include deleted tables » décochée, aucune table supprimée n'apparaît
  dans une liste, un KPI, un graphique ni un total de pagination des 2 pages ; cochée puis
  appliquée, les mêmes écrans les rendent avec leur date de suppression (FR-023).
- **SC-007** : Périmètre appliqué, les blocs Recommandations et Points d'attention de la
  page Gouvernance rendent leur contenu **sans atteindre le délai d'abandon du client**
  (`API_REQUEST_TIMEOUT_MS`, 30 s), et le registre reste dans le même budget quand le
  catalogue grossit. Mesuré contre la warehouse à froid, pas seulement en test : l'exclusion
  des tables supprimées (FR-023) porte le risque d'un plan par ligne contre le catalogue
  entier, et la purge des éphémères (FR-024) en réduit la taille à la source.

  *Amendement du 2026-09-17* — critère **ajouté** : c'est le seul défaut de la branche
  qu'aucun test du dépôt ne pouvait attraper, la suite validant la chaîne SQL et non son
  plan d'exécution.

## Assumptions

- Les lignes `recommendations.object_type = 'CONSUMER'` restent visibles indépendamment
  du filtre catalogue/schéma/table actif (pas de colonne catalogue sur ces lignes) ; une
  évolution future pourra les regrouper dans une section « hors périmètre table »
  dédiée — décision reportée hors de cet Epic.
- Le filtre `GENIE` sur le type de consommateur n'est pas implémenté : `consumer_type`
  n'a aujourd'hui aucune valeur `GENIE` en gold (chantier Data Engineering non démarré,
  hors scope de cet Epic).
- Aucune action d'acquittement (« Acknowledge ») n'est exposée sur les recommandations :
  le pipeline ne connaît que `OPEN`/`RESOLVED` et réécrit `status` à chaque run.
- Les filtres communs ne sont pas persistés lors d'une navigation entre les 2 pages
  (chaque page repart de ses filtres par défaut).
- Les 2 pages sont réservées aux porteurs d'un scope non restreint (FR-021). Élargir
  l'audience suppose un axe de scope par **catalogue** — aucun mapping projet → catalogue
  n'existe aujourd'hui, ce serait un Epic distinct. Ajouter `workspace_id` aux tables
  gold ne résoudrait pas le problème : la page Gouvernance resterait non scopable.
- Le ticket DataEng ne touche que
  `gold_dbx_usage_table_query_performance_daily` ; le grain et les clés de merge des
  8 tables gold restent inchangés.
- La précision du P95 de période est bornée par la largeur des buckets de latence ; c'est
  un compromis assumé face au coût d'un rescan de `curated_dbx_query_history`.
- Les seuils de gouvernance (90 jours d'inutilisation, `downstream_fanout >= 5`,
  seuils RELIABILITY/FINOPS) restent codés en dur côté pipeline (feature 019) ; leur
  paramétrisation n'est pas dans le périmètre de cet Epic.
- `owner` restera `NULL`/« Non renseigné » pour la quasi-totalité des tables tant que le
  tagging UC `owner` n'aura pas été fait ailleurs (hors scope).
