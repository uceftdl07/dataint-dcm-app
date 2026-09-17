# Unused Gold KPIs

Source authority: `docs/spike/compute-metrics-definition/compute_datamodel.md`, confirmed by the Product Owner.

Each pair below is non-selected from the atomic inventory and appears once only.

| KPI | Gold source | Reason |
|---|---|---|
| `cluster_id` | `gold_dbx_compute_cluster_cost_daily` | Identifier detail |
| `owner` | `gold_dbx_compute_cluster_cost_daily` | Detail/filter candidate |
| `cost_center` | `gold_dbx_compute_cluster_cost_daily` | Tag detail |
| `cost_usd_prev_day` | `gold_dbx_compute_cluster_cost_daily` | Used by delta derivation |
| `cost_delta_pct` | `gold_dbx_compute_cluster_cost_daily` | Trend detail |
| `cost_rank` | `gold_dbx_compute_cluster_cost_daily` | Ranking detail |
| `is_top_cost` | `gold_dbx_compute_cluster_cost_daily` | Ranking flag |
| `cpu_util_avg_pct` | `gold_dbx_compute_cluster_efficiency_daily` | Diagnostic detail; p95 retained |
| `mem_util_avg_pct` | `gold_dbx_compute_cluster_efficiency_daily` | Diagnostic detail |
| `mem_util_p95_pct` | `gold_dbx_compute_cluster_efficiency_daily` | Detail metric; CPU p95 retained |
| `cpu_wait_avg_pct` | `gold_dbx_compute_cluster_efficiency_daily` | Technical diagnostic |
| `worker_count_avg` | `gold_dbx_compute_cluster_efficiency_daily` | Sizing detail |
| `worker_count_max` | `gold_dbx_compute_cluster_efficiency_daily` | Sizing detail |
| `autoscale_oscillation` | `gold_dbx_compute_cluster_efficiency_daily` | Trend diagnostic |
| `driver_node_type` | `gold_dbx_compute_cluster_efficiency_daily` | Drawer detail |
| `worker_node_type` | `gold_dbx_compute_cluster_efficiency_daily` | Drawer detail |
| `recommended_node_type` | `gold_dbx_compute_cluster_efficiency_daily` | Recommendation detail |
| `rightsizing_reco` | `gold_dbx_compute_cluster_efficiency_daily` | Recommendation text |
| `estimated_savings_usd` | `gold_dbx_compute_cluster_efficiency_daily` | Drawer opportunity not selected for this page |
| `uptime_hours` | `gold_dbx_compute_cluster_efficiency_daily` | Detail context |
| `active_hours` | `gold_dbx_compute_cluster_efficiency_daily` | Detail context |
| `cost_usd_prev_day` | `gold_dbx_compute_warehouse_cost_daily` | Used by delta derivation |
| `cost_delta_pct` | `gold_dbx_compute_warehouse_cost_daily` | Trend detail |
| `cost_per_query_usd` | `gold_dbx_compute_warehouse_cost_daily` | Unit economics detail |
| `top_consumer` | `gold_dbx_compute_warehouse_cost_daily` | User/team detail |
| `running_hours` | `gold_dbx_compute_warehouse_utilization_daily` | Runtime detail |
| `active_query_hours` | `gold_dbx_compute_warehouse_utilization_daily` | Activity detail |
| `auto_stop_minutes` | `gold_dbx_compute_warehouse_utilization_daily` | Configuration detail |
| `scale_up_events` | `gold_dbx_compute_warehouse_utilization_daily` | Scaling diagnostic |
| `scale_down_events` | `gold_dbx_compute_warehouse_utilization_daily` | Scaling diagnostic |
| `avg_cluster_count` | `gold_dbx_compute_warehouse_utilization_daily` | Sizing detail |
| `max_cluster_count` | `gold_dbx_compute_warehouse_utilization_daily` | Sizing detail |
| `rightsizing_reco` | `gold_dbx_compute_warehouse_utilization_daily` | Recommendation text |
| `mode` | `gold_dbx_compute_recommendations` | Technical provenance |
| `recommendation_id` | `gold_dbx_compute_recommendations` | Identifier detail |
| `object_id` | `gold_dbx_compute_recommendations` | Identifier detail |
| `recommended_action` | `gold_dbx_compute_recommendations` | Drawer action text |
| `title` | `gold_dbx_compute_recommendations` | Drawer detail not selected |
| `detail` | `gold_dbx_compute_recommendations` | Drawer detail not selected |
| `first_seen_date` | `gold_dbx_compute_recommendations` | Lifecycle metadata |
| `last_seen_date` | `gold_dbx_compute_recommendations` | Lifecycle metadata |

Status: non-selected to date, not discarded from the data contract.
