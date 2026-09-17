# Rapport d'implémentation — T001e (`gold_dbx_compute_serverless_governance`)

**Date** : 2026-09-10 · **Branche** : `spike/serverless_cluster` (aucune branche créée) · **Base** : `develop`
**Task** : T001e (spec 025) — snapshot de gouvernance de la dépense serverless au grain
`(cloud_provider, workspace_id, serverless_surface)`, alimente la matrice de couverture du bloc 2
**Diff** : 7 fichiers, **+1 221 / −0** — 2 fichiers créés (689 l.), 5 modifiés (+532 l.)
**Rien n'est stagé, rien n'est committé, rien n'est déployé, aucun job lancé.**

## Ce qu'il faut trancher avant déploiement

**Un seul point, et il n'est pas de T001e : le job `dcm_gold_dbx_compute` n'a pas de `run_as`.**
Il s'exécute donc sous l'identité de qui déploie. C'est **pré-existant et transverse aux 8 jobs**
du bundle (déjà signalé en T001d), hors périmètre de cette task, et non bloquant pour `dev` — mais
bloquant avant un déploiement **prod**, et seul toi peux fournir le nom du service principal.
Ma tâche n'introduit pas la violation et n'en hérite pas d'autre.

Aucune de tes trois décisions du §5 de la baseline ne s'est révélée fausse à la mesure. **Une
valeur de la baseline elle-même est imprécise** et je ne l'ai pas publiée telle quelle : voir §5.

## 1. Ce qui change, fichier par fichier

| Fichier | Nature |
|---|---|
| `pipelines/gold_dbx_compute/serverless_governance.py` | **créé** (397 l.) — le builder |
| `pipelines/gold_dbx_compute/specs.py` | +249 l. — `GOLD_SERVERLESS_GOVERNANCE`, les clés de merge, le commentaire de table, 19 commentaires de colonnes, `SERVERLESS_GOVERNANCE_SPEC`, entrée du registre |
| `pipelines/gold_dbx_compute/entrypoint.py` | +11 l. — import + entrée de dispatch |
| `resources/job_dcm_gold_dbx_compute.yml` | +20 l. — tâche `gold_serverless_governance` |
| `tests/gold_dbx_compute/test_serverless_governance.py` | **créé** (292 l.) — 13 tests |
| `tests/gold_dbx_compute/test_specs.py` | +154 l. — 7 tests |
| `tests/gold_dbx_compute/test_entrypoint.py` | +98 l. — 5 tests |

### Le gabarit : un snapshot, pas une série temporelle

`SERVERLESS_GOVERNANCE_SPEC` reprend exactement le gabarit `CLUSTER_GOVERNANCE_SPEC` que tu as
désigné : `watermark_column=None`, `initial_mode="full"`, `incremental_lookback_days=None`,
`absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD`. Conséquence assumée : recalcul complet
à chaque run sur une fenêtre de **90 jours** (`GOVERNANCE_ACTIVITY_WINDOW_DAYS = max(ROLLING_WINDOWS)`),
et suppression des lignes que le recalcul ne produit plus après le délai de grâce de 7 jours —
sans quoi une surface qui cesse de coûter survivrait indéfiniment dans la matrice avec ses derniers
pourcentages, présentés comme courants.

`source_tables = (CURATED_BILLING_USAGE, CURATED_BILLING_LIST_PRICES)` : **la facturation, pas
`gold_dbx_compute_serverless_cost_daily`**, conformément au §5.2 de la baseline. Le builder
réutilise sans les réécrire les 8 helpers de `sql_helpers.py` (`serverless_scope_predicate`,
`serverless_surface_case_expr`, `serverless_object_id_expr`, `SERVERLESS_OBJECT_ID_SENTINEL`,
`identity_principal_expr`, `identity_source_expr`, `tag_present_sql`, `lower_bound_predicate`) :
zéro SQL de périmètre recopiée, donc aucune divergence possible avec les tables T001d.

### Chaîne de CTE, et pourquoi elle est faite comme ça

`usage_filtered` → `keyed` → `priced` → `surface_grain` → `coverage` → (`policy_grain` →
`policy_inventory`) + `measured_window` → SELECT final.

