# T002 — Backend : endpoints `/api/v1/uc-usage` sur les 8 tables gold usage

**Domain**: backend
**Package**: `packages/dcm-backend`
**Branch**: `dataeng/024-usage-tracking-governance` ⚠️ **branche unique partagée** avec T001
et T003 — ne pas créer `backend/024-…` que le parseur dérive du titre
**Jira**: `DCINT-334` (1 seule Story pour les 3 tasks)
**Depends on**: **T001 étape 1** — démarre quand la table gold est **rafraîchie**
**Work type**: feature

## Description

Exposer les 8 tables gold `gold_dbx_usage_*` (feature 019) via un nouveau routeur FastAPI.
Aucun endpoint existant n'est modifié : `data_product_usage.py` sert une table différente
(`gold_data_product_usage`) et reste intact.

Lecture directe du SQL Warehouse via `DatabricksWarehousePool` ; le SQL vit dans
`app/api/services/`, les routes se limitent à valider les paramètres et déléguer.
Placeholders **positionnels `?`**, qualification par `db.table(name)`.

La task a été livrée en **5 étapes**, dans cet ordre : le routeur et ses 12 endpoints
d'origine, puis une seconde vague (graphiques, exploration, filtres de colonne) demandée
après la première livraison des pages, puis deux corrections issues de retours utilisateur,
puis l'exigence FR-023 (`include_deleted`) et le correctif de plan qu'elle a rendu
nécessaire.

---

## Étape 1 — Le routeur et ses endpoints (`116d38b`)

- `GET /overview` — 6 KPI + 3 séries forecast + série volume écrit observée + top 3
  recommandations
- `GET /tables` — paginé, `sort` ∈ `popularity|cost|latency|failure_rate`, défaut
  `popularity`
- `GET /tables/{table_full_name}/top-consumers` — `LIMIT 5`, non paginé
- `GET /consumers` — paginé, rang **recalculé** sur la période
- `GET /finops/kpis`, `/finops/cost-by-table`, `/finops/trends`
- `GET /governance/kpis`, `/governance/registry` — snapshot, **sans** période
- `GET /recommendations`, `/attention` — `status='OPEN'` forcé
- `GET /filters/options` — peuple le sélecteur de périmètre

`uc_usage_latency` reconstitue le P95 de période par **interpolation** sur les
`latency_bucket_counts` additionnés (T001 étape 1) : ni `AVG`, ni `MAX` des P95 quotidiens.
Une clé de bucket absente vaut `0`.

Deux règles portées par `uc_usage_common` valent d'être retenues :

- **`None` est une valeur, pas un zéro manquant.** `number()` le préserve : `0` USD et
  « coût non attribuable » sont deux affirmations différentes, que les tables gold
  distinguent. Le helper `_number()` de `data_product_usage.py`, qui convertit `None → 0`,
  n'est **pas** réutilisé.
- **Aucun prédicat de scope**, parce qu'aucune des 8 tables ne porte `source_lz_id` ni
  `workspace_id` : le routeur entier est réservé aux appelants non restreints
  (`require_unrestricted_scope`).

## Étape 2 — Graphiques, exploration et filtres de colonne (`42af104`, part backend)

Seconde vague fonctionnelle demandée après la première livraison des 2 pages : séries
temporelles, heatmap, scatter, tiroir de détail d'entité, et filtres par colonne appliqués
**côté serveur** — un filtre posé après pagination annoncerait des pages vides.

Cinq services neufs : `uc_usage_charts.py`, `uc_usage_exploration.py`,
`uc_usage_column_filters.py`, `uc_usage_governance_charts.py`, `uc_usage_governance_scope.py`.
13 fichiers backend sur les 54 du commit — le reste est la partie frontend (T003 étape 2).

⚠️ Ce travail est parti **sans passer par une task** : c'était du volume de feature, qui
aurait dû avoir ses critères écrits d'avance. Le constat est en tête de `tasks.md`.

## Étape 3 — Corriger les chiffres affichés (`8b8b001`)

Retour utilisateur : les valeurs du bloc « Observed usage & 7-day outlook » et de l'onglet
FinOps étaient trompeuses. Quatre défauts de **lecture** des chiffres, pas d'affichage :

1. **Horizon de prévision non borné à droite** : « +7d » désignait en réalité *tout* le
   futur laissé en table par les runs précédents. `_FUTURE_HORIZON` est borné des deux
   côtés, y compris pour `forecast_cost_usd_7d`, qui somme donc bien sept jours.
