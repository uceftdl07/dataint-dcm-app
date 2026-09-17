# Compute Monitoring — Data Model (Curated + Gold)

> Modèle de données pour la feature **Compute Monitoring** (pages Clusters + SQL Warehouses).
> Aligné sur la médaillon DCM existante : `system.*` → **CURATED** (`curated_dbx_*`, SCD1/append idempotent) → **GOLD** (`gold_*`, agrégats métier prêts API).
> Catalog / schéma : `it.ba_data_connect_monitoring__{env}` (`__d` dev, `__p` prod) — jamais codé en dur (vars bundle `catalog` / `schema`).
> Cloud : tables mutualisées Azure/AWS → `cloud_provider` fait toujours partie de la clé.

---

## 0. Vue d'ensemble

```text
system.billing.usage / list_prices ─┐
system.compute.clusters             │
system.compute.node_timeline        ├─►  CURATED (curated_dbx_*)  ─►  GOLD (gold_dbx_compute_*)
system.compute.node_types           │        merge idempotent           agrégats jour + reco + forecast
system.compute.warehouses           │        watermark / SCD1            prêts pour l'API / dashboard
system.compute.warehouse_events     │
system.query.history               ─┘
```

**Grain gold cible : 1 jour × 1 objet compute** (cluster ou warehouse) × LZ × cloud. Suffisant pour FinOps + rightsizing + prédictif ; évite d'exposer la volumétrie fine (node_timeline = 1 ligne/node/min, query.history = 1 ligne/requête) au backend.

**Conventions colonnes partagées (toutes tables gold)** :

| Colonne | Type | Rôle |
|---|---|---|
| `cloud_provider` | STRING | `azure` \| `aws` — anti-collision multi-cloud, partie de clé |
| `source_lz_id` | STRING | Landing Zone (FK → `dim_landing_zone.lz_id`) |
| `workspace_id` | STRING | Workspace Databricks |
| `period_start` | DATE | Début de la période d'agrégation (partition) — jour pour `*_daily` (= le jour lui-même) ; généralisable au 1er du mois / au 1er janvier pour de futurs grains `*_monthly` / `*_yearly` |
| `_generated_at` | TIMESTAMP | Horodatage calcul gold |

> `period_start` remplace l'ancien nom `usage_date` : même sémantique aujourd'hui (1 valeur = 1 jour), mais un nom générique qui évite de renommer la colonne si des grains `*_monthly`/`*_yearly` sont ajoutés plus tard (cf. spike agrégation multi-grain).

---

## 1. Couche CURATED — system tables

### 1.1 Tables déjà ingérées (réutilisées telles quelles)

| Curated table | Source system table | Clé de merge | Watermark |
|---|---|---|---|
| `curated_dbx_billing_usage` | `system.billing.usage` | `cloud_provider, record_id` | `usage_end_time` |
| `curated_dbx_billing_list_prices` | `system.billing.list_prices` | `cloud_provider, sku_name, price_start_time` | — (full) |
| `curated_dbx_compute_clusters` | `system.compute.clusters` | `cloud_provider, account_id, workspace_id, cluster_id, change_time` | `change_time` |
| `curated_dbx_compute_node_timeline` | `system.compute.node_timeline` | `cloud_provider, account_id, workspace_id, cluster_id, instance_id, start_time` | `start_time` |
| `curated_dbx_query_history` | `system.query.history` | `cloud_provider, statement_id` | `start_time` |

### 1.2 Tables à AJOUTER au registre `system_tables/specs.py`

Trois nouvelles `IngestionSpec` à déclarer pour couvrir les warehouses et le rightsizing node.

#### `curated_dbx_compute_warehouses` — source `system.compute.warehouses` (SCD)

| Colonne | Type | Notes |
|---|---|---|
| `cloud_provider` | STRING | clé |
| `account_id` | STRING | clé |
| `workspace_id` | STRING | clé |
| `warehouse_id` | STRING | clé |
| `warehouse_name` | STRING | libellé UI |
| `warehouse_type` | STRING | `CLASSIC` \| `PRO` \| `SERVERLESS` |
| `warehouse_channel` | STRING | `CURRENT` \| `PREVIEW` |
| `warehouse_size` | STRING | `2X-Small`…`4X-Large` |
| `min_clusters` | INT | scaling bas |
| `max_clusters` | INT | scaling haut |
| `auto_stop_minutes` | INT | 0/NULL = pas d'auto-stop |
| `tags` | MAP<STRING,STRING> | owner / cost-center |
| `change_time` | TIMESTAMP | **watermark**, clé SCD |
| `delete_time` | TIMESTAMP | NULL = actif |

Clé merge : `(cloud_provider, account_id, workspace_id, warehouse_id, change_time)`. Watermark : `change_time`.

