# feature : Fenêtres glissantes SQL Warehouses, colonnes redimensionnables et filtres par colonne

**Feature Branch**: `023-colonnes-et-filtres-compute` — branches filles `{domain}/023-colonnes-et-filtres-compute`
**Work Type**: feature
**Priority**: P2
**Created**: 2026-09-06

**Input** (demande utilisateur, verbatim) :

> 3 choses:
> pour les warehouse ajoute aussi les filtre par period (day, 7d, 30d, 90d) et inverse l'ordre des champ warehouse et workspace. Pour warehouse ca doit representer warehouse name pas id.
> front pour toutes les colonne de tous les modules. Mettre une taille fixe pour les collonne avec possibilité pour l'uitlstateur d'augmenter les taille ou la diminuer.
> front pour toutes les colonne de tous les modules. ajouter des filtre par collone avec des combo bar (list, reshearch)

## Clarifications

### Session 2026-09-06

- Q: « tous les modules » — quel périmètre pour la largeur redimensionnable et les
  filtres par colonne ? → A (arbitrage utilisateur) : **les 5 pages pilotées par
  `ComputeDataTable`** — `ComputeClusters`, `ComputeSqlWarehouses`, `LakeflowJobs`,
  `LakeflowJobDetail`, `recommendations-table`. C'est le seul composant de tableau
  piloté par une liste de colonnes : une implémentation unique les couvre toutes. Les
  7 pages à markup `<TableHead>` écrit à la main (`Admin`, `Users`, `CollectionStatus`,
  `MonitoringReports`, `ProjectDetail`, `UnityCatalogExplorer`,
  `AdminEmbeddedDashboardsTab`) ne sont **pas** migrées, et les pages à accordéons
  (`Databricks`, `Databases`, `DataFactory`, `Costs`) n'ont pas de colonne à
  redimensionner.
- Q: « warehouse doit représenter warehouse name pas id » — d'où vient le nom sur les
  onglets Utilisation et Performance, dont les tables gold ne le portent pas ? → A
  (arbitrage utilisateur) : **ajouter `warehouse_name` en gold** sur les 4 tables
  concernées, plutôt que de n'afficher le nom que là où il existe déjà.
- Q: les filtres par colonne s'appliquent-ils à la page affichée ou à tout le
  périmètre ? → **Tout le périmètre, donc côté serveur.** Non soumis à arbitrage : les
  11 tableaux paginent tous côté serveur (25 à 50 lignes par réponse), un filtre construit dans le
  navigateur ne verrait que la page courante. Ce serait exactement le défaut que
  l'utilisateur a déjà signalé sur ces mêmes pages (« je ne vois que 50 cluster ou
  warehouse alors qu'il y en a énormément plus », corrigé par la spec 022 T004).
- Q: « inverse l'ordre des champ warehouse et workspace » — dans quel sens ? →
  **Workspace puis Warehouse**, l'ordre actuel étant Warehouse puis Workspace
  (`ComputeSqlWarehouses.tsx:313` puis `:328`). C'est l'ordre déjà en place sur les trois
  tableaux de la page Cluster (`ComputeClusters.tsx:409`, `:508`, `:578`), donc un
  alignement, pas une préférence arbitraire.
- Q: la fenêtre glissante remplace-t-elle le sélecteur de période libre du header sur la
  page Warehouses ? → **Oui**, même raisonnement que la spec 022 pour les clusters : les
  tables `*_rolling` sont des snapshots « as of » `as_of_date`, une période libre n'a
  aucun effet dessus. Les filtres de scope (workspace, cloud provider, LZ) restent
  actifs.

## Domain Scope

Depuis `intake.json` — « In scope » = lecture autorisée, « Ticket » = reçoit une Story.