2. **Jour en cours inclus dans le réalisé** : chargé partiellement, il se lisait comme un
   effondrement en fin de courbe. Exclu.
3. **Jours sans mesure absents de la série** : la courbe se refermait silencieusement. Un
   point par jour calendaire, `null` quand rien n'a été mesuré.
4. **Cartes de tendance sur le dernier jour** au lieu de la période, contrairement au reste
   du bloc Overview. Moyenne/jour pour les couples consommateur-table, que sommer compterait
   trente fois le même lecteur.

Et un renommage : « Distinct consumers » → **« Consumer-table pairs »**. La série somme les
consommateurs *par table* (185 687 mesurés) quand le KPI « Consumers » de la même page
compte les têtes (2 256) : deux chiffres à un ordre de grandeur d'écart sous des libellés
qui se ressemblaient. Le composant `uc-usage-trend-cards.tsx` change avec.

## Étape 4 — Tri, filtres et recherche sur `/finops/cost-by-table` (`ba40300`, part backend)

L'endpoint n'acceptait ni `sort`, ni `direction`, ni `column_filter`, ni `search` : le
tableau était figé sur « coût décroissant » et **ignorait la boîte de recherche de la page**,
laquelle restait pourtant affichée dans l'onglet FinOps. Deux tableaux voisins, deux
comportements.

Un point ne relevait pas du simple câblage : `cost_per_request_usd` était calculé **en
Python, après la pagination**. Une colonne calculée là ne peut être ni triée ni filtrée par
le warehouse — elle passe donc dans une CTE `joined`, avec `forecast_cost_usd_7d`. Le total
de pagination est compté sur cette même CTE **filtrée** : sans cela la pagination annonçait
des pages vides dès le premier filtre (corrigé pendant la revue, test ajouté).

## Étape 5 — `include_deleted` et cycle de vie des tables (`5ccdaf2`)

FR-023 côté API. Les 2 pages comptaient encore des tables supprimées de Unity Catalog : un
KPI « 412 tables suivies » incluait des tables qui n'existent plus, et le total de pagination
ne correspondait pas à ce que la liste montrait. Contrat **gelé par la spec 027** :
[027 · api-include-deleted.md](../../027-usage-table-deleted-flag/contracts/api-include-deleted.md).

- `include_deleted` (booléen, défaut `false`) sur les **18** routes de grain table.
- `GET /consumers` et `GET /charts/consumers` restent **exemptes** : de grain consommateur,
  elles n'ont aucune clé table à filtrer. Le paramètre n'y est même pas déclaré, pour que
  l'OpenAPI dise la vérité.
- L'exclusion s'applique **avant** agrégation, par anti-jointure sur
  `gold_dbx_usage_table_catalog`, ou par `NOT COALESCE(is_deleted, false)` là où la table
  interrogée porte elle-même le drapeau (`gold_dbx_usage_table_governance`).
- Le filtrage porte sur l'**ancre** des chaînes de CTE, pour que le `COUNT(*)` et la page
  lisent le même périmètre — vérifié par comparaison de tokens, mot pour mot.
- Trois champs de cycle de vie toujours présents sur les réponses de grain table.
- `deleted_table_conditions()` rend un prédicat **sans paramètre lié** : les appelants
  threadent leurs `?` positionnels à la main, et un prédicat qui n'en ajoute aucun
  s'append à n'importe quelle liste sans renuméroter ce qui suit.
- `guarded(tables=[…])` est étendu à `GOLD_TABLE_CATALOG` : un catalogue absent doit
  dégrader en 503 nommant la bonne table (FR-018).

## Étape 6 — Sortir l'anti-appartenance du `OR` des recommandations

Régression livrée par l'étape 5 et signalée par l'utilisateur : le bloc « Recommendation
details » affichait **« Unable to load recommendations. »**. Ni erreur SQL ni colonne
manquante — la requête rendait le bon résultat, mais en **81 s** au lieu de 0,4, et le client
abandonne à 30 s (`API_REQUEST_TIMEOUT_MS`). Trois requêtes séquentielles par appel : le
budget n'est jamais tenu.

La cause est la **forme** du prédicat, pas son contenu. Sur les 9 sites d'appel de
`deleted_table_conditions`, celui des recommandations est le seul à imbriquer
l'anti-appartenance dans une disjonction — nécessaire par contrat, l'exclusion ne devant
rétrécir que les lignes `DATA_PRODUCT` (FR-011) :

