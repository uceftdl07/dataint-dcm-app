import { useMemo, useState } from 'react';
import { Skeleton } from '../../ui/skeleton';
import {
  FORECAST_DISTRIBUTION_METRICS,
  FORECAST_METRIC_LABELS,
  FORECAST_METRICS,
  formatForecastMetricValue,
} from '../../../lib/compute/recommendations';
import type {
  ComputeForecastActualPoint,
  ComputeForecastMetricName,
  ComputeForecastPoint,
} from '../../../types/api';
import { ChartHoverTooltip } from './chart-hover-tooltip';

interface AggregatedForecastPoint {
  date: string;
  /**
   * Sum of the per-object projections for that day, or `null` when the forecast
   * table holds no row for it — a day the observed series knows and the model
   * does not. `null` keeps it out of the scale and out of the dashed line; a 0
   * there would read as "nothing was predicted", which is not the same claim.
   */
  predicted: number | null;
  /**
   * Per-object bounds combined in QUADRATURE around `predicted`, not added (see
   * `aggregateForecastByDate`). `null` when no object carried a bound that day —
   * a zero-width band there would claim certainty the model never expressed.
   */
  lower: number | null;
  upper: number | null;
  /** Observed value when available (historical curve). */
  actual: number | null;
}

/** Running totals for one horizon date, before the square root (see `aggregateForecastByDate`). */
interface ForecastAccumulator {
  predicted: number;
  /** Objects that carried a projection — the divisor of a distribution metric. */
  predictedCount: number;
  /** Σ (predicted − lower)² over the objects that carried a lower bound. */
  lowerSquares: number;
  /** Σ (upper − predicted)² over the objects that carried an upper bound. */
  upperSquares: number;
  lowerCount: number;
  upperCount: number;
}

/**
 * Aggregates the per-object rows of one metric into one series per horizon date.
 *
 * Two natures of metric, and the difference decides both the central value and the
 * band (cf. `FORECAST_DISTRIBUTION_METRICS`):
 *
 *   - ADDITIVE (`cost_usd`, `dbu_quantity`, `query_count`) — the fleet figure is the
 *     SUM of the projections. The expected value of a total is the total of the
 *     expected values, whatever the correlation between objects.
 *   - DISTRIBUTION (`cpu_util_p95_pct`, `queue_time_p95_ms`) — the fleet figure is
 *     their MEAN. Summing would show 2000 % of CPU for 50 clusters at 40 %.
 *
 * The bounds are never summed either. Each object's bound carries the same 95 %
 * (cf. `FORECAST_PREDICTION_INTERVAL_WIDTH`), and adding N of them describes the
 * day where every object lands on its own bound at once — far less likely than
 * 95 %, so the band grew with the size of the fleet rather than with the
 * uncertainty. Half-widths are combined in quadrature instead (`√Σ half²`, the
 * standard error of a sum of independent terms), which grows in √N where the sum
 * grew in N, then divided by N for a mean — the same `1/N` its central value gets.
 * On a single object the square root of a single square is that same half-width, so
 * the band is then exactly the model's own interval, for either nature.
 *
 * The independence this assumes is an approximation, and it errs on the narrow
 * side: objects driven by one shared workload move together, and a truly
 * correlated fleet would justify a wider band — up to the former sum in the
 * degenerate case where all objects are perfectly correlated.
 */
function aggregateForecastByDate(
  items: ComputeForecastPoint[],
  metric: ComputeForecastMetricName
): AggregatedForecastPoint[] {
  const byDate = new Map<string, ForecastAccumulator>();
  const isDistribution = FORECAST_DISTRIBUTION_METRICS.has(metric);

  for (const row of items) {
    if (row.metric_name !== metric) continue;
    const acc = byDate.get(row.horizon_date) ?? {
      predicted: 0,
      predictedCount: 0,
      lowerSquares: 0,
      upperSquares: 0,
      lowerCount: 0,
      upperCount: 0,
    };
    const predicted = row.predicted_value;
    if (predicted != null) {
      acc.predicted += predicted;
      acc.predictedCount += 1;
    }
    // A bound is only usable centred on its own projection: without
    // `predicted_value` there is no half-width to square, and a missing bound is
    // skipped rather than read as 0 — a 0 would fabricate a half-width equal to
    // the projection itself.
    if (predicted != null && row.lower_bound != null) {
      acc.lowerSquares += (predicted - row.lower_bound) ** 2;
      acc.lowerCount += 1;
    }
    if (predicted != null && row.upper_bound != null) {
      acc.upperSquares += (row.upper_bound - predicted) ** 2;
      acc.upperCount += 1;
    }
    byDate.set(row.horizon_date, acc);
  }

  return [...byDate.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, acc]) => {
      // A mean over the objects that actually carried a projection that day; the
      // divisor is never 0 here, an accumulator only exists once a row created it.
      const divisor = isDistribution && acc.predictedCount > 0 ? acc.predictedCount : 1;
      const predicted = acc.predicted / divisor;
      return {
        date,
        predicted,
        // Floored at 0: every projected metric is non-negative by construction
        // (`global_floor` of the pipeline), so a band dipping below 0 would show a
        // figure no scope can reach.
        lower:
          acc.lowerCount === 0
            ? null
            : Math.max(0, predicted - Math.sqrt(acc.lowerSquares) / divisor),
        upper: acc.upperCount === 0 ? null : predicted + Math.sqrt(acc.upperSquares) / divisor,
        actual: null,
      };
    });
}