| Domaine | In scope | Ticket Story | Packages |
|---------|----------|--------------|----------|
| DataEng | ✅ | ✅ | packages/dcm-databricks-pipeline |
| Backend | ✅ | ✅ | packages/dcm-backend |
| Frontend | ✅ | ✅ | packages/dcm-frontend |
| DevOps | ❌ | ❌ | — |
| QA | ❌ | ❌ | — |

## Ticket Plan

| Stories Jira | 3 |
|---|---|
| Mode | one_per_domain |
| Domaines avec ticket | dataeng, backend, frontend |

## Contexte

Trois demandes distinctes, réunies dans une seule spec parce qu'elles convergent sur les
mêmes fichiers : les 11 tableaux de `ComputeDataTable` et les services compute-metrics qui les
alimentent.

**1. Fenêtres glissantes warehouse.** La spec 022 a branché les pages Cluster sur les
tables `gold_dbx_compute_cluster_*_rolling` : quatre plages statiques 1/7/30/90 jours,
avec la période réellement couverte affichée. Les pages SQL Warehouses sont restées sur
les tables `*_daily` avec la période libre du header. Or les trois tables
`gold_dbx_compute_warehouse_*_rolling` existent et leurs **quatre fenêtres sont déjà
peuplées** — mesuré en dev. Aucun travail dataeng n'est nécessaire pour les fenêtres
elles-mêmes : c'est un repointage backend + un sélecteur front.

Le comportement actuel est en outre trompeur : sur une période libre, le service prend le
**dernier jour présent dans la plage** (`QUALIFY ROW_NUMBER() … ORDER BY period_start
DESC`), pas la somme de la plage. Élargir la période ne fait donc que déplacer l'ancre.
Les quatre chips donneront enfin un sens agrégé à « 30 derniers jours ».

**2. Nom du warehouse.** `WarehouseCell` affiche `name || id`. Sur l'onglet Performance
des requêtes, le front passe `name={null}` en dur
(`ComputeSqlWarehouses.tsx:485`) — parce que `gold_dbx_compute_warehouse_query_performance_daily`
ne porte pas la colonne. Seules les deux tables de coût la portent.

**3. Colonnes : largeur et filtres.** `ComputeDataTableColumn` n'a aujourd'hui ni largeur
ni filtre : les colonnes sont dimensionnées par le contenu, et le filtrage vit dans la
barre d'outils de chaque page, avec un jeu de contrôles différent par onglet
(`<select>` de taille, chips « With failures », seuil de latence…).

## Dependency Analysis

Constats de la vérification code et décision retenue.

| Besoin | Domaine requis | Preuve (fichier) | Résolution |
|--------|----------------|------------------|------------|
| `warehouse_name` sur utilisation et performance des requêtes | dataeng | `warehouse_query_performance_daily.py` ne joint pas `curated_dbx_compute_warehouses` ; `warehouse_utilization_daily.py` la joint (CTE `warehouses_as_of`, lignes 439-457) mais ne sélectionne que `auto_stop_minutes` et `max_clusters` | `add_dataeng_ticket` → T001 |
| Lecture des tables `warehouse_*_rolling` | backend | `compute_metrics_warehouses.py:39-40` ne cite que les tables `*_daily` ; aucune occurrence de `window_days` dans le fichier | ticket Backend (T002) |
| Paramètre `window_days` sur les routes warehouse | backend | `app/api/routes/compute_metrics.py:482-627` — les 4 routes prennent `period_start`/`period_end` | ticket Backend (T002) |
| Fenêtres 1/7/30/90 peuplées en gold | — | déjà en place : mesuré en dev, les 3 tables `warehouse_*_rolling` ont les 4 valeurs de `window_days` | aucun besoin |
| Valeurs distinctes par colonne pour les listes de combo | backend | les 11 tableaux filtrent/trient/paginent tous côté serveur (`compute_metrics_clusters.py` `_overview_filters`, `compute_metrics_warehouses.py` `_overview_filters`, `lakeflow_jobs.py:170`) | ticket Backend (T004) |
| Paramètre de filtre par colonne | backend | les filtres existants sont ad hoc et partiels : `search`, `warehouse_size`, `min_failure_rate_pct`, `utilization_status` — pas de filtre sur workspace, type de cluster, sévérité, propriétaire | ticket Backend (T004) |
| Largeur de colonne persistée | frontend | `ComputeDataTableColumn` n'a que `align` et `className` ; aucune largeur, aucun redimensionnement | ticket Frontend (T003/T005) |
| Combo liste + recherche compacte | frontend | `components/ui/combobox.tsx` existe mais est **non réutilisable en l'état** : palette `slate`/`blue` codée en dur au lieu des tokens de design, `w-full` + `py-3`, mono-sélection | ticket Frontend (T006) |

