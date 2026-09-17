# Usage Data Product — Data Mapping (system → curated → gold)

> Mapping de bout en bout pour la feature **Usage Data Product**.
> Colonnes : `Cible` ← `Source` + `Transformation`. Sources = system tables Databricks ingérées en `curated_dbx_*`.
> Voir le modèle : [usage_datamodel.md](usage_datamodel.md).
> Notation `system.access.table_lineage.source_table_full_name` = colonne de la table système.
>
> **Mise à jour (2026-09-04)** : `gold_dbx_usage_dim_workspace` (§2.4bis ci-dessous) a été **retirée** du périmètre livré (T003, `specs/019-usage-data-product-gold`) — redondante avec `dim_dbx_workspace` (spec 020), qui résout `workspace_id → LZ` via un vrai référentiel et est déjà jointe par `dim_landing_zone`. §2.4bis reste ci-dessous à titre de trace de conception (spike), non implémenté.

---

## 0. Conventions de mapping

- **Data product** = table Unity Catalog gouvernée, identifiée par `(catalog, schema, table_name)` (`uc_tables.table_catalog/table_schema/table_name`). Le périmètre « data product » vient du registre `gold_dbx_usage_table_catalog` (tag `data_product` OU schéma/catalogue publié).
- **Lecture d'un data product** = ligne de `curated_dbx_access_table_lineage` où le DP est en `source_table_full_name` (le consommateur = `entity_type` + `created_by`, la cible dérivée = `target_table_full_name`). Complété par `curated_dbx_access_audit` (`action_name='getTable'`) pour les accès directs sans lineage.
- **Consommateur** : `consumer_id` = `created_by` (identité) ; `consumer_type` = mapping de `entity_type` (`JOB`,`DASHBOARD_V3`,`NOTEBOOK`,`PIPELINE`,`SQL_QUERY`…) et de `user_identity` (user vs service principal).
- **Coût $** = `curated_dbx_billing_usage.usage_quantity` × prix effectif (`list_prices.pricing.effective_list.default`, join `sku_name` + fenêtre `price_start_time ≤ usage_date < price_end_time`), **attribué** au data product via les requêtes qui le lisent (join `query.history.statement_id` ↔ usage compute, puis lineage requête → table).
- **Percentiles** : `percentile_approx(col, 0.95)` sur la fenêtre jour.
- **LZ / cloud** : `cloud_provider` propagé depuis curated (contexte d'ingestion). **`source_lz_id` n'existe pas dans les system tables** et **n'est pas exposé par les tables gold usage** (`*_daily`, `*_catalog`, `*_governance`, `recommendations`, `forecast_daily`) — retiré de leur clé/colonnes. Seule la dimension `gold_dbx_usage_dim_workspace` (§2.4bis / data model §0.1) conserve la résolution `workspace_id → LZ` (tag `dcm_lz_id`/`Project` du compute, fallback `source_lz_id = workspace_id`) et le champ `subscription_or_account_id` (`account_id` de la system table à défaut de subscription réelle), à titre de référence, sans être jointe par les autres tables gold. Les autres tables gold usage ne portent ni LZ ni `subscription_or_account_id`. **Aucune dépendance collecteur.**
- **Rattachement requête → data product** : une requête `query.history` produit des lignes `table_lineage` (`entity_type='SQL_QUERY'`, `entity_id=statement_id`) listant les tables sources lues → permet d'attribuer durée/bytes/coût de la requête aux DP lus.

---

## 1. Mapping CURATED (system tables → curated_dbx_*)

### 1.1 Tables déjà produites (réutilisées, non redéfinies ici)

`curated_dbx_access_table_lineage` ← `system.access.table_lineage`, `curated_dbx_access_audit` ← `system.access.audit` (projeté/filtré), `curated_dbx_query_history` ← `system.query.history`, `curated_dbx_billing_usage` ← `system.billing.usage`, `curated_dbx_billing_list_prices` ← `system.billing.list_prices` sont **déjà** déclarées dans `system_tables/specs.py` — mapping système existant.

### 1.2 `curated_dbx_uc_tables` ← `system.information_schema.tables`

| Cible curated | Source | Transformation |
|---|---|---|
| `cloud_provider` | (contexte ingestion) | constante par run (`azure`/`aws`) |
| `table_catalog` | `table_catalog` | direct |
| `table_schema` | `table_schema` | direct |
| `table_name` | `table_name` | direct |
| `table_full_name` | `table_catalog`,`table_schema`,`table_name` | `concat_ws('.', ...)` |
| `table_type` | `table_type` | direct |
| `table_owner` | `table_owner` | direct |
| `comment` | `comment` | direct |
| `created` | `created` | direct |
| `created_by` | `created_by` | direct |
| `last_altered` | `last_altered` | direct |
| `last_altered_by` | `last_altered_by` | direct |

### 1.3 `curated_dbx_uc_table_tags` ← `system.information_schema.table_tags`

| Cible curated | Source | Transformation |
|---|---|---|
| `cloud_provider` | (contexte) | constante |
| `catalog_name` / `schema_name` / `table_name` | idem | direct |
| `tag_name` | `tag_name` | direct |
| `tag_value` | `tag_value` | direct |

### 1.4 `curated_dbx_uc_table_operations` ← `system.access.audit` (actions d'écriture)

Métrique d'opération : quelle opération a modifié la table, quand, par qui. Étend le filtre `ACCESS_AUDIT_ACTIONS` de `specs.py` aux actions d'écriture.

| Cible curated | Source | Transformation |
|---|---|---|
| `cloud_provider` | (contexte) | constante |
| `event_id` | `event_id` | clé de merge |
| `event_time` | `event_time` | watermark |
| `event_date` | `event_date` | partition |
| `account_id` / `workspace_id` | idem | direct |
| `table_full_name` | `request_params` (map) | extraction `catalog.schema.table` de la cible |
| `operation` | `action_name` | normalisation → `CREATE`/`WRITE`/`MERGE`/`UPDATE`/`DELETE`/`OPTIMIZE`/`VACUUM`/`SET_TAGS`/`ALTER` |
| `performed_by` | `user_identity` | email / SP |
| `response_status` | `response` | succès / échec |

> Mapping `action_name → operation` (calé sur valeurs réelles au gate) : `createTable`→`CREATE`, `commit`/`writeIntoTable`→`WRITE`, `mergeIntoTable`→`MERGE`, `updateTableMetadata`→`ALTER`, `deleteTable`→`DELETE`, `optimize`→`OPTIMIZE`, `vacuumEnd`→`VACUUM`, `setTableTags`→`SET_TAGS`.

---

## 2. Mapping GOLD — Page 1 : Data Products

### 2.1 `gold_dbx_usage_table_daily` (fait de consommation)

Base : `curated_dbx_access_table_lineage` (DP en `source_table_full_name`) UNION `curated_dbx_access_audit` (`getTable`), enrichi par `query.history` (durée/bytes/rows) et `billing.usage` (coût), agrégé par `(cloud_provider, catalog, schema, table_name, consumer_id, period_start)`.

| Cible gold | Source | Transformation |
|---|---|---|
| `usage_date` / `period_start` | `table_lineage.event_date` / `audit.event_date` | `to_date(...)` (clé de groupe) |
| `catalog` | `table_lineage.source_table_full_name` \| `uc_tables.table_catalog` | `split_part(source_table_full_name, '.', 1)` (filtré aux DP du registre) |
| `schema` | `table_lineage.source_table_full_name` \| `uc_tables.table_schema` | `split_part(source_table_full_name, '.', 2)` |
| `table_name` | `table_lineage.source_table_full_name` \| `uc_tables.table_name` | `split_part(source_table_full_name, '.', 3)` |
| `table_full_name` | `catalog`,`schema`,`table_name` | `concat_ws('.', ...)` (dérivé, lisibilité/compat) |
| `consumer_id` | `table_lineage.created_by` \| `audit.user_identity.email` | `coalesce` |
| `consumer_name` | `created_by` / `user_identity` | libellé lisible (email → nom) |
| `consumer_type` | `table_lineage.entity_type` / `user_identity` | `CASE entity_type WHEN 'JOB' THEN 'JOB' WHEN 'DASHBOARD_V3' THEN 'DASHBOARD' WHEN 'NOTEBOOK' THEN 'NOTEBOOK' WHEN 'PIPELINE' THEN 'PIPELINE' WHEN 'SQL_QUERY' THEN CASE WHEN sp THEN 'SERVICE_PRINCIPAL' ELSE 'USER' END … END` |
| `cloud_provider` | curated | direct |
| `request_count` | `table_lineage` lignes + `audit` getTable | `COUNT` accès du jour |
| `rows_read` | `query.history.read_rows` | `SUM` (requêtes lisant le DP) |
| `rows_written` | `query.history.written_rows` | `SUM` (si consommateur écrit une cible dérivée) |
| `data_read_bytes` | `query.history.read_bytes` | `SUM` |
| `data_written_bytes` | `query.history.written_bytes` | `SUM` |
| `duration_seconds` | `query.history.total_duration_ms` | `SUM(...)/1000` attribué au DP lu |
| `estimated_cost_usd` | `billing.usage` × `list_prices` (via statement) | `SUM(qty × price)` attribué au DP |
| `failed_access_count` | `audit.response` / `query.history.execution_status` | `COUNT` échecs |
| `last_used_at` | `table_lineage.event_time` / `audit.event_time` | `MAX` |

> **Attribution coût multi-DP** : une requête lisant N data products répartit son coût/bytes au prorata (par défaut : parts égales, ou pondéré par `read_bytes` par table si disponible via lineage colonne). Choix par défaut MVP : parts égales entre DP lus par la requête.

### 2.2 `gold_dbx_usage_table_popularity_daily`

Base : `gold_dbx_usage_table_daily` agrégé par `(cloud_provider, catalog, schema, table_name, period_start)` + `catalog` (registre, owner/domain) + lineage aval (fan-out).

| Cible gold | Source | Transformation |
|---|---|---|
| `catalog` | `daily.catalog` | `MAX` (clé de groupe) |
| `schema` | `daily.schema` | `MAX` (clé de groupe) |
| `table_name` | `daily.table_name` | `MAX` (clé de groupe) |
| `table_full_name` | `daily.table_full_name` | `MAX` (clé de groupe) |
| `owner` | `catalog.owner` | join |
| `domain` | `catalog.domain` | join |
| `distinct_consumers` | `daily.consumer_id` | `COUNT(DISTINCT)` |
| `request_count` | `daily.request_count` | `SUM` |
| `rows_read` / `data_read_bytes` | `daily.*` | `SUM` |
| `estimated_cost_usd` | `daily.estimated_cost_usd` | `SUM` |
| `consumers_by_type` | `daily.consumer_type` | `map_from_entries(collect count per type)` |
| `downstream_fanout` | `table_lineage` (DP en `source`, cibles distinctes) | `COUNT(DISTINCT target_table_full_name)` |
| `popularity_rank` | dérivé | `RANK() OVER (PARTITION BY period_start ORDER BY request_count DESC)` |
| `request_count_prev_day` | même table J-1 | `LAG` sur clé |
| `request_delta_pct` | dérivé | `(rc - prev)/NULLIF(prev,0) × 100` |

### 2.3 `gold_dbx_usage_table_query_performance_daily`

Base : `curated_dbx_query_history` restreint aux requêtes dont le lineage lit le DP, agrégé par `(cloud_provider, catalog, schema, table_name, period_start)`.

| Cible gold | Source | Transformation |
|---|---|---|
| `catalog` | `table_lineage.source_table_full_name` | `split_part(..., '.', 1)` |
| `schema` | `table_lineage.source_table_full_name` | `split_part(..., '.', 2)` |
| `table_name` | `table_lineage.source_table_full_name` | `split_part(..., '.', 3)` |
| `table_full_name` | `table_lineage.source_table_full_name` | direct |
| `query_count` | `statement_id` | `COUNT(DISTINCT)` |
| `failed_count` | `execution_status` | `COUNT(status IN ('FAILED','CANCELED'))` |
| `failure_rate_pct` | dérivé | `failed_count / NULLIF(query_count,0) × 100` |
| `latency_p50_ms` | `total_duration_ms` | `percentile_approx(0.50)` |
| `latency_p95_ms` | `total_duration_ms` | `percentile_approx(0.95)` |
| `bytes_scanned` | `read_bytes` | `SUM` |
| `rows_scanned` | `read_rows` | `SUM` |

### 2.4 `gold_dbx_usage_table_catalog` (registre / fraîcheur)

Base : `curated_dbx_uc_tables` + `curated_dbx_uc_table_tags` (pivot) + `curated_dbx_uc_table_operations` (dernière opération) + derniers événements `table_lineage` (write/read).

| Cible gold | Source | Transformation |
|---|---|---|
| `catalog` | `uc_tables.table_catalog` | direct (clé) |
| `schema` | `uc_tables.table_schema` | direct (clé) |
| `table_name` | `uc_tables.table_name` | direct (clé) |
| `table_full_name` | `uc_tables.table_full_name` | direct |
| `table_type` | `uc_tables.table_type` | direct |
| `owner` | `uc_table_tags['owner']` \| `uc_tables.table_owner` | `coalesce` |
| `domain` | `uc_table_tags['domain']` | pivot tag |
| `cost_center` | `uc_table_tags['cost_center']` | pivot tag |
| `classification` | `uc_table_tags['classification']` | pivot tag |
| `is_data_product` | `uc_table_tags` / schéma | `tags['data_product'] IS NOT NULL OR schema IN (<schémas publiés>)` |
| `created_at` | `uc_tables.created` | direct |
| `created_by` | `uc_tables.created_by` | direct |
| `last_write_at` | `table_lineage` (DP en `target`, write) | `MAX(event_time)` |
| `last_operation` | `uc_table_operations.operation` | `max_by(operation, event_time)` par `table_full_name` |
| `last_operation_at` | `uc_table_operations.event_time` | `MAX(event_time)` par `table_full_name` |
| `last_operation_by` | `uc_table_operations.performed_by` | `max_by(performed_by, event_time)` |
| `last_altered_at` | `uc_tables.last_altered` | direct (repli si opération non résolue) |
| `last_read_at` | `table_lineage` (DP en `source`, read) | `MAX(event_time)` |
| `freshness_lag_hours` | dérivé | `(current_timestamp - last_write_at)` en heures |

### 2.4bis `gold_dbx_usage_dim_workspace` (pont workspace → LZ, cf. data model §0.1) — RETIRÉ (cf. note en tête de document)

Base : tags compute agrégés par `workspace_id` (system-tables-native), fallback identité.

| Cible gold | Source | Transformation |
|---|---|---|
| `workspace_id` | `curated_dbx_compute_clusters` / `_warehouses` | clé |
| `cloud_provider` | curated | direct |
| `source_lz_id` | `tags['dcm_lz_id']` \| `tags['Project']` \| `workspace_id` | `coalesce` (priorité tag, fallback `workspace_id`) |
| `subscription_or_account_id` | `account_id` | direct (à défaut de subscription réelle) |
| `lz_name` | `tags['dcm_lz_id']` \| `workspace_id` | `coalesce` |

> **[NEEDS DECISION PO]** rapprochement avec `dim_landing_zone` existant vs LZ = workspace. Le fallback garantit une donnée non inventée en attendant.

### 2.5 `gold_dbx_usage_table_governance` (cycle de vie, snapshot)

Base : `catalog` + `popularity_daily` (fenêtre N jours) + fan-out lineage.

| Cible gold | Source | Transformation |
|---|---|---|
| `catalog` | `catalog.catalog` | join |
| `schema` | `catalog.schema` | join |
| `table_name` | `catalog.table_name` | join |
| `table_full_name` | `catalog.table_full_name` | join |
| `days_since_last_read` | `catalog.last_read_at` | `datediff(current_date, last_read_at)` |
| `is_unused` | dérivé | `days_since_last_read > N` (ex. 90) OU jamais lu |
| `has_owner_tag` | `catalog.owner` | `owner IS NOT NULL` |
| `has_domain_tag` | `catalog.domain` | `domain IS NOT NULL` |
| `has_cost_center_tag` | `catalog.cost_center` | `cost_center IS NOT NULL` |
| `is_orphan` | dérivé | `NOT has_owner_tag AND NOT has_domain_tag AND NOT has_cost_center_tag` |
| `is_stale_but_consumed` | `catalog` | `freshness_lag_hours > SLA AND days_since_last_read < 7` |
| `downstream_fanout` | `table_lineage` | `COUNT(DISTINCT target)` (30 j) |
| `is_critical` | dérivé | `downstream_fanout ≥ seuil` (ex. 5) |
| `recommended_action` | dérivé | règle prioritaire (orphan > stale_but_consumed > unused) |
| `severity` | dérivé | `HIGH` si stale_but_consumed/critical, `MEDIUM` unused, `LOW` orphan |

---

## 3. Mapping GOLD — Page 2 : Consommateurs

### 3.1 `gold_dbx_usage_consumer_daily`

Base : `gold_dbx_usage_table_daily` agrégé par `(cloud_provider, consumer_id, period_start)`.

| Cible gold | Source | Transformation |
|---|---|---|
| `consumer_name` | `daily.consumer_name` | `MAX` |
| `consumer_type` | `daily.consumer_type` | `MAX` (type dominant) |
| `distinct_data_products` | `daily.catalog, daily.schema, daily.table_name` | `COUNT(DISTINCT)` |
| `request_count` | `daily.request_count` | `SUM` |
| `rows_read` / `data_read_bytes` | `daily.*` | `SUM` |
| `duration_seconds` | `daily.duration_seconds` | `SUM` |
| `estimated_cost_usd` | `daily.estimated_cost_usd` | `SUM` |
| `consumer_rank` | dérivé | `RANK() OVER (PARTITION BY period_start ORDER BY estimated_cost_usd DESC)` |

---

## 4. Mapping GOLD transverse

### 4.1 `gold_dbx_usage_recommendations` (réactif) — règles de génération

Chaque reco est produite par une règle sur les tables gold `governance` / `catalog` / `popularity_daily`.

| Règle (condition) | object_type | category | severity | personas | recommended_action | savings |
|---|---|---|---|---|---|---|
| `governance.is_unused=true AND is_critical=false` | DATA_PRODUCT | LIFECYCLE | MEDIUM | OWN,FIN,GOV | Proposer dépréciation / suppression | coût maintenance évité |
| `governance.is_stale_but_consumed=true` | DATA_PRODUCT | FRESHNESS | HIGH | DE,OWN | Corriger pipeline amont ; prévenir consommateurs | NULL |
| `governance.is_orphan=true` | DATA_PRODUCT | GOVERNANCE | LOW | GOV,FIN | Ajouter tags owner/domain/cost-center | NULL |
| `governance.is_critical=true AND is_unused` (contradiction lineage) | DATA_PRODUCT | LIFECYCLE | HIGH | OWN,GOV | Ne PAS déprécier ; investiguer dépendances aval | NULL |
| `catalog.classification IS NULL` sur DP publié | DATA_PRODUCT | GOVERNANCE | MEDIUM | GOV | Classifier la donnée | NULL |
| `query_perf.failure_rate_pct > seuil` | DATA_PRODUCT | RELIABILITY | HIGH | DE,AN | Investiguer accès en échec (droits/schema) | NULL |
| `consumer_daily.estimated_cost_usd > seuil` | CONSUMER | FINOPS | MEDIUM | FIN | Sensibiliser / optimiser le consommateur | est. |

Champs communs : `recommendation_id = sha2(object_type||object_id||category||generated_date)`, `mode='REACTIVE'`, `first_seen_date`/`last_seen_date` via merge (garde la 1re détection, met à jour la dernière).

### 4.2 `gold_dbx_usage_forecast_daily` (prédictif) — source

| Cible gold | Source | Transformation |
|---|---|---|
| `object_type` / `object_id` | table gold agrégée | dimension de la série |
| `metric_name` | (paramètre) | une passe `ai_forecast` par métrique |
| `predicted_value` / `lower_bound` / `upper_bound` | `ai_forecast(<gold_daily>, horizon)` | sortie forecast (`*_forecast`, `*_lower`, `*_upper`) |
| `horizon_date` | `ai_forecast` | horizon projeté |
| `method` | constante | `'ai_forecast'` |

Séries alimentées (historique gold `*_daily` en entrée) :

| metric_name | Table source gold | Objet |
|---|---|---|
| `request_count` | `gold_dbx_usage_table_popularity_daily` | adoption / déclin |
| `distinct_consumers` | `gold_dbx_usage_table_popularity_daily` | portée |
| `estimated_cost_usd` | `gold_dbx_usage_table_popularity_daily` / `consumer_daily` | budget |
| `data_read_bytes` | `gold_dbx_usage_table_popularity_daily` | volume à venir |

---

## 5. Data Quality (contrôles au passage curated → gold)

| Contrôle | Table | Action si échec |
|---|---|---|
| `(catalog, schema, table_name)` résolu dans le registre `catalog` | `*_daily` | LEFT JOIN + flag `unknown_data_product` (exclu du périmètre DP) |
| `consumer_id IS NOT NULL` | `*_daily` | `expect_or_drop` (accès système/interne non attribuable) |
| `rows_read >= 0` / `data_read_bytes >= 0` | `*_daily` | drop ligne + reject |
| `estimated_cost_usd IS NOT NULL` quand requête facturée | `*_daily` | flag `cost_unresolved` (prix manquant) |
| grain unique (pas de doublon clé) | toutes `*_daily` | `apply_changes` SCD1 (dernier gagne) |
| attribution coût : somme parts = coût requête | `*_daily` | contrôle réconciliation `SUM(part) = cost(query)` |
