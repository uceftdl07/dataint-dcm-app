import { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';
import { Button } from '../../ui/button';
import { Skeleton } from '../../ui/skeleton';
import { DrawerMiniKpi } from '../compute/compute-drawer-sections';
import { formatNumber, formatUsd } from '../../../lib/compute/format';
import { formatBytes } from '../../../lib/uc-usage/labels';
import type {
  UcUsageDailyMetrics,
  UcUsageEntityDetail,
  UcUsageEntitySelection,
} from '../../../types/api';
import { UcUsageDeletedBadge } from './uc-usage-deleted-badge';
import { UcUsageTimeChart } from './uc-usage-time-chart';

export function UcUsageDetailDrawer({
  selection,
  data,
  loading,
  error,
  onClose,
  onRetry,
}: {
  selection: UcUsageEntitySelection;
  data: UcUsageEntityDetail | null;
  loading: boolean;
  error: unknown;
  onClose: () => void;
  onRetry: () => unknown;
}) {
  const ref = useRef<HTMLElement>(null);
  const heading = useId();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    ref.current?.querySelector('button')?.focus();
    return () => {
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  const series = (
    metric: keyof Omit<UcUsageDailyMetrics, 'date'>,
    label: string,
    color?: string
  ) => ({
    key: metric,
    label,
    color,
    points: (data?.daily ?? []).map((point) => ({ date: point.date, value: point[metric] })),
  });
  const total = data?.summary;
  return (
    <>
      <button
        type="button"
        aria-label="Close usage details"
        className="fixed inset-0 z-40 bg-black/40"
        onClick={onClose}
      />
      <aside
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={heading}
        className="fixed right-0 top-0 z-50 flex h-full w-[580px] max-w-[96vw] flex-col border-l border-border bg-[var(--card-background)] shadow-[0_18px_42px_#0f172a1f]"
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            onClose();
          }
          if (event.key === 'Tab') {
            const elements = ref.current?.querySelectorAll<HTMLElement>(
              'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), [tabindex="0"]'
            );
            if (!elements?.length) return;
            const first = elements[0],
              last = elements[elements.length - 1];
            if (event.shiftKey && document.activeElement === first) {
              event.preventDefault();
              last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
              event.preventDefault();
              first.focus();
            }
          }
        }}
      >
        <header className="flex items-start justify-between gap-3 border-b border-border px-6 py-5">
          <div className="min-w-0">
            <p className="text-[10px] font-black uppercase tracking-[1.5px] text-muted-foreground">
              {selection.kind === 'table' ? 'Table details' : 'Consumer details'}
            </p>
            <h2 id={heading} className="mt-1 break-words text-lg font-semibold">
              {selection.label}
            </h2>
            <p className="mt-1 break-all text-xs text-muted-foreground">{selection.id}</p>
            {/*
              Hors du titre : celui-ci nomme la boîte de dialogue, et l'historique
              d'une table supprimée s'ouvre normalement (spec 027).
            */}
            {selection.kind === 'table' && data?.is_deleted ? (
              <p className="mt-2">
                <UcUsageDeletedBadge row={data} />
              </p>
            ) : null}
            {data && (
              <p className="mt-2 text-xs text-muted-foreground">
                {data.period.start} → {data.period.end} · Applied scope · AWS and Azure combined
              </p>
            )}
          </div>
          <Button variant="outline" size="icon" aria-label="Close drawer" onClick={onClose}>
            <X />
          </Button>
        </header>
        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-5 pb-24">
          {loading ? (
            <div role="status" aria-label="Loading usage details">
              <Skeleton className="h-32" />
              <Skeleton className="mt-5 h-56" />
            </div>
          ) : error ? (
            <div role="alert" className="space-y-3 text-sm">
              <p>Unable to load usage details.</p>
              <Button variant="outline" onClick={() => onRetry()}>
                Retry details
              </Button>
            </div>
          ) : !total?.observed_rows ? (
            <p className="text-sm text-muted-foreground">
              No observations for this entity in the applied scope and period.
            </p>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3">
                <DrawerMiniKpi label="Read accesses" value={formatNumber(total.request_count)} />
                <DrawerMiniKpi label="Estimated cost" value={formatUsd(total.estimated_cost_usd)} />
                <DrawerMiniKpi label="Bytes read" value={formatBytes(total.data_read_bytes)} />
                <DrawerMiniKpi
                  label="Bytes written"
                  value={formatBytes(total.data_written_bytes)}
                />
                <DrawerMiniKpi label="Rows written" value={formatNumber(total.rows_written, 1)} />
                <DrawerMiniKpi
                  label={selection.kind === 'table' ? 'Consumers' : 'Tables'}
                  value={formatNumber(total.counterpart_count)}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                {total.active_days} active days · {total.write_days} days with observed writes.
                Write volumes may be allocated across multiple targets; they do not count write
                operations.
              </p>
              <section>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide">
                  Read activity over time
                </h3>
                <UcUsageTimeChart
                  ariaLabel="Entity daily read activity"
                  series={[series('request_count', 'Read accesses')]}
                  unit="Read accesses / day"
                  formatValue={formatNumber}
                />
              </section>
              <section>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide">
                  Read and write volumes
                </h3>
                <UcUsageTimeChart
                  ariaLabel="Entity read and write volumes"
                  series={[
                    series('data_read_bytes', 'Bytes read', 'var(--tdf-blue)'),
                    series('data_written_bytes', 'Bytes written', 'var(--tdf-teal)'),
                  ]}
                  unit="Bytes / day"
                  formatValue={formatBytes}
                  formatAxis={formatBytes}
                />
              </section>
              <section>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide">
                  Estimated cost over time
                </h3>
                <UcUsageTimeChart
                  ariaLabel="Entity daily estimated cost"
                  series={[series('estimated_cost_usd', 'Estimated cost', 'var(--tdf-purple)')]}
                  unit="USD / day"
                  formatValue={formatUsd}
                />
              </section>
              <section>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide">
                  {selection.kind === 'table' ? 'Top consumers' : 'Top tables'}
                </h3>
                <p className="mb-3 text-xs text-muted-foreground">
                  {data?.counterparts.length} of {total.counterpart_count} · Ranked by read
                  accesses, then written volume.
                </p>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="py-2">
                          {selection.kind === 'table' ? 'Consumer' : 'Table'}
                        </th>
                        <th className="px-2 text-right">Reads</th>
                        <th className="px-2 text-right">Written</th>
                        <th className="text-right">Cost</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data?.counterparts.map((row) => (
                        <tr key={row.id} className="border-b border-border/50">
                          <th className="max-w-52 break-words py-3 font-medium" title={row.id}>
                            {row.label}
                          </th>
                          <td className="px-2 text-right tabular-nums">
                            {formatNumber(row.request_count)}
                          </td>
                          <td className="px-2 text-right tabular-nums">
                            {formatBytes(row.data_written_bytes)}
                          </td>
                          <td className="text-right tabular-nums">
                            {formatUsd(row.estimated_cost_usd)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
        </div>
      </aside>
    </>
  );
}