**Pourquoi le gold et pas le backend** pour `warehouse_name` : le service compute-metrics
ne lit **aucune** table curated — vérifié, `rg "curated_dbx" packages/dcm-backend/app/api/services/`
ne renvoie rien. Le faire côté backend ferait franchir la frontière médaillon à un service
qui ne lit que du gold et des dimensions. Joindre la table de coût gold à la place a été
**mesuré et rejeté** : un warehouse peut tourner sans ligne de facturation rattachée ce
jour-là, et il manque alors le nom. Comptage en dev sur `warehouse_utilization_rolling` :

| Fenêtre | Lignes sans nom / total |
|---|---|
| 1 j | 281 / 353 |
| 7 j | 441 / 544 |
| 30 j | 536 / 669 |
| 90 j | 597 / 733 |

Soit ~80 % de lignes anonymes. `curated_dbx_compute_warehouses` porte 463 warehouses,
**nommés à 100 %**, et c'est déjà la source que `warehouse_cost_daily.py` utilise.

## Prerequisites

- **Small branches / small PRs** : trois branches filles, une par package.
- Intake + domain scope confirmés (`intake.json` / `domain-scope.json`).
- Le gap `dataeng` reçoit T001, ordonnancée **avant** T002 (le backend lit la colonne
  qu'elle produit).
- `[NEEDS CLARIFICATION]` : aucun ouvert (cf. Clarifications).
- **Migration T001** : `MERGE WITH SCHEMA EVOLUTION` ajoute `warehouse_name` sans
  reconstruire. Les tables `*_rolling` étant des snapshots complets
  (`watermark_column = None`) elles sont **immédiatement** nommées à 100 % au run
  suivant. Les deux tables `*_daily` ne sont recalculées que sur
  `INCREMENTAL_LOOKBACK_DAYS` (10 jours, cf. 022 T006) : leur historique plus ancien
  garde `warehouse_name = NULL` jusqu'à un `full_refresh`. Aucun consommateur de cette
  feature ne lit ces jours-là (les vues de liste passent aux `*_rolling`), donc le
  `full_refresh` n'est **pas** un prérequis — il est proposé en option dans T001.
- `_normalize_prev_cost` doit être appliqué aux warehouses : `warehouse_cost_rolling.py:115`
  agrège la fenêtre précédente en `SUM(CASE … ELSE 0 END)`, donc `cost_usd_prev_window`
  n'est **structurellement jamais NULL** — même défaut que celui trouvé en vérifiant
  022 T002 sur les clusters.

## User stories

### User Story 1 — `warehouse_name` exposé par les tables d'utilisation et de performance (Priority: P1)

Story **DataEng** (T001). En tant que consommateur des tables gold, je veux que les
4 tables `gold_dbx_compute_warehouse_utilization_*` et
`gold_dbx_compute_warehouse_query_performance_*` portent `warehouse_name`, comme les deux
tables de coût.

**Why this priority** : bloque l'affichage du nom sur 2 des 3 onglets, donc T002 et T003.
**Independent Test** : `pytest` sur les builders (assertions sur le SQL généré), puis
contrôle en dev du taux de remplissage de `warehouse_name` sur les 4 tables.

**Acceptance Scenarios**

1. **Given** un warehouse présent dans `curated_dbx_compute_warehouses`, **When**
   `warehouse_utilization_daily` est recalculée, **Then** la ligne porte le
   `warehouse_name` au dernier état connu ce jour-là
   (`change_time < period_start + INTERVAL 1 DAY`), selon la même règle que
   `warehouse_cost_daily`. *Ce scénario disait `change_time <= period_start` — corrigé le
   2026-09-07 : cette borne, qui vaut minuit, rendait `NULL` tout warehouse créé dans la journée
   et faisait échouer le SC-001 ci-dessous. Les 3 builders warehouse sont désormais alignés sur la
   convention cluster/job (« dernier état de la journée »).*
2. **Given** un warehouse absent de `curated_dbx_compute_warehouses`, **When** les tables
   sont recalculées, **Then** la ligne reste présente avec `warehouse_name = NULL` — la
   jointure enrichit, elle ne filtre pas.
3. **Given** les tables `*_rolling` reconstruites, **When** je compte les lignes sans nom,
   **Then** le taux est inférieur à 5 % sur les 4 fenêtres (contre ~80 % par la jointure
   sur la table de coût).
4. **Given** un warehouse renommé au milieu de la fenêtre, **When** la table `*_rolling`
   est reconstruite, **Then** elle porte le nom du **dernier** jour connu, selon la même
   règle `latest_attrs` que `auto_stop_minutes` et `top_slow_statement_id`.

### User Story 2 — API warehouse par fenêtre glissante (Priority: P1)

Story **Backend** (T002). En tant que page SQL Warehouses, je veux demander une plage
(1, 7, 30 ou 90 jours) et recevoir, par warehouse, les indicateurs de la fenêtre, les
bornes réelles de la période couverte, et le nom du warehouse sur les trois onglets.

**Why this priority** : sans elle le front n'a rien à afficher.
**Independent Test** : tests de routes et de services, puis appel HTTP des endpoints sur
le dev contre la donnée réelle.

**Acceptance Scenarios**

1. **Given** `window_days = 7`, **When** j'appelle `/warehouses/overview|cost|query-performance`,
   **Then** la réponse porte `window_days`, `from_date` (= `window_start`) et `to_date`
   (= `as_of_date`) lus dans le gold, et une seule ligne par warehouse.
2. **Given** une valeur de `window_days` hors de {1, 7, 30, 90}, **When** j'appelle un de
   ces endpoints, **Then** la requête est rejetée en 422 plutôt que silencieusement
   ramenée à une autre fenêtre (même `IntEnum` que `ClusterWindowDays`).
3. **Given** un warehouse sans prédécesseur sur la fenêtre précédente, **When** je liste
   les coûts, **Then** `cost_usd_prev_window` est `null` et non `0`.
4. **Given** l'onglet Performance des requêtes, **When** je le liste, **Then** chaque
   ligne porte `warehouse_name` — plus jamais `null` en dur côté front.
5. **Given** l'onglet Requêtes lentes, **When** la feature est livrée, **Then** son
   contrat de réponse est inchangé (il lit `warehouse_slow_queries`, hors périmètre des
   fenêtres).

### User Story 3 — Page SQL Warehouses par plage, nom et ordre alignés (Priority: P2)

Story **Frontend** (T003). En tant qu'utilisateur FinOps, je veux choisir une plage sur
la page SQL Warehouses comme sur la page Cluster, y lire des noms de warehouse plutôt que
des identifiants, et retrouver l'ordre de colonnes des clusters.

**Independent Test** : vitest + fixtures MSW sur `ComputeSqlWarehouses.tsx`.

**Acceptance Scenarios**

1. **Given** la page SQL Warehouses, **When** elle s'ouvre, **Then** un sélecteur propose
   `Daily`, `Last 7d`, `Last 30d`, `Last 90d` et la période couverte est affichée
   `from_date → to_date`, avec le même composant et la même présentation que la page
   Cluster.
2. **Given** une plage sélectionnée, **When** je change d'onglet, **Then** la plage est
   conservée.
3. **Given** l'onglet Vue d'ensemble, **When** il s'affiche, **Then** la première colonne
   est **Workspace** et la seconde **Warehouse**.
4. **Given** les trois onglets Vue d'ensemble / Coût / Performance, **When** ils
   s'affichent, **Then** la colonne Warehouse montre le **nom** en principal et l'id en
   secondaire monospace — y compris sur Performance, où l'id était seul.
5. **Given** un warehouse sans nom en gold, **When** il s'affiche, **Then** l'id sert de
   libellé de repli (comportement actuel de `WarehouseCell`, conservé).
6. **Given** l'onglet Coût, **When** il s'affiche, **Then** la colonne de variation est
   intitulée « Δ vs prev window » et non « Δ vs prev day ».

### User Story 4 — Valeurs distinctes et filtres par colonne côté serveur (Priority: P2)

Story **Backend** (T004). En tant que tableau compute, je veux pouvoir filtrer sur
n'importe quelle colonne filtrable et obtenir la liste des valeurs possibles sur **tout**
le périmètre, pas sur la page affichée.

**Independent Test** : tests de services et de routes, dont un test qui vérifie qu'un
filtre écarte des lignes situées **au-delà** de la première page.

**Acceptance Scenarios**

1. **Given** une colonne énumérable (workspace, taille, type de cluster, statut
   d'utilisation, sévérité), **When** je demande ses valeurs, **Then** je reçois les
   valeurs distinctes de tout le périmètre autorisé, avec leur nombre de lignes, triées
   par fréquence décroissante.
2. **Given** une colonne à forte cardinalité (nom de warehouse, nom de cluster,
   propriétaire), **When** je demande ses valeurs avec un terme de recherche, **Then** je
   reçois les correspondances plafonnées à une limite bornée — jamais 1 824 valeurs d'un
   coup.
3. **Given** un filtre sur une colonne, **When** je liste la première page, **Then**
   `total` reflète le nombre de lignes **filtrées** et non le total non filtré, et la
   pagination est cohérente avec lui.
4. **Given** un nom de colonne inconnu, **When** je l'envoie en paramètre, **Then** il est
   rejeté et n'atteint jamais le SQL en texte libre (allowlist, comme
   `_OVERVIEW_SORT_COLUMNS`).
5. **Given** plusieurs filtres de colonnes actifs, **When** je liste, **Then** ils se
   combinent en `AND` et se combinent aussi avec la recherche libre existante et les
   filtres de scope.

### User Story 5 — Largeur de colonne fixe et redimensionnable (Priority: P2)

Story **Frontend** (T005). En tant qu'utilisateur, je veux que les colonnes aient une
largeur stable d'un chargement à l'autre, et pouvoir l'élargir ou la réduire moi-même.

**Independent Test** : vitest sur `ComputeDataTable` (largeur appliquée, glissement de la
poignée, persistance, réinitialisation) sur les 5 pages consommatrices.

**Acceptance Scenarios**

1. **Given** un tableau compute, **When** il s'affiche, **Then** chaque colonne a une
   largeur fixe définie par sa déclaration, et la largeur ne change plus quand le contenu
   d'une page diffère de celui de la précédente.
2. **Given** la bordure droite d'un en-tête, **When** je la fais glisser, **Then** la
   colonne suit le curseur, se borne à un minimum et un maximum, et les autres colonnes
   ne se déplacent pas de façon imprévisible.
3. **Given** une largeur ajustée, **When** je recharge la page, **Then** elle est
   conservée ; **When** je réinitialise, **Then** toutes les colonnes reprennent leur
   largeur déclarée.
4. **Given** la poignée de redimensionnement, **When** je clique dessus, **Then** le tri
   de la colonne **n'est pas** déclenché — la poignée et le bouton de tri ne se marchent
   pas dessus.
5. **Given** un utilisateur au clavier, **When** la poignée a le focus, **Then** les
   flèches gauche/droite ajustent la largeur par pas, avec un rôle et un libellé
   accessibles (`separator` orienté verticalement).

### User Story 6 — Filtre par colonne en combo liste + recherche (Priority: P2)

Story **Frontend** (T006). En tant qu'utilisateur, je veux filtrer chaque colonne depuis
son en-tête, avec une liste des valeurs et une recherche dedans.

**Independent Test** : vitest sur `ComputeDataTable` et sur les 5 pages, avec fixtures MSW
pour les valeurs distinctes.

**Acceptance Scenarios**

1. **Given** une colonne filtrable, **When** j'ouvre son entonnoir d'en-tête, **Then** une
   combo s'affiche avec un champ de recherche et la liste des valeurs du **périmètre
   entier**, chacune avec son nombre de lignes.
2. **Given** une valeur sélectionnée, **When** le tableau se recharge, **Then** le filtre
   est appliqué côté serveur, la pagination repart à la page 1, et l'en-tête indique
   visiblement qu'un filtre est actif.
3. **Given** plusieurs colonnes filtrées, **When** je les combine, **Then** elles se
   cumulent, et un contrôle unique permet de les effacer toutes.
4. **Given** une colonne numérique (coût, latence, requêtes), **When** j'ouvre son filtre,
   **Then** la combo propose des seuils prédéfinis plutôt qu'une liste de valeurs —
   lister 3 000 montants distincts n'a pas de sens.
5. **Given** un filtre trop étroit qui ne renvoie aucune ligne, **When** le tableau se
   recharge, **Then** il reste monté avec son en-tête, pour que l'utilisateur puisse
   atteindre le filtre et l'élargir.
6. **Given** les contrôles de barre d'outils existants (recherche libre, `<select>` de
   taille, chips), **When** la feature est livrée, **Then** ils continuent de fonctionner
   et restent cohérents avec les filtres de colonne — un même critère n'est pas piloté
   par deux contrôles qui se contredisent.

