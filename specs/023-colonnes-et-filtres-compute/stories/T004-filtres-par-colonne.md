# T004 — Filtres par colonne et valeurs distinctes

**Domain**: backend
**Package**: packages/dcm-backend
**Branch**: `backend/023-warehouse-windows-et-filtres`
**Jira**: not dispatched (dispatch non exécuté sur cette feature)
**Depends on**: T002 (mêmes fichiers ; T004 filtre aussi les vues repointées sur les rolling)
**Work type**: feature

## Description

Support serveur de la troisième demande. Les 11 tableaux du périmètre paginent **tous** côté
serveur — vérifié, `page`/`page_size` sur les 11 routes — donc un filtre appliqué dans le
composant ne verrait que 25 à 50 lignes et reproduirait le bug déjà corrigé par 022 T004
(« je ne vois que 50 clusters ou warehouses »). Le filtre part dans la requête ; les valeurs
proposées dans la combo aussi, sinon la liste déroulante ne proposerait que les valeurs de la
page courante — même faute, déplacée.

Un **mécanisme unique** : une allowlist par vue, un paramètre répétable
`column_filter=<clé>:<valeur>`, un endpoint de valeurs distinctes. Les paramètres dédiés
existants (`search`, `warehouse_size`, `min_failure_rate_pct`, `utilization_status`,
`min_latency_p95_ms`, `has_spill`, `severity`, `status`, `category`) sont **conservés** et se
normalisent vers la **même** liste de filtres interne : contrat d'API préservé (P15), un seul
point de vérité, et la combo d'en-tête ne peut pas contredire le contrôle de barre d'outils
qui pilote le même critère.

Inventaire complet : **88 colonnes filtrables sur 109**, détaillées vue par vue dans
[contracts/compute-column-filters.md](../contracts/compute-column-filters.md).

## Files to create/modify

- CREATE `packages/dcm-backend/app/api/services/compute_metrics_filters.py`
- UPDATE `packages/dcm-backend/app/api/services/compute_metrics_warehouses.py`
- UPDATE `packages/dcm-backend/app/api/services/compute_metrics_clusters.py`
- UPDATE `packages/dcm-backend/app/api/services/lakeflow_jobs.py`
- UPDATE `packages/dcm-backend/app/api/routes/compute_metrics.py`
- UPDATE `packages/dcm-backend/app/api/routes/lakeflow.py`
- CREATE `packages/dcm-backend/tests/test_compute_metrics_filters.py`
- UPDATE `packages/dcm-backend/tests/test_compute_metrics_routes.py`

### Écarts par rapport à la liste déclarée

Deux fichiers de plus, tous deux appelés par une décision prise en écrivant le code :

- UPDATE `packages/dcm-backend/app/api/services/compute_metrics_recommendations.py` — la
  onzième vue vit dans son propre module ; la liste ci-dessus l'avait oubliée.
- UPDATE `packages/dcm-backend/app/main.py` — un `@application.exception_handler(ColumnFilterError)`
  de 8 lignes. Les 11 services de liste enveloppent leur corps dans un
  `try: … except Exception: page vide` : sans ce handler, un `column_filter` **refusé** serait
  rendu comme un tableau vide, c'est-à-dire exactement le mode de défaillance que FR-009
  interdit. L'alternative — un `try` dans chacun des 13 handlers — dupliquait la même chose
  treize fois. `detail` reprend la forme que FastAPI donne déjà à une erreur de query-string,
  donc un seul chemin d'erreur côté front.

Deux écarts au contrat, dans l'allowlist :

- `clusters-overview.utilization` est **`enum`** et non `numeric`. Le contrat la décrivait sur
  `e.cpu_avg_pct >= ?` ; la colonne affichée rend un badge `utilization_status`. Filtrer sur un
  pourcentage une colonne qui montre un statut aurait donné une combo qui ne parle pas de ce
  qu'on voit — et aurait laissé le paramètre historique `utilization_status` sans jumeau, donc
  hors du « un seul point de vérité ». C'est le même choix que `clusters-efficiency.status`.
- Les `alias_param` sont posés **là où la route accepte réellement le paramètre**, pas
  uniformément : `search` n'existe que sur clusters-cost et warehouses-cost, d'où
  `warehouses-overview.warehouse` et `warehouses-query-performance.warehouse` sans alias. 21
  alias au total. Déclarer un alias sur une route qui n'a pas le paramètre aurait promis une
  synchronisation impossible à T006.

