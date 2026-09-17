import type {
  UcUsageConsumerCharts,
  UcUsageFinopsCharts,
  UcUsageTableCharts,
} from '../../types/api';

const envelope = {
  period: { start: '2026-09-01', end: '2026-09-03' },
  filters: { catalog: null, schema: null, tables: [] },
  grain: 'day' as const,
};
const dates = ['2026-09-01', '2026-09-02', '2026-09-03'];
const points = (values: Array<number | null>) =>
  values.map((value, index) => ({ date: dates[index], value }));

export const ucTableChartsFixture: UcUsageTableCharts = {
  ...envelope,
  series: [
    {
      key: 'orders',
      label: 'main.sales.orders',
      cloud_provider: 'aws',
      entity_count: 1,
      points: points([100, 50, 0]),
    },
    {
      key: 'invoices',
      label: 'main.finance.invoices',
      cloud_provider: 'aws',
      entity_count: 1,
      points: points([50, null, 20]),
    },
  ],
  ranking: [
    {
      key: 'orders',
      label: 'main.sales.orders',
      cloud_provider: 'aws',
      value: 150,
      share_pct: 68.18,
    },
    {
      key: 'invoices',
      label: 'main.finance.invoices',
      cloud_provider: 'aws',
      value: 70,
      share_pct: 31.82,
    },
  ],
  summary: {
    total: 220,
    entity_count: 2,
    unmeasured_entity_count: 0,
    top_5_total: 220,
    other_total: null,
    top_5_share_pct: 100,
    top_10_share_pct: 100,
  },
  activity: {
    grain: 'day',
    columns: dates.map((date) => ({ start: date, end: date })),
    rows: [
      {
        key: 'orders',
        label: 'main.sales.orders',
        cloud_provider: 'aws',
        cells: [100, 50, 0].map((value) => ({ value, observed_days: 1, expected_days: 1 })),
      },
      {
        key: 'invoices',
        label: 'main.finance.invoices',
        cloud_provider: 'aws',
        cells: [50, null, 20].map((value) => ({
          value,
          observed_days: value == null ? 0 : 1,
          expected_days: 1,
        })),
      },
    ],
  },
  single_table_consumers: [],
  ranking_mode: 'tables',
};

export const ucConsumerChartsFixture: UcUsageConsumerCharts = {
  ...envelope,
  total_requests: 220,
  by_type: [
    { key: 'JOB', label: 'JOB', total: 130, share_pct: 59.09, points: points([100, 30, 0]) },
    { key: 'USER', label: 'USER', total: 90, share_pct: 40.91, points: points([50, 20, 20]) },
  ],
  ranking: [
    {
      key: 'job',
      label: 'job-reporting',
      cloud_provider: 'aws',
      value: 130,
      share_pct: 59.09,
      distinct_tables: 2,
      consumer_type: 'JOB',
    },
    {
      key: 'user',
      label: 'analyst',
      cloud_provider: 'aws',
      value: 90,
      share_pct: 40.91,
      distinct_tables: 2,
      consumer_type: 'USER',
    },
  ],
  previous_period: { start: '2026-08-29', end: '2026-08-31' },
  active_consumers: points([2, 2, 1]).map((point, index) => ({
    ...point,
    previous_date: `2026-08-${29 + index}`,
    previous_value: index === 2 ? null : 1,
  })),
};

export const ucFinopsChartsFixture: UcUsageFinopsCharts = {
  ...envelope,
  series: [
    { ...ucTableChartsFixture.series[0], points: points([2, 1, null]) },
    { ...ucTableChartsFixture.series[1], points: points([1, null, 0.4]) },
  ],
  ranking: [
    { ...ucTableChartsFixture.ranking[0], value: 3, share_pct: 68.18 },
    { ...ucTableChartsFixture.ranking[1], value: 1.4, share_pct: 31.82 },
  ],
  summary: {
    total: 4.4,
    entity_count: 2,
    unmeasured_entity_count: 0,
    top_5_total: 4.4,
    other_total: null,
    top_5_share_pct: 100,
    top_10_share_pct: 100,
  },
  unit_cost: points([30, 20, 20]).map((point, index) => ({
    ...point,
    request_count: [150, 50, 20][index],
    costed_request_count: [100, 50, 20][index],
    coverage_pct: index === 0 ? 66.67 : 100,
    cost_attribution_method: 'equal_parts_fallback',
    cost_basis: 'warehouse_prorata',
  })),
  cost_coverage_pct: 77.27,
  cost_attribution_method: 'equal_parts_fallback',
  cost_basis: 'warehouse_prorata',
};
