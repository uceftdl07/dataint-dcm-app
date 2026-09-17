export interface UcUsageColumnDefinition {
  kind: 'text' | 'number';
  unit?: string;
  scale?: number;
}
const numeric: UcUsageColumnDefinition = { kind: 'number' };
const text: UcUsageColumnDefinition = { kind: 'text' };
const bytes: UcUsageColumnDefinition = { kind: 'number', unit: 'GB', scale: 1024 ** 3 };
export const UC_TABLE_FILTERS: Record<string, UcUsageColumnDefinition> = {
  table_full_name: text,
  table_type: text,
  catalog: text,
  schema: text,
  request_count: numeric,
  distinct_consumers: numeric,
  data_read_bytes: bytes,
  data_written_bytes: bytes,
  rows_written: numeric,
  estimated_cost_usd: { kind: 'number', unit: 'USD' },
  latency_p95_ms: { kind: 'number', unit: 'ms' },
  failure_rate_pct: { kind: 'number', unit: '%' },
  freshness_lag_hours: { kind: 'number', unit: 'hours' },
  cost_attribution_method: text,
  cost_basis: text,
};
/**
 * « Cost by table ». Les clés doivent rester celles de `COST_BY_TABLE_COLUMNS`
 * côté backend : une colonne absente de son allowlist est refusée en 422.
 */
export const UC_COST_FILTERS: Record<string, UcUsageColumnDefinition> = {
  table_full_name: text,
  estimated_cost_usd: { kind: 'number', unit: 'USD' },
  cost_per_request_usd: { kind: 'number', unit: 'USD' },
  request_count: numeric,
  data_read_bytes: bytes,
  forecast_cost_usd_7d: { kind: 'number', unit: 'USD' },
};
export const UC_CONSUMER_FILTERS: Record<string, UcUsageColumnDefinition> = {
  consumer_id: text,
  consumer_name: text,
  consumer_type: text,
  distinct_tables: numeric,
  request_count: numeric,
  data_read_bytes: bytes,
  data_written_bytes: bytes,
  rows_written: numeric,
  estimated_cost_usd: { kind: 'number', unit: 'USD' },
};