## Sub-tasks

- [x] **Tests d'abord** : clé de colonne inconnue → 422 avec la liste des clés acceptées ;
      `view` ou `column` inconnu → 422 ; même clé deux fois → 422 ; valeur vide = pas de
      filtre ; une valeur contenant `:` est préservée (découpage sur le **premier** `:`
      seulement) ; `warehouse_size=MEDIUM` et `column_filter=size:MEDIUM` produisent le même
      SQL ; les deux avec des valeurs différentes → 422 ; une tentative d'injection dans la
      clé **ou** dans la valeur ne produit aucun fragment SQL (la clé est allowlistée, la
      valeur est un paramètre lié) ; `filter-options` n'applique **aucun** `column_filter` ;
      `kind = "text"` sans `q` au-delà du seuil → `options: []` + `truncated: true`.
      — **68 tests** : 40 de service (`test_compute_metrics_filters.py`) et 28 de route
      (`TestColumnFilterRoutes`). Le 422 de clé inconnue est asserté sur les **11** routes avec
      `self._issued(mock_db) == []` : la preuve n'est pas seulement le code de retour, c'est
      qu'**aucune** requête n'est partie.
- [x] `compute_metrics_filters.py` : dataclass `ColumnFilterSpec`
      (`key`, `sql`, `kind`, `label`, `options`, `alias_param`) et un dict
      `FILTERABLE_COLUMNS: dict[str, dict[str, ColumnFilterSpec]]` indexé par vue puis par
      clé. Les 11 vues, les 88 colonnes, transcrites depuis le contrat.
      — 11 vues, **88** colonnes (43 `numeric`, 34 `enum`, 11 `text`), **21** portant un
      `alias_param`.
- [x] `parse_column_filters(view, raw: list[str], **legacy) -> list[AppliedFilter]` :
      découpage, allowlist, détection de doublon, fusion des paramètres historiques par
      `alias_param`, détection de contradiction. — appelé **avant** le `try` de chaque service :
      les 11 services renvoient une page vide sur exception, un appel à l'intérieur du `try`
      aurait transformé chaque 422 en 200 vide.
- [x] `build_column_filter_sql(filters) -> tuple[str, list[Any]]` : prédicat par `kind`
      (`enum` → `=`, `text` → `LIKE`, `numeric` → `>=` sauf `sql` explicite comme les taux de
      succès Lakeflow en `<=`). L'expression vient **toujours** de l'allowlist, la valeur
      **toujours** d'un `?`.
- [x] `fetch_filter_options(view, column, q, limit, **scope)` : `GROUP BY` sur l'expression de
      la colonne, comptes, `LIMIT` (défaut 50, plafond 200), drapeau `truncated`. Applique
      exactement les filtres de **scope** de la vue (périmètre autorisé, `cloud_provider`,
      `window_days`) et **aucun** `column_filter` — sinon poser un filtre viderait les listes
      des autres colonnes. — prouvé en dev : réponse **octet pour octet identique** avec et
      sans `column_filter` dans la query-string.
- [x] `kind = "numeric"` : `options` = les seuils **déclarés côté serveur**, sans `count`.
      L'IHM ne les invente ni ne les interpole (P9). — et **aucune requête** n'est émise pour
      une colonne numérique, asserté en test.
- [x] Brancher `column_filter` sur les 11 routes de liste et le `WHERE` des 11 requêtes.
      Remplacer les blocs `filters: list[str]` ad hoc par l'appel unique — sans changer le
      SQL produit pour les paramètres historiques, ce que les tests de régression prouvent.
- [x] Route `GET /compute/filter-options` (préfixe compute-metrics), et une route jumelle ou
      un paramètre `view` couvrant les 2 vues Lakeflow — **une seule forme de réponse** dans
      les deux cas. — route jumelle `GET /api/v1/lakeflow/filter-options` retenue plutôt qu'un
      `view` unique : les deux préfixes ne résolvent pas le même périmètre (`AllowedScope` vs
      `allowed_lz_ids`/`allowed_workspace_ids`). Même forme de réponse, testée des deux côtés,
      et chacune **refuse** les vues de l'autre.
- [x] Vérifier que la route `filter-options` est déclarée **avant** les routes à segment
      variable (`/warehouses/{warehouse_id}`) si elle partage leur préfixe : sinon FastAPI la
      capture comme un id. — déclarée avant `/clusters/overview`, et un test vérifie qu'elle
      n'est pas capturée comme un `cluster_id`/`warehouse_id`.
