import { useState } from 'react';
import type { UcUsageActivityMatrix } from '../../../types/api';
import { formatNumber } from '../../../lib/compute/format';
import { sequentialFill } from '../compute/compute-chart-colors';
import { ucUsageShortDate } from './uc-usage-chart-utils';

/** Count intensity, not a coverage percentage. Missing cells are hatched. */
export function UcUsageActivityHeatmap({ activity }: { activity: UcUsageActivityMatrix }) {
  const [scale, setScale] = useState<'row' | 'shared'>('row');
  const [detail, setDetail] = useState<string | null>(null);
  const max = activity.rows.reduce(
    (maximum, row) =>
      row.cells.reduce((current, cell) => Math.max(current, cell.value ?? 0), maximum),
    0
  );
  if (activity.rows.length === 0)
    return (
      <p className="py-12 text-center text-xs text-muted-foreground">
        No activity observed in this period.
      </p>
    );

  return (
    <div>
      <label className="mb-3 flex items-center justify-end gap-2 text-xs text-muted-foreground">
        Colour scale
        <select
          aria-label="Heatmap colour scale"
          className="h-8 rounded border border-border bg-card px-2"
          value={scale}
          onChange={(event) => setScale(event.target.value as 'row' | 'shared')}
        >
          <option value="row">Per table</option>
          <option value="shared">Shared across tables</option>
        </select>
      </label>
      <div className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-1 text-xs">
          <caption className="sr-only">
            Read accesses by table and {activity.grain === 'week' ? 'week' : 'day'}.{' '}
            {scale === 'row'
              ? 'Each row uses its own peak as the colour maximum.'
              : 'All rows share the same maximum.'}{' '}
            A dash means no observation.
          </caption>
          <thead>
            <tr>
              <th
                scope="col"
                className="sticky left-0 z-10 bg-[var(--card-background)] text-left text-muted-foreground"
              >
                Table
              </th>
              {activity.columns.map((column) => (
                <th
                  key={column.start}
                  scope="col"
                  className="min-w-9 whitespace-nowrap px-1 pb-2 text-center text-[11px] font-normal text-muted-foreground"
                >
                  {ucUsageShortDate(column.start)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {activity.rows.map((row) => {
              const measured = row.cells.flatMap((cell) =>
                cell.value == null ? [] : [cell.value]
              );
              const rowPeak = measured.length ? Math.max(...measured) : null;
              const scaleMax = scale === 'row' ? (rowPeak ?? 0) : max;
              return (
                <tr key={row.key}>
                  <th
                    scope="row"
                    className="sticky left-0 z-10 bg-[var(--card-background)] pr-3 text-left font-medium"
                  >
                    <span className="block w-40 truncate" title={row.label}>
                      {row.label.split('.').slice(-2).join('.')}
                    </span>
                    <span className="text-[11px] font-normal text-muted-foreground">
                      {row.cloud_provider} · Peak {formatNumber(rowPeak)}
                    </span>
                  </th>
                  {row.cells.map((cell, index) => {
                    const column = activity.columns[index];
                    const label = `${row.label}${row.cloud_provider ? ` (${row.cloud_provider})` : ''} · ${column.start}${column.start !== column.end ? ` → ${column.end}` : ''} · ${cell.value == null ? 'No observation' : `${formatNumber(cell.value)} reads`}${activity.grain === 'week' ? ` · ${cell.observed_days}/${cell.expected_days} observed days` : ''}`;
                    return (
                      <td key={column.start} className="p-0">
                        <button
                          type="button"
                          aria-label={label}
                          title={label}
                          data-scale-max={scaleMax}
                          className="min-h-8 w-full rounded-sm px-1 text-[11px] tabular-nums text-foreground [@media(pointer:coarse)]:min-h-11"
                          style={
                            cell.value == null
                              ? {
                                  background:
                                    'repeating-linear-gradient(135deg, transparent, transparent 4px, var(--border) 4px, var(--border) 5px)',
                                }
                              : {
                                  background:
                                    cell.value === 0
                                      ? 'var(--muted)'
                                      : sequentialFill(scaleMax > 0 ? cell.value / scaleMax : 0),
                                }
                          }
                          onPointerEnter={() => setDetail(label)}
                          onFocus={() => setDetail(label)}
                          onClick={() => setDetail(label)}
                        >
                          {cell.value == null
                            ? '—'
                            : cell.value === 0
                              ? '0'
                              : new Intl.NumberFormat('en-GB', {
                                  notation: 'compact',
                                  maximumFractionDigits: 1,
                                }).format(cell.value)}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        <span>Low</span>
        <span
          aria-hidden
          className="h-2 w-20 rounded-sm"
          style={{
            background: `linear-gradient(to right, ${sequentialFill(0)}, ${sequentialFill(1)})`,
          }}
        />
        <span>
          {scale === 'row' ? 'Each table’s peak' : `Shared peak · ${formatNumber(max)} reads`}
        </span>
        <span>0: measured zero · —: no observation</span>
      </div>
      {detail ? <p className="mt-2 break-words text-xs text-foreground">{detail}</p> : null}
    </div>
  );
}
