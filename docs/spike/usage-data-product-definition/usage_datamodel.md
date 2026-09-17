# Usage Data Product — Data Model (Curated + Gold)

> Modèle de données pour la feature **Usage Data Product** (pages Data Products + Consommateurs).
> Aligné sur la médaillon DCM existante : `system.*` → **CURATED** (`curated_dbx_*`, SCD1/append idempotent) → **GOLD** (`gold_*`, agrégats métier prêts API).
> Catalog / schéma : `it.ba_data_connect_monitoring__{env}` (`__d` dev, `__p` prod) — jamais codé en dur (vars bundle `catalog` / `schema`).
> Cloud : tables mutualisées Azure/AWS → `cloud_provider` fait toujours partie de la clé.
> Réconciliation : la table de service **existante** `gold_data_product_usage` (cf. `data-models.md` + route `data_product_usage.py`) devient le fait de consommation standardisé `gold_dbx_usage_table_daily` (mêmes colonnes de service, cf. §2.1).

---

## 0. Vue d'ensemble

```text
system.access.table_lineage    ─┐
system.access.audit             │
system.query.history            ├─►  CURATED (curated_dbx_*)  ─►  GOLD (gold_dbx_usage_*)
system.billing.usage/list_prices│        merge idempotent           agrégats jour + registre + reco
system.information_schema.*     ─┘        watermark / SCD1            prêts pour l'API / dashboard
```

**Grain gold cible : 1 jour × 1 data product × 1 consommateur** × cloud (= fait de consommation). Suffisant pour popularité + refacturation + prédictif ; évite d'exposer la volumétrie fine (`table_lineage` = 1 ligne/événement, `query.history` = 1 ligne/requête) au backend. Des agrégats dérivés (par data product, par consommateur) et des états (registre, gouvernance) complètent ce fait.

**Définition d'un data product** : objet Unity Catalog gouverné (table / vue matérialisée des couches curated/gold) exposé à la consommation, identifié par le **registre** `gold_dbx_usage_table_catalog` (§2.5) construit depuis `information_schema` + tags. Clé stable : `(catalog, schema, table_name)`.

**Conventions colonnes partagées (toutes tables gold)** :

| Colonne | Type | Rôle |
|---|---|---|
| `cloud_provider` | STRING | `azure` \| `aws` — anti-collision multi-cloud, partie de clé |
| `period_start` | DATE | Début de la période d'agrégation (partition) — jour pour `*_daily` ; généralisable `*_monthly`/`*_yearly` |
| `_generated_at` | TIMESTAMP | Horodatage calcul gold |

> `period_start` = même sémantique que `usage_date` de la table de service existante (1 valeur = 1 jour). La colonne `usage_date` est **conservée en alias/synonyme** dans `gold_dbx_usage_table_daily` pour ne pas casser la route backend actuelle (cf. §2.1).

### 0.1 `source_lz_id` — hors périmètre des tables gold usage

**Décision** : la notion de `source_lz_id` (Landing Zone) est **retirée des tables gold du domaine usage** (`*_daily`, `*_catalog`, `*_governance`, `recommendations`, `forecast_daily`). Ces tables ne portent **plus aucune colonne LZ** ; leur clé s'appuie sur `cloud_provider` seul (+ dimensions métier). Aucune dépendance collecteur.

> **Mise à jour (2026-09-04)** : `gold_dbx_usage_dim_workspace` (§2.4bis) a été **retirée** du périmètre livré (T003, `specs/019-usage-data-product-gold`) — redondante avec `dim_dbx_workspace` (spec 020), qui résout `workspace_id → LZ` via un vrai référentiel géré et est déjà jointe par `dim_landing_zone`. La résolution `workspace_id → LZ` du projet vit désormais **uniquement** dans `dim_dbx_workspace`. §2.4bis reste ci-dessous à titre de trace de conception (spike), non implémenté.

---

## 1. Couche CURATED — system tables

