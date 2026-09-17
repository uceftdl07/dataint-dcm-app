import type {
  ComputeClusterCostTrendResponse,
  ComputeClusterDetailResponse,
  ComputeClusterLifetimeTrendResponse,
  ComputeClustersCostResponse,
  ComputeClustersEfficiencyResponse,
  ComputeClustersGovernanceResponse,
  ComputeClustersOverviewResponse,
  ComputeClusterWindow,
} from '../../types/api';

/**
 * The window the API reports as actually covered. Deliberately a 7-day range
 * while the page defaults to `Daily`: the covered period must be read from the
 * response, never recomputed from the selected chip or from `today`.
 */
export const computeClusterWindowFixture: ComputeClusterWindow = {
  window_days: 7,
  from_date: '2026-08-07',
  to_date: '2026-08-13',
};

export const computeClustersOverviewFixture: ComputeClustersOverviewResponse = {
  kpis: {
    total_cost_usd: 34520,
    cost_delta_pct: 6.4,
    active_clusters: 58,
    zombie_count: 7,
    open_recommendations: 5,
  },
  items: [
    {
      cloud_provider: 'azure',
      workspace_id: 'ws-1',
      workspace_name: 'dbw-analytics-prod',
      cluster_id: '0612-114523-abcloop',
      cluster_name: 'etl_ingestion_prod',
      owner: 'data-eng',
      cluster_type: 'JOB',
      cost_usd: 8420,
      cost_usd_prev_window: 8618,
      cost_delta_pct: -2.3,
      cpu_util_p95_pct: 78,
      idle_pct: 4,
      uptime_hours: 120,
      uptime_hours_prev_window: 96,
      uptime_hours_delta_pct: 25,
      utilization_status: 'OPTIMAL',
      severity: 'LOW',
    },
    {
      // Ephemeral job cluster: its id never existed in the previous window, so
      // there is nothing to compare against.
      cloud_provider: 'azure',
      workspace_id: 'ws-1',
      workspace_name: 'dbw-analytics-prod',
      cluster_id: '0612-114523-nohist',
      cluster_name: 'job_run_once',
      owner: null,
      cluster_type: 'JOB',
      cost_usd: 12,
      cost_usd_prev_window: null,
      cost_delta_pct: null,
      cpu_util_p95_pct: 31,
      idle_pct: 12,
      uptime_hours: 2,
      uptime_hours_prev_window: null,
      uptime_hours_delta_pct: null,
      utilization_status: 'OPTIMAL',
      severity: null,
    },
  ],
  // A total far above the two rows returned: the overview pages server-side, so the
  // footer must report the whole scope, not the length of `items`.
  total: 137,
  page: 1,
  page_size: 25,
  window: computeClusterWindowFixture,
  period: { from: '2026-08-07', to: '2026-08-13' },
};

export const computeClustersCostFixture: ComputeClustersCostResponse = {
  items: [
    {
      cloud_provider: 'azure',
      workspace_id: 'ws-1',
      workspace_name: 'dbw-analytics-prod',
      cluster_id: '0612-114523-abcloop',
      cluster_name: 'etl_ingestion_prod',
      owner: 'data-eng',
      cost_center: 'CC-4021',
      sku_group: 'Photon',
      cluster_type: 'JOB',
      dbu_quantity: 34900,
      dbu_cost: 0.241,
      cost_usd: 8420,
      cost_usd_prev_window: 8618,
      cost_delta_pct: -2.3,
      cost_rank: 2,
      is_top_cost: false,
    },
  ],
  total: 1,
  page: 1,
  page_size: 25,
  window: computeClusterWindowFixture,
  period: { from: '2026-08-07', to: '2026-08-13' },
};

export const computeClustersEfficiencyFixture: ComputeClustersEfficiencyResponse = {
  items: [
    {
      cloud_provider: 'azure',
      workspace_id: 'ws-1',
      workspace_name: 'dbw-analytics-prod',
      cluster_id: '0612-114523-abcloop',
      cluster_name: 'etl_ingestion_prod',
      cluster_type: 'JOB',
      driver_node_type: 'Standard_DS4_v2',
      worker_node_type: 'Standard_DS3_v2',
      autoscale_enabled: true,
      autoscale_min_workers: 2,
      autoscale_max_workers: 8,
      configured_worker_count: null,
      cpu_util_avg_pct: 60,
      cpu_util_p95_pct: 78,
      mem_util_avg_pct: 52,
      mem_util_p95_pct: 65,
      cpu_wait_avg_pct: 5,
      idle_pct: 4,
      idle_pct_prev_window: 9,
      idle_pct_delta_pts: -5,
      uptime_hours: 120,
      uptime_hours_prev_window: 96,
      uptime_hours_delta_pct: 25,
      worker_count_avg: 6,
      worker_count_max: 10,
      autoscale_oscillation: 2,
      is_zombie: false,
      utilization_status: 'OPTIMAL',
      recommended_node_type: null,
      rightsizing_reco: null,
      estimated_savings_usd: 0,
    },
  ],
  total: 1,
  page: 1,
  page_size: 25,
  window: computeClusterWindowFixture,
  period: { from: '2026-08-07', to: '2026-08-13' },
};

export const computeClustersGovernanceFixture: ComputeClustersGovernanceResponse = {
  items: [
    {
      cloud_provider: 'azure',
      workspace_id: 'ws-1',
      cluster_id: '0612-114523-abcloop',
      cluster_name: 'etl_ingestion_prod',
      cluster_type: 'JOB',
      has_owner_tag: true,
      has_cost_center_tag: true,
      dbr_version: '14.3',
      dbr_is_lts_current: true,
      node_oversized: false,
      is_single_node: false,
      recommended_action: null,
      severity: 'LOW',
      generated_at: '2026-08-13T10:00:00Z',
    },
  ],
  total: 1,
  page: 1,
  page_size: 25,
  period: { from: '2026-07-14', to: '2026-08-13' },
};

export const computeClusterDetailFixture: ComputeClusterDetailResponse = {
  cloud_provider: 'azure',
  workspace_id: 'ws-1',
  cluster_id: '0612-114523-abcloop',
  cost: computeClustersCostFixture.items[0]!,
  efficiency: computeClustersEfficiencyFixture.items[0]!,
  governance: computeClustersGovernanceFixture.items[0]!,
  window: computeClusterWindowFixture,
  period: { from: '2026-08-07', to: '2026-08-13' },
};

export const computeClusterTrendFixture: ComputeClusterCostTrendResponse = {
  items: [
    { bucket: '2026-06-15', cost_usd: 100, dbu_quantity: 200 },
    { bucket: '2026-06-22', cost_usd: 140, dbu_quantity: 220 },
    { bucket: '2026-06-29', cost_usd: 120, dbu_quantity: 210 },
  ],
  period: { from: '2026-06-15', to: '2026-08-13' },
  granularity: 'week',
};

export const computeClusterLifetimeTrendFixture: ComputeClusterLifetimeTrendResponse = {
  items: [
    { bucket: '2026-06-15', uptime_hours: 68.5, idle_pct: 12.4 },
    { bucket: '2026-06-22', uptime_hours: 71.2, idle_pct: 9.1 },
    // A bucket with uptime but no measured idle: `null`, not `0`.
    { bucket: '2026-06-29', uptime_hours: 40, idle_pct: null },
  ],
  period: { from: '2026-06-15', to: '2026-08-13' },
  granularity: 'week',
};
