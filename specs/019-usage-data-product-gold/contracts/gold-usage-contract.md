# Contract: Gold Usage Data Product — schémas figés

> Contrat de schéma pour les 8 tables gold usage (T002-T004). Toute évolution de colonne (ajout non-breaking OK, renommage/suppression = breaking) doit être documentée ici et versionnée (P14 Schema Versioning). Colonnes détaillées : voir [`data-model.md`](../data-model.md) et le spike [`usage_datamodel.md`](../../../docs/spike/usage-data-product-definition/usage_datamodel.md).
>
> **Note (2026-09-04)** : `gold_dbx_usage_dim_workspace` (T003) a été retirée du périmètre — jamais déployée en dev (0 ligne), redondante avec `dim_dbx_workspace` (spec 020, référentiel LZ fiable déjà joint par `dim_landing_zone`). Voir `specs/019-usage-data-product-gold/stories/T003-gold-usage-catalog-governance.md`.

## Conventions communes (toutes les tables gold usage)

- `cloud_provider` (STRING, `azure`|`aws`) : **toujours** dans la clé/grain.
- `period_start` (DATE) : partition, pour les tables `*_daily`. Alias `usage_date` conservé sur `gold_dbx_usage_table_daily` uniquement (compat historique `gold_data_product_usage`).
- `_generated_at` (TIMESTAMP) : horodatage de calcul gold, sur toutes les tables.
- `table_full_name` (STRING, dérivé `catalog.schema.table_name`) : présent sur toutes les tables portant `(catalog, schema, table_name)`.
- **Interdit** : `source_lz_id`, `subscription_or_account_id` sur toute table gold usage, sans exception (FR-008, non négociable — violation = régression à corriger avant merge). La résolution `workspace_id → LZ` vit uniquement dans `dim_dbx_workspace` (spec 020), hors périmètre de ce contrat.

## T002 — Fait de consommation et agrégats

| Table | Grain | Colonnes clé (hors communes) |
|---|---|---|
| `gold_dbx_usage_table_daily` | `(cloud_provider, catalog, schema, table_name, consumer_id, period_start)` | `consumer_id`, `consumer_name`, `consumer_type`, `request_count`, `rows_read`, `rows_written`, `data_read_bytes`, `data_written_bytes`, `duration_seconds`, `estimated_cost_usd`, `failed_access_count`, `last_used_at` |
| `gold_dbx_usage_table_popularity_daily` | `(cloud_provider, catalog, schema, table_name, period_start)` | `owner`, `domain`, `distinct_consumers`, `request_count`, `rows_read`, `data_read_bytes`, `estimated_cost_usd`, `consumers_by_type`, `downstream_fanout`, `popularity_rank`, `request_count_prev_day`, `request_delta_pct` |
| `gold_dbx_usage_consumer_daily` | `(cloud_provider, consumer_id, period_start)` | `consumer_name`, `consumer_type`, `distinct_data_products`, `request_count`, `rows_read`, `data_read_bytes`, `duration_seconds`, `estimated_cost_usd`, `consumer_rank` |
| `gold_dbx_usage_table_query_performance_daily` | `(cloud_provider, catalog, schema, table_name, period_start)` | `query_count`, `failed_count`, `failure_rate_pct`, `latency_p50_ms`, `latency_p95_ms`, `bytes_scanned`, `rows_scanned` |

## T003 — Registre / état / gouvernance

| Table | Grain | Colonnes clé (hors communes) |
|---|---|---|
| `gold_dbx_usage_table_catalog` | `(cloud_provider, catalog, schema, table_name)` | `table_type`, `owner`, `domain`, `cost_center`, `classification`, `is_data_product`, `created_at`, `created_by`, `last_write_at`, `last_operation`, `last_operation_at`, `last_operation_by`, `last_altered_at`, `last_read_at`, `freshness_basis`, `freshness_lag_hours` |
| `gold_dbx_usage_table_governance` | `(cloud_provider, catalog, schema, table_name)` | `days_since_last_read`, `is_unused` (>90j), `has_owner_tag`, `has_domain_tag`, `has_cost_center_tag`, `is_orphan`, `is_stale_but_consumed` (SLA 24h), `downstream_fanout`, `is_critical` (fanout≥5), `recommended_action`, `severity` |

## T004 — Transverse

| Table | Grain | Colonnes clé (hors communes) |
|---|---|---|
| `gold_dbx_usage_recommendations` | `(recommendation_id)` | `object_type`, `object_id`, `object_name`, `category`, `mode`, `title`, `detail`, `recommended_action`, `estimated_savings_usd`, `severity`, `personas`, `status`, `first_seen_date`, `last_seen_date` |
| `gold_dbx_usage_forecast_daily` | `(cloud_provider, object_type, object_id, metric_name, horizon_date)` | `predicted_value`, `lower_bound`, `upper_bound`, `method` (`ai_forecast`) |

## Règles de non-régression (à vérifier en review de chaque PR T002-T004)

1. Aucune colonne `source_lz_id`/`subscription_or_account_id` sur aucune table gold usage, sans exception.
2. `cloud_provider` présent dans la clé de merge/grain de **toutes** les tables.
3. `table_full_name` dérivé identique (`concat_ws('.', catalog, schema, table_name)`) partout où `(catalog, schema, table_name)` existe.
4. `recommendation_id` stable (même hash pour la même entité/catégorie/jour) — pas de doublon sur re-run.
5. Contrôle de réconciliation coût (`SUM(parts) = coût requête`) testé en pytest, pas seulement documenté.