### 1.1 Tables déjà ingérées (réutilisées telles quelles)

Toutes déjà déclarées dans `system_tables/specs.py` — aucune modification requise pour le MVP usage.

| Curated table | Source system table | Clé de merge | Watermark |
|---|---|---|---|
| `curated_dbx_access_table_lineage` | `system.access.table_lineage` | `cloud_provider, account_id, workspace_id, entity_type, entity_id, entity_run_id, source_table_full_name, source_type, target_table_full_name, target_type, created_by, event_time` | `event_date` |
| `curated_dbx_access_audit` | `system.access.audit` (projeté, filtré `getTable/createTable/deleteTable`) | `cloud_provider, event_id` | `event_time` |
| `curated_dbx_query_history` | `system.query.history` | `cloud_provider, statement_id` | `start_time` |
| `curated_dbx_billing_usage` | `system.billing.usage` | `cloud_provider, record_id` | `usage_end_time` |
| `curated_dbx_billing_list_prices` | `system.billing.list_prices` | `cloud_provider, sku_name, price_start_time` | — (full) |

> `table_lineage` est le **cœur** du fait usage : chaque ligne = un consommateur (`entity_type` ∈ job/query/notebook/dashboard/pipeline, `created_by` = identité) lisant/écrivant une table (`source_table_full_name` → `target_table_full_name`). Les lectures d'un data product = lignes où le DP apparaît en `source_table_full_name`.

### 1.2 Tables à AJOUTER au registre `system_tables/specs.py`

Deux nouvelles `IngestionSpec` pour le **registre** des data products (métadonnées + tags de gouvernance). Sources = vues `system.information_schema` (une par workspace/catalog, faible volumétrie → full load léger, comme `billing.list_prices`).

#### `curated_dbx_uc_tables` — source `system.information_schema.tables`

| Colonne | Type | Notes |
|---|---|---|
| `cloud_provider` | STRING | clé |
| `table_catalog` | STRING | clé |
| `table_schema` | STRING | clé |
| `table_name` | STRING | clé |
| `table_full_name` | STRING | `catalog.schema.table` (dérivé, informatif — les tables gold usage utilisent `catalog`/`schema`/`table_name` séparés) |
| `table_type` | STRING | `MANAGED` \| `VIEW` \| `MATERIALIZED_VIEW` \| … |
| `table_owner` | STRING | propriétaire UC |
| `comment` | STRING | description |
| `created` | TIMESTAMP | création |
| `created_by` | STRING | auteur de la création |
| `last_altered` | TIMESTAMP | dernière modification (structure **ou** données selon UC) |
| `last_altered_by` | STRING | auteur de la dernière modification |

Clé merge : `(cloud_provider, table_catalog, table_schema, table_name)`. Full load (référentiel).

> `last_altered` seul ne dit **pas quelle opération** a eu lieu (INSERT / MERGE / DELETE / OPTIMIZE / VACUUM). Pour la **métrique d'opération** (TODO), on ajoute une table dédiée `curated_dbx_uc_table_operations` (§1.2bis) qui capture le **type d'opération** + horodatage + auteur, base de la fraîcheur *qualifiée* (« dernière écriture = MERGE le 2026-08-18 par X »).

#### `curated_dbx_uc_table_operations` — source `system.access.audit` (actions d'écriture)

