import type { ReactNode } from 'react';
import { cn } from '../../../lib/utils';
import { formatNumber } from '../../../lib/compute/format';
import { Button } from '../../ui/button';
import { Skeleton } from '../../ui/skeleton';
import { GOVERNANCE_SEVERITIES } from './uc-governance-chart-utils';

export interface GovernanceChartState<T> {
  data: T | null;
  loading: boolean;
  error: unknown;
  onRetry: () => unknown;
}

export function GovernanceChartCard({
  title,
  subtitle,
  note,
  children,
  wide = false,
}: {
  title: string;
  subtitle: string;
  note?: ReactNode;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <section
      aria-label={title}
      className={cn(
        'min-w-0 rounded-[var(--card-radius,1.375rem)] border border-border bg-card p-4 shadow-[var(--card-shadow)]',
        wide && 'lg:col-span-2'
      )}
    >
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-foreground">
        {title}
      </h3>
      <p className="mb-4 mt-1 text-xs text-muted-foreground">{subtitle}</p>
      {children}
      {note ? (
        <div className="mt-4 border-t border-border pt-3 text-xs text-muted-foreground">{note}</div>
      ) : null}
    </section>
  );
}

export function GovernanceChartStatus({
  loading,
  error,
  onRetry,
}: Omit<GovernanceChartState<unknown>, 'data'>) {
  if (loading)
    return (
      <div role="status" aria-label="Loading charts" className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-80" />
        <Skeleton className="h-80" />
      </div>
    );
  if (error)
    return (
      <div
        role="alert"
        className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--card-radius)] border border-border bg-card p-4"
      >
        <p className="text-sm">Unable to load charts for this scope.</p>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            onRetry();
          }}
        >
          Retry charts
        </Button>
      </div>
    );
  return <p className="py-6 text-center text-sm text-muted-foreground">No chart data available.</p>;
}

export function GovernanceEmpty({ children }: { children: ReactNode }) {
  return <p className="py-8 text-center text-xs text-muted-foreground">{children}</p>;
}

export function GovernanceSeverityLegend({ unknown = false }: { unknown?: boolean }) {
  return (
    <div
      className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-[11px] text-muted-foreground"
      aria-label="Severity legend"
    >
      {GOVERNANCE_SEVERITIES.filter((s) => unknown || s.key !== 'UNKNOWN').map((s) => (
        <span key={s.key} className="inline-flex items-center gap-1.5">
          <span aria-hidden className="h-2 w-2 rounded-[2px]" style={{ background: s.color }} />
          {s.label}
        </span>
      ))}
    </div>
  );
}

export interface GovernanceBarRow {
  key: string;
  label: string;
  sublabel?: string;
  total: number;
  valueLabel?: string;
  description: string;
  segments: Array<{ value: number; color: string }>;
}

/** Native row buttons provide the same selection on pointer, touch and keyboard.
 * An absolute common scale preserves magnitude; labels retain exact counts. */
export function GovernanceInteractiveBars({
  rows,
  ariaLabel,
  onSelect,
  max,
}: {
  rows: GovernanceBarRow[];
  ariaLabel: string;
  onSelect: (key: string) => void;
  max?: number;
}) {
  const ceiling = max ?? Math.max(1, ...rows.map((r) => r.total));
  return (
    <ol className="flex flex-col gap-3" aria-label={ariaLabel}>
      {rows.map((row) => (
        <li key={row.key}>
          <button
            type="button"
            onClick={() => onSelect(row.key)}
            aria-label={row.description}
            className="grid min-h-11 w-full grid-cols-[minmax(84px,1fr)_minmax(32px,1.2fr)_auto] items-center gap-3 rounded-md text-left hover:bg-muted/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
          >
            <span className="min-w-0 break-words text-xs font-medium text-foreground">
              {row.label}
              {row.sublabel ? (
                <span className="mt-0.5 block text-[11px] font-normal text-muted-foreground">
                  {row.sublabel}
                </span>
              ) : null}
            </span>
            <span className="flex h-3 min-w-0 overflow-hidden rounded-[3px] bg-muted" aria-hidden>
              {row.segments.map((segment, i) => (
                <span
                  key={i}
                  className="h-full"
                  style={{
                    width: `${Math.min(100, Math.max(0, (100 * segment.value) / Math.max(1, ceiling)))}%`,
                    background: segment.color,
                  }}
                />
              ))}
            </span>
            <span className="whitespace-nowrap text-right text-xs font-semibold tabular-nums text-foreground">
              {row.valueLabel ?? formatNumber(row.total)}
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}
