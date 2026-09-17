import { useEffect, useId, useRef, useState, type MouseEvent, type PointerEvent } from 'react';
import type { UcUsageGovernancePoint } from '../../../types/api';
import { formatNumber } from '../../../lib/compute/format';
import { Button } from '../../ui/button';
import { governanceIdentity } from './uc-governance-chart-utils';
import { GovernanceEmpty } from './uc-governance-chart-frame';

function ceiling(value: number): number {
  const magnitude = 10 ** Math.floor(Math.log10(Math.max(1, value)));
  return Math.ceil(value / magnitude) * magnitude;
}

/** Bounded, observed table points. A native picker also exposes overlapping points
 * and the drill-down to keyboard users. Unknown reads are handled outside the plot. */
export function UcGovernanceScatter({
  points,
  onSelect,
}: {
  points: UcUsageGovernancePoint[];
  onSelect: (point: UcUsageGovernancePoint) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const pickerId = useId();
  const [width, setWidth] = useState(480);
  const [activeKey, setActiveKey] = useState('');
  useEffect(() => {
    const target = container.current;
    if (!target) return;
    const measure = () => {
      const value = target.getBoundingClientRect().width;
      if (value > 0) setWidth(value);
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(target);
    return () => observer.disconnect();
  }, []);

  const known = points.filter(
    (
      p
    ): p is UcUsageGovernancePoint & {
      days_since_last_read: number;
      downstream_fanout: number;
    } =>
      p.days_since_last_read != null &&
      p.downstream_fanout != null &&
      Number.isFinite(p.days_since_last_read) &&
      Number.isFinite(p.downstream_fanout) &&
      p.days_since_last_read >= 0 &&
      p.downstream_fanout >= 0
  );
  const identity = (p: UcUsageGovernancePoint) =>
    governanceIdentity(p.cloud_provider, p.table_full_name);
  const active = known.find((p) => identity(p) === activeKey);
  const height = 250,
    left = 54,
    right = 14,
    top = 28,
    bottom = 47;
  const plotWidth = Math.max(1, width - left - right - 16);
  const plotHeight = height - top - bottom - 16;
  const maxX = ceiling(Math.max(90, ...known.map((p) => p.days_since_last_read)) * 1.08);
  const maxY = ceiling(Math.max(5, ...known.map((p) => p.downstream_fanout)) * 1.12);
  const x = (days: number) => left + 8 + (plotWidth * days) / maxX;
  const y = (fanout: number) => top + 8 + plotHeight * (1 - fanout / maxY);
  const tickCount = width < 380 ? 3 : 4;
  const ticks = (max: number) => [
    ...new Set(
      Array.from({ length: tickCount }, (_, i) => Math.round((max * i) / (tickCount - 1)))
    ),
  ];
  const nearest = (event: PointerEvent<SVGSVGElement> | MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - rect.left) * width) / (rect.width || width);
    const py = ((event.clientY - rect.top) * height) / (rect.height || height);
    if (px < left || px > width - right || py < top || py > height - bottom) return undefined;
    return known.reduce<(typeof known)[number] | undefined>(
      (best, p) =>
        !best ||
        Math.hypot(x(p.days_since_last_read) - px, y(p.downstream_fanout) - py) <
          Math.hypot(x(best.days_since_last_read) - px, y(best.downstream_fanout) - py)
          ? p
          : best,
      undefined
    );
  };

  return (
    <div ref={container} className="min-w-0" data-testid="uc-governance-scatter">
      {known.length ? (
        <>
          <svg
            width="100%"
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label="Days since last read and observed downstream objects by table"
            className="block overflow-hidden text-[11px] text-muted-foreground"
            onPointerMove={(event) => {
              const point = nearest(event);
              if (point) setActiveKey(identity(point));
            }}
            onClick={(event) => {
              const point = nearest(event);
              if (point) {
                setActiveKey(identity(point));
                onSelect(point);
              }
            }}
          >
            <title>Inactivity and observed dependencies</title>
            <desc>
              Squares mark unused critical tables; triangles mark stale tables still being read. The
              selector below the chart provides access to every point, including overlapping points.
            </desc>
            <rect
              x={x(90)}
              y={top}
              width={Math.max(0, width - right - x(90))}
              height={Math.max(0, y(5) - top)}
              fill="var(--danger-subtle)"
            />
            {ticks(maxY).map((value) => (
              <g key={value}>
                <line
                  x1={left}
                  x2={width - right}
                  y1={y(value)}
                  y2={y(value)}
                  stroke="var(--border)"
                />
                <text x={left - 8} y={y(value) + 4} textAnchor="end" fill="currentColor">
                  {formatNumber(value)}
                </text>
              </g>
            ))}
            {ticks(maxX).map((value) => (
              <text
                key={value}
                x={x(value)}
                y={height - bottom + 19}
                textAnchor="middle"
                fill="currentColor"
              >
                {formatNumber(value)}
              </text>
            ))}
            <line
              x1={left}
              x2={width - right}
              y1={height - bottom}
              y2={height - bottom}
              stroke="var(--border)"
            />
            <line
              x1={x(90)}
              x2={x(90)}
              y1={top}
              y2={height - bottom}
              stroke="var(--danger)"
              strokeOpacity={0.6}
              strokeDasharray="3 4"
            />
            <line
              x1={left}
              x2={width - right}
              y1={y(5)}
              y2={y(5)}
              stroke="var(--muted-foreground)"
              strokeOpacity={0.5}
              strokeDasharray="3 4"
            />
            <text x={x(90) + 4} y={top + 12} fill="currentColor">
              90 days
            </text>
            <text x={left} y={13} fill="var(--foreground)" data-axis="y">
              Observed downstream objects
            </text>
            <text
              x={(left + width - right) / 2}
              y={height - 4}
              textAnchor="middle"
              fill="var(--foreground)"
              data-axis="x"
            >
              Last read (days elapsed)
            </text>
            {known.map((p) => {
              const cx = x(p.days_since_last_read),
                cy = y(p.downstream_fanout);
              return (
                <g
                  key={identity(p)}
                  data-table={p.table_full_name}
                  data-cloud={p.cloud_provider ?? ''}
                  opacity={0.85}
                >
                  {p.is_unused && p.is_critical ? (
                    <rect x={cx - 4} y={cy - 4} width={8} height={8} fill="var(--danger)" />
                  ) : p.is_stale_but_consumed ? (
                    <polygon
                      points={`${cx},${cy - 5} ${cx - 5},${cy + 4} ${cx + 5},${cy + 4}`}
                      fill="var(--warning)"
                    />
                  ) : (
                    <circle cx={cx} cy={cy} r={3.5} fill="var(--tdf-blue)" />
                  )}
                </g>
              );
            })}
            {active ? (
              <circle
                cx={x(active.days_since_last_read)}
                cy={y(active.downstream_fanout)}
                r={9}
                fill="none"
                stroke="var(--foreground)"
                strokeWidth={1.2}
              />
            ) : null}
          </svg>
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
            <span>
              <span aria-hidden className="text-danger">
                ■
              </span>{' '}
              Unused and critical
            </span>
            <span>
              <span aria-hidden className="text-warning">
                ▲
              </span>{' '}
              Stale but read
            </span>
            <span>
              <span aria-hidden className="text-[var(--tdf-blue)]">
                ●
              </span>{' '}
              Other tables
            </span>
          </div>
          <label htmlFor={pickerId} className="mt-4 block text-xs font-medium">
            Inspect a table in the chart
          </label>
          <select
            id={pickerId}
            className="mt-1 h-9 w-full min-w-0 rounded-md border border-border bg-card px-2 text-xs"
            value={active ? activeKey : ''}
            onChange={(event) => setActiveKey(event.target.value)}
          >
            <option value="">Choose a table…</option>
            {known.map((p) => (
              <option key={identity(p)} value={identity(p)}>
                {p.table_full_name}
                {p.cloud_provider ? ` · ${p.cloud_provider}` : ''}
              </option>
            ))}
          </select>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-muted-foreground">
              {active
                ? `${formatNumber(active.days_since_last_read)} days since last read · ${formatNumber(active.downstream_fanout)} downstream objects`
                : 'Each point represents a table in its cloud.'}
            </p>
            <Button
              variant="ghost"
              size="sm"
              disabled={!active}
              onClick={() => {
                if (active) onSelect(active);
              }}
            >
              View in registry
            </Button>
          </div>
        </>
      ) : (
        <GovernanceEmpty>
          No tables with both an observed read and downstream links.
        </GovernanceEmpty>
      )}
    </div>
  );
}