/**
 * Number of objects aggregated into the plotted series. Above 1 the band is the
 * model's intervals combined in quadrature (cf. `aggregateForecastByDate`), so it
 * remains a ~95 % interval of the total — but one resting on an independence
 * assumption the single-object case does not need. The label says which.
 */
function countForecastObjects(
  items: ComputeForecastPoint[],
  metric: ComputeForecastMetricName
): number {
  const objects = new Set<string>();
  for (const row of items) {
    if (row.metric_name !== metric) continue;
    objects.add(`${row.object_type}::${row.object_id}`);
  }
  return objects.size;
}

/**
 * Observed series merged onto the projected one, by date.
 *
 * The sum below is safe only because the API serves actuals for `cost_usd` and
 * `dbu_quantity` alone (`_ACTUAL_COST_METRICS`), both ADDITIVE, already aggregated
 * to one row per (date, metric). Serving a DISTRIBUTION metric there would need the
 * mean of `aggregateForecastByDate`, not this sum.
 */
function mergeActuals(
  series: AggregatedForecastPoint[],
  actuals: ComputeForecastActualPoint[],
  metric: ComputeForecastMetricName
): AggregatedForecastPoint[] {
  const byDate = new Map<string, number>();
  for (const row of actuals) {
    if (row.metric_name !== metric) continue;
    byDate.set(row.horizon_date, (byDate.get(row.horizon_date) ?? 0) + row.actual_value);
  }
  if (byDate.size === 0) return series;

  const dates = new Set([...series.map((p) => p.date), ...byDate.keys()]);
  return [...dates]
    .sort((a, b) => a.localeCompare(b))
    .map((date) => {
      const existing = series.find((p) => p.date === date);
      return {
        date,
        predicted: existing?.predicted ?? null,
        lower: existing?.lower ?? null,
        upper: existing?.upper ?? null,
        actual: byDate.has(date) ? (byDate.get(date) ?? 0) : (existing?.actual ?? null),
      };
    });
}

const PADDING = 8;

interface PlottedForecastPoint extends AggregatedForecastPoint {
  x: number;
  yPredicted: number | null;
  yActual: number | null;
  isForecast: boolean;
}

/** Values a point contributes to the vertical scale — a missing one is skipped, not read as 0. */
function scaleValues(
  point: AggregatedForecastPoint & { isForecast: boolean },
  useActualHistorical: boolean
): number[] {
  const out = [point.predicted, point.lower, point.upper];
  if (useActualHistorical && !point.isForecast) out.push(point.actual);
  return out.filter((value): value is number => value != null);
}

function plotForecast(
  historical: AggregatedForecastPoint[],
  forecast: AggregatedForecastPoint[],
  width: number,
  height: number,
  useActualHistorical: boolean
): PlottedForecastPoint[] {
  const series = [
    ...historical.map((point) => ({ ...point, isForecast: false })),
    ...forecast.map((point) => ({ ...point, isForecast: true })),
  ];
  const values = series.flatMap((point) => scaleValues(point, useActualHistorical));
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const step = (width - PADDING * 2) / Math.max(series.length - 1, 1);
  const usable = height - PADDING * 2;

  const yFor = (value: number) => height - PADDING - ((value - min) / span) * usable;

  return series.map((point, index) => ({
    ...point,
    x: series.length === 1 ? width / 2 : PADDING + index * step,
    yPredicted: point.predicted == null ? null : yFor(point.predicted),
    yActual:
      !point.isForecast && useActualHistorical && point.actual != null ? yFor(point.actual) : null,
    isForecast: point.isForecast,
  }));
}

/** y of the drawn point: the observed value where there is one, the projection otherwise. */
function plottedY(point: PlottedForecastPoint): number | null {
  return point.isForecast ? point.yPredicted : (point.yActual ?? point.yPredicted);
}

function polylineXY(points: Array<{ x: number; y: number | null }>): string {
  const drawn = points.flatMap((point) => (point.y == null ? [] : [{ x: point.x, y: point.y }]));
  if (drawn.length <= 1) return '';
  return drawn.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ');
}

