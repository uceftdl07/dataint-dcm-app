import type {
  UcUsageDailyMetrics,
  UcUsageWriteCharts,
  UcUsageEntityDetail,
  UcUsageCostChanges,
} from '../../types/api';
import { ucUsageLiveLifecycle } from './uc-usage';

const period = { start: '2026-09-01', end: '2026-09-03' };
const daily: UcUsageDailyMetrics[] = [
  {
    date: '2026-09-01',
    request_count: 100,
    data_read_bytes: 4096,
    data_written_bytes: 2048,
    rows_written: 40,
    estimated_cost_usd: 4,
  },
  {
    date: '2026-09-02',
    request_count: 150,
    data_read_bytes: 8192,
    data_written_bytes: 1024,
    rows_written: 20,
    estimated_cost_usd: 6,
  },
  {
    date: '2026-09-03',
    request_count: null,
    data_read_bytes: null,
    data_written_bytes: null,
    rows_written: null,
    estimated_cost_usd: null,
  },
];
export const ucWriteChartsFixture: UcUsageWriteCharts = {
  period,
  daily,
  summary: {
    data_written_bytes: 3072,
    rows_written: 60,
    tables_with_writes: 1,
    written_without_reads: 0,
  },
  ranking: [
    {
      key: 'orders',
      label: 'main.sales.orders',
      cloud_provider: 'azure',
      value: 3072,
      rows_written: 60,
      request_count: 250,
    },
  ],
};
export const ucEntityDetailFixture: UcUsageEntityDetail = {
  period,
  entity_kind: 'table',
  entity_id: 'main.sales.orders',
  ...ucUsageLiveLifecycle,
  daily,
  summary: {
    request_count: 250,
    data_read_bytes: 12288,
    data_written_bytes: 3072,
    rows_written: 60,
    estimated_cost_usd: 10,
    observed_rows: 3,
    counterpart_count: 1,
    active_days: 2,
    write_days: 2,
  },
  counterparts: [
    {
      id: 'job-reporting',
      label: 'job-reporting',
      request_count: 250,
      data_read_bytes: 12288,
      data_written_bytes: 3072,
      rows_written: 60,
      estimated_cost_usd: 10,
    },
  ],
};
export const ucCostChangesFixture: UcUsageCostChanges = {
  period,
  previous_period: { start: '2026-08-29', end: '2026-08-31' },
  current_total: 10,
  previous_total: 4,
  entity_count: 1,
  items: [
    {
      key: 'orders',
      label: 'main.sales.orders',
      cloud_provider: 'azure',
      current_cost: 10,
      previous_cost: 4,
      delta_usd: 6,
      delta_pct: 150,
    },
  ],
};
