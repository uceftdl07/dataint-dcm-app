/** Field descriptions aligned with Unity Catalog / gold compute datamodel. */
export const computeClusterFieldDescriptions = {
  cluster: 'Databricks cluster display name and technical cluster_id.',
  clusterType:
    'Databricks cluster type from gold tables (`cluster_type`: JOB, PIPELINE, ALL_PURPOSE, etc.).',
  workspace: 'Databricks workspace hosting the cluster (display name preferred).',
  clusterLifetime:
    'Cluster uptime over the selected period, shown as days/hours/minutes/seconds (`uptime_hours`, in hours, from gold cluster efficiency daily).',
  clusterUser:
    'Cluster owner from explicit owner tag, falling back to Databricks owned_by (`owner` from gold cluster cost daily).',
  cost: 'Total cluster cost in USD for the selected period.',
  costPrev:
    'Cost over the window of the same length immediately before (`cost_usd_prev_window`). Empty when the cluster did not exist then — ephemeral job clusters have no predecessor.',
  clusterLifetimePrev:
    'Uptime over the window of the same length immediately before (`uptime_hours_prev_window`).',
  cpuAvg: 'Average CPU utilization over the window (`cpu_util_avg_pct`).',
  cpuP95:
    '95th percentile CPU utilization — sustained peak used for rightsizing (`cpu_util_p95_pct`).',
  idlePct: 'Percentage of RUNNING time without active queries (`idle_pct`).',
  idlePctPrev:
    'Idle share over the previous window of the same length (`idle_pct_prev_window`), compared in percentage points.',
  utilizationStatus:
    'Rightsizing status: OVER (under-used), UNDER (saturated), OPTIMAL, or ZOMBIE (`utilization_status`).',
  governance: 'Highest governance severity from cluster governance snapshot.',
  skuGroup: 'Billing SKU group (Classic, Photon, Serverless).',
  dbu: 'Databricks Units consumed over the selected period.',
  dbuCost: 'Average cost of one DBU over the window (`cost_usd / dbu_quantity`).',
  costDelta: 'Cost change percentage vs the previous window of the same length.',
  costRank: 'Cost rank within the landing zone scope.',
  driverNode: 'Instance type of the driver node (`driver_node_type`).',
  workerNode: 'Instance type of the worker nodes (`worker_node_type`).',
  autoscaling: 'Whether autoscaling is enabled on the cluster (`autoscale_enabled`).',
  nodes:
    'Configured worker sizing: autoscaling bounds (`autoscale_min_workers` – `autoscale_max_workers`) or the fixed worker count — not the observed maximum.',
  memAvg: 'Average memory utilization over the window (`mem_util_avg_pct`).',
  memP95: '95th percentile memory utilization (`mem_util_p95_pct`).',
  status: 'Utilization status derived from CPU and memory p95 thresholds.',
  recommendedNode: 'Recommended node type when rightsizing applies.',
  estimatedSavings: 'Estimated monthly savings if rightsizing recommendation is applied.',
  ownerTag: 'Whether an explicit owner tag is present on the cluster.',
  costCenterTag: 'Whether a cost-center tag is present on the cluster.',
  dbr: 'Databricks Runtime version installed on the cluster.',
  recommendedAction: 'Governance recommended action from gold cluster governance rules.',
  severity: 'Governance issue severity (HIGH, MEDIUM, LOW).',
} as const;

export const computeClusterKpiDescriptions = {
  totalCost: 'Sum of cluster costs over the selected period with delta vs previous period.',
  activeClusters: 'Distinct clusters with cost activity in the period.',
  zombies: 'Clusters flagged as zombie (long uptime with very low utilization).',
  openRecommendations: 'Open compute recommendations targeting clusters.',
  dbuPage: 'Sum of DBU over the rows visible on the current page.',
  topCostly: 'Highest-cost cluster on the current result set.',
  avgCpuP95: 'Average CPU p95 over visible rows.',
  avgMemP95: 'Average memory p95 over visible rows.',
  zombiesPage: 'Rows with is_zombie=true on the current page.',
  estimatedSavingsPage: 'Sum of estimated savings over visible rows.',
  missingTags: 'Rows missing owner or cost-center tag.',
  dbrObsolete: 'Rows not on current DBR LTS.',
  highSeverity: 'Rows with HIGH governance severity.',
} as const;

