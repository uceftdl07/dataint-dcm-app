# T002 — API warehouse par fenêtre glissante

**Domain**: backend
**Package**: packages/dcm-backend
**Branch**: `backend/023-warehouse-windows-et-filtres`
**Jira**: not dispatched (dispatch non exécuté sur cette feature)
**Depends on**: T001 (`warehouse_name` peuplé en dev sur `query_performance_rolling`)
**Work type**: feature

## Description

Les 3 vues de liste warehouse lisent aujourd'hui les tables `*_daily` avec
`_date_where` + `QUALIFY ROW_NUMBER() … ORDER BY period_start DESC = 1` : élargir la période
ne fait que **déplacer l'ancre** du dernier jour trouvé, jamais agréger la période. Cette
task les branche sur `gold_dbx_compute_warehouse_cost_rolling` et
`..._warehouse_query_performance_rolling` avec `window_days ∈ {1, 7, 30, 90}`, expose la
période réellement couverte, ajoute `warehouse_name` à la vue Performance, et normalise
`cost_usd_prev_window`.

Les helpers de fenêtre écrits pour les clusters en 022 **descendent** dans
`compute_metrics_common.py` au lieu d'être dupliqués : `_window_where`, `_window_block`,
`_window_period`, `_bounds_sql`, `_normalize_prev_cost`, et `ClusterWindowDays` généralisé
en `RollingWindowDays`. `compute_metrics_clusters.py` les importe — aucun changement de
comportement côté clusters, et les tests existants doivent le prouver.

`fetch_warehouse_slow_queries` (lit `warehouse_slow_queries`) et
`fetch_warehouse_cost_trend` (série temporelle, grain quotidien assumé) **ne sont pas
touchées**. `fetch_warehouse_detail` non plus dans cette itération : la spec ne demande la
fenêtre que sur les vues de liste.

## Files to create/modify

- UPDATE `packages/dcm-backend/app/api/services/compute_metrics_common.py`
- UPDATE `packages/dcm-backend/app/api/services/compute_metrics_warehouses.py`
- UPDATE `packages/dcm-backend/app/api/services/compute_metrics_clusters.py`
- UPDATE `packages/dcm-backend/app/api/routes/compute_metrics.py`
- UPDATE `packages/dcm-backend/tests/test_compute_metrics_services.py`
- UPDATE `packages/dcm-backend/tests/test_compute_metrics_routes.py`

## Sub-tasks

- [x] **Tests d'abord** : `window_days=5` → 422 ; `window_days="7"` (chaîne, ce que le
      navigateur envoie) → accepté ; `cost_usd_prev_window = 0` → `null` **et**
      `cost_delta_pct = null` ; `cost_usd_prev_window < 0` → `null` (avoir de facturation) ;
      fenêtre vide → `from_date`/`to_date` à `null`, pas de bornes calculées depuis `today` ;
      les 3 vues ne référencent plus `_COST` / `_QUERY_PERF` quotidiennes ; régression
      clusters : les tests existants passent sans modification après la descente des helpers.
- [x] `compute_metrics_common.py` : déplacer `_window_where`, `_window_block`,
      `_window_period`, `_bounds_sql`, `_normalize_prev_cost` ; renommer `ClusterWindowDays`
      en `RollingWindowDays` en conservant `ClusterWindowDays` comme alias le temps de la
      migration interne (P11 : pas de renommage à l'aveugle d'un symbole exporté).
- [x] `compute_metrics_warehouses.py` : constantes `_COST_ROLLING`,
      `_QUERY_PERF_ROLLING` ; garder `_COST` pour `fetch_warehouse_cost_trend` et
      `fetch_warehouse_detail`.
- [x] `fetch_warehouses_overview` : pivot `cost_rolling`, `LEFT JOIN query_performance_rolling`
      sur les 3 clés **+ `window_days`**, `LEFT JOIN dim_dbx_workspace`, `LEFT JOIN`
      recommandations. Le KPI `cost_delta_pct` se lit dans `SUM(cost_usd_prev_window)` de la
      fenêtre — **plus** de seconde requête `_previous_period` (P12 : la comparaison est
      déjà agrégée en gold).
- [x] `fetch_warehouses_cost` : `cost_usd_prev_day` → `cost_usd_prev_window`,
      `period_start` → `as_of_date` + `window_start`, `_normalize_prev_cost` appliqué à
      chaque item.
- [x] `fetch_warehouses_query_performance` : `+ warehouse_name`, `+ as_of_date`,
      `+ window_start`.
- [x] Bloc `window` (`window_days`, `from_date`, `to_date`) dans les 3 réponses ; `period`
      conservé une version, valorisé avec les bornes de la fenêtre (P15).