- **`priced` n'agrège pas, volontairement.** C'est tout l'enjeu du §5.2 : toutes les mesures sont
  des parts de **dollars évaluées ligne à ligne**. Une pré-agrégation ferait hériter une identité,
  un tag ou une policy à des lignes qui n'en portent pas — les 98,54 $ d'orphelins d'`AI_ENDPOINT`
  disparaissent ainsi au grain jour-objet. Trois tests verrouillent l'absence de `GROUP BY` dans
  `usage_filtered`, `keyed` et `priced`.
- **Les pourcentages sont dans une CTE `coverage` dédiée** (`SELECT *, …`) et non dans le SELECT
  final : chaque part est ainsi rapportée au coût de **la même ligne de grain**, sans préfixe
  d'alias, et les lignes restent sous les 100 caractères de `ruff`.
- **L'inventaire des policies passe par deux niveaux.** `policy_grain` agrège d'abord par
  `budget_policy_id` : un `collect_list` appliqué directement à `priced` rendrait une entrée par
  ligne de facturation (des millions), pas une par politique. `COUNT(*)` sur `policy_grain` **est**
  le `COUNT(DISTINCT budget_policy_id)`.
- **`measured_window` groupe par cloud.** Les deux clouds sont deux flux de collecte distincts
  (retard de facturation 3 à 8 jours) : un `MAX(usage_date)` global masquerait le retard de l'un
  derrière l'avance de l'autre.

### Les 19 colonnes et leur formule

| Colonne | Formule |
|---|---|
| `cloud_provider`, `workspace_id` | tels quels depuis la facturation — clés de merge |
| `serverless_surface` | `serverless_surface_case_expr()`, 12 valeurs, `ELSE 'OTHER'` — clé de merge, **jamais NULL** |
| `cost_usd` | `SUM(usage_quantity * COALESCE(effective_price, 0))`, toutes unités de facturation ; dénominateur de toutes les parts |
| `cost_usd_with_owner_tag` | `SUM(CASE WHEN tag_present_sql(custom_tags, OWNER_TAG_KEYS) THEN line_cost_usd ELSE 0 END)` |
| `owner_tag_coverage_pct` | `cost_usd_with_owner_tag / NULLIF(cost_usd, 0) * 100` |
| `cost_usd_with_cost_center_tag` | idem avec `COST_CENTER_TAG_KEYS` |
| `cost_center_tag_coverage_pct` | `cost_usd_with_cost_center_tag / NULLIF(cost_usd, 0) * 100` |
| `cost_usd_with_budget_policy` | `SUM(CASE WHEN usage_metadata.budget_policy_id IS NOT NULL THEN line_cost_usd ELSE 0 END)` |
| `budget_policy_coverage_pct` | `cost_usd_with_budget_policy / NULLIF(cost_usd, 0) * 100` |
| `cost_usd_without_identity` | `SUM(CASE WHEN identity_principal_expr() IS NULL THEN line_cost_usd ELSE 0 END)` — cascade `run_as` → `owned_by` → `created_by` |
| `identity_coverage_pct` | `(cost_usd - cost_usd_without_identity) / NULLIF(cost_usd, 0) * 100` — **la soustraction**, pas un second `SUM` : la part et le numérateur ne peuvent pas se contredire |
| `cost_usd_without_object_key` | `SUM(CASE WHEN object_id <> '_NO_OBJECT' THEN 0 ELSE line_cost_usd END)` |
| `identity_source_mix` | `concat_ws('+', sort_array(collect_set(identity_source)))` — ensemble trié, non pondéré |
| `budget_policy_count` | `COALESCE(COUNT(*) sur policy_grain, 0)` |
| `budget_policy_inventory` | `sort_array(collect_list(named_struct('cost_usd', policy_cost_usd, 'budget_policy_id', budget_policy_id)), false)` — NULL si aucune policy |
| `window_start` | `DATE '<activity_lower_bound>'` = jour du run − 90 j, **la borne réellement filtrée** |
| `window_end` | `MAX(usage_date)` des lignes du périmètre **pour ce cloud** |
| `_generated_at` | `current_timestamp()` |

