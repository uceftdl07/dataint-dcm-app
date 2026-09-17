import type { BadgeProps } from '../../components/ui/badge';
import type { ComputeForecastMetricName } from '../../types/api';
import { formatNumber, formatPct, formatUsd } from './format';

export const FORECAST_METRICS: ComputeForecastMetricName[] = [
  'cost_usd',
  'dbu_quantity',
  'cpu_util_p95_pct',
  'query_count',
  'queue_time_p95_ms',
];

export const FORECAST_METRIC_LABELS: Record<ComputeForecastMetricName, string> = {
  cost_usd: 'Total cost',
  dbu_quantity: 'DBU consumed',
  cpu_util_p95_pct: 'Average CPU p95',
  query_count: 'Query volume',
  queue_time_p95_ms: 'Average queue time p95',
};

/**
 * Metrics of DISTRIBUTION, which do not add up across objects: the fleet figure is
 * the MEAN of the per-object projections, never their sum. Adding 50 clusters at
 * 40 % would show 2000 %, and adding per-warehouse p95 queue times a wait nobody
 * ever had.
 *
 * Mirrors the distinction the pipeline already makes when it trains the models —
 * additive metrics get a densified series (a day without a row is worth 0), these
 * ones stay sparse (a day without activity has no percentile at all), cf.
 * `pipelines.gold_dbx_compute.forecast._observed_sql`. Every metric absent from
 * this set is additive and sums.
 */
export const FORECAST_DISTRIBUTION_METRICS: ReadonlySet<ComputeForecastMetricName> = new Set([
  'cpu_util_p95_pct',
  'queue_time_p95_ms',
]);

export const RECOMMENDATION_CATEGORIES = [
  'FINOPS',
  'RIGHTSIZING',
  'GOVERNANCE',
  'RELIABILITY',
] as const;

export type RecommendationCategory = (typeof RECOMMENDATION_CATEGORIES)[number];

export function categoryLabel(category: string | null | undefined): string {
  const s = (category || '').trim().toUpperCase();
  if (s === 'FINOPS') return 'FinOps';
  if (s === 'RIGHTSIZING') return 'Rightsizing';
  if (s === 'GOVERNANCE') return 'Governance';
  if (s === 'RELIABILITY') return 'Reliability';
  return category || '—';
}

export function categoryBadgeVariant(
  category: string | null | undefined
): NonNullable<BadgeProps['variant']> {
  const s = (category || '').trim().toUpperCase();
  if (s === 'FINOPS') return 'warning';
  if (s === 'RIGHTSIZING') return 'info';
  if (s === 'GOVERNANCE') return 'secondary';
  if (s === 'RELIABILITY') return 'destructive';
  return 'outline';
}

export function recommendationStatusBadgeVariant(
  status: string | null | undefined
): NonNullable<BadgeProps['variant']> {
  const s = (status || '').trim().toUpperCase();
  if (s === 'OPEN') return 'warning';
  if (s === 'RESOLVED') return 'success';
  if (s === 'DISMISSED') return 'outline';
  return 'outline';
}

export function recommendationStatusLabel(status: string | null | undefined): string {
  const s = (status || '').trim().toUpperCase();
  if (s === 'OPEN') return 'Open';
  if (s === 'RESOLVED') return 'Resolved';
  if (s === 'DISMISSED') return 'Dismissed';
  return status || '—';
}

export function objectTypeLabel(objectType: string | null | undefined): string {
  const s = (objectType || '').trim().toUpperCase();
  if (s === 'CLUSTER') return 'Cluster';
  if (s === 'WAREHOUSE') return 'SQL Warehouse';
  if (s === 'JOB') return 'Job';
  if (s === 'PIPELINE') return 'Pipeline (DLT)';
  return objectType || '—';
}

export function objectDetailPath(objectType: string | null | undefined): string {
  const s = (objectType || '').trim().toUpperCase();
  if (s === 'WAREHOUSE') return '/databricks/sql-warehouse';
  if (s === 'JOB') return '/databricks/job-compute';
  if (s === 'PIPELINE') return '/databricks/pipeline-compute';
  return '/databricks/cluster';
}

export function formatRecommendationSavings(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return formatUsd(value);
}

export function formatForecastMetricValue(
  metric: ComputeForecastMetricName,
  value: number | null | undefined
): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  if (metric === 'cost_usd') return formatUsd(value);
  if (metric === 'cpu_util_p95_pct') return formatPct(value, 0);
  if (metric === 'queue_time_p95_ms') {
    if (value >= 60_000) return `${(value / 60_000).toFixed(1)} min`;
    if (value >= 1000) return `${(value / 1000).toFixed(1)} s`;
    return `${Math.round(value)} ms`;
  }
  return formatNumber(value, metric === 'dbu_quantity' ? 0 : 0);
}

export function daysSince(isoDate: string | null | undefined, referenceIso: string): string {
  if (!isoDate) return '—';
  const start = new Date(`${isoDate}T00:00:00Z`).getTime();
  const end = new Date(`${referenceIso}T00:00:00Z`).getTime();
  if (Number.isNaN(start) || Number.isNaN(end)) return '—';
  const days = Math.max(0, Math.round((end - start) / (24 * 60 * 60 * 1000)));
  if (days === 0) return 'Today';
  if (days === 1) return '1d';
  return `${days}d`;
}