## Acceptance Criteria

1. **Given** la page SQL Warehouses, **When** je sélectionne les 4 plages successivement,
   **Then** chaque onglet affiche ses indicateurs sur la fenêtre demandée avec la période
   couverte, et le nom du warehouse partout.
2. **Given** les 5 pages pilotées par `ComputeDataTable`, **When** elles s'affichent,
   **Then** toutes leurs colonnes ont une largeur fixe redimensionnable et persistée, et
   leurs colonnes filtrables offrent une combo liste + recherche appliquée côté serveur.
3. **Given** un filtre de colonne, **When** il est actif, **Then** il porte sur tout le
   périmètre — démontré par un cas où la ligne filtrée est au-delà de la première page.
4. **Given** l'onglet Requêtes lentes et la page Cluster, **When** la feature est livrée,
   **Then** aucune régression de leur comportement existant.
5. Gates des trois packages verts (lint → types → tests → build).

## Out of scope (cet Epic)

- **Les 7 pages à markup `<TableHead>` manuel** (`Admin`, `Users`, `CollectionStatus`,
  `MonitoringReports`, `ProjectDetail`, `UnityCatalogExplorer`,
  `AdminEmbeddedDashboardsTab`) : arbitrage utilisateur. Elles gardent leurs largeurs
  automatiques et leurs filtres actuels.