- [x] Gates : `pytest` (suite complète), `ruff check app tests`. — **508 passés, 1 échec
      pré-existant** (`test_connection.py`, voir T002) ; ruff **156 = référence HEAD**, delta 0.
- [x] Vérification HTTP en dev : les 9 contrôles de [quickstart.md](../quickstart.md) §5bis.
      — **9/9**, en HTTP réel cette fois (voir ci-dessous), plus deux balayages non demandés :
      parité **26/26** et la colonne `status` sur ses 6 valeurs réelles **7/7**.

## Acceptance Criteria

- [x] **FR-007** : les 88 colonnes filtrables acceptent un `column_filter`, appliqué côté
      serveur sur **tout** le périmètre autorisé. — les 88 interrogées en dev, chacune rendant
      le `kind` que le contrat lui donne.
- [x] **FR-008** : `filter-options` rend les valeurs distinctes du périmètre, bornées
      (`limit` 50 / plafond 200), interrogeables par `q`, avec `truncated` explicite. — mesuré :
      une colonne `text` sans `q` rend `options: []` + `truncated: true` ; `q=dcm` rend 2
      valeurs.
- [x] **FR-009** : clé, vue ou valeur de colonne non reconnues → **422**. Jamais un `WHERE`
      construit sur une entrée client, jamais un filtre ignoré en silence. — 422 sur les 11
      routes de liste **et** les 2 routes `filter-options`, avec les clés acceptées dans
      `detail`. Formes couvertes : clé inconnue, `nocolon`, `cost` sans `:`, `:100` sans clé,
      clé répétée, vue inconnue, clé porteuse d'une injection.
- [x] **SC-003** : filtrer sur une valeur portée par une seule ligne située au-delà de la
      première page ramène cette ligne, avec `total = 1`. — `dataset_company`, ligne 51,
      page 3 → `total = 1`.
- [x] Un paramètre historique et son `column_filter` équivalent produisent le **même** total
      et les **mêmes** items ; une contradiction entre les deux est rejetée, pas arbitrée en
      silence. — balayage des 13 paires : 12 exploitables, **totaux et items identiques** sur
      les 12 ; `has_spill=true` vs `spill:with` → 9 des deux côtés ; contradiction
      `has_spill=true` + `spill:without` → 422. La 13ᵉ (`reason` sur slow-queries) est ignorée
      faute de valeur en dev, la table n'y étant pas déployée.
- [x] `filter-options` ignore les `column_filter` en cours : poser un filtre sur une colonne
      ne réduit pas les listes des autres. — réponse **octet pour octet identique** avec et sans
      `column_filter`.
- [x] Aucune régression sur les 11 vues sans `column_filter` : mêmes totaux, mêmes items,
      même ordre. — les 11 répondent, totaux relevés dans le tableau ci-dessous, et chaque total
      filtré est borné par son total non filtré.
- [x] Aucun nom de colonne ni valeur client interpolé dans une requête. — test dédié : la valeur
      `x'; drop table it.gold; --` ressort comme **paramètre lié** `%x'; drop table it.gold; --%`
      et aucun `DROP` n'apparaît dans le SQL ; une injection dans la **clé** part en 422 sans
      qu'aucune requête ne soit émise.

## Vérification dev du 2026-09-07 — HTTP réel, sous OAuth utilisateur

T002 n'avait pu vérifier que le **SQL généré** : `app/db/connection.py:155-158` n'offre que
OAuth M2M à secret de service principal, ou PAT — les deux prohibées (quickstart §6.1), donc
pas de backend démarrable en local. La contrainte n'a pas changé, mais elle est contournable
**sans** l'affaiblir : un remplaçant de pool (`CliPool`) exécute chaque statement via
`databricks api post /api/2.0/sql/statements -p dcm-dev` — OAuth U2M, jeton dans le keyring de
l'OS, aucun secret dans le code — et la véritable application FastAPI répond en HTTP réel
in-process (`httpx.ASGITransport`). Sont donc couverts cette fois la validation FastAPI, le
routage, la sérialisation et le `exception_handler`, que le substitut de T002 laissait dehors.
Le remplaçant refuse toute écriture (`execute()` lève) et vit hors du repo : il n'est jamais
importé par l'application.

**§5bis : 9/9, 55 statements.**