#### `curated_dbx_compute_warehouse_events` — source `system.compute.warehouse_events`

| Colonne | Type | Notes |
|---|---|---|
| `cloud_provider` | STRING | clé |
| `account_id` | STRING | clé |
| `workspace_id` | STRING | clé |
| `warehouse_id` | STRING | clé |
| `event_type` | STRING | `STARTING`,`RUNNING`,`STOPPING`,`STOPPED`,`SCALING_UP`,`SCALED_UP`,`SCALED_DOWN` |
| `cluster_count` | INT | nb clusters actifs au moment de l'événement |
| `event_time` | TIMESTAMP | **watermark**, clé |

Clé merge : `(cloud_provider, account_id, workspace_id, warehouse_id, event_time, event_type)`. Watermark : `event_time`. Partition : `event_date` (dérivée).

#### `curated_dbx_compute_node_types` — source `system.compute.node_types`

| Colonne | Type | Notes |
|---|---|---|
| `cloud_provider` | STRING | clé |
| `account_id` | STRING | clé |
| `node_type` | STRING | clé (ex. `Standard_DS3_v2`, `m5.xlarge`) |
| `core_count` | DOUBLE | vCPU |
| `memory_mb` | BIGINT | RAM |
| `gpu_count` | INT | 0 si CPU-only |

Full load léger (référentiel). Clé merge : `(cloud_provider, account_id, node_type)`.

---

## 2. Couche GOLD — Page 1 : Clusters

### 2.1 `gold_dbx_compute_cluster_cost_daily` — FinOps

Grain : `(cloud_provider, source_lz_id, workspace_id, cluster_id, period_start)`

| Colonne | Type | Description | Mode |
|---|---|---|---|
| `cluster_id` | STRING | identifiant | — |
| `cluster_name` | STRING | libellé UI | — |
| `owner` | STRING | `owned_by` / tag owner | — |
| `ba_name` | STRING | business area (tags / dim_landing_zone) | — |
| `cost_center` | STRING | tag cost-center (NULL si absent) | R |
| `sku_group` | STRING | `classic` \| `photon` \| `serverless` | R |
| `dbu_quantity` | DOUBLE | DBU du jour | R+P |
| `cost_usd` | DOUBLE | dbu × effective_list price | R+P |
| `cost_usd_prev_day` | DOUBLE | J-1 pour delta | R+P |
| `cost_delta_pct` | DOUBLE | variation vs J-1 | R+P |
| `cost_rank` | INT | rang coût dans la LZ (top N) | R+P |
| `is_top_cost` | BOOLEAN | dans le top N coûteux | R |
| `_generated_at` | TIMESTAMP | | — |

### 2.2 `gold_dbx_compute_cluster_efficiency_daily` — Utilisation / rightsizing

Grain : `(cloud_provider, source_lz_id, workspace_id, cluster_id, period_start)`

| Colonne | Type | Description | Mode |
|---|---|---|---|
| `cpu_util_avg_pct` | DOUBLE | moyenne user+system | R+P |
| `cpu_util_p95_pct` | DOUBLE | pic soutenu (base rightsizing) | R+P |
| `mem_util_avg_pct` | DOUBLE | moyenne mémoire | R+P |
| `mem_util_p95_pct` | DOUBLE | pression mémoire | R+P |
| `cpu_wait_avg_pct` | DOUBLE | I/O bound | R |
| `idle_pct` | DOUBLE | % temps RUNNING sans requête | R+P |
| `uptime_hours` | DOUBLE | heures allumé | R+P |
| `active_hours` | DOUBLE | heures avec activité | R+P |
| `worker_count_avg` | DOUBLE | workers moyens | R+P |
| `worker_count_max` | DOUBLE | workers max observés | R |
| `autoscale_oscillation` | INT | nb changements de taille (instabilité) | R+P |
| `driver_node_type` | STRING | node driver actuel | — |
| `worker_node_type` | STRING | node worker actuel | — |
| `is_zombie` | BOOLEAN | uptime élevé + util basse | R |
| `utilization_status` | STRING | `UNDER` \| `OPTIMAL` \| `OVER` | R |
| `recommended_node_type` | STRING | node cible proposé | R+P |
| `rightsizing_reco` | STRING | action lisible | R+P |
| `estimated_savings_usd` | DOUBLE | gain estimé si appliqué | R+P |
| `_generated_at` | TIMESTAMP | | — |

**Dérivation `utilization_status`** : `OVER` si `cpu_util_p95 < 40 AND mem_util_p95 < 50` ; `UNDER` si `cpu_util_p95 > 85 OR mem_util_p95 > 85` ; sinon `OPTIMAL`.

### 2.3 `gold_dbx_compute_cluster_reliability_daily` — Fiabilité

Grain : `(cloud_provider, source_lz_id, workspace_id, cluster_id, period_start)`