- **Les pages à accordéons** (`Databricks`, `Databases`, `DataFactory`, `Costs`) : pas de
  colonne, rien à redimensionner.
- **Réordonnancement et masquage de colonnes** par l'utilisateur : non demandé.
- **Filtres multi-valeurs** (`IN (…)`) : la combo est mono-sélection par colonne dans
  cette itération, comme le composant existant.
- **`full_refresh` des tables `*_daily`** pour nommer l'historique : proposé en option
  dans T001, non requis par les critères d'acceptation.
- **`gold_dbx_compute_warehouse_utilization_rolling` côté API** : la table gagne
  `warehouse_name` (T001) mais aucun endpoint ne la lit aujourd'hui, et aucun indicateur
  demandé ne s'y rattache.
- Export CSV/Excel des tableaux filtrés.

## Work Breakdown (preview)

| ID | Domain | Summary | Ticket |
|----|--------|---------|--------|
| T001 | DataEng | `warehouse_name` sur `warehouse_utilization_daily`/`_rolling` et `warehouse_query_performance_daily`/`_rolling`, depuis `curated_dbx_compute_warehouses` | ✅ |
| T002 | Backend | Services et routes warehouse sur les `*_rolling` : `window_days`, `from_date`/`to_date`, `warehouse_name` sur les 3 onglets, `_normalize_prev_cost` | ✅ |
| T003 | Frontend | Page SQL Warehouses : sélecteur de plage + période couverte, ordre Workspace → Warehouse, nom du warehouse partout | ✅ |
| T004 | Backend | Valeurs distinctes par colonne et paramètres de filtre par colonne pour les 11 tableaux paginés serveur (88 colonnes filtrables sur 109) | ✅ |
| T005 | Frontend | `ComputeDataTable` : largeur fixe déclarée, poignée de redimensionnement, persistance, réinitialisation | ✅ |
| T006 | Frontend | `ComputeDataTable` : filtre d'en-tête en combo liste + recherche, branché sur T004 | ✅ |

