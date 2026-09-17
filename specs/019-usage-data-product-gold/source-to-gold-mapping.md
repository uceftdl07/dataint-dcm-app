# Mapping source -> curated -> gold

## Perimetre reel de la feature 019

Les 8 tables gold du registre `pipelines/gold_dbx_usage/specs.py::GOLD_SPECS`:

- `gold_dbx_usage_table_daily`
- `gold_dbx_usage_table_popularity_daily`
- `gold_dbx_usage_consumer_daily`
- `gold_dbx_usage_table_query_performance_daily`
- `gold_dbx_usage_table_catalog`
- `gold_dbx_usage_table_governance`
- `gold_dbx_usage_recommendations`
- `gold_dbx_usage_forecast_daily`

Les 7 premieres sont ecrites par le job `dcm_gold_dbx_usage`
(`resources/job_dcm_gold_dbx_usage.yml`). `forecast_daily` est ecrite par le job
`dcm_gold_forecast` (`resources/job_dcm_gold_forecast.yml`, tache
`gold_usage_forecast_daily`) : `ai_forecast` exige un SQL Warehouse
Pro/Serverless, incompatible avec l'environnement serverless generique du job
quotidien.

`gold_dbx_usage_dim_workspace` est hors perimetre : remplacee par
`dim_dbx_workspace` de la spec 020.

Toutes les tables gold utilisent `cloud_provider` pour eviter les collisions Azure/AWS. Aucune ne contient `workspace_id`, `source_lz_id` ni `subscription_or_account_id` : `workspace_id` sert de cle de jointure vers les sources curated, jamais de colonne de sortie.

## Vue bout en bout

```text
system.access.table_lineage
  -> curated_dbx_access_table_lineage
  -> table_daily / popularity_daily / query_performance_daily

system.access.audit
  -> curated_dbx_access_audit
  -> table_daily (getTable)

system.access.audit [actions d'ecriture]
  -> curated_dbx_uc_table_operations
  -> table_catalog

system.query.history
  -> curated_dbx_query_history
  -> table_daily / query_performance_daily

system.billing.usage + system.billing.list_prices
  -> curated_dbx_billing_usage + curated_dbx_billing_list_prices
  -> table_daily

system.information_schema.tables
  -> curated_dbx_uc_tables
  -> table_daily / table_catalog

system.information_schema.table_tags
  -> curated_dbx_uc_table_tags
  -> table_popularity_daily / table_catalog

table_daily
  -> table_popularity_daily / consumer_daily / table_catalog

table_popularity_daily + table_catalog
  -> table_governance

table_governance + table_catalog + table_popularity_daily
  + table_query_performance_daily + consumer_daily
  -> recommendations

table_popularity_daily
  -> forecast_daily [job dcm_gold_forecast, ai_forecast sur SQL Warehouse]
```

## Sources system et tables curated

| Source system | Table curated | Role |
|---|---|---|
| `system.access.table_lineage` | `curated_dbx_access_table_lineage` | Evenements de lecture/ecriture entre table source et cible; identite et type d'entite; `statement_id` pour rejoindre l'historique SQL. |
| `system.access.audit` actions d'acces | `curated_dbx_access_audit` | Acces directs `getTable` non couverts par un lineage SQL; statut de reponse et identite. |
| `system.access.audit` actions d'ecriture | `curated_dbx_uc_table_operations` | Derniere operation UC qualifiee, horodatage et auteur. La cible est extraite de `request_params`. |
| `system.query.history` | `curated_dbx_query_history` | Statut, duree, lignes/octets lus ET ecrits (`written_rows`, `written_bytes`), compute et identite d'une requete; jointure par `(cloud_provider, workspace_id, statement_id)`. |
| `system.billing.usage` | `curated_dbx_billing_usage` | Quantite facturee par compute, SKU et jour. |
| `system.billing.list_prices` | `curated_dbx_billing_list_prices` | Prix effectif par SKU et fenetre de validite. |
| `system.information_schema.tables` | `curated_dbx_uc_tables` | Registre des tables UC: type, proprietaire, creation, derniere alteration. |
| `system.information_schema.table_tags` | `curated_dbx_uc_table_tags` | Tags `owner`, `domain`, `cost_center`, `classification`, `data_product`. |

