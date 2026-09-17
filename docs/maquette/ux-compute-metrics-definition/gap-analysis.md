# Compute Monitoring Gap Analysis

## Source authority

- Spike input: `docs/spike/compute-metrics-definition/`
- Gold authority: `docs/spike/compute-metrics-definition/compute_datamodel.md`
- Confirmation: Product Owner confirmed this file as authoritative for this execution.
- Design system: `spec-kit-dcm-workflow/agents/dcm-ux-agent/references/Design_system_pour_les_maquettes.html`

## Coverage summary

| Table | Coverage | Treatment |
|---|---|---|
| `gold_dbx_compute_cluster_cost_daily` | calculable | Clusters / Cost |
| `gold_dbx_compute_cluster_efficiency_daily` | calculable | Clusters / Efficiency |
| `gold_dbx_compute_cluster_reliability_daily` | blocked | Excluded |
| `gold_dbx_compute_cluster_governance` | partially covered | Excluded |
| `gold_dbx_compute_warehouse_cost_daily` | calculable | SQL Warehouses / Cost |
| `gold_dbx_compute_warehouse_utilization_daily` | calculable | SQL Warehouses / Utilization |
| `gold_dbx_compute_warehouse_query_performance_daily` | partially covered | Excluded |
| `gold_dbx_compute_recommendations` | calculable | Recommendations |
| `gold_dbx_compute_forecast_daily` | blocked | Excluded |

## Atomic calculable KPI inventory

One KPI per row. Every row is reconciled against generated HTML or `unused-gold-kpis.md`.