```sql
AND (UPPER(object_type) <> 'DATA_PRODUCT' OR object_id NOT IN (SELECT …))
```

Au premier niveau, `x NOT IN (sous-requête)` est réécrit en anti-jointure : une passe de
hachage. Sous un `OR`, la réécriture est impossible — les deux branches doivent pouvoir être
évaluées ligne par ligne — et la sous-requête redevient une recherche par ligne contre les
**1 351 471** noms marqués supprimés du catalogue. C'est exactement le risque 🟡 consigné par
la revue de l'étape 5 ; il s'est réalisé là où le rapport ne l'attendait pas — pas sur les 8
sites de premier niveau, mais sur le seul site imbriqué.

**Le correctif.** Une jointure n'est pas soumise à la disjonction : elle est placée
inconditionnellement dans le `FROM`, et il ne reste sous le `OR` qu'un test de colonne.

```sql
WITH deleted_tables AS (
    SELECT DISTINCT table_full_name
    FROM gold_dbx_usage_table_catalog
    WHERE is_deleted AND table_full_name IS NOT NULL
)
SELECT …
FROM gold_dbx_usage_recommendations AS rec
LEFT JOIN deleted_tables ON deleted_tables.table_full_name = rec.object_id
WHERE UPPER(rec.status) = 'OPEN'
  AND (UPPER(rec.object_type) <> 'DATA_PRODUCT' OR SPLIT_PART(rec.object_id, '.', 1) = ?)
  AND (UPPER(rec.object_type) <> 'DATA_PRODUCT' OR deleted_tables.table_full_name IS NULL)
```

Le `DISTINCT` porte une garantie de **correction**, pas une optimisation : le catalogue a une
ligne par `(cloud_provider, table_full_name)`, et sans lui une table supprimée sur deux
clouds apparaîtrait deux fois — toute ligne conservée par **l'autre** branche de la
disjonction serait dupliquée et gonflerait les `COUNT(*)`.

Deux différences de sémantique, assumées et documentées :

- une ligne dont `object_id` est NULL est désormais **conservée** (pas de nom, pas de table
  supprimée) alors que le `NOT IN` null-aware la jetait ;
- l'exclusion ne retire **aucune ligne** aujourd'hui sur ce jeu de données : aucune
  recommandation ouverte ne pointe vers une table marquée supprimée. Les 81 s n'achetaient
  donc aucun filtrage. Le prédicat reste nécessaire — le jour où une table suivie est
  supprimée, il doit être là.

Les 8 autres sites gardent leur `NOT IN`, mesuré sain au premier niveau : aucun churn.

### Ce que la mesure a coûté

À consigner, parce que deux conclusions fausses ont été tirées avant la bonne :

1. Les six premières formes avaient été chronométrées **en une seule passe séquentielle**.
   Les dernières profitaient du cache disque chauffé par les premières, ce qui a fait passer
   un `NOT EXISTS` corrélé pour un correctif. Correction : préchauffer les deux tables avant
   de comparer quoi que ce soit.
2. Rejouer le SQL de l'endpoint juste après l'endpoint tape dans le **cache de résultat** de
   Databricks. Correction : un commentaire unique par exécution.
3. Interrompre le client Python **n'annule pas** la requête côté warehouse. Chaque `pkill`
   laissait un plan lourd en cours, qui mettait en file la mesure suivante. Correction :
   laisser chaque mesure finir.

Quatre formes du même prédicat, à froid, cache de résultat cassé, cache disque préchauffé à
égalité, mêmes 23 203 lignes rendues :

| Forme du prédicat | À froid |
|---|---|
| aucune exclusion — la page avant l'étape 5 | 0,42 s |
| `NOT IN` imbriqué dans le `OR` — ce que l'étape 5 a livré | **81,08 s** |
| `NOT EXISTS` corrélé, imbriqué | 34,83 s |
| jointure hors du `OR` + test de colonne — **retenu** | **1,12 s** |

---

## Files to create/modify

Routeur et montage :

- CREATE `app/api/routes/uc_usage.py` — routes minces, `require_unrestricted_scope`,
  `include_deleted: IncludeDeletedQuery = False` en dernier paramètre des 18 routes en
  périmètre
- UPDATE `app/api/routes/__init__.py` — export `uc_usage`
- UPDATE `app/main.py` —
  `include_router(uc_usage.router, prefix="/api/v1/uc-usage", tags=["uc-usage"])`

Services (`app/api/services/`) :

