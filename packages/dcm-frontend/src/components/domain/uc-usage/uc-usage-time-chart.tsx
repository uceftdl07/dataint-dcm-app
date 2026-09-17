import { useEffect, useRef, useState, type PointerEvent } from 'react';
import type { UcUsageChartSeries } from '../../../types/api';
import { ucUsageSeriesColor, ucUsageShortDate } from './uc-usage-chart-utils';
import { cn } from '../../../lib/utils';

export interface UcUsageVisualSeries extends UcUsageChartSeries {
  color?: string;
  dashed?: boolean;
  legendDetail?: string;
  details?: Record<string, string>;
}

const compact = (value: number) =>
  new Intl.NumberFormat('en-GB', {
    notation: 'compact',
    maximumSignificantDigits: 3,
  }).format(value);

function niceCeiling(value: number): number {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / magnitude) * magnitude;
}

/**
 * Compute-style SVG with a shared scale, daily hover, null gaps and togglable
 * series. The measured viewBox keeps axis text readable at mobile widths.
 * Stacked columns use absolute counts, not a normalised percentage stack.
 */
export function UcUsageTimeChart({
  series,
  ariaLabel,
  unit,
  formatValue,
  variant = 'line',
  formatAxis = compact,
  maxValue,
}: {
  series: UcUsageVisualSeries[];
  ariaLabel: string;
  unit: string;
  formatValue: (value: number | null) => string;
  variant?: 'line' | 'stacked';
  formatAxis?: (value: number) => string;
  maxValue?: number;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [activeDate, setActiveDate] = useState<string | null>(null);
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const measure = () => {
      const measured = element.getBoundingClientRect().width;
      if (measured > 0) setWidth(measured);
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const days = [...new Set(series.flatMap((entry) => entry.points.map((p) => p.date)))].sort();
  const visible = series.filter((entry) => !hidden.has(entry.key));
  const values = new Map(
    visible.map((entry) => [
      entry.key,
      new Map(entry.points.map((point) => [point.date, point.value])),
    ])
  );
  const measured = visible.flatMap((entry) =>
    entry.points.flatMap((p) => (p.value == null ? [] : [p.value]))
  );
  const maximum =
    variant === 'stacked'
      ? days.reduce(
          (max, day) =>
            Math.max(
              max,
              visible.reduce((sum, entry) => sum + (values.get(entry.key)?.get(day) ?? 0), 0)
            ),
          0
        )
      : measured.reduce((max, value) => Math.max(max, value), 0);
  const ceiling = maxValue ?? niceCeiling(maximum * 1.08);
  const height = 220,
    left = 62,
    right = 12,
    top = 12,
    bottom = 32;
  const plotWidth = Math.max(1, width - left - right),
    plotHeight = height - top - bottom;
  const band = plotWidth / Math.max(days.length, 1);
  const x = (index: number) => left + band * (index + 0.5);
  const y = (value: number) => top + plotHeight * (1 - value / ceiling);
  const activeIndex = activeDate == null ? -1 : days.indexOf(activeDate);
  const tickCount = width < 420 ? 2 : 4;
  const ticks = [
    ...new Set(
      Array.from({ length: tickCount }, (_, i) =>
        Math.round((i * (days.length - 1)) / (tickCount - 1))
      )
    ),
  ].filter((i) => i >= 0);
  const focus = (event: PointerEvent<SVGSVGElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const index = Math.min(
      days.length - 1,
      Math.max(
        0,
        Math.floor(
          (((event.clientX - bounds.left) * width) / (bounds.width || width) - left) / band
        )
      )
    );
    setActiveDate(days[index] ?? null);
  };

  return (
    <div ref={container} className="min-w-0" data-testid="uc-usage-time-chart">
      <p className="mb-1 text-[11px] text-muted-foreground">{unit}</p>
      <div className="relative">
        {measured.length > 0 ? (
          <svg
            width="100%"
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label={ariaLabel}
            className="block overflow-visible"
            onPointerMove={focus}
            onPointerDown={focus}
            onPointerLeave={(event) => {
              if (event.pointerType !== 'touch') setActiveDate(null);
            }}
          >
            <title>{ariaLabel}</title>
            {[0, ceiling / 2, ceiling].map((value) => (
              <g key={value}>
                <line
                  x1={left}
                  x2={width - right}
                  y1={y(value)}
                  y2={y(value)}
                  stroke="currentColor"
                  className="text-border"
                />
                <text
                  x={left - 8}
                  y={y(value) + 4}
                  textAnchor="end"
                  fill="currentColor"
                  className="text-[11px] text-muted-foreground"
                >
                  {formatAxis(value)}
                </text>
              </g>
            ))}
            {ticks.map((index) => (
              <text
                key={index}
                x={x(index)}
                y={height - 9}
                textAnchor={index === 0 ? 'start' : index === days.length - 1 ? 'end' : 'middle'}
                fill="currentColor"
                className="text-[11px] text-muted-foreground"
              >
                {ucUsageShortDate(days[index])}
              </text>
            ))}
            {variant === 'stacked'
              ? days.map((day, index) => {
                  let cumulative = 0;
                  return visible.map((entry) => {
                    const value = values.get(entry.key)?.get(day);
                    if (value == null) return null;
                    cumulative += value;
                    return (
                      <rect
                        key={`${entry.key}-${day}`}
                        x={x(index) - band * 0.34}
                        y={y(cumulative)}
                        width={band * 0.68}
                        height={Math.max(0, (value / ceiling) * plotHeight)}
                        fill={entry.color ?? ucUsageSeriesColor(entry.key)}
                        opacity={activeIndex < 0 || activeIndex === index ? 1 : 0.65}
                      />
                    );
                  });
                })
              : visible.map((entry) => {
                  let connected = false;
                  const path = days
                    .map((day, index) => {
                      const value = values.get(entry.key)?.get(day);
                      if (value == null) {
                        connected = false;
                        return '';
                      }
                      const command = `${connected ? 'L' : 'M'}${x(index).toFixed(2)},${y(value).toFixed(2)}`;
                      connected = true;
                      return command;
                    })
                    .join(' ');
                  const color = entry.color ?? ucUsageSeriesColor(entry.key);
                  return (
                    <g key={entry.key} data-series-key={entry.key}>
                      <path
                        d={path}
                        stroke={color}
                        strokeWidth="2"
                        strokeLinejoin="round"
                        fill="none"
                        strokeDasharray={entry.dashed ? '5 4' : undefined}
                      />
                      {days.map((day, index) => {
                        const value = values.get(entry.key)?.get(day);
                        const isolated =
                          values.get(entry.key)?.get(days[index - 1]) == null &&
                          values.get(entry.key)?.get(days[index + 1]) == null;
                        return value == null ||
                          (days.length > 45 && !isolated && index !== activeIndex) ? null : (
                          <circle
                            key={day}
                            cx={x(index)}
                            cy={y(value)}
                            r={index === activeIndex ? 4 : 2}
                            fill={color}
                          />
                        );
                      })}
                    </g>
                  );
                })}
            {activeIndex >= 0 ? (
              <line
                x1={x(activeIndex)}
                x2={x(activeIndex)}
                y1={top}
                y2={height - bottom}
                stroke="currentColor"
                strokeDasharray="3 3"
                className="text-muted-foreground/60"
              />
            ) : null}
          </svg>
        ) : (
          <p className="flex h-[220px] items-center justify-center text-center text-xs text-muted-foreground">
            {visible.length === 0 && series.length > 0
              ? 'Select a series in the legend.'
              : 'No observations in this period.'}
          </p>
        )}
        {activeIndex >= 0 && measured.length > 0 ? (
          <div
            aria-hidden
            className={cn(
              'pointer-events-none absolute top-0 z-20 w-64 max-w-full rounded-[var(--radius)] border border-border bg-[var(--card-background)] p-3 text-xs shadow-[var(--card-shadow)]',
              activeIndex < days.length / 2 ? 'right-0' : 'left-0'
            )}
          >
            <p className="mb-2 font-semibold">{ucUsageShortDate(days[activeIndex])}</p>
            {visible.map((entry) => (
              <div key={entry.key} className="mb-1">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="min-w-0 break-words">
                    <span
                      aria-hidden
                      style={{ background: entry.color ?? ucUsageSeriesColor(entry.key) }}
                      className="mr-1 inline-block size-2 rounded-sm"
                    />
                    {entry.label}
                  </span>
                  <span className="shrink-0 font-semibold tabular-nums">
                    {formatValue(values.get(entry.key)?.get(days[activeIndex]) ?? null)}
                  </span>
                </div>
                {entry.cloud_provider ? (
                  <p className="text-muted-foreground">{entry.cloud_provider}</p>
                ) : null}
                {entry.details?.[days[activeIndex]] ? (
                  <p className="text-muted-foreground">{entry.details[days[activeIndex]]}</p>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2" aria-label="Displayed series">
        {series.map((entry) => (
          <button
            type="button"
            key={entry.key}
            aria-pressed={!hidden.has(entry.key)}
            aria-label={
              entry.cloud_provider ? `${entry.label} · ${entry.cloud_provider}` : entry.label
            }
            title={entry.label}
            className={cn(
              'inline-flex max-w-full items-center gap-1.5 text-left text-xs text-foreground',
              hidden.has(entry.key) && 'opacity-40'
            )}
            onClick={() => {
              setHidden((current) => {
                const next = new Set(current);
                if (next.has(entry.key)) next.delete(entry.key);
                else next.add(entry.key);
                return next;
              });
              setActiveDate(null);
            }}
          >
            <span
              aria-hidden
              className="inline-block w-3 shrink-0 border-t-2"
              style={{
                borderColor: entry.color ?? ucUsageSeriesColor(entry.key),
                borderStyle: entry.dashed ? 'dashed' : 'solid',
              }}
            />
            <span className="truncate">
              {entry.label.split('.').slice(-2).join('.')}
              {entry.cloud_provider ? ` · ${entry.cloud_provider}` : ''}
              {entry.legendDetail ? ` · ${entry.legendDetail}` : ''}
            </span>
          </button>
        ))}
      </div>
      <ul className="sr-only">
        {days.map((day) => (
          <li key={day}>
            {day} :{' '}
            {visible
              .map(
                (entry) =>
                  `${entry.label}${entry.cloud_provider ? ` (${entry.cloud_provider})` : ''} ${formatValue(values.get(entry.key)?.get(day) ?? null)}${entry.details?.[day] ? `, ${entry.details[day]}` : ''}`
              )
              .join(' ; ')}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The remainder is an aggregate and never sets the individual-table scale. */
export function UcUsageTableTimeChart(props: Parameters<typeof UcUsageTimeChart>[0]) {
  const individual = props.series.filter((item) => item.key !== 'other-tables');
  const other = props.series.filter((item) => item.key === 'other-tables');
  return (
    <>
      <UcUsageTimeChart {...props} series={individual} />
      {other.length > 0 && (
        <details className="mt-4 rounded-md border border-border bg-muted/20 px-3 py-2">
          <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
            Other tables combined · {other[0].entity_count ?? 'remaining'} tables · separate scale
          </summary>
          <div className="pt-4">
            <UcUsageTimeChart
              {...props}
              ariaLabel={`${props.ariaLabel} — other tables combined`}
              series={other.map((item) => ({ ...item, label: 'Other tables combined' }))}
            />
          </div>
        </details>
      )}
    </>
  );
}
