import { Card, CardContent } from '../../ui/card';
import { ComputeTrendChart } from '../compute/compute-trend-chart';
import { formatNumber, formatUsd } from '../../../lib/compute/format';
import {
  UC_USAGE_FORECAST_HORIZON_LABEL,
  formatBytes,
  formatIsoDate,
} from '../../../lib/uc-usage/labels';
import type {
  UcUsageForecastMetric,
  UcUsageForecastSeries,
  UcUsageWrittenBytesPoint,
} from '../../../types/api';

const METRIC_LABELS: Record<UcUsageForecastMetric, string> = {
  request_count: 'Read accesses',
  // Sommée sur les tables du périmètre, la métrique compte les couples
  // (consommateur, table) actifs du jour — pas les consommateurs, qui sont 80
  // fois moins nombreux et tenus par le KPI « Consumers ».
  distinct_consumers: 'Consumer–table pairs',
  estimated_cost_usd: 'Estimated cost',
  data_read_bytes: 'Bytes read',
};

function formatMetricValue(metric: UcUsageForecastMetric, value: number | null): string {
  if (metric === 'estimated_cost_usd') return formatUsd(value);
  if (metric === 'data_read_bytes') return formatBytes(value);
  return formatNumber(value);
}

/**
 * Une métrique additive se cumule sur la période ; `distinct_consumers` non —
 * elle compte des couples (consommateur, table) par jour, et le même couple
 * réapparaît chaque jour. Sa moyenne journalière est la seule lecture juste.
 */
const ADDITIVE_METRICS: Record<UcUsageForecastMetric, boolean> = {
  request_count: true,
  estimated_cost_usd: true,
  data_read_bytes: true,
  distinct_consumers: false,
};

/** Cumul ou moyenne selon la métrique ; `null` si rien n'a été mesuré. */
function aggregate(metric: UcUsageForecastMetric, values: (number | null)[]): number | null {
  const measured = values.filter((value): value is number => value != null);
  if (measured.length === 0) return null;
  const total = measured.reduce((sum, value) => sum + value, 0);
  return ADDITIVE_METRICS[metric] ? total : total / measured.length;
}

function TrendCard({ series }: { series: UcUsageForecastSeries }) {
  const observed = series.observed ?? [];
  // Réalisé d'abord, prévision ensuite : une courbe unique, dont seule la queue
  // est pointillée — jamais deux séries superposées qu'on croirait comparables.
  const observedPoints = observed.map((point) => ({
    label: formatIsoDate(point.period_start),
    value: point.value,
    tooltip: `${formatIsoDate(point.period_start)} · observed ${formatMetricValue(
      series.metric_name,
      point.value
    )}`,
  }));
  const forecastPoints = series.points.map((point) => ({
    label: formatIsoDate(point.horizon_date),
    value: point.predicted_value,
    tooltip: `${formatIsoDate(point.horizon_date)} · forecast ${formatMetricValue(
      series.metric_name,
      point.predicted_value
    )}`,
  }));
  const points = [...observedPoints, ...forecastPoints];

  // Dernier jour MESURÉ, pas dernier point : la série porte un point par jour
  // calendaire et les jours sans lecture y valent `null`.
  const measured = observed.filter((point) => point.value != null);
  const lastMeasured = measured[measured.length - 1] ?? null;
  const lastForecast = series.points[series.points.length - 1] ?? null;
  // Le chiffre porte sur TOUTE la période, comme le reste du bloc « Overview » :
  // la valeur d'un seul jour s'y lisait comme un cumul.
  const observedTotal = aggregate(
    series.metric_name,
    observed.map((point) => point.value)
  );
  const forecastTotal = aggregate(
    series.metric_name,
    series.points.map((point) => point.predicted_value)
  );
  // Le réalisé prime quand il existe : une projection ne tient pas lieu de mesure.
  const headline = measured.length ? observedTotal : forecastTotal;
  const kind = ADDITIVE_METRICS[series.metric_name] ? 'Total' : 'Avg/day';

  return (
    <Card className="h-full">
      <CardContent className="space-y-2 py-4">
        <p className="text-[10px] font-black uppercase tracking-[1.2px] text-muted-foreground">
          {METRIC_LABELS[series.metric_name] ?? series.metric_name}{' '}
          {observed.length
            ? `observed → ${UC_USAGE_FORECAST_HORIZON_LABEL}`
            : UC_USAGE_FORECAST_HORIZON_LABEL}
        </p>
        <p className="text-lg font-semibold text-foreground">
          {formatMetricValue(series.metric_name, headline)}
          {measured.length && forecastTotal != null ? (
            <span className="ml-1 text-xs font-medium text-muted-foreground">
              → {formatMetricValue(series.metric_name, forecastTotal)} forecast
            </span>
          ) : null}
        </p>
        {/* Sans la fenêtre, un cumul de période et un cumul d'horizon se confondent. */}
        <p className="text-xs text-muted-foreground">
          {kind} ·{' '}
          {lastMeasured
            ? `${measured.length} day${measured.length > 1 ? 's' : ''} observed to ${formatIsoDate(lastMeasured.period_start)}`
            : 'no measured day in the period'}
          {lastForecast ? ` → next ${series.points.length} days` : ''}
        </p>
        <ComputeTrendChart
          points={points}
          dashedFromIndex={observedPoints.length > 0 ? observedPoints.length : undefined}
          ariaLabel={`Trend ${METRIC_LABELS[series.metric_name] ?? series.metric_name} ${UC_USAGE_FORECAST_HORIZON_LABEL}`}
        />
      </CardContent>
    </Card>
  );
}

/**
 * Une métrique sans réalisé **ni** prévision est **absente** de `trends` : ne
 * rien rendre pour elle, plutôt qu'une série à zéro (SC-005).
 */
export function UcUsageTrendCards({ series }: { series: UcUsageForecastSeries[] }) {
  if (series.length === 0) {
    return <p className="text-sm text-muted-foreground">No forecast available for this scope.</p>;
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      {series.map((entry) => (
        <TrendCard key={entry.metric_name} series={entry} />
      ))}
    </div>
  );
}

/**
 * Volume écrit **observé** (`data_written_bytes`), jamais une projection. Un
 * point `null` reste un trou dans la courbe, pas un zéro.
 */
export function UcUsageWrittenBytesCard({ points }: { points: UcUsageWrittenBytesPoint[] }) {
  const chartPoints = points.map((point) => ({
    label: formatIsoDate(point.period_start),
    value: point.data_written_bytes,
    tooltip: `${formatIsoDate(point.period_start)} · ${formatBytes(point.data_written_bytes)}`,
  }));
  const measured = points.filter((point) => point.data_written_bytes != null);
  const total = measured.length
    ? measured.reduce((sum, point) => sum + Number(point.data_written_bytes), 0)
    : null;

  return (
    <Card className="h-full">
      <CardContent className="space-y-2 py-4">
        <p className="text-[10px] font-black uppercase tracking-[1.2px] text-muted-foreground">
          Written volume (observed)
        </p>
        <p className="text-lg font-semibold text-foreground">{formatBytes(total)}</p>
        <p className="text-xs text-muted-foreground">Observed volume across the selected period.</p>
        {chartPoints.length > 0 ? (
          <ComputeTrendChart
            points={chartPoints}
            variant="bar"
            ariaLabel="Observed written volume"
          />
        ) : null}
      </CardContent>
    </Card>
  );
}
