import { useState } from 'react';
import { cn } from '../../../lib/utils';
import { formatPct } from '../../../lib/compute/format';
import { SEQUENTIAL_TEXT_CLASS, sequentialFill, sequentialIntensity } from './compute-chart-colors';
import { ChartHoverTooltip } from './chart-hover-tooltip';
import { ComputeInfoTip } from './compute-info-tip';

export interface ComputeCoverageColumn {
  /** Key looked up in each row's `cells`. */
  key: string;
  label: string;
  /** Shown through `ComputeInfoTip`, like a table column description. */
  description?: string;
}

export interface ComputeCoverageCell {
  /** Coverage in percent of dollars. `null` = not measurable, rendered `—`, never `0 %`. */
  pct: number | null;
  /** Pre-formatted readout shown on hover — the dollars behind the percentage. */
  tooltip: string;
}

export interface ComputeCoverageRow {
  key: string;
  label: string;
  /** Second line under the label — the row's weight in dollars, typically. */
  sublabel?: string;
  cells: Record<string, ComputeCoverageCell>;
}

/**
 * Coverage matrix: rows × dimensions, each cell a share of dollars on one sequential hue.
 *
 * A real `<table>` rather than an SVG grid, unlike the two other new charts: every axis
 * here is a label and every cell prints its own value, so the picture is a table that
 * happens to be coloured. Colour is the redundant channel — the figure is always written
 * in the cell, so a cell is never readable by hue alone.
 *
 * The ramp runs the same direction everywhere: darker = better covered. A blank is `—`,
 * because `0 %` would claim the dimension was measured and found empty.
 */
export function ComputeCoverageHeatmap({
  rows,
  columns,
  ariaLabel,
  rowHeader = 'Surface',
  className,
}: {
  rows: ComputeCoverageRow[];
  columns: ComputeCoverageColumn[];
  ariaLabel: string;
  /** Header of the first column, naming the grain of a row. */
  rowHeader?: string;
  className?: string;
}) {
  const [active, setActive] = useState<string | null>(null);

  if (rows.length === 0 || columns.length === 0) return null;

  return (
    <div className={cn('overflow-x-auto', className)} data-testid="compute-coverage-heatmap">
      <table className="w-full border-separate border-spacing-1 text-xs">
        <caption className="sr-only">{ariaLabel}</caption>
        <thead>
          <tr>
            <th
              scope="col"
              className="w-40 px-1 pb-1 text-left text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
            >
              {rowHeader}
            </th>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className="px-1 pb-1 text-center text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
              >
                <span className="inline-flex items-center gap-1">
                  {column.label}
                  {column.description ? <ComputeInfoTip description={column.description} /> : null}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <th scope="row" className="max-w-40 px-1 text-left align-middle font-normal">
                <div className="truncate font-semibold text-foreground" title={row.label}>
                  {row.label}
                </div>
                {row.sublabel ? (
                  <div className="truncate text-[11px] text-muted-foreground">{row.sublabel}</div>
                ) : null}
              </th>

              {columns.map((column, columnIndex) => {
                const cell = row.cells[column.key];
                const pct =
                  cell?.pct == null || Number.isNaN(Number(cell.pct)) ? null : Number(cell.pct);
                const ratio = pct == null ? null : Math.min(Math.max(pct, 0), 100) / 100;
                const cellKey = `${row.key}:${column.key}`;

                return (
                  <td
                    key={column.key}
                    className="relative p-0"
                    onMouseEnter={() => setActive(cellKey)}
                    onMouseMove={() => setActive(cellKey)}
                    onMouseLeave={() => setActive(null)}
                  >
                    <div
                      className={cn(
                        'rounded-[var(--radius)] px-2 py-1.5 text-center font-semibold tabular-nums',
                        ratio == null ? 'bg-muted text-muted-foreground' : SEQUENTIAL_TEXT_CLASS
                      )}
                      style={ratio == null ? undefined : { backgroundColor: sequentialFill(ratio) }}
                      data-intensity={ratio == null ? undefined : sequentialIntensity(ratio)}
                    >
                      {formatPct(pct, 1)}
                    </div>

                    {active === cellKey && cell ? (
                      <ChartHoverTooltip index={columnIndex} count={columns.length}>
                        {cell.tooltip}
                      </ChartHoverTooltip>
                    ) : null}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