Trois choix de forme qui ne se déduisent pas du code, et qui sont documentés dans le commentaire
de table pour que personne ne « complète » la table :

1. **Un numérateur en dollars par axe, plus sa part** ; le complémentaire se soustrait de
   `cost_usd` et n'est pas publié. Le numérateur retenu est celui que la gouvernance doit lire :
   les dollars **couverts** pour les tags et les policies, les dollars **orphelins** pour
   l'identité (à 97,8 % de couverture, c'est le résidu qui porte l'information).
2. **`NULLIF(cost_usd, 0)` partout** : une part de dollars n'est pas définie sans dollars.
   Ce n'est pas théorique — **90 des 1 316 lignes** produites coûtent 0 $ (SKU `GENIE_FREE_USAGE`,
   DBU gratuits) et sortent donc à NULL et non à 0 %.
3. **La clé de tri est le PREMIER champ du struct** de l'inventaire : `sort_array` compare les
   structs champ par champ dans l'ordre de déclaration. Permuter les deux champs trierait par
   identifiant, silencieusement, sans changer la forme du schéma (mutation M11).

### `entrypoint.py` et le YAML

Dispatch `"serverless_governance"` → `build_serverless_governance(...)` avec
`activity_lower_bound = today - timedelta(days=GOVERNANCE_ACTIVITY_WINDOW_DAYS)`, `today` venant du
`datetime.now(UTC)` unique du run (déjà en place). La tâche `gold_serverless_governance` porte
`environment_key: gold_compute_env` (réutilise l'environnement serverless du job, aucun compute
supplémentaire), `max_retries: 0`, et **aucun `depends_on`** : ce snapshot ne lit aucune table gold.
Le commentaire du YAML porte la raison chiffrée, sinon la prochaine relecture « corrigera » en le
chaînant derrière `gold_serverless_cost_daily`.

## 2. Contrôles read-only contre la baseline

Profil OAuth **`dcm-dev`** uniquement, warehouse `DCM-metrics`, Statement Execution API. **Aucune
écriture, aucun DDL, aucun job lancé.** Les requêtes de contrôle **enveloppent la requête
réellement générée** par `build_serverless_governance` — elle est capturée en important le module
(`spark.sql` bouchonné), jamais retranscrite à la main :

```python
spark = _CaptureSpark()
build_serverless_governance(
    spark,
    billing_usage_table="it.ba_data_connect_monitoring__d.curated_dbx_billing_usage",
    billing_list_prices_table="it.ba_data_connect_monitoring__d.curated_dbx_billing_list_prices",
    activity_lower_bound=date(2026, 6, 12),   # = 2026-09-10 − 90 j, la fenêtre de référence
)
src = f"({spark.query}) g"      # puis : SELECT … FROM {src} GROUP BY …
```

### Contrôle 1 + 4 — coût et couvertures par cloud

`SELECT cloud_provider, ROUND(SUM(cost_usd),2), ROUND(SUM(cost_usd_with_owner_tag)/SUM(cost_usd)*100,1), … FROM {src} GROUP BY ROLLUP (cloud_provider)`

| cloud | `cost_usd` | owner | cc | policy | identité | orphelins $ | sans objet $ | surfaces | fenêtre |
|---|---|---|---|---|---|---|---|---|---|
| aws | **767 022,09** | 4,0 % | 11,5 % | 7,6 % | 97,9 % | 15 931,23 | 61 846,43 | **12** | 2026-06-12 → 2026-09-09 |
| azure | **269 200,25** | 0,6 % | 42,8 % | 29,8 % | 97,6 % | 6 533,14 | 17 433,02 | **11** | 2026-06-12 → 2026-09-09 |
| **total** | **1 036 222,34** | **3,1 %** | **19,6 %** | **13,4 %** | **97,8 %** | 22 464,37 | 79 279,45 | 12 | — |

→ contrôles **1** (coût bi-cloud et par cloud), **4** (owner 3,1 % / cost center 19,6 %) et **5**
(12 surfaces aws, **11** azure — aucune ligne fabriquée pour `OTHER` côté azure) **conformes au
chiffre près**. `window_start` = 2026-06-12 et `window_end` = 2026-09-09 sur les deux clouds :
la fenêtre publiée est bien celle mesurée.

