import { useState } from 'react';
import { cn } from '../../../lib/utils';
import { ChartHoverTooltip } from './chart-hover-tooltip';

/** Top padding, in user units, so the tallest point is not clipped. */
const PAD_TOP = 4;

export interface ComputeTrendPoint {
  /** Bucket start, as returned by the API (`bucket`). */
  label: string;
  /** `null` renders a gap — a bucket without measure is not a zero. */
  value: number | null;
  /** Pre-formatted text shown on hover for this point. */
  tooltip: string;
}

/**
 * Bar and line trend chart drawn as inline SVG — no charting library, in line
 * with the rest of the compute UI.
 *
 * Each bucket carries a full-height transparent band so every point stays
 * hoverable, including a zero-height bar and a `null` gap. Hovering reveals the
 * bucket's own figures: a `<title>` would only do so after the browser's own
 * delay, which is too slow to read a series by sweeping across it.
 */
export function ComputeTrendChart({
  points,
  variant = 'line',
  width = 320,
  height = 88,
  color = 'var(--tdf-blue)',
  dashedFromIndex,
  ariaLabel,
  className,
}: {
  points: ComputeTrendPoint[];
  variant?: 'bar' | 'line';
  width?: number;
  height?: number;
  color?: string;
  /** Index du premier point projeté : à partir de là, le trait passe en pointillés. */
  dashedFromIndex?: number;
  ariaLabel: string;
  className?: string;
}) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  if (points.length === 0) return null;

  const values = points.map((point) =>
    point.value == null || Number.isNaN(Number(point.value)) ? null : Number(point.value)
  );
  const measured = values.filter((value): value is number => value != null);
  const max = measured.length > 0 ? Math.max(...measured) : 0;
  // A flat all-zero series must render a flat baseline, not a division by zero.
  const span = max > 0 ? max : 1;
  const usable = height - PAD_TOP;
  const band = width / points.length;
  const barWidth = Math.max(band * 0.62, 1);
  const dotRadius = points.length > 45 ? 1 : 2;

  const yFor = (value: number) => height - (value / span) * usable;
  const xFor = (index: number) => (points.length === 1 ? width / 2 : band * index + band / 2);

  // A `null` bucket breaks the line instead of being joined through.
  const segments: Array<{ points: string; dashed: boolean }> = [];
  // Le point de bascule appartient aux deux traits, sinon la courbe s'interrompt
  // entre le dernier réalisé et le premier projeté.
  const boundary = dashedFromIndex == null ? null : Math.max(1, dashedFromIndex);
  let segment: Array<{ index: number; coords: string }> = [];
  const flush = () => {
    if (segment.length < 2) {
      segment = [];
      return;
    }
    if (boundary == null) {
      segments.push({ points: segment.map((entry) => entry.coords).join(' '), dashed: false });
      segment = [];
      return;
    }
    const solid = segment.filter((entry) => entry.index <= boundary - 1);
    const dashed = segment.filter((entry) => entry.index >= boundary - 1);
    if (solid.length > 1) {
      segments.push({ points: solid.map((entry) => entry.coords).join(' '), dashed: false });
    }
    if (dashed.length > 1) {
      segments.push({ points: dashed.map((entry) => entry.coords).join(' '), dashed: true });
    }
    segment = [];
  };
  values.forEach((value, index) => {
    if (value == null) {
      flush();
      return;
    }
    segment.push({ index, coords: `${xFor(index).toFixed(2)},${yFor(value).toFixed(2)}` });
  });
  flush();

  // Clamped in case a series shrinks while the cursor is still over the chart.
  const active = activeIndex != null && activeIndex < points.length ? activeIndex : null;

  return (
    <div
      className={cn('relative', className)}
      onMouseLeave={() => setActiveIndex(null)}
      data-testid="compute-trend-chart"
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height={height}
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
        />

        {active != null ? (
          <line
            x1={xFor(active)}
            y1="0"
            x2={xFor(active)}
            y2={height}
            stroke="currentColor"
            strokeWidth="1"
            strokeDasharray="3 3"
            className="text-muted-foreground/60"
          />
        ) : null}

        {variant === 'bar'
          ? values.map((value, index) =>
              value == null ? null : (
                <rect
                  key={`bar-${points[index]!.label}`}
                  x={xFor(index) - barWidth / 2}
                  y={yFor(value)}
                  width={barWidth}
                  height={Math.max(height - yFor(value), 0)}
                  fill={color}
                  opacity={active === index ? '1' : '0.85'}
                />
              )
            )
          : segments.map((entry) => (
              <polyline
                key={`${entry.dashed ? 'f' : 'o'}-${entry.points.slice(0, 24)}`}
                points={entry.points}
                fill="none"
                stroke={color}
                strokeWidth="2"
                strokeLinejoin="round"
                strokeDasharray={entry.dashed ? '4 3' : undefined}
                opacity={entry.dashed ? 0.75 : 1}
              />
            ))}

        {variant === 'line'
          ? values.map((value, index) =>
              value == null ? null : (
                <circle
                  key={`dot-${points[index]!.label}`}
                  cx={xFor(index)}
                  cy={yFor(value)}
                  r={active === index ? dotRadius + 2 : dotRadius}
                  fill={color}
                  opacity={boundary != null && index >= boundary ? 0.75 : 1}
                />
              )
            )
          : null}

        {points.map((point, index) => (
          <rect
            key={`hover-${point.label}`}
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

      {active != null ? (
        <ChartHoverTooltip index={active} count={points.length}>
          {points[active]!.tooltip}
        </ChartHoverTooltip>
      ) : null}

      {/* The figures behind the picture, for anyone not using a pointer: the SVG is
          a single `role="img"`, so per-bucket markup inside it is never announced. */}
      <ul className="sr-only">
        {points.map((point) => (
          <li key={`sr-${point.label}`}>{point.tooltip}</li>
        ))}
      </ul>
    </div>
  );
}