function splitHistoricalForecast(
  series: AggregatedForecastPoint[],
  splitDate: string
): { historical: AggregatedForecastPoint[]; forecast: AggregatedForecastPoint[] } {
  const historical: AggregatedForecastPoint[] = [];
  const forecast: AggregatedForecastPoint[] = [];

  for (const point of series) {
    if (point.date <= splitDate) {
      historical.push(point);
    } else {
      forecast.push(point);
    }
  }

  return { historical, forecast };
}

const CHART_WIDTH = 640;
const CHART_HEIGHT = 140;

function ForecastChart({
  historical,
  forecast,
  metric,
  useActualHistorical,
}: {
  historical: AggregatedForecastPoint[];
  forecast: AggregatedForecastPoint[];
  metric: ComputeForecastMetricName;
  useActualHistorical: boolean;
}) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const width = CHART_WIDTH;
  const height = CHART_HEIGHT;
  const plotted = useMemo(
    () => plotForecast(historical, forecast, width, height, useActualHistorical),
    [historical, forecast, width, height, useActualHistorical]
  );
  const histLine = polylineXY(
    plotted
      .filter((point) => !point.isForecast)
      .map((point) => ({ x: point.x, y: plottedY(point) }))
  );
  // The dashed line starts on the last DRAWN historical point — the observed
  // value where there is one, and the only point available when the model holds
  // no row for that day — so the projection continues the curve.
  const fcLine = polylineXY(
    plotted.slice(Math.max(historical.length - 1, 0)).map((point, index) => ({
      x: point.x,
      y: index === 0 && !point.isForecast ? plottedY(point) : point.yPredicted,
    }))
  );

  const values = plotted.flatMap((point) => scaleValues(point, useActualHistorical));
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const usable = height - PADDING * 2;
  const yFor = (value: number) => height - PADDING - ((value - min) / span) * usable;
  const bandPts = plotted.flatMap((point) =>
    point.isForecast && point.lower != null && point.upper != null
      ? [{ x: point.x, lower: point.lower, upper: point.upper }]
      : []
  );
  const bandPolygon =
    bandPts.length > 1
      ? [
          ...bandPts.map((p) => `${p.x.toFixed(1)},${yFor(p.upper).toFixed(1)}`),
          ...[...bandPts].reverse().map((p) => `${p.x.toFixed(1)},${yFor(p.lower).toFixed(1)}`),
        ].join(' ')
      : '';

  const band = plotted.length > 0 ? width / plotted.length : width;
  const activePoint = activeIndex == null ? null : (plotted[activeIndex] ?? null);
  const activeY = activePoint ? plottedY(activePoint) : null;
  const labelIndexes = new Set(
    [0, Math.floor((plotted.length - 1) / 2), plotted.length - 1].filter((i) => i >= 0)
  );

  return (
    <div className="relative" onMouseLeave={() => setActiveIndex(null)}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height={height}
        role="img"
        aria-label={`${FORECAST_METRIC_LABELS[metric]} forecast`}
      >
        {bandPolygon ? <polygon points={bandPolygon} fill="var(--purple)" opacity="0.12" /> : null}
        {histLine ? (
          <polyline points={histLine} fill="none" stroke="var(--primary)" strokeWidth="2.5" />
        ) : null}
        {fcLine ? (
          <polyline
            points={fcLine}
            fill="none"
            stroke="var(--purple)"
            strokeWidth="2.5"
            strokeDasharray="5 4"
          />
        ) : null}

        {plotted.map((point, index) => {
          const y = plottedY(point);
          const value = point.isForecast ? point.predicted : (point.actual ?? point.predicted);
          if (!labelIndexes.has(index) || y == null || value == null) return null;
          return (
            <g key={`label-${point.date}`}>
              <circle
                cx={point.x}
                cy={y}
                r="2.5"
                fill={point.isForecast ? 'var(--purple)' : 'var(--primary)'}
              />
              <text
                x={point.x}
                y={y - 6}
                textAnchor="middle"
                className="fill-muted-foreground"
                style={{ fontSize: 8, fontWeight: 600 }}
              >
                {formatForecastMetricValue(metric, value)}
              </text>
            </g>
          );
        })}

        {activePoint ? (
          <>
            <line
              x1={activePoint.x}
              y1="0"
              x2={activePoint.x}
              y2={height}
              stroke="currentColor"
              strokeWidth="1"
              strokeDasharray="3 3"
              className="text-muted-foreground/60"
            />
            {activeY != null ? (
              <circle
                cx={activePoint.x}
                cy={activeY}
                r="3.5"
                fill={activePoint.isForecast ? 'var(--purple)' : 'var(--primary)'}
              />
            ) : null}
          </>
        ) : null}

        {plotted.map((point, index) => (
          <rect
            key={`hover-${point.date}`}
            x={band * index}
            y="0"
            width={band}
            height={height}
            fill="transparent"
            aria-hidden
            onMouseEnter={() => setActiveIndex(index)}
            onMouseMove={() => setActiveIndex(index)}
          />
        ))}
      </svg>

      {activePoint && activeIndex != null ? (
        <ChartHoverTooltip index={activeIndex} count={plotted.length}>
          {activePoint.date} ·{' '}
          {activePoint.isForecast
            ? formatForecastMetricValue(metric, activePoint.predicted)
            : formatForecastMetricValue(
                metric,
                useActualHistorical && activePoint.actual != null
                  ? activePoint.actual
                  : activePoint.predicted
              )}
          {activePoint.isForecast ? (
            <span className="ml-1 font-medium text-muted-foreground">
              (CI {formatForecastMetricValue(metric, activePoint.lower)} –{' '}
              {formatForecastMetricValue(metric, activePoint.upper)})
            </span>
          ) : useActualHistorical && activePoint.actual != null ? (
            <span className="ml-1 font-medium text-muted-foreground">(observed)</span>
          ) : null}
        </ChartHoverTooltip>
      ) : null}
    </div>
  );
}

