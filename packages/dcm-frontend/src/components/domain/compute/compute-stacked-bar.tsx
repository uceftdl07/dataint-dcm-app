import { useState } from 'react';
import { cn } from '../../../lib/utils';
import { ChartHoverTooltip } from './chart-hover-tooltip';

/**
 * Parts of a whole, as inline SVG — no charting library, in line with the rest of the
 * compute UI (plan decision D12).
 *
 * A single bar rather than a pie: with two classes a pie asks the reader to compare two
 * angles, which nobody does accurately, and it wastes the one comparison a share is good
 * at — reading one length against the full width.
 *
 * `valueLabel` is pre-formatted by the caller and shown in the legend, so the figures are
 * always on screen and not only under the cursor.
 */
export interface ComputeStackedSegment {
  /** Stable key of the class — also what pins its colour (see `compute-chart-colors`). */
  key: string;
  label: string;
  /** `null` is not a zero: the segment is dropped, and the legend reads its own label. */
  value: number | null;
  /** Pre-formatted figure shown in the legend (`$226,000 · 79.3 %`). */
  valueLabel: string;
  color: string;
}

const MIN_VISIBLE_SHARE_PCT = 0.6;

/**
 * Geometry rounded to two decimals before it reaches an attribute.
 *
 * `0.4 * 136` is `54.400000000000006` in binary floating point, and stacking three of
 * those puts seventeen meaningless digits in the DOM and a tenth of a pixel of drift
 * between the top of a stack and the padding it is supposed to reach.
 */
function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

