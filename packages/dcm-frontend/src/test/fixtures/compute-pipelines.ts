import type {
  ComputeJobWindow,
  ComputePipelineCostTrendResponse,
  ComputePipelineDetailResponse,
  ComputePipelinesCostResponse,
  ComputePipelinesEfficiencyResponse,
  ComputePipelinesOverviewResponse,
  ComputePipelineUptimeTrendResponse,
} from '../../types/api';

/** Covered window reported by the API — read from the response, never recomputed. */
export const computePipelineWindowFixture: ComputeJobWindow = {
  window_days: 7,
  from_date: '2026-08-07',
  to_date: '2026-08-13',
};

export const computePipelinesOverviewFixture: ComputePipelinesOverviewResponse = {
  kpis: {
    total_cost_usd: 5340,
    cost_delta_pct: -2.1,
    active_pipelines: 18,
  },
  items: [
    {
      cloud_provider: 'azure',
      workspace_id: 'ws-1',
      dlt_pipeline_id: 'dlt-7781',
      pipeline_name: 'bronze-to-silver',
      dbu_quantity: 260,
      cost_usd: 980,
      cost_usd_prev_window: 1120,
      cost_delta_pct: -12.5,
      cost_rank: 1,
      is_top_cost: true,
      window_start: '2026-08-07',
      as_of_date: '2026-08-13',
      // Measured pipeline: the efficiency snapshot joined a row. The four values are
      // copies of `computePipelinesEfficiencyFixture` below — the Overview reads that
      // very column, so a different figure here would state something the backend
      // cannot produce.
      uptime_hours: 63.25,
      uptime_hours_prev_window: 70,
      uptime_hours_delta_pct: -9.6,
      utilization_status: 'OPTIMAL',
    },
    {
      // No predecessor window: Prev cost reads "—". Empty name → id is the fallback.
      cloud_provider: 'aws',
      workspace_id: 'ws-2',
      dlt_pipeline_id: 'dlt-9902',
      pipeline_name: null,
      dbu_quantity: 40,
      cost_usd: 150,
      cost_usd_prev_window: null,
      cost_delta_pct: null,
      cost_rank: 2,
      is_top_cost: false,
      window_start: '2026-08-07',
      as_of_date: '2026-08-13',
      // Serverless: billed, never measured, so "—" everywhere — a `0` would claim
      // the pipeline never ran.
      uptime_hours: null,
      uptime_hours_prev_window: null,
      uptime_hours_delta_pct: null,
      utilization_status: null,
    },
  ],
  total: 18,
  page: 1,
  page_size: 25,
  window: computePipelineWindowFixture,
  period: { from: '2026-08-07', to: '2026-08-13' },
};

export const computePipelinesCostFixture: ComputePipelinesCostResponse = {
  items: computePipelinesOverviewFixture.items,
  total: 18,
  page: 1,
  page_size: 25,
  window: computePipelineWindowFixture,
  period: { from: '2026-08-07', to: '2026-08-13' },
};

/**
 * Utilization at the pipeline grain. `dlt-9902` is serverless: billed, never
 * measured by `node_timeline`, so every metric is `null` and the row must read "—"
 * rather than `0 %` (024 SC-005).
 */