### Contrôles 2 + 3 — par surface et par cloud

Même requête groupée par `(serverless_surface, cloud_provider)`. Les 23 lignes reproduisent le §2
de la baseline **à la valeur exacte** ; extraits qui portent les contrôles demandés :

| surface | cloud | `cost_usd` | owner | cc | policy | identité | sans objet | policies |
|---|---|---|---|---|---|---|---|---|
| `SQL_WAREHOUSE` | aws | 372 051,29 | 0,3 | 6,4 | **0,0** | 100,0 | 0,0 | **0** |
| `SQL_WAREHOUSE` | azure | 86 154,39 | 1,4 | 42,7 | **0,0** | 100,0 | 0,0 | **0** |
| `JOB` | aws | 159 889,00 | 18,4 | 34,9 | 19,6 | 100,0 | 0,0 | 51 |
| `JOB` | azure | 73 746,24 | 0,1 | 69,8 | 67,2 | 100,0 | 0,0 | 18 |
| `NOTEBOOK` | aws / azure | 61 599,21 / 12 733,65 | 0,0 / 0,6 | 12,3 / 40,5 | 23,5 / 40,9 | 100,0 | 1,1 / 9,9 | 71 / 28 |
| `AI_ENDPOINT` | aws / azure | 35 424,43 / 15 642,26 | 0,0 | 0,0 / 39,9 | 2,7 / 32,3 | **99,6 / 96,8** | 1,1 / 0,0 | 2 / 4 |
| `LAKEBASE` | aws / azure | 12 780,30 / 5 265,96 | 0,0 | 0,5 / 53,6 | 7,9 / 53,6 | **5,5 / 0,1** | 9,6 / 0,3 | 7 / 3 |
| `NETWORKING` | aws / azure | 3 704,84 / 767,83 | 0,0 / 0,3 | 0,0 | 0,0 | **0,0 / 0,0** | **100,0** | 0 |
| `GENIE` / `PLATFORM_AUTO` / `OTHER` | aws+azure | 35 652,51 / 35 582,92 / 6,56 | — | — | 0,0 / ~0,3 / 0,0 | 100,0 / 100,0 / **0,3** | **100,0** | 0 / 9 / 0 |

→ contrôle **2** : couverture policy `SQL_WAREHOUSE` **0,0 % et 0 policy distincte sur les deux
clouds**, pour **458 205,68 $** cumulés (372 051,29 + 86 154,39) = **44 % du serverless bi-cloud**.
C'est le levier le plus lourd de la page, et il est **absent de la story** — il est donc porté dans
le commentaire de `budget_policy_coverage_pct` et dans la docstring du module.
→ contrôle **3** : identité 97,8 % bi-cloud, `NETWORKING` **0,0 %** sur les deux clouds,
`LAKEBASE` **5,5 % aws / 0,1 % azure**, et `AI_ENDPOINT` **n'est pas à 100 %** (99,6 / 96,8),
contrairement à la story. `NETWORKING` + `LAKEBASE` concentrent ~97 % des 22 464,37 $ orphelins.
→ `no_object` vaut **100 %** pour `GENIE`, `PLATFORM_AUTO`, `NETWORKING` et `OTHER` : ce que le
commentaire de `cost_usd_without_object_key` affirme est mesuré, pas déduit.

### Contrôle 6 — clés de merge, et ce que `merge_into_table` ferait d'une NULL

```sql
SELECT COUNT(*), SUM(CASE WHEN cloud_provider IS NULL THEN 1 ELSE 0 END), … FROM {src}
```

| lignes | `cloud_provider` NULL | `workspace_id` NULL | `serverless_surface` NULL | `identity_source_mix` NULL | `window_end` NULL | lignes à 0 $ | dont un pct non NULL |
|---|---|---|---|---|---|---|---|
| 1 316 | **0** | **0** | **0** | 0 | 0 | 90 | **0** |

