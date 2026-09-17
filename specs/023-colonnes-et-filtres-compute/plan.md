# Implementation Plan: Fenêtres glissantes SQL Warehouses, colonnes redimensionnables et filtres par colonne

**Branch**: `dataeng/023-…` → `backend/023-…` → `frontend/023-…` | **Date**: 2026-09-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/023-colonnes-et-filtres-compute/spec.md`

**Réf. socle réutilisé** :
- [`pipelines/gold_dbx_compute/warehouse_cost_daily.py`](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/warehouse_cost_daily.py) — **modèle de référence** pour `warehouse_name` : CTE `warehouses_as_of` joignant `curated_dbx_compute_warehouses` sur `change_time < period_start + INTERVAL 1 DAY` + `QUALIFY ROW_NUMBER()`. *La borne était `change_time <= period_start` quand ce plan a été écrit ; alignée sur la convention cluster/job le 2026-09-07 parce qu'elle rendait `NULL` tout warehouse créé dans la journée et faisait échouer SC-001 — arbitrage en [stories/T001](./stories/T001-warehouse-name-en-gold.md).*
- [`pipelines/gold_dbx_compute/warehouse_cost_rolling.py`](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/warehouse_cost_rolling.py) — CTE `latest_attrs` qui reporte le dernier état connu d'un attribut sur les 4 fenêtres.
- [`app/api/services/compute_metrics_clusters.py`](../../packages/dcm-backend/app/api/services/compute_metrics_clusters.py) — **modèle de référence** pour la fenêtre glissante côté API : `ClusterWindowDays(IntEnum)`, `_window_where`, `_window_block`, `_window_period`, `_bounds_sql`, `_normalize_prev_cost`.
- [`app/api/services/compute_metrics_common.py`](../../packages/dcm-backend/app/api/services/compute_metrics_common.py) — `_scope_where`, `_clamp_page`, `_row_to_dict`, `_json_safe`, `_empty_page`.
- [`src/components/domain/compute/compute-data-table.tsx`](../../packages/dcm-frontend/src/components/domain/compute/compute-data-table.tsx) — le seul tableau piloté par colonnes ; point d'application unique de T005 et T006.
- [`src/components/ui/combobox.tsx`](../../packages/dcm-frontend/src/components/ui/combobox.tsx) — **modèle d'interaction** (recherche, `ArrowUp`/`ArrowDown`/`Enter`/`Escape`, `role="combobox"` + `listbox`, clic extérieur), à ne **pas** réutiliser tel quel : palette `slate`/`blue` codée en dur, `w-full`, `py-3`.

## Summary

Six livrables, en deux fils indépendants.

**Fil A — warehouses (T001 → T002 → T003), séquentiel strict.**

1. **T001 DataEng** — ajouter `warehouse_name` aux 4 tables
   `gold_dbx_compute_warehouse_utilization_daily`/`_rolling` et
   `..._query_performance_daily`/`_rolling`. Sur `utilization_daily` c'est une colonne de
   plus dans la CTE `warehouses_as_of` qui joint **déjà** `curated_dbx_compute_warehouses`
   (lignes 439-457) — aucune source nouvelle. Sur `query_performance_daily`, la table ne
   lit aujourd'hui que `curated_dbx_query_history` : il faut un paramètre
   `warehouses_table` et une CTE `warehouses_as_of` copiée sur celle de `cost_daily`. Sur
   les deux `*_rolling`, la colonne passe par `latest_attrs`, comme `auto_stop_minutes` et
   `top_slow_statement_id`. Migration : `MERGE WITH SCHEMA EVOLUTION` suffit, aucun `DROP`
   — les `*_rolling` sont des snapshots complets (`watermark_column = None`) donc nommées
   à 100 % dès le run suivant.

   Ce que T002 **exige** est le seul couple `query_performance_daily`/`_rolling` :
   `rg "warehouse_utilization" packages/dcm-backend/app/` ne renvoie rien, aucun endpoint
   ne lit les tables d'utilisation. Elles sont incluses quand même parce que le coût est
   de 6 lignes (la jointure curated y est déjà présente) et que les 4 familles de tables
   gold warehouse portent alors le même attribut identifiant — mais elles ne conditionnent
   aucun critère d'acceptation de T002 ni de T003, et pourraient être retirées de T001
   sans rien casser d'autre que SC-001.

2. **T002 Backend** — brancher les 3 vues de liste warehouse sur
   `warehouse_cost_rolling` / `warehouse_query_performance_rolling` avec
   `window_days ∈ {1, 7, 30, 90}`, exposer `window_days` / `from_date` / `to_date` lus
   dans `window_start` / `as_of_date`, ajouter `warehouse_name` à la vue Performance, et
   appliquer `_normalize_prev_cost` — `warehouse_cost_rolling.py:115` agrège la fenêtre
   précédente en `SUM(CASE … ELSE 0 END)`, donc `cost_usd_prev_window` n'est jamais `NULL`
   et « pas de prédécesseur » est indiscernable de « a coûté zéro » (défaut identique à
   celui trouvé en vérifiant 022 T002). Les mutualisables de `compute_metrics_clusters.py`
   (`_window_where`, `_window_block`, `_window_period`, `_bounds_sql`,
   `_normalize_prev_cost`, `ClusterWindowDays` → `RollingWindowDays`) **descendent** dans
   `compute_metrics_common.py` plutôt qu'être dupliqués. `fetch_warehouse_slow_queries` et
   `fetch_warehouse_cost_trend` **ne sont pas touchées** (l'une lit
   `warehouse_slow_queries`, l'autre est une série temporelle sur la quotidienne).

3. **T003 Frontend** — sur `ComputeSqlWarehouses.tsx` : sélecteur de 4 plages statiques
   avec `from_date → to_date`, ordre Workspace puis Warehouse dans la vue d'ensemble,
   `WarehouseCell` alimenté par `warehouse_name` sur les 3 onglets (le `name={null}` en dur
   de la ligne 485 disparaît), et « Δ vs prev day » devient « Δ vs prev window ».

**Fil B — colonnes (T005 → T004 → T006).**

4. **T005 Frontend** — `ComputeDataTable` : `width` (px) déclarée par colonne, rendu en
   `table-layout: fixed` + `<colgroup>`, poignée de redimensionnement sur le bord droit de
   chaque en-tête (souris + clavier), bornes `minWidth`/`maxWidth`, persistance
   `localStorage` par `tableId` (nouveau prop **requis** : sans lui deux tableaux
   partageraient une clé), et remise à zéro.

5. **T004 Backend** — un mécanisme unique de filtre par colonne : une allowlist par vue
   qui associe un nom de colonne à son expression SQL et à son *kind*
   (`enum` / `text` / `numeric`), un paramètre répétable `column_filter=<colonne>:<valeur>`,
   et un endpoint de valeurs distinctes calculées sur **tout** le périmètre autorisé. Les
   paramètres dédiés existants (`search`, `warehouse_size`, `min_failure_rate_pct`,
   `utilization_status`, `min_latency_p95_ms`, `has_spill`) sont conservés et **traduits
   dans la même liste de filtres interne** : un seul point de vérité côté service, contrat
   d'API préservé, et la combo d'en-tête ne peut pas contredire le contrôle de barre
   d'outils qui pilote le même critère.

6. **T006 Frontend** — `ComputeDataTable` : entonnoir de filtre dans l'en-tête ouvrant une
   combo compacte (liste + recherche), alimentée par l'endpoint de T004, avec état de
   filtre remonté à la page (qui possède déjà les paramètres de requête), retour à la
   page 1 à chaque changement, et un « effacer tous les filtres » unique.

**T005 avant T006** : les deux modifient la même cellule d'en-tête. Poser d'abord la
géométrie (`colgroup`, poignée) puis y greffer l'entonnoir évite de réécrire deux fois le
même bloc et de faire se marcher dessus la poignée, le bouton de tri et l'entonnoir.

## Technical Context

**Language/Version**: Python 3.12 (pipeline + backend), TypeScript 5 / React 18 (frontend).

**Primary Dependencies**: aucune nouvelle dans les trois packages. Pipeline : `pyspark` +
`pipelines/common/`. Backend : FastAPI + `DatabricksWarehousePool`. Frontend : React Query
+ composants `compute-*` ; la combo compacte et la poignée de redimensionnement sont
écrites à la main (aucune librairie de table ou de dropdown introduite — le repo n'en a
aucune et `combobox.tsx` prouve que le patron est déjà tenu à la main ici).

**Storage**: Unity Catalog `it.ba_data_connect_monitoring__<env>` (dev `__d`, prod `__p`).
Tables **écrites** : `gold_dbx_compute_warehouse_utilization_daily`, `..._utilization_rolling`,
`..._query_performance_daily`, `..._query_performance_rolling`. Tables **lues** par le
backend après T002 : `..._warehouse_cost_rolling`, `..._warehouse_query_performance_rolling`,
`..._warehouse_cost_daily` (tendance de coût uniquement), `..._recommendations`,
`warehouse_slow_queries`, `dim_dbx_workspace`.

**Testing**: pipeline → `pytest` avec `FakeSpark` (assertions sur le SQL généré, aucune
JVM). Backend → `pytest` (`tests/test_compute_metrics_services.py`,
`tests/test_compute_metrics_routes.py`). Frontend → `vitest` + fixtures MSW
(`src/test/fixtures/compute-warehouses.ts`, `compute-clusters.ts`).

**Target Platform**: Databricks Jobs (wheel task, `job_dcm_gold_dbx_compute.yml`) pour
T001 ; API FastAPI et SPA React pour le reste.

**Project Type**: multi-package — 3 branches filles, une par package.

**Performance Goals**: les vues de liste warehouse passent d'une agrégation à la volée sur
la quotidienne à une lecture d'une ligne par warehouse dans `*_rolling`. L'endpoint de
valeurs distinctes est **borné** : `LIMIT` explicite et `q` obligatoire au-delà d'un seuil
de cardinalité, pour ne jamais renvoyer les 1 824 noms de warehouse d'un coup.

**Constraints**:
- `window_days` strictement dans `{1, 7, 30, 90}` : une valeur hors liste est rejetée
  (422), jamais rabattue silencieusement — `IntEnum`, pas `Query(enum=…)` (le second ne
  décore que le schéma OpenAPI, cf. le docstring de `ClusterWindowDays`).
- `cost_usd_prev_window` ≤ 0 se rend `null` : « pas de comparaison », pas « c'était
  gratuit ».
- La jointure `curated_dbx_compute_warehouses` **enrichit** : `LEFT JOIN`, jamais `INNER`
  — un warehouse absent du curated garde sa ligne avec `warehouse_name = NULL`.
- **Un nom de colonne n'atteint jamais le SQL en texte libre** : allowlist par vue, sur
  le modèle de `_OVERVIEW_SORT_COLUMNS`. Les valeurs passent en paramètre lié `?`.
- Un filtre de colonne s'applique au **périmètre entier**, jamais à la page affichée :
  c'est la raison d'être de T004 (cf. Complexity Tracking).
- `tableId` est **requis** sur `ComputeDataTable` : deux tableaux se partageant une clé de
  persistance échangeraient leurs largeurs.
- La poignée de redimensionnement `stopPropagation` sur `pointerdown` : sinon un
  glissement déclenche le tri de la colonne.
- Onglet Requêtes lentes et page Cluster strictement inchangés dans leur comportement.

**Scale/Scope**: T001 = 4 builders + `entrypoint.py` + `specs.py` (commentaires de
colonnes, `source_tables`) + 2 fichiers de tests. T002 = 2 services (`_warehouses`
réécrit sur les rolling, `_common` reçoit les helpers descendus de `_clusters`), 1 module
de routes, 2 fichiers de tests. T003 = 1 page, 1 hook, 1 type. T004 = 1 nouveau module de
filtres, 3 services, 1 module de routes, 2 fichiers de tests. T005 + T006 = 1 composant
`compute-data-table.tsx` (~+300 lignes), 2 nouveaux composants (poignée, combo de
colonne), 1 hook de persistance, les 11 jeux de colonnes des 5
pages, 3 fichiers de
tests.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principe | Statut | Justification |
|---|---|---|
| P1 Test-First & Code Quality (NON-NEGOTIABLE) | ✅ PASS | Tests avant code dans les 6 tasks : SQL généré (pipeline), services + routes (backend), rendu + interactions clavier et souris (frontend). Gates lint/types/tests par package. |
| P2 Simplicité, Explicitness & Versioning | ✅ PASS | Aucune dépendance nouvelle. Un **seul** mécanisme de filtre côté service, les paramètres existants n'étant que des alias qui s'y traduisent. Les helpers de fenêtre sont **descendus** dans `_common` plutôt que dupliqués entre clusters et warehouses. |
| P3 Self-Documenting Code | ✅ PASS | `warehouse_name` reçoit un `column_comment` avec sa règle de résolution. Les commentaires portent le *pourquoi* : pourquoi la jointure sur la table de coût a été rejetée (mesure ~80 %), pourquoi `stopPropagation` sur la poignée, pourquoi `tableId` est requis. |
| P4 Fail Fast, Fail Loud | ⚠️ NOTE | `window_days` et un nom de colonne invalides → 422 immédiat. Mais les `fetch_*` conservent leur `try/except` + soft-fail : comportement **pré-existant** et uniforme sur toute la page Compute, non introduit ici. |
| P5 Architecture explicite & modularité | ✅ PASS | Frontière médaillon respectée : `warehouse_name` est résolu en gold, le backend continue de ne lire que du gold et des dimensions (`rg "curated_dbx" app/api/services/` → rien, et cela reste vrai après). |
| P6 Idempotency by Design | ✅ PASS | Les 4 tables gardent leurs `merge_keys` ; `warehouse_name` est déterministe pour un état source donné. Les `*_rolling` sont des snapshots complets, rejouables par construction. |
| P7/P8 Secrets Management (NON-NEGOTIABLE) | ✅ PASS | Aucun secret touché. Déploiement pipeline via bundle et OAuth (`databricks auth login`) — **jamais** de PAT. Les largeurs de colonne persistent dans `localStorage` : préférence d'affichage, aucune donnée métier ni identifiant. |
| P9 No Fake Data in Production (NON-NEGOTIABLE) | ✅ PASS | `warehouse_name` vient du curated réel ; un warehouse inconnu se rend `NULL` puis retombe sur son id à l'affichage, jamais sur un nom inventé. Les seuils numériques des combos sont des bornes de filtre déclarées, pas des données. Fixtures cantonnées à `src/test/`. |
| P10 Observability & Traceability | ⚠️ NOTE | `logging` stdlib (pas de JSON structuré) — écart pré-existant et uniforme, non introduit ici. |
| P11 Naming Conventions | ✅ PASS | `warehouse_name` reprend à l'identique la colonne des tables de coût. `RollingWindowDays` généralise `ClusterWindowDays` sans le renommer à l'aveugle (alias conservé le temps de la migration interne). |
| P12 Medallion — Aggregations on Gold Only | ✅ PASS | Cœur du fil A : les fenêtres 1/7/30/90 sont déjà agrégées en gold, l'API les lit au lieu de les recalculer. L'endpoint de valeurs distinctes est un `GROUP BY` de **support d'IHM**, pas un indicateur métier. |
| P13 Immutable Raw Layer | N/A | Aucune couche Raw dans ce flux. |
| P14 Schema Versioning | N/A | Tables gold hors `MetricPayload`. |
| P15 API Contract Stability | ⚠️ NOTE | `window_days`, `from_date`, `to_date`, `warehouse_name` et `column_filter` sont **ajoutés** ; tous les paramètres existants restent acceptés. Deux ruptures assumées et tracées : les vues de liste warehouse renvoient désormais la fenêtre du gold et non la période demandée (inhérent à la demande « filtre par période day/7d/30d/90d »), et `cost_usd_prev_day` de la vue Coût devient `cost_usd_prev_window`. |
| P16 Frontend Quality | ✅ PASS | Composants typés, `ComputeDataTable` reste le point d'application unique, états vides existants réutilisés, tests vitest. Accessibilité explicitement couverte : `role="separator"` + `aria-orientation` pour la poignée, `role="combobox"`/`listbox` pour le filtre, navigation clavier des deux. |

**Verdict** : PASS. Trois `⚠️ NOTE`, toutes sur des écarts pré-existants ou explicitement
tracés, aucune sur un principe NON-NEGOTIABLE.

## Project Structure

### Documentation

```
specs/023-colonnes-et-filtres-compute/
├── spec.md
├── plan.md              ← ce fichier
├── research.md          ← décisions de conception (R1…R8)
├── data-model.md        ← colonne gold ajoutée + contrats de réponse
├── quickstart.md        ← déploiement dev + contrôles d'acceptation
├── merge-strategy.md    ← ordre de merge des 3 branches filles
├── contracts/           ← formes de réponse des endpoints touchés
├── intake.json
├── domain-scope.json
├── tasks.md
└── stories/             ← T001…T006
```

### Code — fichiers touchés

**T001 — `packages/dcm-databricks-pipeline`**

```
pipelines/gold_dbx_compute/
├── warehouse_utilization_daily.py            (M) +warehouse_name dans warehouses_as_of → enriched → SELECT
├── warehouse_utilization_rolling.py          (M) +warehouse_name dans daily → latest_attrs → SELECT
├── warehouse_query_performance_daily.py      (M) +param warehouses_table, +CTE warehouses_as_of
├── warehouse_query_performance_rolling.py    (M) +warehouse_name dans daily → latest_attrs → SELECT
├── entrypoint.py                             (M) passe warehouses_table à query_performance_daily
└── specs.py                                  (M) column_comments ×4, source_tables de QUERY_PERFORMANCE_DAILY
tests/gold_dbx_compute/
├── test_warehouse_utilization.py             (M)
├── test_warehouse_query_performance.py       (M)
└── test_entrypoint.py                        (M)
```

**T002 + T004 — `packages/dcm-backend`**

```
app/api/services/
├── compute_metrics_common.py     (M) helpers de fenêtre descendus de _clusters + RollingWindowDays
├── compute_metrics_warehouses.py (M) 3 fetch_* repointés sur *_rolling, window_days, warehouse_name
├── compute_metrics_clusters.py   (M) importe les helpers descendus (aucun changement de comportement)
├── compute_metrics_filters.py    (N) allowlist par vue, build_column_filters, fetch_filter_options
└── lakeflow_jobs.py              (M) branche les filtres de colonne
app/api/routes/
└── compute_metrics.py            (M) window_days sur 3 routes warehouse, column_filter, /filter-options
tests/
├── test_compute_metrics_services.py (M)
├── test_compute_metrics_routes.py   (M)
└── test_compute_metrics_filters.py  (N)
```

**T003 + T005 + T006 — `packages/dcm-frontend`**

```
src/components/domain/compute/
├── compute-data-table.tsx        (M) colgroup, largeurs, poignée, entonnoir, tableId requis
├── compute-column-resizer.tsx    (N) poignée souris + clavier
├── compute-column-filter.tsx     (N) combo compacte liste + recherche, tokens de design
└── recommendations-table.tsx     (M) tableId + largeurs
src/hooks/
├── useColumnWidths.ts            (N) lecture/écriture localStorage, bornes, reset
├── useComputeWarehousesQueries.ts(M) window_days, column_filter
├── useComputeClustersQueries.ts  (M) column_filter
├── useLakeflowQueries.ts         (M) column_filter
└── useColumnFilterOptions.ts     (N) valeurs distinctes, debounce de recherche
src/pages/
├── ComputeSqlWarehouses.tsx      (M) plages, ordre Workspace→Warehouse, nom, largeurs, filtres
├── ComputeClusters.tsx           (M) largeurs, filtres
├── LakeflowJobs.tsx              (M) largeurs, filtres
└── LakeflowJobDetail.tsx         (M) largeurs, filtres
src/types/api.ts                  (M) window/window_days warehouse, warehouse_name, options de filtre
src/test/fixtures/                (M) compute-warehouses.ts, + fixture d'options de filtre
```

## Phase 0 — Research

Décisions consignées dans [research.md](./research.md) :

| # | Question | Décision |
|---|---|---|
| R1 | D'où vient `warehouse_name` sur utilisation et performance ? | Du curated, en gold. La jointure sur la table de coût gold est **mesurée** à ~80 % de lignes anonymes — rejetée. |
| R2 | Faut-il un `full_refresh` pour nommer l'historique ? | Non. Les `*_rolling` sont des snapshots complets, nommées à 100 % au run suivant ; les `*_daily` au-delà de 10 jours restent `NULL` mais aucun consommateur de cette feature ne les lit. |
| R3 | Repointer les vues warehouse sur `*_rolling` ou ajouter `window_days` sur les `*_daily` ? | Repointer, comme 022 pour les clusters. Les 4 fenêtres sont déjà peuplées et le comportement actuel (dernier jour de la plage) n'est pas une agrégation de plage. |
| R4 | Filtres de colonne côté client ou serveur ? | Serveur. Les 11 tableaux paginent tous côté serveur ; un filtre client ne verrait que 25 à 50 lignes. |
| R5 | Un paramètre par colonne ou un paramètre répétable ? | Répétable `column_filter=<colonne>:<valeur>`, allowlisté. Un paramètre par colonne ferait exploser la signature des routes. |
| R6 | Que devient le `<select>` de taille de la barre d'outils ? | Conservé, et traduit dans la **même** liste de filtres interne que la combo de colonne — un seul point de vérité, aucune contradiction possible. |
| R7 | Comment lister les valeurs d'une colonne à forte cardinalité ? | *Kind* par colonne : `enum` (liste complète + comptes), `text` (recherche obligatoire, `LIMIT` borné), `numeric` (seuils déclarés côté serveur). |
| R8 | `table-layout: fixed` casse-t-il les tableaux existants ? | À vérifier au montage de T005 : c'est ce qui rend les largeurs effectives, mais les cellules cessent de s'élargir sur leur contenu. Bornes + `truncate` + `title` sur les cellules longues. |

## Phase 1 — Design

- [data-model.md](./data-model.md) — la colonne gold ajoutée et sa règle de résolution,
  les champs de réponse ajoutés ou renommés.
- [contracts/](./contracts/) — formes de réponse des 3 routes warehouse repointées et de
  la nouvelle route de valeurs distinctes.
- [quickstart.md](./quickstart.md) — déploiement dev du pipeline, contrôles d'acceptation
  SQL, puis vérification HTTP des endpoints.

### Ordre d'exécution imposé

```
Fil A : T001 (gold) ──► déploiement dev + vérification ──► T002 (API) ──► T003 (UI)
Fil B :                                    T005 (largeurs) ──► T004 (API filtres) ──► T006 (UI filtres)
```

T002 lit la colonne que T001 crée ; T003 consomme les champs que T002 expose. T006 lit
l'endpoint que T004 expose, et se greffe sur l'en-tête que T005 restructure. Les deux
fils ne partagent qu'un fichier, `compute-data-table.tsx`, et seulement à partir de T005 :
T003 ne le touche pas (il ne modifie que les déclarations de colonnes de sa page).

## Complexity Tracking

| Écart | Pourquoi c'est nécessaire | Alternative rejetée |
|---|---|---|
| Les vues de liste warehouse ignorent `period_start`/`period_end` | La demande porte sur 4 plages statiques ; les tables `*_rolling` sont des snapshots « as of » `as_of_date`, une période libre n'a aucun effet dessus | Garder la période libre **et** ajouter les plages : deux sélecteurs de temps contradictoires sur un même écran, et la période libre ne filtre déjà rien d'utile aujourd'hui (elle ne déplace que l'ancre du « dernier jour ») |
| `cost_usd_prev_day` → `cost_usd_prev_window` sur la vue Coût | Une fenêtre de 30 jours n'a pas de « veille » : la comparaison pertinente est la fenêtre précédente de même longueur, déjà calculée en gold | Conserver `cost_usd_prev_day` en le lisant sur la quotidienne : mélangerait deux grains dans une même ligne |
| Un nouveau module `compute_metrics_filters.py` | Les allowlists de colonnes filtrables concernent 3 services (clusters, warehouses, lakeflow) : les laisser dans chacun les dupliquerait à trois exemplaires | Étendre `compute_metrics_common.py` : il est déjà le point de passage de tous les payloads compute, y empiler les tables de colonnes le rendrait illisible |
| `tableId` devient un prop **requis** de `ComputeDataTable` | La clé de persistance des largeurs doit être unique par tableau ; une valeur par défaut ferait silencieusement partager les largeurs entre la vue d'ensemble et l'onglet Coût | Dériver la clé de la route ou de la liste des ids de colonnes : casse dès qu'on ajoute une colonne ou qu'un onglet change d'URL |
| `table-layout: fixed` | Sans lui une largeur déclarée n'est qu'une suggestion que le contenu écrase — la demande « taille fixe » ne serait pas tenue | Largeur en `min-width` seulement : le tableau redeviendrait dépendant du contenu de la page affichée, donc instable d'une page à l'autre |

## Progress Tracking

- [x] Constitution Check initial — PASS
- [x] Phase 0 — Research (R1…R8, R1/R4 tranchées par la mesure)
- [x] Phase 1 — Design (data-model, contracts, quickstart)
- [ ] Constitution Check après design
- [ ] Tasks générées
- [ ] T001 implémentée + vérifiée en dev
- [ ] T002 implémentée + vérifiée en dev
- [ ] T003 implémentée
- [ ] T005 implémentée
- [ ] T004 implémentée + vérifiée en dev
- [ ] T006 implémentée