## Requirements & Success Criteria

**Exigences fonctionnelles**

- **FR-001** : la page SQL Warehouses propose exactement quatre plages statiques — 1, 7,
  30 et 90 jours — et aucune saisie de dates libre.
- **FR-002** : la période réellement couverte est affichée (`from_date` → `to_date`) et
  provient de la donnée (`window_start` / `as_of_date`), pas d'un calcul depuis `today`.
- **FR-003** : les vues de liste warehouse rendent une ligne par warehouse, celle de la
  fenêtre demandée au dernier `as_of_date` disponible.
- **FR-004** : la colonne Warehouse affiche le nom en libellé principal sur les trois
  onglets, l'id en repli.
- **FR-005** : l'ordre des colonnes de la vue d'ensemble warehouse est Workspace puis
  Warehouse.
- **FR-006** : chacune des 109 colonnes des 11 tableaux `ComputeDataTable` a une largeur fixe
  déclarée, redimensionnable à la souris et au clavier, bornée, persistée, et
  réinitialisable.
- **FR-007** : chaque colonne filtrable porte un filtre d'en-tête en combo avec liste et
  recherche ; le filtrage s'applique côté serveur sur tout le périmètre.
- **FR-008** : la liste de valeurs d'une combo provient d'une source calculée sur tout le
  périmètre autorisé, bornée en taille et interrogeable par terme de recherche.
- **FR-009** : un nom de colonne ou une valeur de fenêtre non reconnus sont rejetés, pas
  silencieusement remplacés.

**Critères de succès mesurables**

- **SC-001** : `warehouse_name` renseigné sur > 95 % des lignes des 4 tables `*_rolling`
  concernées, contre ~20 % par une jointure sur la table de coût.
- **SC-002** : les 4 fenêtres répondent sur les 3 onglets warehouse, avec la période
  couverte lue en gold.
- **SC-003** : un filtre de colonne sur une valeur portée par une seule ligne, située
  au-delà de la première page, ramène cette ligne — vérifié sur la donnée de dev.
- **SC-004** : une largeur de colonne ajustée survit à un rechargement de page.
- **SC-005** : aucune régression sur les 5 pages (`vitest`, `tsc`, `build` verts) ni sur
  les gates backend et pipeline.