Métrique d'opération sur les tables : **quelle** opération a modifié le data product, **quand**, **par qui**. `system.access.audit` loggue les actions Unity Catalog ; on projette/filtre les actions d'écriture (en plus des `getTable/createTable/deleteTable` déjà ingérés pour l'usage — cf. `ACCESS_AUDIT_ACTIONS` dans `specs.py`, à étendre).

| Colonne | Type | Notes |
|---|---|---|
| `cloud_provider` | STRING | clé |
| `event_id` | STRING | clé de merge |
| `event_time` | TIMESTAMP | **watermark** |
| `event_date` | DATE | partition |
| `account_id` | STRING | compte |
| `workspace_id` | STRING | workspace (→ LZ, §0.1) |
| `table_full_name` | STRING | objet cible (`catalog.schema.table`), extrait de `request_params` |
| `operation` | STRING | `CREATE` \| `WRITE`/`COMMIT` \| `MERGE` \| `UPDATE` \| `DELETE` \| `OPTIMIZE` \| `VACUUM` \| `SET_TAGS` \| `ALTER` (normalisé depuis `action_name`) |
| `performed_by` | STRING | `user_identity` (email / SP) |
| `response_status` | STRING | succès / échec de l'opération |

Clé merge : `(cloud_provider, event_id)`. Watermark : `event_time`. Partition : `event_date`.

> Actions `access.audit` correspondant à une écriture (à normaliser en `operation`) : `createTable`, `commit`, `writeIntoTable`, `mergeIntoTable`, `updateTableMetadata`, `deleteTable`, `optimize`, `vacuumEnd`, `setTableTags`… La liste exacte est calée sur les valeurs réelles observées (gate de validation), sans invention.

#### `curated_dbx_uc_table_tags` — source `system.information_schema.table_tags`

| Colonne | Type | Notes |
|---|---|---|
| `cloud_provider` | STRING | clé |
| `catalog_name` | STRING | clé |
| `schema_name` | STRING | clé |
| `table_name` | STRING | clé |
| `tag_name` | STRING | clé (ex. `data_product`, `owner`, `domain`, `cost_center`, `classification`) |
| `tag_value` | STRING | valeur |

Clé merge : `(cloud_provider, catalog_name, schema_name, table_name, tag_name)`. Full load (référentiel).

> Option (hors MVP) : `system.access.column_lineage` pour l'usage au grain colonne, et `information_schema.table_privileges` pour croiser droits accordés vs accès réels.

---

## 2. Couche GOLD

> **Deux natures d'objets gold à ne pas confondre (TODO clarification)** :
> - **Le fait de consommation** `gold_dbx_usage_table_daily` (§2.1) = *la* « gold table » servie à l'API (succède à `gold_data_product_usage`). Grain jour × DP × consommateur. C'est la mesure d'**usage**.
> - **Le registre data product** `gold_dbx_usage_table_catalog` (§2.5) = *le* « gold data product » : 1 ligne = 1 data product (état courant), ses métadonnées, tags, fraîcheur **et dernière opération**. C'est la mesure d'**inventaire / état**.
>
> Les agrégats (§2.2 popularité, §2.3 consommateur), la performance (§2.4) et la gouvernance (§2.6) dérivent de ces deux socles. Le registre §2.5 est la **dimension** `table` ; le fait §2.1 la référence via `(catalog, schema, table_name)`.

### 2.1 `gold_dbx_usage_table_daily` — fait de consommation (succède à `gold_data_product_usage`)

Grain : `(cloud_provider, catalog, schema, table_name, consumer_id, period_start)`

**Colonnes de service (dérivées de la table existante `gold_data_product_usage` — compat backend via mapping de route)** :

| Colonne | Type | Description | Mode |
|---|---|---|---|
| `usage_date` | DATE | = `period_start` (alias conservé pour la route actuelle) | — |
| `catalog` | STRING | catalogue Unity Catalog (`uc_tables.table_catalog`) | — |
| `schema` | STRING | schéma Unity Catalog (`uc_tables.table_schema`) | — |
| `table_name` | STRING | nom de la table (`uc_tables.table_name`) | — |
| `table_full_name` | STRING | `catalog.schema.table_name` (dérivé, lisibilité/compat) | — |
| `consumer_id` | STRING | identité consommatrice (`created_by` / user_identity) | — |
| `consumer_name` | STRING | libellé lisible du consommateur | — |
| `cloud_provider` | STRING | | — |
| `request_count` | BIGINT | nb d'accès / requêtes du jour | R+P |
| `rows_read` | BIGINT | lignes lues | R+P |
| `rows_written` | BIGINT | lignes écrites (si consommateur producteur) | R+P |
| `data_read_bytes` | BIGINT | octets lus | R+P |
| `data_written_bytes` | BIGINT | octets écrits | R+P |
| `duration_seconds` | DOUBLE | temps compute cumulé attribué | R+P |
| `estimated_cost_usd` | DOUBLE | coût attribué (compute des requêtes) | R+P |
| `last_used_at` | TIMESTAMP | dernier accès du jour | R |

**Colonnes ajoutées (enrichissement usage, optionnelles côté API)** :

| Colonne | Type | Description | Mode |
|---|---|---|---|
| `consumer_type` | STRING | `USER` \| `SERVICE_PRINCIPAL` \| `JOB` \| `DASHBOARD` \| `NOTEBOOK` \| `PIPELINE` | R |
| `failed_access_count` | BIGINT | accès refusés/en échec du jour | R |
| `_generated_at` | TIMESTAMP | | — |

### 2.2 `gold_dbx_usage_table_popularity_daily` — agrégat par table

Grain : `(cloud_provider, catalog, schema, table_name, period_start)`

| Colonne | Type | Description | Mode |
|---|---|---|---|
| `catalog` | STRING | catalogue Unity Catalog | — |
| `schema` | STRING | schéma Unity Catalog | — |
| `table_name` | STRING | nom de la table | — |
| `table_full_name` | STRING | `catalog.schema.table_name` (dérivé, lisibilité/compat) | — |
| `owner` | STRING | tag owner / `table_owner` | — |
| `domain` | STRING | tag domaine métier | — |
| `distinct_consumers` | BIGINT | identités distinctes du jour | R+P |
| `request_count` | BIGINT | accès/requêtes du jour | R+P |
| `rows_read` | BIGINT | lignes lues | R+P |
| `data_read_bytes` | BIGINT | octets lus | R+P |
| `estimated_cost_usd` | DOUBLE | coût attribué du jour | R+P |
| `consumers_by_type` | MAP<STRING,BIGINT> | répartition par `consumer_type` | R |
| `downstream_fanout` | INT | nb d'objets aval dépendants (jobs/dashboards/tables) | R+P |
| `popularity_rank` | INT | rang global par lectures | R+P |
| `request_count_prev_day` | BIGINT | J-1 (delta adoption) | R+P |
| `request_delta_pct` | DOUBLE | variation vs J-1 | R+P |
| `_generated_at` | TIMESTAMP | | — |

### 2.3 `gold_dbx_usage_consumer_daily` — agrégat par consommateur

Grain : `(cloud_provider, consumer_id, period_start)`

| Colonne | Type | Description | Mode |
|---|---|---|---|
| `consumer_name` | STRING | libellé UI | — |
| `consumer_type` | STRING | user / SP / job / … | R |
| `distinct_data_products` | BIGINT | tables distinctes consommées | R+P |
| `request_count` | BIGINT | accès/requêtes | R+P |
| `rows_read` | BIGINT | lignes lues | R+P |
| `data_read_bytes` | BIGINT | octets lus | R+P |
| `duration_seconds` | DOUBLE | compute cumulé | R+P |
| `estimated_cost_usd` | DOUBLE | coût attribué | R+P |
| `consumer_rank` | INT | rang consommateur global | R+P |
| `_generated_at` | TIMESTAMP | | — |

### 2.4 `gold_dbx_usage_table_query_performance_daily` — performance d'accès (page 2)

Grain : `(cloud_provider, catalog, schema, table_name, period_start)`

| Colonne | Type | Description | Mode |
|---|---|---|---|
| `catalog` | STRING | catalogue Unity Catalog | — |
| `schema` | STRING | schéma Unity Catalog | — |
| `table_name` | STRING | nom de la table | — |
| `table_full_name` | STRING | `catalog.schema.table_name` (dérivé, lisibilité/compat) | — |
| `query_count` | BIGINT | requêtes lisant le DP | P |
| `failed_count` | BIGINT | FAILED + CANCELED | R |
| `failure_rate_pct` | DOUBLE | taux d'échec | R |
| `latency_p50_ms` | DOUBLE | médiane durée totale | R+P |
| `latency_p95_ms` | DOUBLE | p95 | R+P |
| `bytes_scanned` | BIGINT | volume lu | R+P |
| `rows_scanned` | BIGINT | lignes lues | R+P |
| `_generated_at` | TIMESTAMP | | — |

### 2.5 `gold_dbx_usage_table_catalog` — registre / état courant

Grain : `(cloud_provider, catalog, schema, table_name)` — dernier état connu.

| Colonne | Type | Description | Mode |
|---|---|---|---|
| `catalog` | STRING | catalogue Unity Catalog (`uc_tables.table_catalog`) | — |
| `schema` | STRING | schéma Unity Catalog (`uc_tables.table_schema`) | — |
| `table_name` | STRING | nom de la table (`uc_tables.table_name`) | — |
| `table_full_name` | STRING | `catalog.schema.table_name` (dérivé, lisibilité/compat) | — |
| `table_type` | STRING | MANAGED / VIEW / MATERIALIZED_VIEW | — |
| `owner` | STRING | tag owner / `table_owner` | R |
| `domain` | STRING | tag domaine | R |
| `cost_center` | STRING | tag cost-center | R |
| `classification` | STRING | tag classification (public/confidentiel…) | R |
| `is_data_product` | BOOLEAN | présence tag `data_product` ou schéma publié | R |
| `created_at` | TIMESTAMP | création UC | — |
| `created_by` | STRING | auteur création (`uc_tables.created_by`) | — |
| `last_write_at` | TIMESTAMP | fraîcheur (dernier write) | R |
| `last_operation` | STRING | **type** de la dernière opération d'écriture (`MERGE`/`DELETE`/`OPTIMIZE`…) — TODO opération | R |
| `last_operation_at` | TIMESTAMP | horodatage de la dernière opération | R |
| `last_operation_by` | STRING | auteur de la dernière opération | R |
| `last_altered_at` | TIMESTAMP | `uc_tables.last_altered` (repli si opération non résolue) | R |
| `last_read_at` | TIMESTAMP | dernier accès en lecture | R |
| `freshness_lag_hours` | DOUBLE | `now - last_write_at` | R |
| `_generated_at` | TIMESTAMP | | — |

### 2.6 `gold_dbx_usage_table_governance` — gouvernance / cycle de vie (snapshot)

Grain : `(cloud_provider, catalog, schema, table_name)` — dernier état connu.

| Colonne | Type | Description | Mode |
|---|---|---|---|
| `catalog` | STRING | catalogue Unity Catalog | — |
| `schema` | STRING | schéma Unity Catalog | — |
| `table_name` | STRING | nom de la table | — |
| `table_full_name` | STRING | `catalog.schema.table_name` (dérivé, lisibilité/compat) | — |
| `days_since_last_read` | INT | inactivité | R+P |
| `is_unused` | BOOLEAN | 0 lecture sur N jours | R |
| `has_owner_tag` | BOOLEAN | tag owner présent | R |
| `has_domain_tag` | BOOLEAN | tag domaine présent | R |
| `has_cost_center_tag` | BOOLEAN | tag cost-center présent | R |
| `is_orphan` | BOOLEAN | aucun tag gouvernance | R |
| `is_stale_but_consumed` | BOOLEAN | périmé (fraîcheur > SLA) mais lu récemment | R |
| `downstream_fanout` | INT | dépendances aval (criticité) | R+P |
| `is_critical` | BOOLEAN | fort fan-out → dépréciation risquée | R |
| `recommended_action` | STRING | action gouvernance lisible | R |
| `severity` | STRING | `LOW` \| `MEDIUM` \| `HIGH` | R |
| `_generated_at` | TIMESTAMP | | — |

---

## 3. GOLD transverse — Réactif & Prédictif

### 3.1 `gold_dbx_usage_recommendations` — socle RÉACTIF (fait actionnable unifié)

Centralise les « reco d'action » des pages data products + gouvernance. Une ligne = une reco active pour un objet.

Grain : `(recommendation_id)` — `recommendation_id = sha2(object_type || object_id || category || generated_date)`.

| Colonne | Type | Description |
|---|---|---|
| `recommendation_id` | STRING | clé (hash) |
| `cloud_provider` | STRING | |
| `object_type` | STRING | `DATA_PRODUCT` \| `CONSUMER` |
| `object_id` | STRING | `catalog.schema.table_name` / consumer_id |
| `object_name` | STRING | libellé UI |
| `category` | STRING | `LIFECYCLE` \| `FRESHNESS` \| `GOVERNANCE` \| `FINOPS` \| `RELIABILITY` |
| `mode` | STRING | `REACTIVE` |
| `title` | STRING | résumé court |
| `detail` | STRING | contexte chiffré |
| `recommended_action` | STRING | action concrète |
| `estimated_savings_usd` | DOUBLE | gain estimé (NULL si non chiffrable) |
| `severity` | STRING | `LOW` \| `MEDIUM` \| `HIGH` |
| `personas` | ARRAY<STRING> | `OWN`,`FIN`,`DE`,`AN`,`GOV` |
| `status` | STRING | `OPEN` \| `ACK` \| `RESOLVED` |
| `first_seen_date` | DATE | 1re détection |
| `last_seen_date` | DATE | dernière détection |
| `_generated_at` | TIMESTAMP | |

### 3.2 `gold_dbx_usage_forecast_daily` — socle PRÉDICTIF (séries projetées)

Projection des métriques `P` / `R+P` (lectures, consommateurs distincts, coût $, volume lu) via `ai_forecast` sur l'historique gold journalier. Alimente l'anticipation adoption / budget / cycle de vie.

Grain : `(cloud_provider, object_type, object_id, metric_name, horizon_date)`

| Colonne | Type | Description |
|---|---|---|
| `object_type` | STRING | `DATA_PRODUCT` \| `CONSUMER` |
| `object_id` | STRING | `catalog.schema.table_name` (table) / `consumer_id` (consommateur) |
| `metric_name` | STRING | `request_count`,`distinct_consumers`,`estimated_cost_usd`,`data_read_bytes` |
| `horizon_date` | DATE | jour projeté |
| `predicted_value` | DOUBLE | valeur estimée |
| `lower_bound` | DOUBLE | borne basse (IC) |
| `upper_bound` | DOUBLE | borne haute (IC) |
| `method` | STRING | `ai_forecast` |
| `_generated_at` | TIMESTAMP | |

> **Historisation** : les tables `*_daily` conservent l'historique jour (append/SCD1 sur clé + date) → le prédictif se calcule sans re-collecte. Les tables d'état (`*_catalog`, `*_governance`) gardent le dernier état connu.

> **Nommage** : convention `gold_dbx_usage_<objet>_<grain>` (ex. `gold_dbx_usage_table_daily`). Le préfixe `dbx` distingue explicitement ce socle Databricks/Unity Catalog du domaine `usage` générique. `gold_dbx_usage_table_daily` **remplace** l'ancien `gold_data_product_usage` (colonnes de service renommées : `data_product_id`/`data_product_name` → `catalog`/`schema`/`table_name`, `subscription_or_account_id` retiré) ; la route backend adapte son mapping de colonnes en conséquence.

---

## 4. Positionnement médaillon & rafraîchissement

| Couche | Objet | Type | Rafraîchissement |
|---|---|---|---|
| CURATED | `curated_dbx_access_*`, `curated_dbx_query_history`, `curated_dbx_billing_*` | merge idempotent (watermark) | à chaque run ingestion |
| CURATED | `curated_dbx_uc_tables`, `curated_dbx_uc_table_tags` | full load léger (référentiel) | quotidien |
| CURATED | `curated_dbx_uc_table_operations` | merge idempotent (watermark `event_time`) | à chaque run ingestion |
| GOLD `dim_workspace` | pont `workspace_id → LZ` (§0.1) | materialized view (dernier état) | quotidien |
| GOLD `*_daily` | agrégats jour | materialized view / apply_changes SCD1 | quotidien (batch serverless) |
| GOLD `*_catalog` | registre / fraîcheur / opération | materialized view (dernier état) | quotidien |
| GOLD `*_governance` | snapshot cycle de vie | materialized view (règles seuils) | quotidien |
| GOLD `recommendations` | fait réactif | materialized view (règles) | quotidien |
| GOLD `forecast_daily` | prédictif | job SQL `ai_forecast` | quotidien / hebdo |

`source_lz_id` : hors périmètre des tables gold usage (§0.1). Seule `gold_dbx_usage_dim_workspace` conserve la résolution `workspace_id → LZ`, à titre de référence, sans être jointe par les autres tables gold.

---

## 5. Guidelines & conventions (TODO guideline)

Règles à respecter pour l'implémentation de ce socle usage (dérivées de la constitution DCM + conventions repo) :

1. **100 % system tables, zéro collecteur** — toute donnée provient des `system.*` (access, query, billing, information_schema). Aucun champ n'est fourni par un collecteur. Un champ non disponible en source reste **`NULL`** (jamais `0`, jamais inventé — règle P7/P8/P9).
2. **`cloud_provider` toujours dans la clé** — tables mutualisées Azure/AWS ; anti-collision multi-cloud.
3. **Pas de LZ dans les tables gold usage** — `source_lz_id` n'est **pas** une colonne des tables gold du domaine usage (§0.1). La seule résolution `workspace_id → LZ` vit dans `gold_dbx_usage_dim_workspace`, conservée à part, non référencée par les autres tables gold.
4. **Idempotence** — curated : MERGE sur clé documentée + watermark. Gold : `apply_changes` SCD1 (dernier gagne) ou materialized view ; grain unique garanti (pas de doublon de clé).
5. **Nommage** — curated `curated_dbx_<source>` ; gold `gold_dbx_usage_<objet>_<grain>` (`_daily`, `_catalog`, `_governance`). Préfixe `dbx` = socle Databricks/UC.
6. **Compat backend** — `gold_dbx_usage_table_daily` reprend le périmètre fonctionnel de `gold_data_product_usage`, avec colonnes renommées (`catalog`/`schema`/`table_name` au lieu de `data_product_id`/`data_product_name`, plus de `subscription_or_account_id`) et `usage_date` conservé en alias de `period_start`. Bascule = renommage de `_GOLD_TABLE` + adaptation du mapping de colonnes côté route.
7. **Fraîcheur honnête** — exposer un `as_of` réel (dernier `_ingested_at`) ; les system tables ont plusieurs heures de latence, ne pas prétendre au temps réel.
8. **Data product = périmètre explicite** — une table n'est un data product que si le registre `*_catalog` la marque `is_data_product = true` (tag `data_product` ou schéma publié). Les autres accès sont exclus du fait usage (`unknown_data_product`).
9. **Opération qualifiée** — la fraîcheur d'un DP s'accompagne du **type d'opération** (`last_operation`) ; ne pas se limiter à `last_altered` (qui ne dit pas *ce qui* a changé).
10. **Attribution coût déterministe** — coût d'une requête multi-DP réparti par règle documentée (défaut : parts égales, cf. mapping §2.1) ; contrôle de réconciliation `SUM(parts) = coût requête`.
11. **Tests obligatoires** — chaque couche livrée avec ses tests (pytest/chispa pipeline). Ruff/mypy zéro warning.
