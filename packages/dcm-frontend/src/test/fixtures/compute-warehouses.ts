import type {
  ComputeWarehouseCostSnapshot,
  ComputeWarehouseDetailResponse,
  ComputeWarehouseQueryPerformanceSnapshot,
  ComputeWarehousesCostResponse,
  ComputeWarehousesOverviewResponse,
  ComputeWarehousesQueryPerformanceResponse,
  ComputeWarehousesSlowQueriesResponse,
  ComputeWarehouseWindow,
} from '../../types/api';

/**
 * The window the API reports as actually covered. Deliberately a 7-day range
 * while the page defaults to `Daily`: the covered period must be read from the
 * response, never recomputed from the selected chip or from `today`.
 */
export const computeWarehouseWindowFixture: ComputeWarehouseWindow = {
  window_days: 7,
  from_date: '2026-08-07',
  to_date: '2026-08-13',
};

export const computeWarehousesOverviewFixture: ComputeWarehousesOverviewResponse = {
  kpis: {
    total_cost_usd: 18240,
    cost_delta_pct: -4.2,
    active_warehouses: 12,
    query_count: 458_000,
    failed_count: 920,
    open_recommendations: 7,
  },
  items: [
    {
      cloud_provider: 'azure',
      source_lz_id: 'lz-1',
      workspace_id: 'ws-1',
      workspace_name: 'dbw-analytics-prod',
      warehouse_id: 'wh-analytics',
      warehouse_name: 'Analytics WH',
      warehouse_size: 'Medium',
      // `PRO` and not `SERVERLESS`: the default row has efficiency figures and rightsizing
      // advice, which is only coherent on a non-serverless warehouse.
      warehouse_type: 'PRO',
      is_serverless: false,
      cost_usd: 4200,
      query_count: 120_000,
      failure_rate_pct: 0.8,
      latency_p95_ms: 4200,
    },
  ],
  // A total far above the single row returned: the overview pages server-side, so the
  // footer must report the whole scope, not the length of `items`.
  total: 96,
  page: 1,
  page_size: 25,
  window: computeWarehouseWindowFixture,
  period: { from: '2026-08-07', to: '2026-08-13' },
};

export const computeWarehousesCostFixture: ComputeWarehousesCostResponse = {
  items: [
    {
      cloud_provider: 'azure',
      source_lz_id: 'lz-1',
      workspace_id: 'ws-1',
      warehouse_id: 'wh-analytics',
      warehouse_name: 'Analytics WH',
      warehouse_size: 'Medium',
      dbu_quantity: 1200,
      cost_usd: 4200,
      cost_usd_prev_window: 140,
      cost_delta_pct: 2.1,
      query_count: 120_000,
      cost_per_query_usd: 0.035,
      top_consumer: 'data-eng',
      window_start: '2026-08-07',
      as_of_date: '2026-08-13',
    },
    // Created inside the window: it has no predecessor, so both comparison fields
    // are `null` and the column must read `—`, never `$0`.
    {
      cloud_provider: 'azure',
      source_lz_id: 'lz-1',
      workspace_id: 'ws-1',
      warehouse_id: 'wh-newcomer',
      warehouse_name: 'Newcomer WH',
      warehouse_size: 'Small',
      dbu_quantity: 40,
      cost_usd: 96,
      cost_usd_prev_window: null,
      cost_delta_pct: null,
      query_count: 300,
      cost_per_query_usd: 0.32,
      top_consumer: 'data-science',
      window_start: '2026-08-07',
      as_of_date: '2026-08-13',
    },
  ],
  total: 2,
  page: 1,
  page_size: 25,
  window: computeWarehouseWindowFixture,
  period: { from: '2026-08-07', to: '2026-08-13' },
};