→ contrôle **6** : **0 clé de merge NULL**. C'était la vérification que tu demandais explicitement,
parce que `merge_into_table` fusionne sur `<=>` null-safe : une clé NULL ne lève pas, elle fond un
workspace entier en une ligne. Les jointures finales du builder peuvent donc rester en `=`.
Bonus mesuré : les **90 lignes à 0 $** sortent toutes avec des pourcentages **NULL** — la décision
`NULLIF` n'est pas cosmétique, sans elle 6,8 % des lignes afficheraient « 0 % couvert ».

### Contrôle 7 — la somme des surfaces d'un cloud, par un chemin indépendant

Comparaison avec `gold_dbx_compute_serverless_cost_daily` (chaîne T001d, déjà en table) sur la même
fenêtre : `SELECT cloud_provider, ROUND(SUM(cost_usd),2) FROM …serverless_cost_daily WHERE period_start >= DATE '2026-06-12' GROUP BY ROLLUP (cloud_provider)`

| cloud | table quotidienne T001d | ma table |
|---|---|---|
| aws | 767 022,09 | 767 022,09 |
| azure | 269 200,25 | 269 200,25 |
| total | 1 036 222,34 | 1 036 222,34 |

→ contrôle **7** : égalité **au centime** par un chemin de calcul indépendant. Cela valide trois
choses d'un coup : le `CASE` de surface **partitionne** les lignes (aucune perte, aucun double
comptage), la jointure de prix ne **duplique** aucune ligne (fenêtres de validité non
chevauchantes), et sommer les surfaces d'un même cloud est bien légitime.

### Contrôles supplémentaires que je me suis imposés

| Contrôle | Requête | Résultat |
|---|---|---|
| Politiques distinctes par cloud, reconstruites en explosant l'inventaire | `LATERAL VIEW explode(budget_policy_inventory)` + `COUNT(DISTINCT p.budget_policy_id)` | **49 aws / 20 azure** = les 69 du §1 de la baseline. La méthode que promet le commentaire de `budget_policy_count` fonctionne donc réellement |
| Ordre de l'inventaire | `budget_policy_inventory[0].cost_usd = array_max(transform(…, x -> x.cost_usd))` sur les lignes à ≥ 2 policies | **0 ligne mal triée** sur 37 — le tri décroissant par coût est effectif |
| Taille max de l'inventaire | `MAX(size(budget_policy_inventory))` | 11 (`NOTEBOOK` aws) ; NULL là où `budget_policy_count = 0` |

## 3. Campagne de mutation — 25 mutations, 25 tuées

