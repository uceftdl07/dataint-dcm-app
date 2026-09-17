# Compute Monitoring — Data Mapping (system → curated → gold)

> Mapping de bout en bout pour la feature **Compute Monitoring**.
> Colonnes : `Cible` ← `Source` + `Transformation`. Sources = system tables Databricks ingérées en `curated_dbx_*`.
> Voir le modèle : [propososition_compute_datamodel.md](propososition_compute_datamodel.md).
> Notation `system.compute.usage_metadata.cluster_id` = champ imbriqué (struct) de la table système.

---

## 0. Conventions de mapping

- **Coût $** = `curated_dbx_billing_usage.usage_quantity` × prix effectif :
  `list_prices.pricing.effective_list.default` du SKU actif à `usage_date` (join sur `sku_name` + fenêtre `price_start_time ≤ usage_date < price_end_time`).
- **Rattachement usage → objet compute** : `billing_usage.usage_metadata.cluster_id` (clusters) ou `usage_metadata.warehouse_id` (warehouses).
- **Percentiles** : `percentile_approx(col, 0.95)` sur la fenêtre jour (perf + coût).
- **LZ / cloud** : `source_lz_id` et `cloud_provider` propagés depuis curated ; join `dim_landing_zone` pour `ba_name`.
- **Idle cluster** : minutes RUNNING (node_timeline présent) sans requête active (`query_history` chevauchant la minute) / minutes RUNNING totales.

---

## 1. Mapping CURATED (system tables → curated_dbx_*)

### 1.1 `curated_dbx_compute_warehouses` ← `system.compute.warehouses`

| Cible curated | Source | Transformation |
|---|---|---|
| `cloud_provider` | (contexte ingestion) | constante par run (`azure`/`aws`) |
| `account_id` | `account_id` | direct |
| `workspace_id` | `workspace_id` | direct |
| `warehouse_id` | `warehouse_id` | direct |
| `warehouse_name` | `warehouse_name` | direct |
| `warehouse_type` | `warehouse_type` | direct |
| `warehouse_channel` | `warehouse_channel` | direct |
| `warehouse_size` | `warehouse_size` | direct |
| `min_clusters` | `min_clusters` | direct |
| `max_clusters` | `max_clusters` | direct |
| `auto_stop_minutes` | `auto_stop_minutes` | direct |
| `tags` | `tags` | direct (MAP) |
| `change_time` | `change_time` | watermark |
| `delete_time` | `delete_time` | NULL = actif |

### 1.2 `curated_dbx_compute_warehouse_events` ← `system.compute.warehouse_events`

| Cible curated | Source | Transformation |
|---|---|---|
| `cloud_provider` | (contexte) | constante |
| `account_id` / `workspace_id` / `warehouse_id` | idem | direct |
| `event_type` | `event_type` | direct |
| `cluster_count` | `cluster_count` | direct |
| `event_time` | `event_time` | watermark |
| `event_date` | `event_time` | `to_date(event_time)` (partition) |

### 1.3 `curated_dbx_compute_node_types` ← `system.compute.node_types`

| Cible curated | Source | Transformation |
|---|---|---|
| `cloud_provider` | (contexte) | constante |
| `account_id` | `account_id` | direct |
| `node_type` | `node_type` | direct |
| `core_count` | `core_count` | direct |
| `memory_mb` | `memory_mb` | direct |
| `gpu_count` | `gpu_count` | `coalesce(gpu_count, 0)` |

> Les tables `curated_dbx_billing_usage`, `curated_dbx_billing_list_prices`, `curated_dbx_compute_clusters`, `curated_dbx_compute_node_timeline`, `curated_dbx_query_history` sont **déjà** produites (cf. `system_tables/specs.py`) — mapping système existant, non redéfini ici.

---

## 2. Mapping GOLD — Page 1 : Clusters

### 2.1 `gold_dbx_compute_cluster_cost_daily`