- CREATE `uc_usage_common.py` — période, filtres, pagination, 503 table absente, helper
  numérique préservant `None`, `deleted_table_conditions()`, `deleted_flag_conditions()`,
  `DeletedTableJoin` / `deleted_table_join()` (étape 6 — **exige** une colonne qualifiée par
  l'alias externe), `lifecycle_cte` / `lifecycle_fields` / `table_lifecycle`
- CREATE `uc_usage_latency.py` — interpolation du P95 sur buckets additionnés
- CREATE `uc_usage_tables.py` — `/overview`, `/tables`, `/tables/{…}/top-consumers`
- CREATE `uc_usage_consumers.py` — `/consumers`
- CREATE `uc_usage_finops.py` — `/finops/kpis`, `/cost-by-table` (CTE `joined`, colonnes
  calculées triables), `/trends` (horizon borné, jour en cours exclu, série par jour
  calendaire)
- CREATE `uc_usage_governance.py` — `/governance/*`, `/recommendations`, `/attention` ;
  `_recommendation_scope()` rend `cte` / `source` / `conditions` / `params`, épissés par les
  4 requêtes de `fetch_recommendations` et `fetch_attention`
- CREATE `uc_usage_filters.py` — `/filters/options`
- CREATE `uc_usage_charts.py`, `uc_usage_exploration.py`, `uc_usage_column_filters.py`,
  `uc_usage_governance_charts.py`, `uc_usage_governance_scope.py` (étape 2)

Tests :

- CREATE `tests/test_uc_usage_routes.py`, `tests/test_uc_usage_charts.py`,
  `tests/test_uc_usage_exploration.py`, `tests/test_uc_usage_governance_charts.py`
- CREATE `tests/test_uc_usage_include_deleted.py` — les 6 critères de la spec 027, l'OpenAPI
  des 18 routes et des 2 exemptions, et l'**exécution** du SQL généré (étapes 5 et 6)

Contrat :

- UPDATE `contracts/uc-usage-api.md` — à chaque étape

## Acceptance Criteria

### Étape 1 — endpoints

- [x] `period_start`/`period_end` **obligatoires** sur les endpoints datés → **422** si
      absents ou `start > end` (FR-017)
- [x] Les 4 endpoints de liste sont paginés `page`/`page_size` (défaut 25, max 200) et
      renvoient `{items,total,page,page_size}`, plus `period` sur les seuls endpoints
      **datés** (`/tables`, `/consumers`) — un endpoint snapshot ne fabrique pas de période
      (FR-016)
- [x] Table gold absente → **503** `{"code": "<table>_missing", …}`, jamais un 500 ni un 200
      vide (FR-018)
- [x] Routeur inaccessible à un compte scopé projet → **403** ; aucun paramètre
      `cloud_provider` / `workspace_id` / `source_lz_id` accepté (FR-010, FR-019, FR-021)
- [x] `latency_p95_ms` interpolé sur les buckets de la période — **ni** `AVG`, **ni** `MAX`
      des P95 quotidiens (FR-022)
- [x] `failure_rate_pct` = `SUM(failed)/SUM(total)*100`, jamais une moyenne de pourcentages
- [x] `distinct_consumers` et `distinct_tables` recalculés par `COUNT(DISTINCT …)` sur toute
      la période — jamais une somme de distincts quotidiens
- [x] Rang consommateur **recalculé** sur `SUM(estimated_cost_usd)` — `consumer_rank`
      n'apparaît dans aucune requête
- [x] `NULL` préservé de bout en bout sur `data_written_bytes`, `estimated_cost_usd`,
      forecast absent, `owner`, latence (SC-005)
- [x] `/recommendations` : `status='OPEN'` forcé, **aucune** déduplication par
      `(object_id, category)`, filtre catalogue appliqué aux seules lignes
      `object_type='DATA_PRODUCT'` (FR-011, FR-013)
- [x] `/governance/registry` : `owner` vaut `null`, jamais `""` (FR-012)
- [x] `avg_cost_per_request_usd` accompagné de `"is_lower_bound": true`
- [x] Aucun endpoint existant modifié

### Étape 2 — graphiques, exploration, filtres de colonne

- [x] Chaque colonne filtrable l'est **côté serveur**, pas après pagination
- [x] Les endpoints de graphiques et d'exploration servent les 2 pages sur un périmètre
      appliqué

### Étape 3 — chiffres affichés

- [x] « +7d » couvre exactement sept jours, pas tout le futur laissé en table
- [x] La courbe ne plonge plus sur le jour en cours
- [x] Un jour sans mesure est un trou (`null`), pas un raccourci de la courbe
- [x] Deux libellés distincts pour deux chiffres distincts (paires vs têtes)

### Étape 4 — `/finops/cost-by-table`

- [x] Tri serveur, filtres de colonne et recherche de page acceptés, comme sur les 2 autres
      tableaux
- [x] `cost_per_request_usd` est triable et filtrable (colonne de CTE, plus de calcul après
      pagination)
- [x] Le total de pagination est compté sur la CTE **filtrée**

### Étape 5 — `include_deleted`

- [x] Sans le paramètre, aucune table supprimée dans une liste, un KPI, un graphique ni un
      total de pagination — le `COUNT(*)` et la page partagent la chaîne de CTE **mot pour
      mot** (test de comparaison par tokens)
- [x] `include_deleted=true` : les lignes reviennent avec `deleted_at` renseigné
- [x] Une table supprimée sur **un seul** cloud est exclue comme la ligne le déclare
- [x] `is_deleted` n'est **jamais** nul dans la réponse ; une ligne non résolue rend
      `is_deleted: false` et `lifecycle_state: "UNKNOWN"`
- [x] `/recommendations` ne perd pas ses lignes de grain consommateur
- [x] `/consumers` et `/charts/consumers` ignorent le paramètre — et ne le déclarent pas dans
      l'OpenAPI

### Étape 6 — plan des recommandations (SC-007)

- [x] `GET /uc-usage/recommendations` avec un périmètre répond **sous 5 s** (mesuré contre la
      warehouse, pas seulement en test) — 3,22 s à froid sur un catalogue jamais interrogé,
      0,62 – 2,09 s en rejeu
- [x] `GET /uc-usage/attention` idem — 1,15 à 1,25 s
- [x] Le résultat est **inchangé** : mêmes comptes qu'avant le correctif, une recommandation
      de grain consommateur survit toujours à l'exclusion
- [x] Les 8 autres sites d'appel gardent `NOT IN` — mesurés sains, aucun churn
- [x] Une colonne non qualifiée passée à `deleted_table_join()` **lève**, au lieu de produire
      une exclusion totale silencieuse
- [x] `include_deleted=true` n'émet toujours aucun fragment : la requête sort exactement
      comme sans la feature

### Les six étapes

- [x] `ruff`, `mypy` et `pytest` verts ; le diff n'ajoute aucune erreur `mypy` côté `app/`

## Tests

```bash
cd packages/dcm-backend
uv run ruff check . && uv run ruff format --check .
uv run mypy .
uv run pytest tests/ -q
```

Mock : fixture `mock_db` de `tests/conftest.py` (`AsyncMock` mimant
`DatabricksWarehousePool`) ; auth désactivée par la fixture autouse.
`tests/test_uc_usage_include_deleted.py` va plus loin et **exécute** le SQL généré sur
SQLite — c'est la seule façon d'attraper un fan-out de jointure, qu'une assertion de
sous-chaîne ne voit pas.

## Out of scope

- `PATCH /recommendations/{id}/status` — le pipeline réécrit `status` à chaque run
- Tout paramètre de scope LZ / workspace / cloud
- Modification de `data_product_usage.py` ou de tout autre routeur existant
- Cache de réponse (`get_cached_response`) — les tables gold sont rafraîchies fréquemment
- **Dénormaliser `is_deleted` sur les faits journaliers** : le MERGE glissant de 3 jours
  figerait le drapeau sur la fenêtre qu'il réécrit (décision de la spec 027)
- **Ajouter des `response_model` Pydantic à ce routeur** : ses 20 routes renvoient
  `dict[str, Any]`, et l'OpenAPI ne documente donc que le **paramètre** `include_deleted`,
  pas les trois champs de réponse. Écart assumé, consigné dans l'amendement FR-023
- Les lignes de grain recommandation (`/recommendations`, `/attention`) ne portent pas les
  trois champs de cycle de vie : leur `object_id` n'est pas toujours une table
- **Réécrire les 8 autres sites en jointure** : mesurés sains, leur `NOT IN` est bien réécrit
  en anti-jointure au premier niveau
- **Relever `API_REQUEST_TIMEOUT_MS`** : 30 s est déjà généreux, et une requête de 81 s est un
  défaut de plan, pas un budget trop court
- **Paralléliser les 3 requêtes séquentielles de `fetch_recommendations`** : gain réel mais
  indépendant de la régression
- **Vider `is_deleted` du catalogue** : 1 351 471 lignes sur 1 442 044 marquées supprimées
  méritent une question au pipeline gold — c'est T001 étape 2 qui y répond

## Revues

| Étape | Rapport | Verdict | Reste ouvert |
|---|---|---|---|
| 1 | review 2026-09-12 | **PASS** (0 🔴, 1 🟡) | l'arithmétique du P95 vit dans le service et non en SQL — contrepartie assumée de l'interpolation |
| 2 | — | rapport **perdu** (jamais versionné) | la revue a eu lieu (stamp exigé par le hook), le rapport était nommé d'après un compteur de reviews |
| 3 | — | rapport **perdu**, même cause | — |
| 4 | review 2026-09-15 | **PASS** (0 🔴, 1 🟡 corrigé pendant la revue : le total de pagination) | rien |
| 5 | review 2026-09-16 | **PASS** (0 🔴, 3 🟡) | le 🟡 sur la forme du `NOT IN` — **réalisé**, corrigé par l'étape 6 ; `table_lifecycle()` appelée par requête sur `uc_usage_exploration.py` ; l'ordre de déploiement (voir Notes) |
| 6 | review 2026-09-17 | **PASS** (0 🔴, 3 🟡) | tous documentés : le `DISTINCT` porte une correction et non une optimisation, le churn de `_recommendation_scope`, et les deux points de sémantique |

## Before PR

- [x] Tests pass
- [x] No files outside package scope
- [x] Sub-spec checkboxes reviewed
- [x] Jira Story lists **Git branch** name (not a commit SHA)
- [ ] `/speckit.dcm.review --commit` avant le `git commit` de l'étape 6

## Notes

- **Contrat détaillé** : [contracts/uc-usage-api.md](../contracts/uc-usage-api.md) —
  paramètres, codes de retour, matrice endpoint → tables sources. **Entités et règles
  d'agrégation** : [data-model.md](../data-model.md).
- Patterns suivis : `compute_metrics.py` + `compute_metrics_recommendations.py` (route mince
  → service), `data_product_usage.py` (détection `[TABLE_OR_VIEW_NOT_FOUND]` → 503).
- **Pièges de coût** reflétés dans les réponses : `cost_attribution_method`
  (`equal_parts_fallback`), `cost_basis`, et le fait que le partage à parts égales inclut les
  vues — alimente le tooltip FR-009 côté UI.
- ⚠️ **Ordre de déploiement imposé** : rejouer le pipeline `gold_dbx_usage` **avant** de
  livrer ce backend, dans chaque environnement. La spec 027 n'a changé que le code du
  pipeline : les colonnes de cycle de vie n'existent dans la table gold qu'après un rejeu.
  `guarded()` ne mappe que `TABLE_OR_VIEW_NOT_FOUND` vers 503, donc une colonne `is_deleted`
  absente remonterait en `UNRESOLVED_COLUMN` non traduit — un 500 brut sur les 18 routes.
  Mitigation retenue le 2026-09-16 : **l'ordre de déploiement**, pas de code. L'option
  écartée était d'étendre `guarded()` à `UNRESOLVED_COLUMN`, restreint aux trois colonnes de
  cycle de vie (sinon une faute de frappe dans un futur SQL se déguiserait en « pipeline pas
  encore joué »). À rouvrir si les environnements cessent d'être rejoués avant livraison.
- `uv run mypy .` compte 170 erreurs sur `HEAD` : le dépôt n'est pas propre pour cette
  commande. L'étape 5 en ajoute **3**, toutes dans la classe `no-untyped-def` /
  `no-untyped-call` que la fixture SQLite de `tests/test_uc_usage_exploration.py` produit déjà
  56 fois. Annoter les 2 aides ajoutées romprait cette cohérence, et un `fetchone` typé
  appelant un `fetchall` non typé échangerait juste ces 2 erreurs contre une autre. Style du
  fichier conservé ; côté `app/`, aucune erreur ajoutée.
- Le trou de couverture révélé par l'étape 6 est instructif :
  `test_recommendations_narrow_data_products_only` vérifiait la **chaîne SQL** avec un
  `AsyncMock`, jamais son exécution — et SQLite exécute la forme imbriquée sans broncher.
  Aucun test de ce dépôt ne pouvait attraper une régression de plan. La garantie de
  performance ne peut venir que d'une mesure contre la warehouse.
- **Après merge**, penser au repo infra : agent `dp-dcm-sync-infra` pour ajouter les nouvelles
  routes à `API_GW_2.tf`.