## Gold 1: `gold_dbx_usage_table_daily`

**Grain / cle:** `(cloud_provider, catalog, schema, table_name, consumer_id, period_start)`.

**Sources et calcul:**

- Lit `curated_dbx_access_table_lineage` pour les lectures dont le data product est `source_table_full_name`.
- Separe les lignes `entity_type = 'DBSQL_QUERY'` des acces directs (`JOB`, `NOTEBOOK`, `DASHBOARD_V3`, `PIPELINE` ou type NULL).
- Rejoint les requetes SQL a `curated_dbx_query_history` par `statement_id`, jamais par `entity_id`.
- Ajoute les acces directs `getTable` de `curated_dbx_access_audit`.
- Rejoint la facturation et les prix pour estimer le cout compute; le cout/duree d'une requete multi-table est reparti a parts egales (`equal_parts_fallback`).
- Ajoute une branche d'ECRITURE: les cibles de lineage (`target_*`, types `TABLE`/`MATERIALIZED_VIEW`/`STREAMING_TABLE`) jointes a `curated_dbx_query_history` par `statement_id`. Cette branche alimente `rows_written`, `data_written_bytes` et `last_used_at`, et rien d'autre: elle emet `request_count = 0` puisque le meme statement est deja compte par la branche de lecture.
- Resout le registre `curated_dbx_uc_tables` pour `unknown_data_product` et `catalog_resolution_status`.
- Agrege par jour, data product et consommateur.

| Champ | Description |
|---|---|
| `usage_date` | Alias de `period_start`, conserve pour compatibilite historique. |
| `catalog` | Catalogue Unity Catalog extrait du nom qualifie de la table. |
| `schema` | Schema Unity Catalog extrait du nom qualifie de la table. |
| `table_name` | Nom de la table du data product. |
| `table_full_name` | Nom qualifie derive: `catalog.schema.table_name`. |
| `consumer_id` | Identite consommatrice issue de `created_by`, `executed_by` ou `user_identity`. |
| `consumer_name` | Libelle UI; aligne sur `consumer_id`. |
| `cloud_provider` | Fournisseur d'origine du run d'ingestion: `azure` ou `aws`. |
| `period_start` | Jour d'agregation. |
| `request_count` | Nombre d'acces ou de requetes du groupe. Une table uniquement ecrite porte `request_count = 0` et un volume ecrit non nul: la branche d'ecriture n'ajoute pas de requete. |
| `rows_read` | Lignes lues, reparties entre les tables sources d'une requete. NULL (jamais `0`) quand la lecture n'est pas mesurable: acces `getTable` de l'audit, ou lineage sans `statement_id` joignable. |
| `rows_written` | `query_history.written_rows` reparti a parts egales entre les tables CIBLES du statement. NULL (jamais `0`) quand le statement n'est pas joignable, cas des ecritures de pipelines DLT. |
| `data_read_bytes` | Octets lus, repartis entre les tables sources d'une requete. NULL (jamais `0`), meme raison que `rows_read`. |
| `data_written_bytes` | `query_history.written_bytes` reparti a parts egales entre les tables CIBLES du statement. NULL (jamais `0`), meme raison que `rows_written`. |
| `duration_seconds` | Duree compute attribuee au data product, en secondes. NULL quand aucun statement n'est joignable. |
| `estimated_cost_usd` | Cout compute attribue; NULL si la facturation ou le prix ne peut pas etre resolu. Le partage a parts egales porte sur tous les objets sources, vues incluses: une table lue via une vue partage son cout avec cette vue. |
| `costed_request_count` | Sous-ensemble de `request_count` dont le cout a pu etre calcule. `< request_count` signale un `estimated_cost_usd` SOUS-ESTIME; `0` va de pair avec un cout NULL. |
| `cost_attribution_method` | `equal_parts_fallback` quand un cout a ete calcule, NULL sinon: la colonne trace un calcul effectue, pas une intention. |
| `cost_basis` | Seau de facturation dont le prorata de duree tire le cout: `warehouse_prorata` (seul prorata fidele), `serverless_job_prorata`, `cluster_prorata`, ou `mixed` quand le groupe additionne plusieurs seaux, donc des grandeurs differentes. NULL quand aucun cout n'est calcule. |
| `consumer_type` | `USER`, `SERVICE_PRINCIPAL`, type d'entite du lineage repris tel quel (`JOB`, `NOTEBOOK`, `PIPELINE`, `DASHBOARD_V3`) ou `UNKNOWN`. Vocabulaire non ferme hors branche audit: la valeur y est `COALESCE(entity_type, 'UNKNOWN')`. Jamais NULL. |
| `failed_access_count` | Nombre d'acces ou de requetes en echec; SQL: `FAILED`/`CANCELED`, audit: statut HTTP non succes. |
| `last_used_at` | Dernier horodatage d'acces du groupe, lectures et ecritures confondues. |
| `unknown_data_product` | Vrai si `(catalog, schema, table_name)` n'est pas present dans `curated_dbx_uc_tables`; la ligne est conservee. Confond « hors registre » et « invisible du pipeline »: lire `catalog_resolution_status` pour trancher. |
| `catalog_resolution_status` | `RESOLVED`, `NOT_VISIBLE_TO_PIPELINE` (un acces a reussi, donc l'objet existe, mais le pipeline n'a pas le privilege de le voir dans `system.information_schema.tables`) ou `NEVER_RESOLVED` (aucun acces reussi). |
| `_generated_at` | Horodatage de generation de la ligne gold. |