| KPI | Table gold | Status |
|---|---|---|
| `cluster_id` | `gold_dbx_compute_cluster_cost_daily` | non-selected |
| `cluster_name` | `gold_dbx_compute_cluster_cost_daily` | retained in table |
| `owner` | `gold_dbx_compute_cluster_cost_daily` | non-selected |
| `ba_name` | `gold_dbx_compute_cluster_cost_daily` | retained in filter |
| `cost_center` | `gold_dbx_compute_cluster_cost_daily` | non-selected |
| `sku_group` | `gold_dbx_compute_cluster_cost_daily` | retained in filter |
| `dbu_quantity` | `gold_dbx_compute_cluster_cost_daily` | retained |
| `cost_usd` | `gold_dbx_compute_cluster_cost_daily` | retained |
| `cost_usd_prev_day` | `gold_dbx_compute_cluster_cost_daily` | non-selected |
| `cost_delta_pct` | `gold_dbx_compute_cluster_cost_daily` | non-selected |
| `cost_rank` | `gold_dbx_compute_cluster_cost_daily` | non-selected |
| `is_top_cost` | `gold_dbx_compute_cluster_cost_daily` | non-selected |
| `cpu_util_avg_pct` | `gold_dbx_compute_cluster_efficiency_daily` | non-selected |
| `cpu_util_p95_pct` | `gold_dbx_compute_cluster_efficiency_daily` | retained |
| `mem_util_avg_pct` | `gold_dbx_compute_cluster_efficiency_daily` | non-selected |
| `mem_util_p95_pct` | `gold_dbx_compute_cluster_efficiency_daily` | non-selected |
| `cpu_wait_avg_pct` | `gold_dbx_compute_cluster_efficiency_daily` | non-selected |
| `idle_pct` | `gold_dbx_compute_cluster_efficiency_daily` | retained |
| `uptime_hours` | `gold_dbx_compute_cluster_efficiency_daily` | non-selected |
| `active_hours` | `gold_dbx_compute_cluster_efficiency_daily` | non-selected |
| `worker_count_avg` | `gold_dbx_compute_cluster_efficiency_daily` | non-selected |
| `worker_count_max` | `gold_dbx_compute_cluster_efficiency_daily` | non-selected |
| `autoscale_oscillation` | `gold_dbx_compute_cluster_efficiency_daily` | non-selected |
| `driver_node_type` | `gold_dbx_compute_cluster_efficiency_daily` | non-selected |
| `worker_node_type` | `gold_dbx_compute_cluster_efficiency_daily` | non-selected |
| `is_zombie` | `gold_dbx_compute_cluster_efficiency_daily` | retained in filter |
| `utilization_status` | `gold_dbx_compute_cluster_efficiency_daily` | retained in table |
| `recommended_node_type` | `gold_dbx_compute_cluster_efficiency_daily` | non-selected |
| `rightsizing_reco` | `gold_dbx_compute_cluster_efficiency_daily` | non-selected |
| `estimated_savings_usd` | `gold_dbx_compute_cluster_efficiency_daily` | non-selected |
| `warehouse_name` | `gold_dbx_compute_warehouse_cost_daily` | retained in table |
| `warehouse_size` | `gold_dbx_compute_warehouse_cost_daily` | retained in filter |
| `dbu_quantity` | `gold_dbx_compute_warehouse_cost_daily` | retained in table |
| `cost_usd` | `gold_dbx_compute_warehouse_cost_daily` | retained |
| `cost_usd_prev_day` | `gold_dbx_compute_warehouse_cost_daily` | non-selected |
| `cost_delta_pct` | `gold_dbx_compute_warehouse_cost_daily` | non-selected |
| `query_count` | `gold_dbx_compute_warehouse_cost_daily` | retained |
| `cost_per_query_usd` | `gold_dbx_compute_warehouse_cost_daily` | non-selected |
| `top_consumer` | `gold_dbx_compute_warehouse_cost_daily` | non-selected |
| `running_hours` | `gold_dbx_compute_warehouse_utilization_daily` | non-selected |
| `active_query_hours` | `gold_dbx_compute_warehouse_utilization_daily` | non-selected |
| `idle_pct` | `gold_dbx_compute_warehouse_utilization_daily` | retained |
| `active_to_running_ratio` | `gold_dbx_compute_warehouse_utilization_daily` | retained in table |
| `auto_stop_minutes` | `gold_dbx_compute_warehouse_utilization_daily` | non-selected |
| `has_auto_stop` | `gold_dbx_compute_warehouse_utilization_daily` | retained in filter |
| `scale_up_events` | `gold_dbx_compute_warehouse_utilization_daily` | non-selected |
| `scale_down_events` | `gold_dbx_compute_warehouse_utilization_daily` | non-selected |
| `avg_cluster_count` | `gold_dbx_compute_warehouse_utilization_daily` | non-selected |
| `max_cluster_count` | `gold_dbx_compute_warehouse_utilization_daily` | non-selected |
| `utilization_status` | `gold_dbx_compute_warehouse_utilization_daily` | retained in filter |
| `rightsizing_reco` | `gold_dbx_compute_warehouse_utilization_daily` | non-selected |
| `estimated_savings_usd` | `gold_dbx_compute_warehouse_utilization_daily` | retained in drawer |
| `recommendation_id` | `gold_dbx_compute_recommendations` | non-selected |
| `object_type` | `gold_dbx_compute_recommendations` | retained in filter |
| `object_id` | `gold_dbx_compute_recommendations` | non-selected |
| `object_name` | `gold_dbx_compute_recommendations` | retained in table |
| `category` | `gold_dbx_compute_recommendations` | retained in filter |
| `mode` | `gold_dbx_compute_recommendations` | non-selected |
| `title` | `gold_dbx_compute_recommendations` | non-selected |
| `detail` | `gold_dbx_compute_recommendations` | non-selected |
| `recommended_action` | `gold_dbx_compute_recommendations` | non-selected |
| `estimated_savings_usd` | `gold_dbx_compute_recommendations` | retained |
| `severity` | `gold_dbx_compute_recommendations` | retained in filter |
| `personas` | `gold_dbx_compute_recommendations` | retained in table |
| `status` | `gold_dbx_compute_recommendations` | retained in filter |
| `first_seen_date` | `gold_dbx_compute_recommendations` | non-selected |
| `last_seen_date` | `gold_dbx_compute_recommendations` | non-selected |

## Selected primary KPIs

| KPI | Persona | Objective | Value | Formula |
|---|---|---|---|---|
| `cost_usd` | FinOps | Prioritize spend | Control budget | `SUM(dbu_quantity * effective_list_price)` |
| `dbu_quantity` | FinOps, Data Engineer | Track consumption | Explain usage trend | `SUM(usage_quantity)` |
| `cpu_util_p95_pct` | Data Engineer | Detect sustained pressure | Size nodes correctly | `percentile_approx(cpu_util_pct, 0.95)` |
| `idle_pct` | FinOps | Find unused runtime | Reduce recoverable waste | `idle_minutes / running_minutes * 100` |
| `query_count` | FinOps, Analyst | Compare cost with workload | Detect inefficient spend | `COUNT(statement_id)` |
| `severity` | Governance, FinOps | Prioritize urgent action | Reduce risk | Gold severity classification |
| `status` | FinOps, Data Engineer | Track remediation backlog | Close operational actions | `OPEN / ACK / RESOLVED` |

## Exclusions and blockers

Blocked and partially covered tables are excluded from navigation, cards, rows and mock values: reliability, governance, query performance and forecast.

## Generation checks

- Atomic KPI inventory reconciled 100% with HTML or `unused-gold-kpis.md`.
- `clusters` and `warehouses`: 2 calculable Gold tables, therefore 2 subviews each.
- `recommendations`: 1 calculable Gold table, therefore no domain toggle.
- All pages share the same topbar date range and sidebar footer.