| Colonne | Type | Description | Mode |
|---|---|---|---|
| `start_count` | INT | démarrages du jour | R+P |
| `avg_startup_seconds` | DOUBLE | latence spin-up moyenne | R+P |
| `unexpected_termination_count` | INT | terminaisons anormales | R |
| `top_termination_reason` | STRING | cause dominante | R |
| `auto_termination_minutes` | INT | config auto-stop | R |
| `has_auto_termination` | BOOLEAN | auto-stop actif | R |
| `_generated_at` | TIMESTAMP | | — |

### 2.4 `gold_dbx_compute_cluster_governance` — Conformité (snapshot état courant)

Grain : `(cloud_provider, source_lz_id, workspace_id, cluster_id)` — dernier état connu.

| Colonne | Type | Description | Mode |
|---|---|---|---|
| `cluster_name` | STRING | libellé | — |
| `has_owner_tag` | BOOLEAN | tag owner présent | R |
| `has_cost_center_tag` | BOOLEAN | tag cost-center présent | R |
| `dbr_version` | STRING | version runtime | R |
| `dbr_is_lts_current` | BOOLEAN | LTS supportée à jour | R |
| `node_oversized` | BOOLEAN | node > util p95 | R+P |
| `is_single_node` | BOOLEAN | single-node | R |
| `recommended_action` | STRING | action gouvernance | R |
| `severity` | STRING | `LOW` \| `MEDIUM` \| `HIGH` | R |
| `_generated_at` | TIMESTAMP | | — |

---

## 3. Couche GOLD — Page 2 : SQL Warehouses

### 3.1 `gold_dbx_compute_warehouse_cost_daily` — FinOps

Grain : `(cloud_provider, source_lz_id, workspace_id, warehouse_id, period_start)`

| Colonne | Type | Description | Mode |
|---|---|---|---|
| `warehouse_name` | STRING | libellé UI | — |
| `warehouse_size` | STRING | taille | — |
| `dbu_quantity` | DOUBLE | DBU du jour | R+P |
| `cost_usd` | DOUBLE | coût du jour | R+P |
| `cost_usd_prev_day` | DOUBLE | J-1 | R+P |
| `cost_delta_pct` | DOUBLE | variation | R+P |
| `query_count` | BIGINT | requêtes du jour | R+P |
| `cost_per_query_usd` | DOUBLE | coût / requête | R+P |
| `top_consumer` | STRING | user le plus consommateur | R |
| `_generated_at` | TIMESTAMP | | — |

### 3.2 `gold_dbx_compute_warehouse_utilization_daily` — Efficience

Grain : `(cloud_provider, source_lz_id, workspace_id, warehouse_id, period_start)`

| Colonne | Type | Description | Mode |
|---|---|---|---|
| `running_hours` | DOUBLE | heures RUNNING | R+P |
| `active_query_hours` | DOUBLE | heures avec requêtes | R+P |
| `idle_pct` | DOUBLE | RUNNING sans query | R+P |
| `active_to_running_ratio` | DOUBLE | cible > 0.70 | R+P |
| `auto_stop_minutes` | INT | config | R |
| `has_auto_stop` | BOOLEAN | auto-stop actif | R |
| `scale_up_events` | INT | montées d'échelle | R+P |
| `scale_down_events` | INT | descentes | R+P |
| `avg_cluster_count` | DOUBLE | clusters moyens | R+P |
| `max_cluster_count` | INT | clusters max | R |
| `peak_concurrency` | INT | requêtes simultanées max | P |
| `utilization_status` | STRING | `UNDER` \| `OPTIMAL` \| `OVER` | R |
| `rightsizing_reco` | STRING | action lisible | R+P |
| `estimated_savings_usd` | DOUBLE | gain estimé | R+P |
| `_generated_at` | TIMESTAMP | | — |

### 3.3 `gold_dbx_compute_warehouse_query_performance_daily` — Performance requêtes

Grain : `(cloud_provider, source_lz_id, workspace_id, warehouse_id, period_start)`

| Colonne | Type | Description | Mode |
|---|---|---|---|
| `query_count` | BIGINT | volume | P |
| `failed_count` | BIGINT | FAILED + CANCELED | R |
| `failure_rate_pct` | DOUBLE | taux d'échec | R |
| `latency_p50_ms` | DOUBLE | médiane durée totale | R+P |
| `latency_p95_ms` | DOUBLE | p95 | R+P |
| `latency_p99_ms` | DOUBLE | p99 | R+P |
| `queue_time_avg_ms` | DOUBLE | attente compute moyenne | R+P |
| `queue_time_p95_ms` | DOUBLE | attente p95 (saturation) | R+P |
| `spill_query_count` | BIGINT | requêtes avec spill disk/mem | R |
| `cache_hit_pct` | DOUBLE | efficacité cache I/O | R+P |
| `bytes_scanned` | BIGINT | volume lu | R+P |
| `rows_scanned` | BIGINT | lignes lues | R+P |
| `top_slow_statement_id` | STRING | requête la plus lente | R |
| `_generated_at` | TIMESTAMP | | — |