Méthode : chaque mutation est appliquée au **code de production**, la suite `tests/gold_dbx_compute`
est rejouée, puis le fichier est restauré (`try/finally`). Une mutation dont l'ancre ne matche pas
exactement une fois est comptée comme **survivante** (aucune mutation n'a été perdue ainsi).

| # | Mutation (chacune est une erreur plausible, pas un sabotage arbitraire) | Tuée par |
|---|---|---|
| M01 | couverture booléenne « au moins un tag » au lieu des clés nommées | `test_governance_never_publishes_a_boolean_tag_coverage` |
| M02 | `window_start` figé, décorrélé de la fenêtre filtrée | `test_governance_publishes_the_window_it_actually_filtered` |
| M03 | filtre de fenêtre retiré (snapshot non borné) | 3 tests, dont `…_scope_is_the_activity_window` |
| M04 | périmètre réduit au seul `is_serverless` (liste blanche perdue) | `test_governance_scope_is_the_serverless_whitelist_bounded_by_the_window` |
| M05 | `serverless_surface` prise ailleurs → clé de merge nullable | `test_governance_keeps_the_surface_case_that_makes_the_merge_key_non_nullable` |
| M06 | pré-agrégation avant la mesure (le piège du §5.2) | `test_governance_measures_are_computed_line_by_line` |
| M07 | `usage_policy_id` au lieu de `budget_policy_id` | `test_governance_policy_count_is_zero_when_measured_…` |
| M08 | `NULLIF` retiré → 0 % au lieu de NULL | `test_governance_coverage_pct_is_null_and_not_zero_without_dollars` |
| M09 | couverture identité = part orpheline (complémentaire inversé) | `test_governance_identity_coverage_is_the_complement_of_the_orphan_dollars` |
| M10 | absence d'objet détectée sur NULL au lieu de la sentinelle | `test_governance_counts_the_dollars_without_object_key_on_the_sentinel` |
| M11 | champs du `named_struct` permutés → tri par identifiant | `test_governance_policy_inventory_sorts_by_cost_and_not_by_identifier` |
| M12 | inventaire trié par coût **croissant** | idem M11 |
| M13 | `budget_policy_count` NULL au lieu de 0 | `test_governance_policy_count_is_zero_when_measured_…` |
| M14 | `window_end` mesuré par surface et non par cloud | `test_governance_window_end_is_measured_per_cloud` |
| M15 | `identity_source_mix` réduit à `MAX(identity_source)` | `test_governance_identity_coverage_…` |
| M16 | une colonne retirée du SELECT final | `test_governance_output_columns_match_the_published_comments` |
| M17 | inventaire agrégé par jour au lieu de par policy | `test_governance_policy_inventory_sorts_by_cost_…` |
| M18 | spec : watermark ajouté (le snapshot devient incrémental) | 2 tests (spec + MERGE) |
| M19 | spec : garde-fou de suppression retiré | 2 tests (spec + MERGE) |
| M20 | spec : source déclarée = la table quotidienne gold | `test_serverless_governance_sources_the_billing_lines_not_the_daily_gold_table` |
| M21 | spec : `serverless_surface` retirée des clés de merge | `test_serverless_governance_is_a_bounded_snapshot_at_the_surface_grain` |
| M22 | spec : commentaire de colonne orphelin (`window_end` → `as_of_date`) | 2 tests de parité colonnes/commentaires |
| M23 | spec : mesure booléenne « au moins un tag » publiée | 3 tests |
| M24 | entrypoint : builder câblé sur la table quotidienne gold | `test_main_wires_serverless_governance_to_the_billing_lines_not_to_the_daily_gold` |
| M25 | entrypoint : fenêtre de gouvernance remplacée par une autre fenêtre **importée** | `test_main_serverless_governance_scope_is_the_activity_window` |

Deux points de méthode issus de ta consigne :

- **Les assertions négatives passent par `_code_only()`**, qui retire les commentaires SQL. La
  requête générée est très commentée et ses commentaires **citent** les constructions interdites
  (`size(custom_tags) > 0`, `usage_policy_id`, `object_id IS NULL`…) : sans ce filtre, un
  `"X" not in query` serait satisfait par le commentaire qui explique justement pourquoi X est faux.
- Deux mutations ont été **renforcées après un premier passage trop facile** :
  `GROUP BY cloud_provider` était vérifié par un `in` que M14 satisfaisait encore en ajoutant une
  colonne de regroupement → l'assertion est devenue un `endswith` exact ; et M25 a été rejouée avec
  une constante **réellement importée** (`FORECAST_OBSERVED_LOOKBACK_DAYS`), la première version
  échouant sur un `NameError` — ce qui aurait compté un kill pour la mauvaise raison.

## 4. Gates

| Gate | Résultat |
|---|---|
| `.venv/bin/python -m pytest -q` | ✅ **846 passed** (821 avant, **+25**, **0 retiré**) |
| `.venv/bin/python -m ruff check` sur les 7 fichiers touchés | ✅ **All checks passed** |
| `.venv/bin/python -m ruff check` (paquet entier) | 269 erreurs — **identique à l'existant**, toutes sur les 3 modules DLT historiques, **0 dans mes fichiers** |
| `mypy pipelines/gold_dbx_compute/` | 10 erreurs, **toutes dans `forecast.py`** (non touché) ; **0 dans mes fichiers** |
| `mypy` sur les 3 fichiers de tests touchés | 1 erreur pré-existante (`test_entrypoint.py:452`, section T001b) ; **0 nouvelle** — le `no-any-return` de mon helper a été corrigé par une annotation locale |
| `databricks bundle validate -t dev -p dcm-dev` | ✅ **Validation OK!** |

Les 25 nouveaux tests : 13 sur le SQL généré (`test_serverless_governance.py`), 7 sur la spec et
les commentaires publiés (`test_specs.py`), 5 sur le dispatch, le MERGE et **le YAML du job**
(`test_entrypoint.py`). Ce dernier verrouille un trou que rien ne couvrait : une clé du registre
qu'aucune tâche n'exécute donne une table qui n'existe jamais, sans qu'aucun test de code ne le voie.

## 5. Ce que je corrige de la baseline, et ce que je n'ai pas relitigé

**Une valeur de la baseline est imprécise, et je ne l'ai pas publiée telle quelle.** Le §0 annonce
« ≈ 22 800 $ » de dollars sans propriétaire sur 90 jours. La mesure donne **22 464,37 $**
(15 931,23 aws + 6 533,14 azure) — l'écart de ~335 $ vient de ce que 22 800 est reconstruit depuis
le pourcentage arrondi (2,2 % × 1 036 222,34 = 22 797), alors que 22 464,37 / 1 036 222,34 = 2,168 %
arrondit bien à 2,2 %. Le commentaire de colonne publié dans Unity Catalog porte donc la valeur
**mesurée**, avec sa répartition par cloud et les 4 472,67 $ intégralement orphelins de `NETWORKING`.
J'ai aussi ajouté au commentaire de `cost_usd_without_object_key` son total mesuré
(79 279,45 $, soit 7,6 % de la dépense) : la colonne n'en portait aucun ordre de grandeur.

Appliqué sans relitiger, comme demandé — et vérifié :

- **`OWNER_TAG_KEYS` n'a pas été touchée.** 3,1 % est publié tel quel, avec un commentaire qui
  nomme l'angle mort, renvoie vers `identity_coverage_pct` (97,8 %) pour ne pas faire lire « la
  dépense n'a pas de responsable », et **nomme les candidats écartés** : aws `CreatorEmail` 3,7 % /
  `CreateBy` 3,2 % (injectés par Databricks), azure `AppOwner` 5,3 % / `CyberContact` 5,3 % (tags
  TTE délibérés, à arbitrer séparément). Raison du non-touché : la constante est partagée avec
  `cluster_governance`, y ajouter une graphie changerait des chiffres de conformité **déjà publiés**
  par cette autre table.
- **Aucune mesure « au moins un tag »**, sur les deux clouds : côté azure la clé plateforme
  `Environment` couvre 100,0 % de la dépense, une couverture booléenne afficherait 0 % de non-tagué.
- **Aucun nom de policy promis** : `system.billing` n'expose que `account_prices`,
  `attributed_usage`, `list_prices` et `usage`. Le commentaire dit l'absence **et sa cause**, et
  donne la méthode de recomptage par explosion de l'inventaire (vérifiée, cf. §2).
- **Chaque chiffre publié porte sa fenêtre et son cloud**, commentaire de table comme commentaires
  de colonnes. Un test parcourt tous les commentaires en `_pct` et exige la fenêtre
  `2026-06-12..2026-09-09`, les deux clouds, et la mention du cas 0 $.

## 6. Ce qui n'est pas fait, et pourquoi

- **Aucun déploiement, aucun `bundle run`, aucun commit, rien de stagé** — un run est en file sur
  `dcm_gold_dbx_compute` (`max_concurrent_runs: 1`). Les fichiers sont laissés non stagés pour
  `/speckit.dcm.review --commit`.
- **La table n'existe pas encore en dev** : elle sera créée au premier run de la tâche
  (`saveAsTable`, cible absente), puis mise à jour en MERGE. Tous les chiffres du §2 sont donc
  mesurés en **exécutant la requête du builder à la volée**, pas en lisant la table cible.
- **`run_as` non ajouté** : hors périmètre T001e, transverse aux 8 jobs, et il faut un nom de
  service principal que seul toi peux fournir (cf. en tête).
- **`_surface_list_sql` dupliqué dans `serverless_cost_daily.py`** (relevé de la revue T001d) :
  non factorisé ici, mon builder n'en a pas besoin et toucher T001d dépasserait la task.
- **Pas de `partitioned_by` / `cluster_by`** sur la table : 1 316 lignes, un `OPTIMIZE` ou un
  partitionnement y coûterait plus que le scan complet.
- **`window_start` n'est pas une clé de merge** : la table décrit **l'état courant**, pas une série
  d'états. Si la page devait un jour comparer deux fenêtres, ce serait une autre table (et il
  faudrait alors retirer le garde-fou de suppression).