Base : `curated_dbx_billing_usage` filtré `usage_metadata.cluster_id IS NOT NULL`, agrégé par `(cloud_provider, workspace_id, cluster_id, period_start)` (`period_start = usage_date` tel qu'ingéré).

| Cible gold | Source | Transformation |
|---|---|---|
| `cluster_id` | `billing_usage.usage_metadata.cluster_id` | clé de groupe |
| `cluster_name` | `curated_dbx_compute_clusters.cluster_name` | join dernier `change_time` ≤ jour |
| `owner` | `clusters.owned_by` \| `tags['owner']` | `coalesce` |
| `ba_name` | `dim_landing_zone.ba_name` | join `source_lz_id` |
| `cost_center` | `clusters.tags['cost_center']` | direct (NULL si absent) |
| `sku_group` | `billing_usage.sku_name` | `CASE WHEN sku LIKE '%SERVERLESS%' THEN 'serverless' WHEN sku LIKE '%PHOTON%' THEN 'photon' ELSE 'classic' END` |
| `dbu_quantity` | `billing_usage.usage_quantity` | `SUM` (filtre `usage_unit='DBU'`) |
| `cost_usd` | `usage_quantity` × `list_prices.pricing.effective_list.default` | `SUM(qty × price)` |
| `cost_usd_prev_day` | même table, `period_start - 1 jour` | `LAG` sur clé |
| `cost_delta_pct` | dérivé | `(cost - prev) / NULLIF(prev,0) × 100` |
| `cost_rank` | dérivé | `RANK() OVER (PARTITION BY source_lz_id, period_start ORDER BY cost_usd DESC)` |
| `is_top_cost` | dérivé | `cost_rank ≤ 10` |

### 2.2 `gold_dbx_compute_cluster_efficiency_daily`

Base : `curated_dbx_compute_node_timeline` agrégé par `(cloud_provider, workspace_id, cluster_id, period_start)` (`period_start = to_date(start_time)`) + join `clusters`, `node_types`, `cost_daily`.

| Cible gold | Source | Transformation |
|---|---|---|
| `cpu_util_avg_pct` | `node_timeline.cpu_user_percent + cpu_system_percent` | `AVG(user+system)` |
| `cpu_util_p95_pct` | idem | `percentile_approx(user+system, 0.95)` |
| `mem_util_avg_pct` | `node_timeline.mem_used_percent` | `AVG` |
| `mem_util_p95_pct` | `node_timeline.mem_used_percent` | `percentile_approx(0.95)` |
| `cpu_wait_avg_pct` | `node_timeline.cpu_wait_percent` | `AVG` |
| `idle_pct` | `node_timeline` × `query_history` | minutes RUNNING sans query / minutes RUNNING |
| `uptime_hours` | `node_timeline` | `COUNT(minutes distinctes) / 60` |
| `active_hours` | `query_history` | heures distinctes avec ≥1 query sur le cluster |
| `worker_count_avg` | `node_timeline` (non-driver) | `AVG(count instances par minute)` |
| `worker_count_max` | `node_timeline` (non-driver) | `MAX(count instances par minute)` |
| `autoscale_oscillation` | `node_timeline` | nb changements de `worker_count` sur le jour |
| `driver_node_type` | `clusters.driver_node_type` | join |
| `worker_node_type` | `clusters.worker_node_type` | join |
| `is_zombie` | dérivé | `uptime_hours > 8 AND cpu_util_p95_pct < 15 AND active_hours < 1` |
| `utilization_status` | dérivé | `OVER` si `cpu_p95<40 AND mem_p95<50` ; `UNDER` si `cpu_p95>85 OR mem_p95>85` ; sinon `OPTIMAL` |
| `recommended_node_type` | `node_types` | node ≥ util p95 le moins cher (lookup capacité) |
| `rightsizing_reco` | dérivé | texte selon `utilization_status` (ex. « Réduire vers {recommended_node_type} ») |
| `estimated_savings_usd` | `cost_daily` × ratio | `cost_usd × (1 - prix_node_cible / prix_node_actuel)` si `OVER` |

### 2.3 `gold_dbx_compute_cluster_reliability_daily`

Base : `curated_dbx_compute_clusters` (SCD) + `curated_dbx_access_audit` (événements cluster).

| Cible gold | Source | Transformation |
|---|---|---|
| `start_count` | `access_audit` action `create`/`start` cluster | `COUNT` par jour |
| `avg_startup_seconds` | `access_audit` (start → running) | `AVG(delta)` |
| `unexpected_termination_count` | `clusters.delete_time` / audit `termination_reason` | count reasons ≠ `USER_REQUEST`/`INACTIVITY` |
| `top_termination_reason` | audit `termination_reason` | `MODE` |
| `auto_termination_minutes` | `clusters.auto_termination_minutes` | dernier état |
| `has_auto_termination` | dérivé | `auto_termination_minutes > 0` |

### 2.4 `gold_dbx_compute_cluster_governance`

Base : `curated_dbx_compute_clusters` dernier `change_time` (état courant) + `efficiency_daily`.

| Cible gold | Source | Transformation |
|---|---|---|
| `cluster_name` | `clusters.cluster_name` | direct |
| `has_owner_tag` | `clusters.tags` | `tags['owner'] IS NOT NULL` |
| `has_cost_center_tag` | `clusters.tags` | `tags['cost_center'] IS NOT NULL` |
| `dbr_version` | `clusters.dbr_version` | direct |
| `dbr_is_lts_current` | `dbr_version` | lookup référentiel LTS supportées |
| `node_oversized` | `efficiency_daily.utilization_status` | `= 'OVER'` sur N derniers jours |
| `is_single_node` | `clusters.worker_count` | `worker_count = 0` |
| `recommended_action` | dérivé | règle prioritaire (tag manquant > DBR obsolète > oversize) |
| `severity` | dérivé | `HIGH` si DBR obsolète/sécurité, `MEDIUM` oversize, `LOW` tag |

---

## 3. Mapping GOLD — Page 2 : SQL Warehouses

### 3.1 `gold_dbx_compute_warehouse_cost_daily`

Base : `curated_dbx_billing_usage` filtré `usage_metadata.warehouse_id IS NOT NULL` + `query_history` (comptage) + `warehouses`, agrégé par `(cloud_provider, workspace_id, warehouse_id, period_start)`.

| Cible gold | Source | Transformation |
|---|---|---|
| `warehouse_name` | `curated_dbx_compute_warehouses.warehouse_name` | join dernier `change_time` |
| `warehouse_size` | `warehouses.warehouse_size` | join |
| `dbu_quantity` | `billing_usage.usage_quantity` | `SUM` (unit DBU) |
| `cost_usd` | `usage_quantity × effective_list` | `SUM(qty × price)` |
| `cost_usd_prev_day` | même table J-1 | `LAG` |
| `cost_delta_pct` | dérivé | `(c-prev)/NULLIF(prev,0)×100` |
| `query_count` | `query_history` (`compute.warehouse_id`) | `COUNT(statement_id)` |
| `cost_per_query_usd` | dérivé | `cost_usd / NULLIF(query_count,0)` |
| `top_consumer` | `query_history.executed_by` | user avec `MAX(SUM durée)` |

### 3.2 `gold_dbx_compute_warehouse_utilization_daily`

Base : `curated_dbx_compute_warehouse_events` + `query_history` + `warehouses`, agrégé par `(cloud_provider, workspace_id, warehouse_id, period_start)`.

| Cible gold | Source | Transformation |
|---|---|---|
| `running_hours` | `warehouse_events` | somme intervalles `RUNNING`→`STOPPED` du jour |
| `active_query_hours` | `query_history` | heures distinctes avec ≥1 query |
| `idle_pct` | dérivé | `(running_hours - active_query_hours)/NULLIF(running_hours,0)×100` |
| `active_to_running_ratio` | dérivé | `active_query_hours / NULLIF(running_hours,0)` |
| `auto_stop_minutes` | `warehouses.auto_stop_minutes` | join dernier état |
| `has_auto_stop` | dérivé | `auto_stop_minutes > 0` |
| `scale_up_events` | `warehouse_events` | `COUNT(event_type IN ('SCALING_UP','SCALED_UP'))` |
| `scale_down_events` | `warehouse_events` | `COUNT(event_type='SCALED_DOWN')` |
| `avg_cluster_count` | `warehouse_events.cluster_count` | `AVG` pondéré temps |
| `max_cluster_count` | `warehouse_events.cluster_count` | `MAX` |
| `peak_concurrency` | `query_history` | max requêtes chevauchantes (`start_time`/`end_time`) |
| `utilization_status` | dérivé | `OVER` si `idle_pct>60` ; `UNDER` si `peak_concurrency ≥ max_clusters × seuil` ; sinon `OPTIMAL` |
| `rightsizing_reco` | dérivé | texte selon status (ex. « Réduire taille / activer auto-stop ») |
| `estimated_savings_usd` | `cost_daily` × `idle_pct` | `cost_usd × idle_pct/100` (borne récupérable) |

### 3.3 `gold_dbx_compute_warehouse_query_performance_daily`

Base : `curated_dbx_query_history` filtré sur `compute.warehouse_id`, agrégé par `(cloud_provider, workspace_id, warehouse_id, period_start)`.

| Cible gold | Source | Transformation |
|---|---|---|
| `query_count` | `statement_id` | `COUNT` |
| `failed_count` | `execution_status` | `COUNT(status IN ('FAILED','CANCELED'))` |
| `failure_rate_pct` | dérivé | `failed_count / NULLIF(query_count,0) × 100` |
| `latency_p50_ms` | `total_duration_ms` | `percentile_approx(0.50)` |
| `latency_p95_ms` | `total_duration_ms` | `percentile_approx(0.95)` |
| `latency_p99_ms` | `total_duration_ms` | `percentile_approx(0.99)` |
| `queue_time_avg_ms` | `waiting_for_compute_duration_ms` | `AVG` |
| `queue_time_p95_ms` | `waiting_for_compute_duration_ms` | `percentile_approx(0.95)` |
| `spill_query_count` | `spilled_local_bytes` | `COUNT(spilled_local_bytes > 0)` |
| `cache_hit_pct` | `read_io_cache_percent` | `AVG` |
| `bytes_scanned` | `read_bytes` | `SUM` |
| `rows_scanned` | `read_rows` | `SUM` |
| `top_slow_statement_id` | `statement_id`, `total_duration_ms` | `statement_id` du `MAX(total_duration_ms)` |

---

## 4. Mapping GOLD transverse

### 4.1 `gold_dbx_compute_recommendations` (réactif) — règles de génération

Chaque reco est produite par une règle sur les tables gold `*_daily` / `governance`. `estimated_savings_usd` repris de la table source.

| Règle (condition) | object_type | category | severity | personas | recommended_action | savings |
|---|---|---|---|---|---|---|
| `efficiency.utilization_status='OVER'` | CLUSTER | RIGHTSIZING | MEDIUM | FIN,DE | Réduire vers `recommended_node_type` | `estimated_savings_usd` |
| `efficiency.is_zombie=true` | CLUSTER | FINOPS | HIGH | FIN,DE | Éteindre / activer auto-stop | `idle_pct × cost` |
| `reliability.has_auto_termination=false` | CLUSTER | FINOPS | HIGH | FIN,GOV | Imposer auto-termination | est. idle |
| `governance.has_owner_tag=false` | CLUSTER | GOVERNANCE | LOW | GOV,FIN | Ajouter tag owner/cost-center | NULL |
| `governance.dbr_is_lts_current=false` | CLUSTER | GOVERNANCE | HIGH | GOV,DE | Monter version DBR LTS | NULL |
| `utilization.has_auto_stop=false` | WAREHOUSE | FINOPS | HIGH | FIN,GOV | Activer auto-stop | est. idle |
| `utilization.utilization_status='OVER'` | WAREHOUSE | RIGHTSIZING | MEDIUM | FIN,DE | Réduire taille warehouse | `estimated_savings_usd` |
| `query_perf.queue_time_p95_ms > seuil` | WAREHOUSE | RIGHTSIZING | MEDIUM | DE,AN | Augmenter max_clusters (scaling) | NULL |
| `query_perf.failure_rate_pct > seuil` | WAREHOUSE | RELIABILITY | HIGH | DE,AN | Investiguer requêtes en échec | NULL |
| `query_perf.spill_query_count > seuil` | WAREHOUSE | RIGHTSIZING | MEDIUM | DE | Tuner requêtes / upsize ciblé | NULL |

Champs communs : `recommendation_id = sha2(object_type||object_id||category||generated_date)`, `mode='REACTIVE'`, `first_seen_date`/`last_seen_date` via merge (garde la 1re détection, met à jour la dernière).

### 4.2 `gold_dbx_compute_forecast_daily` (prédictif) — source

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
| `cost_usd` | `gold_dbx_compute_cluster_cost_daily` / `gold_dbx_compute_warehouse_cost_daily` | budget |
| `dbu_quantity` | idem | consommation |
| `cpu_util_p95_pct` | `gold_dbx_compute_cluster_efficiency_daily` | rightsizing anticipé |
| `query_count` | `gold_dbx_compute_warehouse_query_performance_daily` | charge à venir |
| `queue_time_p95_ms` | `gold_dbx_compute_warehouse_query_performance_daily` | saturation à venir |

---

## 5. Data Quality (contrôles au passage curated → gold)

| Contrôle | Table | Action si échec |
|---|---|---|
| `usage_quantity >= 0` | cost_daily | drop ligne + reject |
| `cpu_util_p95_pct BETWEEN 0 AND 100` | efficiency_daily | clamp [0,100] |
| `cost_usd IS NOT NULL` quand `dbu_quantity > 0` | cost_daily | expect_or_drop (prix manquant) |
| `warehouse_id` résolu dans `warehouses` | warehouse_* | LEFT JOIN + flag `unknown_warehouse` |
| grain unique (pas de doublon clé) | toutes `*_daily` | `apply_changes` SCD1 (dernier gagne) |