- [x] Routes `/warehouses/overview|cost|query-performance` : paramètre
      `window_days: RollingWindowDays = RollingWindowDays.DAY`. **`IntEnum`, pas
      `Query(enum=[…])`** — le second ne décore que le schéma OpenAPI, `window_days=5`
      serait accepté et rendrait une page vide sans erreur.
- [x] Vérifier que tous les champs numériques nouvellement exposés traversent `_json_safe` :
      sans lui Pydantic v2 sérialise un `Decimal` en **chaîne** JSON, et `toFixed` lève un
      `TypeError` côté front (défaut trouvé en vérifiant 022 T002).
- [x] **Garde en lecture sur `as_of_date`**, ajoutée au périmètre le 2026-09-07 après mesure
      en dev ([research.md](../research.md) R9a) : les 3 vues doivent filtrer
      `as_of_date = (SELECT MAX(as_of_date) FROM <table>)`, sinon elles lisent des lignes
      rémanentes qu'aucun run ne supprime. Mesuré : **358 warehouses au lieu de 202** sur la
      fenêtre 1, dont 156 datant de deux jours et indiscernables des courants.
      Le `MAX` est global à la table, **pas par `window_days`** : le snapshot courant porte un
      seul `as_of_date` pour ses 4 fenêtres, et un `MAX` par fenêtre ferait ressortir le
      périmé de toute fenêtre dont la population courante est vide.
      Un test doit **poser** deux `as_of_date` dans la table de test et vérifier que seul le
      plus récent ressort — sans lui, un jeu de test à un seul `as_of_date` passe à vide.
- [x] Gates : `pytest` (suite complète), `ruff check app tests`.
- [x] Vérification en dev des 9 contrôles de [quickstart.md](../quickstart.md) §5 — jouée en
      **SQL généré** et non en HTTP, voir « Vérification dev » ci-dessous : la seule
      authentification que `app/db/connection.py` sait offrir est prohibée par le garde-fou
      TTE (quickstart §6.1).

## Acceptance Criteria

- [x] `window_days ∈ {1, 7, 30, 90}` accepté sur les 3 routes ; toute autre valeur → **422**,
      jamais un repli silencieux. — 12 cas verts, 15 cas à 422 (`0, 5, 14, 365, -7` × 3 routes).
- [x] Les 3 vues renvoient une ligne par warehouse et le bloc `window`, avec
      `from_date`/`to_date` **lus** dans `window_start`/`as_of_date` du gold, et
      `to_date - from_date + 1 = window_days`. — mesuré : `span_days` = 1 / 7 / 30 / 90 sur les
      deux tables, et `MIN(window_start) = MAX(window_start)` par fenêtre (borne non ambiguë).
- [x] Aucune requête des 3 vues de liste ne touche `warehouse_cost_daily` ni
      `warehouse_query_performance_daily`.
- [x] `cost_usd_prev_window` est `null` — **jamais `0`** — quand la fenêtre précédente
      n'existe pas ; `cost_delta_pct` est `null` dans ce cas. — en dev, `prev_null = 0` et
      `prev_zero` = 9 / 50 / 89 / **306** lignes selon la fenêtre : le défaut était visible sur
      30 % de la page 90 jours.
- [x] Chaque item de `/warehouses/query-performance` porte `warehouse_name`, renseigné sur
      > 95 % des items en dev. — **100,0000 %** sur les 4 fenêtres (202 / 536 / 632 / 691).
- [x] `/warehouses/slow-queries`, `/warehouses/{id}` et `/warehouses/{id}/cost-trend` ont un
      contrat **inchangé**, prouvé par test.
- [x] Les tests clusters existants passent **sans modification** : la descente des helpers
      dans `_common` ne change aucun comportement. — prouvé par le diff : 573 ajouts et
      **1 seule suppression** dans les fichiers de test, la ligne d'import remplacée.
- [x] Aucun champ numérique sérialisé en chaîne JSON.
- [x] Une fenêtre sans donnée rend une page vide avec `from_date`/`to_date` à `null`, pas
      des bornes inventées depuis `today` (P9).
- [x] Les 3 vues ne rendent que le **snapshot courant** : chaque requête filtre
      `as_of_date = (SELECT MAX(as_of_date) FROM <table>)`, `MAX` global à la table et non par
      `window_days`. Prouvé par un test qui pose **deux** `as_of_date` dans la table de test et
      vérifie que seul le plus récent ressort. Sans cette garde, remesuré en dev le
      2026-09-07 : **463 warehouses rendus au lieu de 205** sur la fenêtre 1, dont **258**
      périmés du 2026-09-04 et indiscernables des courants ([research.md](../research.md) R9a).

## Vérification dev du 2026-09-07 — SQL généré, pas HTTP

