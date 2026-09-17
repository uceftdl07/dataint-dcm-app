# Modèle de données

## État actuel

Le modèle actif DCM est maintenant centré sur **Unity Catalog + Databricks SQL Warehouse**.

Le backend ne lit plus une couche Lakebase/PostgreSQL. Il utilise `DatabricksWarehousePool` et `databricks-sql-connector` pour interroger directement les tables du catalogue Databricks configure (`DCM_DATABRICKS_CATALOG` + `DCM_DATABRICKS_SCHEMA`).

À lire en priorité :

- [`../MIGRATION-LAKEBASE-TO-WAREHOUSE.md`](../MIGRATION-LAKEBASE-TO-WAREHOUSE.md) : ce qui a été changé dans le code et la configuration.
- [`data-models.md`](./data-models.md) : historique détaillé du datamodel, avec note d'actualisation Warehouse.
- [`REFAC-2026-04-30-datamodel-backend.md`](./REFAC-2026-04-30-datamodel-backend.md) : trace du refactoring des noms métier (`cluster` -> `compute`, `compliance` -> `standard_check`).

## Couches actives

| Couche | Rôle | Exemples de tables |
| --- | --- | --- |
| RAW | Archive opaque des payloads collectés | `raw_metrics` |
| CURATED | Tables normalisées par domaine, consommées par l'API | `curated_pipeline_metrics`, `curated_compute_metrics`, `curated_standard_checks` |
| GOLD | Agrégats métier prêts pour l'UI | `gold_standard_check_score`, `gold_data_product_usage` |
| ADMIN | Configuration applicative DCM | `dcm_app_users`, `dcm_landing_zones`, `dcm_alert_rules` |

## Domaines couverts

- Pipelines et activity runs.
- Compute / clusters.
- Coûts.
- Databases.
- Sécurité.
- Users.
- Standard Checks.
- Landing Zones et métadonnées d'administration.

L'isolation multi-LZ reste portée par `source_lz_id` et `subscription_or_account_id`. Les rôles non admin sont filtrés côté backend via `dcm_user_lz_access`.

---

Les anciens passages qui mentionnent Lakebase/PostgreSQL décrivent l'architecture précédente ou les décisions de workshop. Ils ne doivent plus être utilisés comme cible d'implémentation backend.