---

## 4. GOLD transverse — Réactif & Prédictif

### 4.1 `gold_dbx_compute_recommendations` — socle RÉACTIF (fait actionnable unifié)

Centralise toutes les « reco d'optimisation » des pages, clusters + warehouses, avec persona et sévérité. Une ligne = une reco active pour un objet.

Grain : `(recommendation_id)` — `recommendation_id = sha2(object_type || object_id || category || generated_date)`.

| Colonne | Type | Description |
|---|---|---|
| `recommendation_id` | STRING | clé (hash) |
| `cloud_provider` | STRING | |
| `source_lz_id` | STRING | FK dim_landing_zone |
| `workspace_id` | STRING | |
| `object_type` | STRING | `CLUSTER` \| `WAREHOUSE` |
| `object_id` | STRING | cluster_id / warehouse_id |
| `object_name` | STRING | libellé UI |
| `cluster_type` | STRING | `ALL_PURPOSE`\|`JOB`\|`PIPELINE` (CLUSTER uniquement, NULL si WAREHOUSE) |
| `category` | STRING | `FINOPS` \| `RIGHTSIZING` \| `RELIABILITY` \| `GOVERNANCE` |
| `mode` | STRING | `REACTIVE` (état courant) |
| `title` | STRING | résumé court |
| `detail` | STRING | contexte chiffré |
| `recommended_action` | STRING | action concrète |
| `estimated_savings_usd` | DOUBLE | gain estimé (NULL si non chiffrable) |
| `severity` | STRING | `LOW` \| `MEDIUM` \| `HIGH` |
| `personas` | ARRAY<STRING> | `FIN`,`DE`,`AN`,`GOV` |
| `status` | STRING | `OPEN` \| `ACK` \| `RESOLVED` |
| `first_seen_date` | DATE | 1re détection |
| `last_seen_date` | DATE | dernière détection |
| `_generated_at` | TIMESTAMP | |

### 4.2 `gold_dbx_compute_forecast_daily` — socle PRÉDICTIF (séries projetées)

Projection des métriques `P` / `R+P` (coût, DBU, util p95, volume queries, queue time) via `ai_forecast` sur l'historique gold journalier. Alimente l'anticipation budget / saturation / rightsizing.

Grain : `(cloud_provider, source_lz_id, object_type, object_id, metric_name, horizon_date)`

| Colonne | Type | Description |
|---|---|---|
| `object_type` | STRING | `CLUSTER` \| `WAREHOUSE` \| `LZ` |
| `object_id` | STRING | identifiant (ou LZ agrégée) |
| `metric_name` | STRING | `cost_usd`,`dbu_quantity`,`cpu_util_p95_pct`,`query_count`,`queue_time_p95_ms` |
| `horizon_date` | DATE | jour projeté |
| `predicted_value` | DOUBLE | valeur estimée |
| `lower_bound` | DOUBLE | borne basse (IC) |
| `upper_bound` | DOUBLE | borne haute (IC) |
| `method` | STRING | `ai_forecast` |
| `_generated_at` | TIMESTAMP | |

> **Historisation** : les tables `*_daily` conservent l'historique jour (append/SCD1 sur clé + date) → le prédictif se calcule sans re-collecte. Les tables d'état (`gold_dbx_compute_cluster_governance`) gardent le dernier état connu.

> **Nommage** : convention `gold_<source>_<domain>_<metric>` (ex. `gold_dbx_compute_cluster_cost_daily`, `gold_dbx_workflow_tasks`). Le préfixe `dbx` distingue explicitement ce socle Databricks compute (clusters + warehouses) du domaine `compute` générique existant (`curated_compute_metrics` → `gold_compute_utilization`), sans lien avec ce nouveau socle.

---

## 5. Positionnement médaillon & rafraîchissement

| Couche | Objet | Type | Rafraîchissement |
|---|---|---|---|
| CURATED | `curated_dbx_*` | DLT streaming / merge idempotent | à chaque run ingestion (watermark) |
| GOLD `*_daily` | agrégats jour | materialized view / apply_changes SCD1 | quotidien (batch serverless) |
| GOLD `governance` | snapshot état | materialized view (dernier `change_time`) | quotidien |
| GOLD `recommendations` | fait réactif | materialized view (règles seuils) | quotidien |
| GOLD `forecast_daily` | prédictif | job SQL `ai_forecast` | quotidien / hebdo |

FK commune : toutes les tables gold référencent `dim_landing_zone (lz_id)` (cohérent avec les gold existantes `gold_compute_utilization`).