Le contrôle §5 demande des appels HTTP. Il n'a pas pu être joué ainsi, et ce n'est pas un
manque de temps : `app/db/connection.py:155-158` n'offre que deux authentifications, OAuth
**M2M à secret de service principal** et **PAT**, toutes deux prohibées par le garde-fou TTE.
Le `.env` local porte les deux (`DCM_DATABRICKS_SPN_CLIENT_SECRET`, `DCM_DATABRICKS_TOKEN`) —
il n'a pas été utilisé pour autant. C'est le point laissé ouvert en quickstart §6.1, hors
périmètre de 023.

Substitut retenu, plus fort que HTTP sur la partie SQL : les statements sont **générés par le
service lui-même** (recorder branché sur les 3 fetchers, `window_days ∈ {1, 7, 30, 90}`,
paramètres inlinés — tous entiers), puis exécutés tels quels en dev sous le profil OAuth
`dcm-dev`. **32 statements, 32 `SUCCEEDED`.** Ce que ça ne couvre pas — sérialisation FastAPI,
validation `IntEnum`, forme de la réponse — est couvert par les 93 lignes de tests de route.

| # §5 | Résultat mesuré |
|---|---|
| 5.1 | 32/32 `SUCCEEDED` ; `_total` = 205 / 583 / 719 / 1020 (cost, overview) et 202 / 536 / 632 / 691 (perf) |
| 5.2 | 15 cas → 422 (test de route) |
| 5.3 | `from_date` = `MIN(window_start)` = `MAX(window_start)` par fenêtre ; `to_date` = `MAX(as_of_date)` = **2026-09-06** (la veille — d'où la lecture depuis le gold et non depuis `today`) |
| 5.4 | `span_days` = 1 / 7 / 30 / 90, exactement `window_days`, sur les deux tables |
| 5.5 | `prev_zero` = 9 / 50 / 89 / 306 et `prev_null` = **0** : la colonne n'est jamais `NULL` en gold, `_normalize_prev_cost` est donc la seule chose qui distingue « pas de prédécesseur » de « a coûté zéro » |
| 5.6 | `Decimal` → `float` sur 5 champs (test de route) |
| 5.7 | `warehouse_name` **100,0000 %** sur les 4 fenêtres |
| 5.8 | `total` overview croissant : 205 → 583 → 719 → 1020 |
| 5.9 | contrat slow-queries inchangé (test de route + test de service) |

Deux mesures qui n'étaient pas demandées et qui valident des choix du code :

- `COUNT(*)` vs `SUM(CASE WHEN cost_usd > 0 …)` : **198 warehouses facturés pour 205 lignes**
  sur la fenêtre 1 (633 pour 719 sur 30 jours). Le KPI « actifs » aurait surcompté de 7 à 86.
- `n_guarded = COUNT(DISTINCT cloud_provider, workspace_id, warehouse_id)` sur
  `query_performance_rolling`, sur les 4 fenêtres : le `LEFT JOIN p` de l'overview ne peut pas
  démultiplier une ligne. La clé de jointure à 4 colonnes est donc bien unique côté source.

Gates : `pytest` **440 passés, 1 échec** — `test_connection.py::test_connect_timeout_has_actionable_message`,
**pré-existant et dépendant du poste** : le test construit `Settings(databricks_warehouse_id="warehouse-id")`
mais le `.env` local définit `DCM_DATABRICKS_HTTP_PATH`, que `resolved_http_path` préfère.
Aucun fichier de ce test n'est dans le diff. `ruff check app tests` : 156 erreurs au total,
**0 sur les 6 fichiers touchés** (`All checks passed!`).

### Défaut latent trouvé au passage, non corrigé

Cycle d'import **pré-existant** : `services.compute_metrics_common` → `routes._lz_filter` →
`routes/__init__` (qui importe tous les modules de route) → `routes.compute_metrics` →
`services.compute_metrics_clusters` → `services.compute_metrics_common` partiellement
initialisé. Importer un module de service **avant** `app.main` lève donc un `ImportError` —
rencontré en écrivant le générateur de SQL. Invisible en test parce que `conftest.py` importe
`app.main` d'abord. Existait à HEAD (`compute_metrics_clusters` importait déjà de `_common`) :
la correction est de sortir `add_scope_lz_filter` de `routes/`, hors périmètre de T002.

## Notes cyber

Aucun accès Databricks nouveau : le service passe par `DatabricksWarehousePool` déjà
configuré. Aucun secret, aucune chaîne de connexion ajoutée. La vérification HTTP en local
suppose une authentification du backend — voir la contrainte réelle et non résolue en
[quickstart.md](../quickstart.md) §6.1 (`app/db/connection.py:155-158` n'offre pas de chemin
OAuth U2M).