export const computeWarehouseFieldDescriptions = {
  warehouse: 'SQL warehouse display name and technical warehouse_id (`warehouse_name`).',
  workspace: 'Databricks workspace hosting the warehouse (display name preferred).',
  warehouseSize: 'Warehouse size tier (Small, Medium, Large, X-Large) from `warehouse_size`.',
  warehouseType:
    'Compute form of the warehouse (`warehouse_type`) — `SERVERLESS`, `PRO` or `CLASSIC` carry the whole estate, but the vocabulary is Databricks’ and stays open, so an unlisted SKU is shown as received rather than forced into one of the three. Read from the utilization snapshot, where the form actually **billed** takes precedence over the one declared. Empty when the two disagree, or when the warehouse is billed over the window but absent from that snapshot: unknown, rather than assumed classic.',
  cost: 'Total warehouse cost in USD over the selected rolling window (`cost_usd`).',
  dbu: 'Databricks Units consumed over the selected rolling window (`dbu_quantity`).',
  costDelta:
    'Cost change percentage vs the window of the same length immediately before (`cost_delta_pct`), with that window’s cost underneath. Empty when the warehouse had no activity then — nothing to compare, not a 0 % variation.',
  queries: 'Number of queries executed on the warehouse (`query_count`).',
  costPerQuery: 'Average cost per query (`cost_per_query_usd`).',
  topConsumer:
    'Principal with the highest share of query duration on the warehouse (`top_consumer`).',
  failureRate:
    'Share of failed queries (`failure_rate_pct` from `gold_dbx_compute_warehouse_query_performance_rolling`).',
  failedCount: 'Count of failed queries (`failed_count`).',
  latencyP50: '50th percentile query latency in ms (`latency_p50_ms`).',
  latencyP95: '95th percentile query latency in ms (`latency_p95_ms`).',
  latencyP99: '99th percentile query latency in ms (`latency_p99_ms`).',
  queueP95: '95th percentile queue wait time in ms (`queue_time_p95_ms`).',
  spillCount: 'Queries that spilled to disk (`spill_query_count`).',
  cacheHit: 'Result cache hit rate percentage (`cache_hit_pct`).',
  statementId: 'Databricks statement identifier for the slow query.',
  executedBy: 'User or service principal that ran the query (`executed_by`).',
  startTime: 'Query start timestamp.',
  duration: 'Total query duration in milliseconds.',
  status: 'Final query status (e.g. FINISHED, FAILED).',
  reason: 'Slow query classification: FAILURE, SLOW, or SPILL.',
  errorMessage: 'Error message when the query failed.',
} as const;

export const computeWarehouseKpiDescriptions = {
  totalCost:
    'Sum of warehouse costs over the selected rolling window, with delta vs the window of the same length immediately before (`gold_dbx_compute_warehouse_cost_rolling`).',
  activeWarehouses:
    'Warehouses actually billed over the window (`cost_usd > 0`) — not those merely listed.',
  queryCount: 'Total queries executed across all warehouses (`query_count`).',
  failedQueries: 'Failed queries summed over the window across warehouses (`failed_count`).',
  openRecommendations:
    'Open compute recommendations targeting active warehouses (`gold_dbx_compute_recommendations`, object_type=WAREHOUSE).',
  dbuPage: 'Sum of DBU over the rows visible on the current page.',
  topCostly: 'Highest-cost warehouse on the current result set.',
  avgFailureRate: 'Average failure rate over visible rows.',
  avgLatencyP95: 'Average p95 latency over visible rows.',
  spillQueriesPage: 'Sum of spill query counts over visible rows.',
  failedQueriesPage: 'Sum of failed query counts over visible rows.',
} as const;

export const computeRecommendationsFieldDescriptions = {
  object: 'Databricks cluster or SQL warehouse targeted by the recommendation.',
  category: 'Recommendation category: FinOps, Rightsizing, Governance, or Reliability.',
  title: 'Short recommendation title from gold rules.',
  severity: 'Issue severity (HIGH, MEDIUM, LOW).',
  estimatedSavings: 'Estimated monthly savings when the recommendation is actionable.',
  actualCost:
    'Actual cluster/warehouse spend (USD) over the selected period from gold cost daily tables.',
  status: 'Recommendation lifecycle status (OPEN, RESOLVED, DISMISSED).',
  since: 'Days since the recommendation was first observed (`first_seen_date`).',
} as const;