## Gold 2: `gold_dbx_usage_table_popularity_daily`

**Grain / cle:** `(cloud_provider, catalog, schema, table_name, period_start)`.

**Sources et calcul:**

- Agrege `gold_dbx_usage_table_daily` par data product et jour.
- Rejoint `curated_dbx_access_table_lineage` pour le fan-out aval (`COUNT(DISTINCT entity_id)`).
- Pivote `curated_dbx_uc_table_tags` pour `owner` et `domain`.
- Compare avec le jour precedent par auto-jointure, avec un jour de marge lors d'un run incremental.

| Champ | Description |
|---|---|
| `cloud_provider` | Fournisseur cloud. |
| `catalog` | Catalogue Unity Catalog. |
| `schema` | Schema Unity Catalog. |
| `table_name` | Nom de la table. |
| `table_full_name` | Nom qualifie derive. |
| `owner` | Valeur du tag UC `owner`. |
| `domain` | Valeur du tag UC `domain`. |
| `period_start` | Jour d'agregation. |
| `distinct_consumers` | Nombre d'identites consommatrices distinctes. |
| `request_count` | Total des acces/requetes. |
| `rows_read` | Total des lignes lues. |
| `data_read_bytes` | Total des octets lus. |
| `estimated_cost_usd` | Total des couts attribues. |
| `consumers_by_type` | Map `consumer_type -> nombre de consommateurs distincts`. |
| `downstream_fanout` | Nombre d'entites aval distinctes dependantes du data product. |
| `popularity_rank` | `RANK()` sur `request_count` decroissant, partitionne par `(cloud_provider, period_start)`. Rang JOURNALIER: il ne peut pas servir de classement sur une periode, qui se recalcule en sommant puis en reclassant. |
| `request_count_prev_day` | `request_count` du jour precedent. |
| `request_delta_pct` | Variation en pourcentage par rapport au jour precedent. |
| `_generated_at` | Horodatage de generation. |

## Gold 3: `gold_dbx_usage_consumer_daily`

**Grain / cle:** `(cloud_provider, consumer_id, period_start)`.

**Source et calcul:**

- Lit uniquement `gold_dbx_usage_table_daily`.
- Compte les data products distincts par `table_full_name`.
- Agrege volume, duree et cout par consommateur.
- Resout `consumer_type` avec une priorite explicite, plutot qu'un `MAX` alphabetique.

