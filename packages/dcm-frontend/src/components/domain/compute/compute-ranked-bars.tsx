import { useState } from 'react';
import { cn } from '../../../lib/utils';
import {
  RAMP_CEILING_STANDALONE_PCT,
  sequentialFill,
  sequentialIntensity,
} from './compute-chart-colors';
import { ChartHoverTooltip } from './chart-hover-tooltip';

export interface ComputeRankedItem {
  /** Stable key of the ranked entity (surface, notebook, principal…). */
  key: string;
  label: string;
  /** Second line under the label — a workspace, an id, a share. Optional. */
  sublabel?: string;
  /** `null` is not a zero: the row keeps its place and draws no bar. */
  value: number | null;
  /** Pre-formatted figure shown at the end of the row (`$24,543`). */
  valueLabel: string;
  /** Pre-formatted readout shown on hover, richer than `valueLabel`. */
  tooltip: string;
}

/**
 * Sorted horizontal bars, one sequential hue — the shape a ranking of magnitudes takes.
 *
 * Deliberately **no per-item colour prop**: a ranking of eleven surfaces drawn in eleven
 * categorical colours reads as eleven kinds of thing, and the reader starts looking for a
 * meaning in the hues that is not there. Intensity carries the magnitude, and it is the
 * same magnitude the figure at the end of the row states.
 *
 * The bars are inline SVG (plan decision D12, no charting library), the labels and the
 * figures are real DOM text: they have to truncate, wrap and be announced, which SVG
 * text does badly.
 */
export function ComputeRankedBars({
  items,
  ariaLabel,
  className,
  labelWidthClassName = 'w-40',
}: {
  items: ComputeRankedItem[];
  ariaLabel: string;
  className?: string;
  /** Width of the label column, so several rankings can be visually aligned. */
  labelWidthClassName?: string;
}) {
  const [activeKey, setActiveKey] = useState<string | null>(null);

  if (items.length === 0) return null;

  const measured = (value: number | null) =>
    value == null || Number.isNaN(Number(value)) ? null : Number(value);

  // Sorted here rather than trusted from the caller: the chart claims to be a ranking, so
  // it must be one even when the server sorted the page on another column.
  const ranked = [...items].sort((left, right) => {
    const a = measured(left.value);
    const b = measured(right.value);
    if (a == null && b == null) return 0;
    if (a == null) return 1;
    if (b == null) return -1;
    return b - a;
  });

  const values = ranked.map((item) => measured(item.value)).filter((v): v is number => v != null);
  const max = values.length > 0 ? Math.max(...values, 0) : 0;
  const span = max > 0 ? max : 1;

  return (
    <ol className={cn('flex flex-col gap-2', className)} aria-label={ariaLabel}>
      {ranked.map((item) => {
        const value = measured(item.value);
        const ratio = value == null ? null : Math.max(value, 0) / span;

        return (
          <li
            key={item.key}
            className="relative flex items-center gap-3"
            onMouseEnter={() => setActiveKey(item.key)}
            onMouseMove={() => setActiveKey(item.key)}
            onMouseLeave={() => setActiveKey(null)}
            data-testid="compute-ranked-bars-row"
          >
            <div className={cn('min-w-0 shrink-0', labelWidthClassName)}>
              <div className="truncate text-xs font-semibold text-foreground" title={item.label}>
                {item.label}
              </div>
              {item.sublabel ? (
                <div className="truncate text-[11px] text-muted-foreground">{item.sublabel}</div>
              ) : null}
            </div>

            <svg
              viewBox="0 0 100 10"
              width="100%"
              height="10"
              preserveAspectRatio="none"
              aria-hidden
              className="block min-w-0 flex-1 overflow-hidden rounded-[2px] bg-muted"
            >
              {ratio == null ? null : (
                <rect
                  x="0"
                  y="0"
                  width={Math.max(Math.round(ratio * 10_000) / 100, ratio > 0 ? 0.5 : 0)}
                  height="10"
                  fill={sequentialFill(ratio, RAMP_CEILING_STANDALONE_PCT)}
                  data-intensity={sequentialIntensity(ratio, RAMP_CEILING_STANDALONE_PCT)}
                />
              )}
            </svg>

            <div className="shrink-0 text-right text-xs font-semibold tabular-nums text-foreground">
              {item.valueLabel}
            </div>

            {activeKey === item.key ? (
              // One readout per row: the row is its own coordinate space, so the tooltip
              // sits centred above it rather than above a shared horizontal axis.
              <ChartHoverTooltip index={0} count={1}>
                {item.tooltip}
              </ChartHoverTooltip>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