| # §5bis | Résultat mesuré |
|---|---|
| 1 | les **88** colonnes des 11 vues répondent, chacune avec le `kind` du contrat |
| 2 | vue inconnue, colonne inconnue et clé inconnue → 422, `detail` listant « Accepted columns » |
| 3 | clé inconnue → 422 sur les **11** routes de liste, sans qu'aucune requête ne soit émise |
| 4 | même clé deux fois → 422 |
| 5 | `warehouse_size=2x_small` et `column_filter=size:2x_small` → **130** des deux côtés, items identiques |
| 6 | contradiction → 422 : `'warehouse_size=2x_small' contradicts 'column_filter=size:xxlarge'` |
| 7 | colonne `text` sans `q` → `options: []` + `truncated: true` ; `q=dcm` → 2 valeurs |
| 8 | **SC-003** : `dataset_company`, ligne 51, page 3 → `total = 1` |
| 9 | `filter-options` **octet pour octet identique** avec et sans `column_filter` |

**Parité et non-régression : 26/26, 93 statements.** Totaux non filtrés relevés :
clusters-overview 9 899, clusters-cost 9 899, efficiency 4 407, governance 5 410 305,
warehouses-overview 205, warehouses-cost 205, query-performance 202, slow-queries 0 avec
`enabled=false`, recommendations 6 671 500, lakeflow-jobs 188 103, job-runs 435 (workflow
`846231347314554`).

**Colonne `status` de Lakeflow, reprise à part : 7/7, 28 statements.** Le premier balayage
donnait `status=SUCCESS` et `column_filter=status:success` d'accord — mais à **0** des deux
côtés, ce qui ne prouve rien : deux prédicats faux sont toujours d'accord. Or `last_status` est
sur la branche `need_last_run` de `_query_jobs_page`, celle-là même que
`filters_need_last_run` a fallu ajouter. Reprise sur les 6 valeurs que dev propose réellement
(`succeeded` 170 370, `queued` 269, `failed` 16 893, `skipped` 11, `cancelled` 473,
`timed_out` 87) : **totaux et items identiques** des deux côtés, sur des pages non vides.

### Un défaut trouvé en dev, corrigé

`warehouse_slow_queries` n'est pas déployée en dev. Les 4 colonnes d'options de cette vue
tombaient donc dans le `except` et rendaient une liste vide — que l'IHM ne peut pas distinguer
de « aucune valeur dans votre périmètre ». `_empty_options` ajoute maintenant
`"enabled": false` dans ce cas, exactement le drapeau que la route de **liste** slow-queries
envoie déjà. Omis quand tout a fonctionné, comme les autres routes de liste. La combo de T006
doit l'honorer : une liste qu'on n'a pas pu construire ne doit pas s'afficher comme vide.

### Une erreur SQL transitoire, non reproduite

Le balayage de parité a journalisé une erreur sur un statement commençant par
`SELECT cloud_provider, CAST(NULL AS STRING) A…`, soit la page `/lakeflow/jobs` sur sa branche
`need_last_run=False`. Trois rejeux ciblés — 7 variantes de `/lakeflow/jobs`, puis la séquence
exacte du balayage (jobs 50, jobs 5, runs, runs filtrés), puis les 6 valeurs de `status` — ont
rendu **0 erreur SQL** sur 40 appels, tous en 200. Faute de reproduction, c'est consigné comme
transitoire du warehouse (statement lourd) et non comme un défaut du code. Si elle réapparaît,
le point d'entrée est `_query_jobs_page`, branche `need_last_run=False`.

## Notes cyber

Aucun secret, aucun accès nouveau. Le point de vigilance est l'**injection SQL** : c'est la
raison pour laquelle l'allowlist par vue est la seule source d'expressions SQL et pourquoi
toute valeur passe en paramètre lié. Le patron existe déjà dans le repo
(`_OVERVIEW_SORT_COLUMNS` protège `ORDER BY`) et doit être suivi à l'identique.

La vérification dev n'a utilisé **ni PAT ni secret de service principal**, alors que le `.env`
local porte les deux : le remplaçant de pool passe par le profil OAuth `dcm-dev` de la CLI, en
lecture seule. C'est la voie qui lève le blocage de quickstart §6.1 côté outillage de
vérification — le blocage lui-même, `app/db/connection.py` sans chemin OAuth U2M, reste ouvert
et hors périmètre de 023.