| Champ | Description |
|---|---|
| `cloud_provider` | Fournisseur cloud. |
| `consumer_id` | Identite consommatrice. |
| `consumer_name` | Libelle lisible du consommateur. |
| `consumer_type` | Type dominant selon priorite explicite (`USER` > `SERVICE_PRINCIPAL` > type d'entite du lineage), et non un `MAX` alphabetique. |
| `period_start` | Jour d'agregation. |
| `distinct_data_products` | Nombre de tables distinctes consommees CE JOUR: une somme sur plusieurs jours recompte les tables recurrentes. |
| `request_count` | Nombre total d'acces/requetes. |
| `rows_read` | Total des lignes lues. |
| `data_read_bytes` | Total des octets lus. |
| `duration_seconds` | Duree compute totale attribuee, en secondes. |
| `estimated_cost_usd` | Cout total attribue. |
| `consumer_rank` | `RANK()` sur `SUM(estimated_cost_usd)` decroissant, partitionne par `period_start` SEUL. Rang journalier, et **non partitionne par `cloud_provider`** contrairement a `popularity_rank`: les consommateurs Azure et AWS d'un meme jour se classent ensemble. |
| `_generated_at` | Horodatage de generation. |

## Gold 4: `gold_dbx_usage_table_query_performance_daily`

**Grain / cle:** `(cloud_provider, catalog, schema, table_name, period_start)`.

**Sources et calcul:**

- Filtre `curated_dbx_access_table_lineage` aux entites `DBSQL_QUERY`.
- Rejoint `curated_dbx_query_history` par `(cloud_provider, statement_id)` et le jour.
- Compte une requete distincte par `statement_id`, puis calcule les echecs, latences et volumes lus.

| Champ | Description |
|---|---|
| `cloud_provider` | Fournisseur cloud. |
| `catalog` | Catalogue Unity Catalog lu par la requete. |
| `schema` | Schema Unity Catalog lu par la requete. |
| `table_name` | Table lue par la requete. |
| `table_full_name` | Nom qualifie derive. |
| `period_start` | Jour d'agregation. |
| `query_count` | Nombre de `statement_id` distincts. |
| `failed_count` | Nombre de requetes `FAILED` ou `CANCELED`. |
| `failure_rate_pct` | `failed_count / query_count * 100`. Sur une periode, se recalcule par `SUM(failed_count) / SUM(query_count)` et jamais par une moyenne des taux journaliers. |
| `latency_p50_ms` | `percentile_approx(total_duration_ms, 0.50)` du jour. |
| `latency_p95_ms` | `percentile_approx(total_duration_ms, 0.95)` du jour. Non re-agregeable: un percentile de plusieurs jours n'est pas calculable depuis les percentiles journaliers, et une moyenne de P95 n'est pas un P95. Un P95 de periode exige de repartir de `curated_dbx_query_history`. |
| `bytes_scanned` | Somme de `read_bytes`. |
| `rows_scanned` | Somme de `read_rows`. |
| `_generated_at` | Horodatage de generation. |

## Gold 5: `gold_dbx_usage_table_catalog`

**Grain / cle:** `(cloud_provider, catalog, schema, table_name)`. Snapshot complet de l'etat courant.

**Sources et calcul:**

- Base `curated_dbx_uc_tables` pour le registre UC.
- Pivot exact de `curated_dbx_uc_table_tags` pour `owner`, `domain`, `cost_center`, `classification` et `data_product`.
- Prend la derniere operation de `curated_dbx_uc_table_operations` parmi `createTable`, `deleteTable`, `updateTables`.
- Prend `last_read_at` depuis `MAX(gold_dbx_usage_table_daily.last_used_at)`.
- `freshness_lag_hours` vaut l'age de `last_write_at` quand une ecriture est prouvee, et se replie sinon sur `last_altered_at`; `freshness_basis` nomme le signal retenu.

| Champ | Description |
|---|---|
| `cloud_provider` | Fournisseur cloud. |
| `catalog` | Catalogue UC issu de `table_catalog`. |
| `schema` | Schema UC issu de `table_schema`. |
| `table_name` | Nom de la table. |
| `table_full_name` | Nom qualifie derive. |
| `table_type` | Type UC, par exemple `MANAGED`, `VIEW`, `MATERIALIZED_VIEW`. |
| `owner` | Tag UC `owner`. |
| `domain` | Tag UC `domain`. |
| `cost_center` | Tag UC `cost_center`. |
| `classification` | Tag UC `classification`. |
| `is_data_product` | Vrai si un tag `data_product` existe; sa valeur n'est pas interpretee. |
| `created_at` | Date/heure de creation UC. |
| `created_by` | Identite ayant cree la table. |
| `last_write_at` | Derniere ecriture PROUVEE: cote cible du lineage qualifie par `written_rows > 0`. NULL sur les objets sans contenu propre (une vue n'est jamais ecrite) et au-dela de la retention du lineage. |
| `last_operation` | `action_name` brut de la derniere operation d'audit: `createTable`, `deleteTable` ou `updateTables`. Ni `MERGE`, ni `WRITE`, ni `OPTIMIZE`, ni `VACUUM`: l'audit UC ne journalise pas ces operations sous ce nom. |
| `last_operation_at` | `MAX(event_time)` de l'audit UC. **Pas un alias de `last_write_at`**: l'audit date un appel d'API, sans compteur de lignes. Une valeur ici ne prouve aucune ecriture. |
| `last_operation_by` | Identite de l'auteur de la derniere operation d'audit. |
| `last_altered_at` | `last_altered` de `information_schema.tables`: date la modification de la DEFINITION de la relation, pas une ecriture de donnees. Se trompe dans les deux sens (un `SET TBLPROPERTIES` le fait bouger; a l'inverse il est anterieur a une ecriture prouvee dans 44 % des cas). |
| `last_read_at` | Dernier acces connu selon `gold_dbx_usage_table_daily`. |
| `freshness_basis` | Signal ayant produit `freshness_lag_hours`: `lineage_write` (preuve) ou `table_altered` (repli heuristique, cf. `last_altered_at`). A lire avant toute conclusion sur la fraicheur. |
| `freshness_lag_hours` | Heures depuis `COALESCE(last_write_at, last_altered_at)`. NULL seulement si les deux signaux manquent. |
| `_generated_at` | Horodatage de generation du snapshot. |

## Gold 6: `gold_dbx_usage_table_governance`

**Grain / cle:** `(cloud_provider, catalog, schema, table_name)`. Snapshot complet de gouvernance.

**Sources et calcul:**

- Base `gold_dbx_usage_table_catalog`.
- Rejoint le dernier `downstream_fanout` connu de `gold_dbx_usage_table_popularity_daily`.
- Seuils codes en dur dans `specs.py`, non parametrables: `UNUSED_AFTER_DAYS = 90`, `CRITICAL_FANOUT_THRESHOLD = 5`, `STALE_WRITE_LAG_HOURS = 24` (avec lecture dans les 7 derniers jours).

| Champ | Description |
|---|---|
| `cloud_provider` | Fournisseur cloud. |
| `catalog` | Catalogue UC. |
| `schema` | Schema UC. |
| `table_name` | Nom de la table. |
| `table_full_name` | Nom qualifie derive. |
| `days_since_last_read` | Nombre de jours depuis le dernier acces; NULL si jamais lue. |
| `is_unused` | Vrai si jamais lue ou non lue depuis plus de 90 jours. |
| `has_owner_tag` | Vrai si `owner` est present. |
| `has_domain_tag` | Vrai si `domain` est present. |
| `has_cost_center_tag` | Vrai si `cost_center` est present. |
| `is_orphan` | Vrai si les trois tags de gouvernance sont absents. |
| `is_stale_but_consumed` | Vrai si `freshness_lag_hours > 24` et `days_since_last_read < 7`. Heuristique et non constat quand `freshness_basis = 'table_altered'`: l'anciennete est alors deduite de `last_altered_at`, qui se trompe dans les deux sens. |
| `downstream_fanout` | Fan-out aval du dernier jour de popularite connu, 0 par defaut. |
| `is_critical` | Vrai si `downstream_fanout >= 5`. |
| `recommended_action` | `archiver` si inutilisee, sinon `documenter` si orpheline, sinon `surveiller` si stale mais consommee, sinon NULL. |
| `severity` | `high` si critique et inutilisee; `medium` si inutilisee ou orpheline; `low` si stale mais consommee; sinon NULL. |
| `_generated_at` | Horodatage de generation du snapshot. |

## Gold 7: `gold_dbx_usage_recommendations`

**Grain / cle:** `(recommendation_id)`.

**Sources et calcul:**

- `gold_dbx_usage_table_governance` pour les signaux de cycle de vie, fraicheur et criticite.
- `gold_dbx_usage_table_catalog` pour la classification et l'identite du data product.
- `gold_dbx_usage_table_popularity_daily` pour l'adoption, le fan-out et les couts.
- `gold_dbx_usage_table_query_performance_daily` pour les erreurs et la fiabilite.
- `gold_dbx_usage_consumer_daily` pour la regle FinOps consommateur, seule regle au grain `CONSUMER`.
- Sept regles reparties sur cinq categories, `mode` toujours `REACTIVE`: LIFECYCLE `MEDIUM` (`is_unused AND NOT is_critical`), LIFECYCLE `HIGH` (`is_critical AND is_unused`), FRESHNESS `HIGH` (`is_stale_but_consumed`), GOVERNANCE `LOW` (`is_orphan`), GOVERNANCE `MEDIUM` (`is_data_product AND classification IS NULL`), RELIABILITY `HIGH` (`failure_rate_pct > USAGE_FAILURE_RATE_PCT_THRESHOLD`), FINOPS `MEDIUM` (`estimated_cost_usd > USAGE_HIGH_COST_USD_THRESHOLD`). Au plus une ligne GOVERNANCE par objet, orphelin prioritaire sur classification.
- RELIABILITY et FINOPS n'evaluent que le DERNIER JOUR disponible de leur source quotidienne, pas une fenetre.
- Cycle de vie `OPEN` -> `RESOLVED`: une anomalie qui disparait fait passer sa ligne a `RESOLVED`, ou elle est FIGEE (plus jamais reecrite, aucun `DELETE`). Si l'anomalie se redeclenche, une NOUVELLE ligne est inseree avec un nouveau `recommendation_id` et un nouveau `first_seen_date`, a cote de l'ancienne.

| Champ | Description |
|---|---|
| `recommendation_id` | `sha2` sur `cloud_provider`, `object_type`, `object_id`, `category` et `first_seen_date`. `first_seen_date` et non la date de generation: c'est ce qui rend l'identifiant stable d'un run a l'autre, et distinct entre deux occurrences separees par une resolution. |
| `cloud_provider` | Fournisseur cloud de l'objet concerne. |
| `object_type` | `DATA_PRODUCT` ou `CONSUMER`. Jamais `TABLE`: un filtre ecrit contre `TABLE` ne renvoie rien. |
| `object_id` | Identifiant stable: `catalog.schema.table_name` (`DATA_PRODUCT`) ou `consumer_id` (`CONSUMER`). |
| `object_name` | Nom lisible de l'objet cible. |
| `category` | `LIFECYCLE`, `FRESHNESS`, `GOVERNANCE`, `RELIABILITY` ou `FINOPS`. |
| `mode` | `REACTIVE` pour les sept regles. |
| `title` | Resume court de la recommandation. |
| `detail` | Contexte detaille et indicateurs ayant declenche la regle. |
| `recommended_action` | Action concrete a prendre, en phrase. Sans rapport avec le mot-cle court de `table_governance.recommended_action`. |
| `estimated_savings_usd` | Economie estimee, renseignee uniquement pour LIFECYCLE inutilise (dernier cout journalier connu de la table); NULL pour les quatre autres categories. |
| `severity` | `LOW`, `MEDIUM` ou `HIGH`, en MAJUSCULES. `table_governance.severity` porte les memes niveaux en minuscules: les deux vocabulaires coexistent. |
| `personas` | `ARRAY<STRING>` de profils concernes, par exemple `OWN`, `FIN`, `DE`, `AN`, `GOV`. |
| `status` | `OPEN` ou `RESOLVED`. Il n'existe pas d'etat d'acquittement: le `MERGE` reecrit `status` depuis les regles a chaque run, donc une ecriture applicative serait ecrasee. |
| `first_seen_date` | Date de premiere detection, preservee lors des recalculs. |
| `last_seen_date` | Date de derniere detection. |
| `_generated_at` | Horodatage de generation. |

Table snapshot sans `period_start`: un filtre de periode ne peut porter que sur `first_seen_date`/`last_seen_date`.

## Gold 8: `gold_dbx_usage_forecast_daily`

**Grain / cle:** `(cloud_provider, object_type, object_id, metric_name, horizon_date)`.

**Sources et calcul:**

- Historique `gold_dbx_usage_table_popularity_daily` sur `FORECAST_OBSERVED_LOOKBACK_DAYS = 14` jours, pour les quatre series `request_count`, `distinct_consumers`, `estimated_cost_usd` et `data_read_bytes`.
- Fonction SQL native Databricks `ai_forecast`, appelee une seule fois avec `value_col => array(...)` des quatre metriques, puis depivotee en `UNION ALL` vers une ligne par metrique. Aucune dependance Python.
- `group_col` n'accepte qu'UNE colonne: la serie est identifiee par une cle composite `object_key` (`cloud_provider::object_id`), redecoupee apres l'appel.
- `FORECAST_HORIZON_DAYS = 7` jours projetes, `FORECAST_PREDICTION_INTERVAL_WIDTH = 0.95`, `parameters => '{"global_floor": 0}'` pour interdire les valeurs negatives.
- Ecrite par le job `dcm_gold_forecast` et non `dcm_gold_dbx_usage`: `ai_forecast` exige un SQL Warehouse Pro/Serverless, donc un appel via la Statement Execution API plutot que par Spark.
- Une table sans historique sur la fenetre de 14 jours ne produit AUCUNE ligne: l'absence de projection n'est pas une projection a zero.

| Champ | Description |
|---|---|
| `cloud_provider` | Fournisseur cloud de la serie projetee. |
| `object_type` | Toujours `DATA_PRODUCT`: seule `table_popularity_daily` alimente la projection, il n'y a pas de serie consommateur. |
| `object_id` | Nom qualifie du data product. |
| `metric_name` | `request_count`, `distinct_consumers`, `estimated_cost_usd` ou `data_read_bytes`. Aucune projection de volume ecrit. |
| `horizon_date` | Date future couverte par la projection, dans les 7 jours suivant la fenetre observee. |
| `predicted_value` | Valeur centrale predite par `ai_forecast`, plancher a 0. |
| `lower_bound` | Borne basse de l'intervalle de prediction a 95 %. |
| `upper_bound` | Borne haute de l'intervalle de prediction a 95 %. |
| `method` | `ai_forecast`. |
| `_generated_at` | Horodatage de generation de la projection. |

`distinct_consumers` etant projete par table, une somme sur plusieurs tables donne une borne SUPERIEURE du nombre de consommateurs distincts, pas ce nombre.

## Points d'attention

- Le mapping du spike mentionne une attribution ponderee par `read_bytes`, mais le code livre utilise `equal_parts_fallback`: ni lineage ni `query.history` ne fournissent le volume par table source.
- Le partage a parts egales porte sur TOUS les objets sources d'une requete, vues incluses: une table lue via une vue partage son cout avec cette vue.
- `costed_request_count < request_count` signale un `estimated_cost_usd` sous-estime; `cost_basis = 'mixed'` signale un total qui additionne des seaux de facturation mesurant des grandeurs differentes.
- `gold_dbx_usage_table_daily` conserve les lignes dont le data product n'est pas dans le registre, avec `unknown_data_product = true`; il ne fabrique pas de valeur de remplacement. `catalog_resolution_status` distingue « hors registre » de « invisible du pipeline ».
- Les tables journalieres gardent un historique par `period_start`; `table_catalog`, `table_governance` et `recommendations` sont des snapshots recalcules integralement.
- `forecast_daily` est la seule table gold du domaine ecrite par un job distinct (`dcm_gold_forecast`): `ai_forecast` exige un SQL Warehouse Pro/Serverless.
- `gold_dbx_usage_dim_workspace` est retiree du perimetre, remplacee par `dim_dbx_workspace` de la spec 020.
- Toutes les tables gold utilisent `cloud_provider` pour eviter les collisions Azure/AWS. Aucune ne contient `workspace_id`, `source_lz_id` ni `subscription_or_account_id`.