export function ComputeStackedBar({
  segments,
  height = 16,
  ariaLabel,
  className,
}: {
  segments: ComputeStackedSegment[];
  height?: number;
  ariaLabel: string;
  className?: string;
}) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  if (segments.length === 0) return null;

  const values = segments.map((segment) =>
    segment.value == null || Number.isNaN(Number(segment.value)) ? null : Number(segment.value)
  );
  const total = values.reduce<number>((sum, value) => sum + Math.max(value ?? 0, 0), 0);

  // A perimeter billed nothing renders an empty track, not a division by zero — and the
  // legend still names every class, each with its own `valueLabel`.
  const spans: Array<{ x: number; width: number } | null> = [];
  let cursor = 0;
  values.forEach((value) => {
    if (value == null || total <= 0) {
      spans.push(null);
      return;
    }
    const width = round2((Math.max(value, 0) / total) * 100);
    spans.push({ x: round2(cursor), width });
    cursor = round2(cursor + width);
  });

  const active = activeIndex != null && activeIndex < segments.length ? activeIndex : null;

  return (
    <div
      className={cn('relative', className)}
      onMouseLeave={() => setActiveIndex(null)}
      data-testid="compute-stacked-bar"
    >
      <svg
        viewBox={`0 0 100 ${height}`}
        width="100%"
        height={height}
        preserveAspectRatio="none"
        role="img"
        aria-label={ariaLabel}
        className="block overflow-hidden rounded-[var(--radius)] bg-muted"
      >
        {spans.map((span, index) =>
          span == null ? null : (
            <rect
              key={`segment-${segments[index]!.key}`}
              x={span.x}
              y="0"
              // A class carrying a fraction of a percent still gets a hairline: dropping
              // it would show a bar that does not add up to the total in the legend.
              width={Math.max(span.width, span.width > 0 ? MIN_VISIBLE_SHARE_PCT : 0)}
              height={height}
              fill={segments[index]!.color}
              opacity={active == null || active === index ? '1' : '0.55'}
            />
          )
        )}

        {spans.map((span, index) =>
          span == null ? null : (
            <rect
              key={`hover-${segments[index]!.key}`}
              x={span.x}
              y="0"
              width={span.width}
              height={height}
              fill="transparent"
              aria-hidden
              onMouseEnter={() => setActiveIndex(index)}
              onMouseMove={() => setActiveIndex(index)}
            />
          )
        )}
      </svg>

      {active != null ? (
        <ChartHoverTooltip index={active} count={segments.length}>
          {`${segments[active]!.label} · ${segments[active]!.valueLabel}`}
        </ChartHoverTooltip>
      ) : null}

      {/* Legend from two classes, per the form rules — and it carries the figures, so
          nothing on this chart is reachable only with a pointer. */}
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1" data-testid="compute-stacked-bar-legend">
        {segments.map((segment) => (
          <li key={`legend-${segment.key}`} className="flex items-center gap-1.5 text-xs">
            <span
              aria-hidden
              className="size-2.5 shrink-0 rounded-[2px]"
              style={{ backgroundColor: segment.color }}
            />
            <span className="text-muted-foreground">{segment.label}</span>
            <span className="font-semibold text-foreground">{segment.valueLabel}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export interface ComputeStackedSeries {
  /** Stable key of the series — the caller pins its colour to the entity, not to a rank. */
  key: string;
  label: string;
  color: string;
}

export interface ComputeStackedColumn {
  /** Bucket start as returned by the API (`bucket`). */
  label: string;
  /** Value per series key; a missing or `null` entry is an absence, not a zero. */
  values: Record<string, number | null>;
  /** Pre-formatted readout for the whole bucket, shown on hover and to screen readers. */
  tooltip: string;
}

/** Top padding, in user units, so the tallest column is not clipped. */
const PAD_TOP = 4;

/**
 * One stacked column per bucket, on a shared absolute scale.
 *
 * Absolute and not normalised to 100 %: the question this chart answers is whether the
 * spend moves, and a percentage stack hides a day that doubles. The series order is the
 * caller's — the API returns it ordered by total cost over the whole period, so the
 * stack and the legend do not reshuffle between two refreshes.
 */
export function ComputeStackedColumns({
  series,
  columns,
  height = 140,
  ariaLabel,
  className,
}: {
  series: ComputeStackedSeries[];
  columns: ComputeStackedColumn[];
  height?: number;
  ariaLabel: string;
  className?: string;
}) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  if (columns.length === 0 || series.length === 0) return null;

  const totals = columns.map((column) =>
    series.reduce((sum, entry) => {
      const value = column.values[entry.key];
      return sum + (value == null || Number.isNaN(Number(value)) ? 0 : Math.max(Number(value), 0));
    }, 0)
  );
  const max = Math.max(...totals, 0);
  // A perimeter with no spend at all draws a baseline, not a division by zero.
  const span = max > 0 ? max : 1;
  const usable = height - PAD_TOP;
  const width = 100;
  const band = width / columns.length;
  const barWidth = round2(Math.max(band * 0.7, 0.4));

  const active = activeIndex != null && activeIndex < columns.length ? activeIndex : null;

  return (
    <div
      className={cn('relative', className)}
      onMouseLeave={() => setActiveIndex(null)}
      data-testid="compute-stacked-columns"
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height={height}
        preserveAspectRatio="none"
        role="img"
        aria-label={ariaLabel}
        className="block"
      >
        <line
          x1="0"
          y1={height}
          x2={width}
          y2={height}
          stroke="currentColor"
          strokeWidth="1"
          className="text-border"
          vectorEffect="non-scaling-stroke"
        />

        {columns.map((column, columnIndex) => {
          let stacked = 0;
          return series.map((entry) => {
            const raw = column.values[entry.key];
            const value =
              raw == null || Number.isNaN(Number(raw)) ? null : Math.max(Number(raw), 0);
            if (value == null || value === 0) return null;
            const barHeight = round2((value / span) * usable);
            const y = round2(height - stacked - barHeight);
            stacked = round2(stacked + barHeight);
            return (
              <rect
                key={`bar-${column.label}-${entry.key}`}
                x={round2(band * columnIndex + (band - barWidth) / 2)}
                y={y}
                width={barWidth}
                height={barHeight}
                fill={entry.color}
                opacity={active == null || active === columnIndex ? '1' : '0.55'}
              />
            );
          });
        })}

        {columns.map((column, columnIndex) => (
          <rect
            key={`hover-${column.label}`}
            x={round2(band * columnIndex)}
            y="0"
            width={round2(band)}
            height={height}
            fill="transparent"
            aria-hidden
            onMouseEnter={() => setActiveIndex(columnIndex)}
            onMouseMove={() => setActiveIndex(columnIndex)}
          />
        ))}
      </svg>

      {active != null ? (
        <ChartHoverTooltip index={active} count={columns.length}>
          {columns[active]!.tooltip}
        </ChartHoverTooltip>
      ) : null}

      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1" data-testid="compute-stacked-bar-legend">
        {series.map((entry) => (
          <li key={`legend-${entry.key}`} className="flex items-center gap-1.5 text-xs">
            <span
              aria-hidden
              className="size-2.5 shrink-0 rounded-[2px]"
              style={{ backgroundColor: entry.color }}
            />
            <span className="text-muted-foreground">{entry.label}</span>
          </li>
        ))}
      </ul>

      {/* The figures behind the picture: the SVG is a single `role="img"`, so per-bucket
          markup inside it is never announced. */}
      <ul className="sr-only">
        {columns.map((column) => (
          <li key={`sr-${column.label}`}>{column.tooltip}</li>
        ))}
      </ul>
    </div>
  );
}