export function ForecastWidget({
  items,
  actuals = [],
  loading,
  metric,
  onMetricChange,
  periodEnd,
}: {
  items: ComputeForecastPoint[];
  actuals?: ComputeForecastActualPoint[];
  loading?: boolean;
  metric: ComputeForecastMetricName;
  onMetricChange: (metric: ComputeForecastMetricName) => void;
  periodEnd: string;
}) {
  const predictedSeries = useMemo(() => aggregateForecastByDate(items, metric), [items, metric]);
  const series = useMemo(
    () => mergeActuals(predictedSeries, actuals, metric),
    [predictedSeries, actuals, metric]
  );
  const splitDate = periodEnd || new Date().toISOString().slice(0, 10);
  const { historical, forecast } = useMemo(
    () => splitHistoricalForecast(series, splitDate),
    [series, splitDate]
  );
  const useActualHistorical = historical.some((point) => point.actual != null);
  const objectCount = useMemo(() => countForecastObjects(items, metric), [items, metric]);

  const headlinePoint =
    forecast.length > 0 ? forecast[forecast.length - 1] : series[series.length - 1];
  const headlineValue = headlinePoint
    ? formatForecastMetricValue(metric, headlinePoint.predicted)
    : '—';
  const boundsLabel =
    objectCount <= 1
      ? 'Confidence interval'
      : `Confidence interval over ${objectCount} objects (combined)`;
  const rangeLabel =
    headlinePoint && headlinePoint.lower != null && headlinePoint.upper != null
      ? `${boundsLabel}: ${formatForecastMetricValue(metric, headlinePoint.lower)} – ${formatForecastMetricValue(metric, headlinePoint.upper)}`
      : `${boundsLabel} unavailable`;

  return (
    <div className="overflow-hidden rounded-[var(--card-radius)] border border-border bg-[var(--card-background)] px-[var(--card-padding-x)] py-[var(--card-padding-y)] shadow-[var(--card-shadow)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-black uppercase tracking-[1.5px] text-muted-foreground">
            Forecast
          </p>
          {loading ? (
            <Skeleton className="mt-2 h-8 w-40" />
          ) : (
            <p className="mt-1 text-2xl font-bold tracking-tight text-foreground">
              {headlineValue}
            </p>
          )}
          <p className="mt-1 text-xs text-muted-foreground">
            {rangeLabel}
            {forecast.length > 0 ? ` · ${forecast.length}-day projection` : ''}
          </p>
        </div>
        <select
          className="rounded-full border border-border bg-background px-3 py-2 text-xs font-semibold text-foreground"
          value={metric}
          onChange={(e) => onMetricChange(e.target.value as ComputeForecastMetricName)}
          aria-label="Forecast metric"
        >
          {FORECAST_METRICS.map((name) => (
            <option key={name} value={name}>
              {FORECAST_METRIC_LABELS[name]}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4">
        {loading ? (
          <Skeleton className="h-[140px] w-full" />
        ) : series.length === 0 ? (
          <div className="flex h-[140px] items-center justify-center text-xs text-muted-foreground">
            No forecast data for this scope
          </div>
        ) : (
          <ForecastChart
            historical={historical}
            forecast={forecast}
            metric={metric}
            useActualHistorical={useActualHistorical}
          />
        )}
      </div>

      <div className="mt-2 flex flex-wrap gap-4 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-2">
          <span className="inline-block h-0.5 w-5 bg-primary" />
          {useActualHistorical ? 'Historical (observed)' : 'Historical (forecast model)'}
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="inline-block h-0.5 w-5 border-t-2 border-dashed border-purple bg-transparent" />
          Forecast (ai_forecast)
        </span>
      </div>
    </div>
  );
}