export const computeRecommendationsKpiDescriptions = {
  openCount: 'Open recommendations across clusters and warehouses in the current scope.',
  openSavings: 'Sum of estimated savings for open recommendations with a quantifiable impact.',
  periodActualCost:
    'Actual compute spend (clusters + warehouses) over the selected period — compare with potential savings.',
  resolved30d: 'Recommendations resolved in the last 30 days.',
  highSeverityOpen: 'Open recommendations with HIGH severity — prioritize these first.',
} as const;

export const computeServerlessKpiDescriptions = {
  serverlessCost:
    'Serverless spend over the selected rolling window, all surfaces together (`gold_dbx_compute_serverless_cost_rolling`).',
  costDelta:
    'Change vs the window of the same length immediately before (`cost_usd_prev_window`). Empty when there is no comparable window — which is not the same as a flat one.',
  costWithoutIdentity:
    'Spend whose principal could not be resolved from the governance snapshot (`cost_usd_without_identity`): nobody to charge it back to.',
  costWithoutObjectKey:
    'Spend billed at workspace grain, with no listable object (`cost_usd_without_object_key`). A property of how Databricks bills Genie, networking and automatic platform activity — not a defect to fix.',
  budgetPolicyCoverage:
    'Share of serverless dollars carrying a budget policy, over the **whole** perimeter (`budget_policy_coverage_pct` of the governance snapshot) — not the figure of any single surface.',
  serverlessShare:
    'Serverless share of compute spend, in **dollars** (`serverless_share.pct`). Never in DBUs: a serverless DBU and a classic DBU are different units at different prices, so their ratio is a share of nothing.',
} as const;

export const computeServerlessFieldDescriptions = {
  surface: 'Serverless surface as classified in gold (`serverless_surface`).',
  object:
    'Object billed under the surface. Empty on the surfaces Databricks bills to the workspace (Genie, networking, automatic platform) — those rows carry real cost and no object.',
  workspace: 'Databricks workspace that was billed (display name preferred).',
  cost: 'Cost in USD over the selected rolling window.',
  costDelta: 'Cost change vs the window of the same length immediately before.',
  dbu: 'Databricks Units consumed over the window (`dbu_quantity`).',
  runs: 'Executions counted over the window (`run_count`). Empty — never zero — on the eleven surfaces that do not count runs at all.',
  costPerRun:
    'Cost of one execution (`cost_per_run_p50_usd`, and p95/p99 for the tail). Only meaningful where runs are counted.',
  performanceTarget:
    '`performance_target` declared on the object. Unset is a fourth value, not missing data — and it carries most of the dollars.',
  budgetPolicy:
    'Budget policy attached to the spend (`budget_policy_id`). There is no policy **name**: `system.billing` exposes no budget-policy table.',
  identity:
    'Principal the spend is attributed to (`identity_principal`), with the field it was read from (`identity_source`).',
  identitySource:
    'Which field carried the identity: `OWNED_BY` for warehouses, `CREATED_BY` for apps, `RUN_AS` for jobs and notebooks. "Owner" and "runner" are not the same rechargeability semantics.',
  ownerTagCoverage: 'Share of the row’s dollars carrying an explicit owner tag.',
  costCenterTagCoverage: 'Share of the row’s dollars carrying a cost-center tag.',
  objectKeyCoverage:
    'Share of the surface’s dollars that resolve to an object (`object_key_coverage_pct`).',
  policyCount: 'Distinct budget policies seen on the row (`budget_policy_count`).',
  dltFailureRate:
    'Failed share of **requested** executions over the window, deduplicated by `request_id` (`failure_rate_pct`). A measure of this period, never a property of a compute form — the direction reverses between the window and full history.',
  dltDuration:
    'Duration percentiles of the requested executions (`duration_p50_sec`, `duration_p95_sec`).',
  dltConcentration:
    'Share of the window’s failures carried by the few noisiest pipelines (`failure_concentration_pct`).',
} as const;
