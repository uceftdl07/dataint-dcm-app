# Contracts — Gold Tables Consumption Interface

Cette feature n'expose pas d'API HTTP ; l'interface consommable par les futurs systèmes (Epic d'exposition backend, cf. spec.md "Out of scope") est le **contrat de schéma des tables Delta gold** dans `it.ba_data_connect_monitoring__{env}`. Ce fichier fixe ce qui est garanti stable pour un consommateur externe ; le détail colonne-par-colonne exhaustif reste dans le spike (liens ci-dessous).

## Garanties de contrat (toutes tables gold de cet Epic)

1. **Nommage stable** : `gold_dbx_compute_cluster_{cost,efficiency,reliability}_daily`, `gold_dbx_compute_cluster_governance`, `gold_dbx_compute_warehouse_{cost,utilization,query_performance}_daily`, `gold_dbx_compute_recommendations`, `gold_dbx_compute_forecast_daily`. Tout renommage ultérieur est un **breaking change** (P14/P2 — nécessite un plan de migration).
2. **Clé de grain stable** : documentée dans [data-model.md](./data-model.md) — un consommateur peut s'appuyer sur l'unicité `(cloud_provider, workspace_id, {cluster_id|warehouse_id}, period_start)` (ou clé équivalente pour `governance`/`recommendations`/`forecast_daily`). **Exception** : les 4 tables `gold_dbx_compute_cluster_*` (cost/efficiency/reliability/governance) ne portent PAS `source_lz_id`/`ba_name` — `account_id` (system tables) n'est pas mappable de façon fiable vers `dim_landing_zone.subscription_or_account_id` aujourd'hui (cf. T002 sub-spec Notes) ; leur `cost_rank`/`is_top_cost` est un classement global, pas par LZ.
3. **Colonnes obligatoires sur toutes les tables** : `cloud_provider`, `workspace_id` (sauf `recommendations`/`forecast_daily` qui portent `object_type`/`object_id` à la place de `cluster_id`/`warehouse_id`), `_generated_at`. `source_lz_id` est obligatoire sauf sur les 4 tables `gold_dbx_compute_cluster_*` (cf. exception ci-dessus, point 2). Voir [`compute_datamodel.md`](../../docs/spike/compute-metrics-definition/compute_datamodel.md) §0 pour le détail des conventions communes.
4. **Fraîcheur** : rafraîchissement quotidien best-effort (pas de SLA horaire garanti — cf. Clarifications spec.md).
5. **Idempotence côté lecture** : un consommateur peut relire la table à tout moment sans risque de doublon (MERGE garanti côté écriture — FR-014).
6. **Historique disponible** : au moins 30 jours dès l'activation (FR-017), croissant ensuite indéfiniment (pas de purge dans cet Epic).

## Schémas détaillés par table

| Table | Détail colonnes | Mapping / dérivation |
|---|---|---|
| `curated_dbx_compute_warehouses` | [compute_datamodel.md §1.2](../../docs/spike/compute-metrics-definition/compute_datamodel.md) | [compute_datamapping.md §1.1](../../docs/spike/compute-metrics-definition/compute_datamapping.md) |
| `curated_dbx_compute_warehouse_events` | idem §1.2 | idem §1.2 |
| `curated_dbx_compute_node_types` | idem §1.2 | idem §1.3 |
| `gold_dbx_compute_cluster_cost_daily` | [compute_datamodel.md §2.1](../../docs/spike/compute-metrics-definition/compute_datamodel.md) | [compute_datamapping.md §2.1](../../docs/spike/compute-metrics-definition/compute_datamapping.md) |
| `gold_dbx_compute_cluster_efficiency_daily` | §2.2 | §2.2 |
| `gold_dbx_compute_cluster_reliability_daily` | §2.3 | §2.3 |
| `gold_dbx_compute_cluster_governance` | §2.4 | §2.4 |
| `gold_dbx_compute_warehouse_cost_daily` | §3.1 | §3.1 |
| `gold_dbx_compute_warehouse_utilization_daily` | §3.2 | §3.2 |
| `gold_dbx_compute_warehouse_query_performance_daily` | §3.3 | §3.3 |
| `gold_dbx_compute_recommendations` | §4.1 | §4.1 (règles de génération) |
| `gold_dbx_compute_forecast_daily` | §4.2 | §4.2 |

## Data Quality (contrôle au passage curated → gold)

Repris de [compute_datamapping.md §5](../../docs/spike/compute-metrics-definition/compute_datamapping.md) — chaque job gold applique ces contrôles avant merge :

| Contrôle | Action si échec |
|---|---|
| `usage_quantity >= 0` | drop ligne + reject |
| `cpu_util_p95_pct BETWEEN 0 AND 100` | clamp `[0,100]` |
| `cost_usd IS NOT NULL` quand `dbu_quantity > 0` | reject (prix manquant) |
| `warehouse_id` résolu dans `curated_dbx_compute_warehouses` | LEFT JOIN + flag `unknown_warehouse` |
| grain unique (pas de doublon clé) | MERGE idempotent (dernier gagne) |