export const computePipelinesEfficiencyFixture: ComputePipelinesEfficiencyResponse = {
  items: [
    {
      cloud_provider: 'azure',
      workspace_id: 'ws-1',
      dlt_pipeline_id: 'dlt-7781',
      pipeline_name: 'bronze-to-silver',
      cluster_count: 5,
      cpu_util_avg_pct: 55,
      cpu_util_p95_pct: 72,
      mem_util_avg_pct: 58,
      mem_util_p95_pct: 81,
      cpu_wait_avg_pct: 6,
      idle_pct: 21,
      idle_pct_prev_window: 17,
      idle_pct_delta_pts: 4,
      uptime_hours: 63.25,
      uptime_hours_prev_window: 70,
      uptime_hours_delta_pct: -9.6,
      active_hours: 50,
      worker_count_avg: 3,
      worker_count_max: 6,
      autoscale_oscillation: 1,
      driver_node_type: 'Standard_DS4_v2',
      worker_node_type: 'Standard_DS3_v2',
      autoscale_enabled: false,
      autoscale_min_workers: null,
      autoscale_max_workers: null,
      configured_worker_count: 4,
      utilization_status: 'OPTIMAL',
      recommended_node_type: null,
      rightsizing_reco: null,
      estimated_savings_usd: 0,
      window_days: 7,
      window_start: '2026-08-07',
      as_of_date: '2026-08-13',
    },
    {
      cloud_provider: 'aws',
      workspace_id: 'ws-2',
      dlt_pipeline_id: 'dlt-9902',
      pipeline_name: null,
      cluster_count: null,
      cpu_util_avg_pct: null,
      cpu_util_p95_pct: null,
      mem_util_avg_pct: null,
      mem_util_p95_pct: null,
      cpu_wait_avg_pct: null,
      idle_pct: null,
      idle_pct_prev_window: null,
      idle_pct_delta_pts: null,
      uptime_hours: null,
      uptime_hours_prev_window: null,
      uptime_hours_delta_pct: null,
      active_hours: null,
      worker_count_avg: null,
      worker_count_max: null,
      autoscale_oscillation: null,
      driver_node_type: null,
      worker_node_type: null,
      autoscale_enabled: null,
      autoscale_min_workers: null,
      autoscale_max_workers: null,
      configured_worker_count: null,
      utilization_status: null,
      recommended_node_type: null,
      rightsizing_reco: null,
      estimated_savings_usd: null,
      window_days: 7,
      window_start: '2026-08-07',
      as_of_date: '2026-08-13',
    },
  ],
  // Smaller than the cost population: serverless pipelines are billed unmeasured.
  total: 11,
  page: 1,
  page_size: 25,
  window: computePipelineWindowFixture,
  period: { from: '2026-08-07', to: '2026-08-13' },
};

/** Drawer payload of a measured pipeline — no `governance` key at this grain (024 C2). */
export const computePipelineDetailFixture: ComputePipelineDetailResponse = {
  cloud_provider: 'azure',
  workspace_id: 'ws-1',
  dlt_pipeline_id: 'dlt-7781',
  cost: computePipelinesCostFixture.items[0]!,
  efficiency: computePipelinesEfficiencyFixture.items[0]!,
  window: computePipelineWindowFixture,
  period: { from: '2026-08-07', to: '2026-08-13' },
};

/**
 * A serverless pipeline: billed, `efficiency` null. Modelled on the real dev case
 * billed $941 over 30 days — such a row is shown, never hidden (024 SC-005).
 */
export const computePipelineDetailWithoutEfficiencyFixture: ComputePipelineDetailResponse = {
  cloud_provider: 'aws',
  workspace_id: 'ws-2',
  dlt_pipeline_id: 'dlt-9902',
  cost: computePipelinesCostFixture.items[1]!,
  efficiency: null,
  window: computePipelineWindowFixture,
  period: { from: '2026-08-07', to: '2026-08-13' },
};

export const computePipelineCostTrendFixture: ComputePipelineCostTrendResponse = {
  items: [
    { bucket: '2026-06-15', cost_usd: 120, dbu_quantity: 32 },
    { bucket: '2026-06-22', cost_usd: 145, dbu_quantity: 39 },
    { bucket: '2026-06-29', cost_usd: 130, dbu_quantity: 35 },
  ],
  period: { from: '2026-06-15', to: '2026-08-13' },
  granularity: 'week',
};

export const computePipelineUptimeTrendFixture: ComputePipelineUptimeTrendResponse = {
  items: [
    { bucket: '2026-06-15', uptime_hours: 18.5, idle_pct: 22.1 },
    { bucket: '2026-06-22', uptime_hours: 16, idle_pct: 19.7 },
    // A bucket with no update at all: `null`, never `0`.
    { bucket: '2026-06-29', uptime_hours: null, idle_pct: null },
  ],
  period: { from: '2026-06-15', to: '2026-08-13' },
  granularity: 'week',
};
