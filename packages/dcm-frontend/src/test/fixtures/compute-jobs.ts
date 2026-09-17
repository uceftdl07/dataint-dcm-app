import type {
  ComputeJobCostTrendResponse,
  ComputeJobDetailResponse,
  ComputeJobsCostResponse,
  ComputeJobsEfficiencyResponse,
  ComputeJobsOverviewResponse,
  ComputeJobUptimeTrendResponse,
  ComputeJobWindow,
} from '../../types/api';

/**
 * The window the API reports as actually covered. Deliberately a 7-day range while
 * the page defaults to `Daily`: the covered period is read from the response, never
 * recomputed from the selected chip.
 */
export const computeJobWindowFixture: ComputeJobWindow = {
  window_days: 7,
  from_date: '2026-08-07',
  to_date: '2026-08-13',
};

export const computeJobsOverviewFixture: ComputeJobsOverviewResponse = {
  kpis: {
    total_cost_usd: 9120,
    cost_delta_pct: 3.4,
    active_jobs: 42,
  },
  items: [
    {
      cloud_provider: 'azure',
      workspace_id: 'ws-1',
      job_id: 'job-1042',
      job_name: 'nightly-ingest',
      cluster_count: 6,
      dbu_quantity: 480,
      cost_usd: 1820,
      cost_usd_prev_window: 1610,
      cost_delta_pct: 13.0,
      cost_rank: 1,
      is_top_cost: true,
      window_start: '2026-08-07',
      as_of_date: '2026-08-13',
      // Measured job: the efficiency snapshot joined a row. The four values are copies
      // of `computeJobsEfficiencyFixture` below — the Overview reads that very column,
      // so a different figure here would state something the backend cannot produce.
      uptime_hours: 41.5,
      uptime_hours_prev_window: 36,
      uptime_hours_delta_pct: 15.3,
      utilization_status: 'OVER',
    },
    {
      // No predecessor window: both cost fields null, the Prev cost column reads "—".
      cloud_provider: 'aws',
      workspace_id: 'ws-2',
      // Empty name in gold: the id is the visible fallback.
      job_id: 'job-2087',
      job_name: null,
      cluster_count: 2,
      dbu_quantity: 90,
      cost_usd: 320,
      cost_usd_prev_window: null,
      cost_delta_pct: null,
      cost_rank: 2,
      is_top_cost: false,
      window_start: '2026-08-07',
      as_of_date: '2026-08-13',
      // Billed but unmeasured: no efficiency row joined, so "—" everywhere — a `0`
      // would claim the job never ran.
      uptime_hours: null,
      uptime_hours_prev_window: null,
      uptime_hours_delta_pct: null,
      utilization_status: null,
    },
  ],
  // A total far above the two rows returned: the page cuts server-side, so the
  // footer reports the whole scope, not the length of `items`.
  total: 42,
  page: 1,
  page_size: 25,
  window: computeJobWindowFixture,
  period: { from: '2026-08-07', to: '2026-08-13' },
};

export const computeJobsCostFixture: ComputeJobsCostResponse = {
  items: computeJobsOverviewFixture.items,
  total: 42,
  page: 1,
  page_size: 25,
  window: computeJobWindowFixture,
  period: { from: '2026-08-07', to: '2026-08-13' },
};

/**
 * Utilization at the job grain. Two rows on purpose:
 * - `job-1042` is fully measured;
 * - `job-2087` is billed with no `node_timeline` sample, so every metric is `null`
 *   and the row must read "—" rather than `0 %` (024 SC-005).
 *
 * `cluster_count` is 7 here against 6 in the cost fixture: the two rollups do not
 * count the same thing (billing vs node timeline), and the UI does not reconcile them.
 */
export const computeJobsEfficiencyFixture: ComputeJobsEfficiencyResponse = {
  items: [
    {
      cloud_provider: 'azure',
      workspace_id: 'ws-1',
      job_id: 'job-1042',
      job_name: 'nightly-ingest',
      cluster_count: 7,
      cpu_util_avg_pct: 61,
      cpu_util_p95_pct: 84,
      mem_util_avg_pct: 47,
      mem_util_p95_pct: 62,
      cpu_wait_avg_pct: 4,
      idle_pct: 12,
      idle_pct_prev_window: 19,
      idle_pct_delta_pts: -7,
      uptime_hours: 41.5,
      uptime_hours_prev_window: 36,
      uptime_hours_delta_pct: 15.3,
      active_hours: 36.5,
      worker_count_avg: 4,
      worker_count_max: 8,
      autoscale_oscillation: 2,
      driver_node_type: 'Standard_DS4_v2',
      worker_node_type: 'Standard_DS3_v2',
      autoscale_enabled: true,
      autoscale_min_workers: 2,
      autoscale_max_workers: 8,
      configured_worker_count: null,
      utilization_status: 'OVER',
      recommended_node_type: 'Standard_D4ads_v5',
      rightsizing_reco: 'Downsize the workers',
      estimated_savings_usd: 210.5,
      window_days: 7,
      window_start: '2026-08-07',
      as_of_date: '2026-08-13',
    },
    {
      cloud_provider: 'aws',
      workspace_id: 'ws-2',
      job_id: 'job-2087',
      job_name: null,
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
  // Smaller than the cost population: a measured job is a billed job, not the reverse.
  total: 31,
  page: 1,
  page_size: 25,
  window: computeJobWindowFixture,
  period: { from: '2026-08-07', to: '2026-08-13' },
};

/** Drawer payload of a measured job — no `governance` key at this grain (024 C2). */
export const computeJobDetailFixture: ComputeJobDetailResponse = {
  cloud_provider: 'azure',
  workspace_id: 'ws-1',
  job_id: 'job-1042',
  cost: computeJobsCostFixture.items[0]!,
  efficiency: computeJobsEfficiencyFixture.items[0]!,
  window: computeJobWindowFixture,
  period: { from: '2026-08-07', to: '2026-08-13' },
};

/**
 * A job billed without a single measured minute: `efficiency` is `null`, the cost
 * block stays populated. The drawer must stay usable and never print `0 %`.
 */
export const computeJobDetailWithoutEfficiencyFixture: ComputeJobDetailResponse = {
  cloud_provider: 'aws',
  workspace_id: 'ws-2',
  job_id: 'job-2087',
  cost: computeJobsCostFixture.items[1]!,
  efficiency: null,
  window: computeJobWindowFixture,
  period: { from: '2026-08-07', to: '2026-08-13' },
};

export const computeJobCostTrendFixture: ComputeJobCostTrendResponse = {
  items: [
    { bucket: '2026-06-15', cost_usd: 210, dbu_quantity: 60 },
    { bucket: '2026-06-22', cost_usd: 260, dbu_quantity: 72 },
    { bucket: '2026-06-29', cost_usd: 190, dbu_quantity: 55 },
  ],
  period: { from: '2026-06-15', to: '2026-08-13' },
  granularity: 'week',
};

export const computeJobUptimeTrendFixture: ComputeJobUptimeTrendResponse = {
  items: [
    { bucket: '2026-06-15', uptime_hours: 12.5, idle_pct: 14.2 },
    { bucket: '2026-06-22', uptime_hours: 9.75, idle_pct: 8.4 },
    // A bucket where the job did not run at all: `null`, never `0`.
    { bucket: '2026-06-29', uptime_hours: null, idle_pct: null },
  ],
  period: { from: '2026-06-15', to: '2026-08-13' },
  granularity: 'week',
};