export const computeWarehousesQueryPerformanceFixture: ComputeWarehousesQueryPerformanceResponse = {
  items: [
    {
      cloud_provider: 'azure',
      source_lz_id: 'lz-1',
      workspace_id: 'ws-1',
      warehouse_id: 'wh-analytics',
      warehouse_name: 'Analytics WH',
      query_count: 120_000,
      failed_count: 960,
      failure_rate_pct: 0.8,
      latency_p50_ms: 900,
      latency_p95_ms: 4200,
      latency_p99_ms: 9800,
      queue_time_avg_ms: 120,
      queue_time_p95_ms: 800,
      spill_query_count: 12,
      cache_hit_pct: 72.5,
      bytes_scanned: 1_200_000_000,
      rows_scanned: 45_000_000,
      top_slow_statement_id: 'stmt-001',
      window_start: '2026-08-07',
      as_of_date: '2026-08-13',
    },
  ],
  total: 1,
  page: 1,
  page_size: 25,
  window: computeWarehouseWindowFixture,
  period: { from: '2026-08-07', to: '2026-08-13' },
};

export const computeWarehousesSlowQueriesFixture: ComputeWarehousesSlowQueriesResponse = {
  enabled: true,
  items: [
    {
      cloud_provider: 'azure',
      source_lz_id: 'lz-1',
      workspace_id: 'ws-1',
      warehouse_id: 'wh-analytics',
      statement_id: 'stmt-001',
      warehouse_name: 'Analytics WH',
      executed_by: 'data-eng@example.com',
      start_time: '2026-07-30T14:22:00Z',
      duration_ms: 45_000,
      status: 'FAILED',
      reason: 'FAILURE',
      error_message: 'Query timeout',
      query_profile_url: 'https://example.cloud.databricks.com/sql/history?statementId=stmt-001',
    },
  ],
  total: 1,
  page: 1,
  page_size: 25,
  period: { from: '2026-07-01', to: '2026-07-31' },
};

/**
 * `/warehouses/{id}` still reads the `*_daily` tables: its snapshots carry a
 * `period_start` and a day-over-day comparison, not a window.
 */
const warehouseCostSnapshot: ComputeWarehouseCostSnapshot = {
  cloud_provider: 'azure',
  source_lz_id: 'lz-1',
  workspace_id: 'ws-1',
  warehouse_id: 'wh-analytics',
  warehouse_name: 'Analytics WH',
  warehouse_size: 'Medium',
  dbu_quantity: 180,
  cost_usd: 620,
  cost_usd_prev_day: 140,
  cost_delta_pct: 2.1,
  query_count: 18_000,
  cost_per_query_usd: 0.035,
  top_consumer: 'data-eng',
  period_start: '2026-08-13',
};

const warehousePerfSnapshot: ComputeWarehouseQueryPerformanceSnapshot = {
  cloud_provider: 'azure',
  source_lz_id: 'lz-1',
  workspace_id: 'ws-1',
  warehouse_id: 'wh-analytics',
  warehouse_name: 'Analytics WH',
  query_count: 18_000,
  failed_count: 140,
  failure_rate_pct: 0.8,
  latency_p50_ms: 900,
  latency_p95_ms: 4200,
  latency_p99_ms: 9800,
  queue_time_avg_ms: 120,
  queue_time_p95_ms: 800,
  spill_query_count: 2,
  cache_hit_pct: 72.5,
  bytes_scanned: 180_000_000,
  rows_scanned: 6_400_000,
  top_slow_statement_id: 'stmt-001',
  period_start: '2026-08-13',
};

export const computeWarehouseDetailFixture: ComputeWarehouseDetailResponse = {
  cloud_provider: 'azure',
  source_lz_id: 'lz-1',
  workspace_id: 'ws-1',
  warehouse_id: 'wh-analytics',
  cost: warehouseCostSnapshot,
  query_performance: warehousePerfSnapshot,
  period: { from: '2026-07-01', to: '2026-07-31' },
};

export const computeWarehouseTrendFixture = {
  items: [
    { bucket: '2026-07-01', cost_usd: 120, dbu_quantity: 40 },
    { bucket: '2026-07-08', cost_usd: 140, dbu_quantity: 45 },
  ],
  period: { from: '2026-05-03', to: '2026-07-31' },
  granularity: 'week' as const,
};
