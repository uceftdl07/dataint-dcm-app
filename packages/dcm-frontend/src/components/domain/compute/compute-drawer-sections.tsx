import type { ReactNode } from 'react';
import { Skeleton } from '../../ui/skeleton';
import { cn } from '../../../lib/utils';
import type { ComputeMetricTrendGranularity } from '../../../types/api';
import { ComputeTrendChart, type ComputeTrendPoint } from './compute-trend-chart';

/**
 * Visual primitives shared by the compute detail drawers. Extracted when the job
 * and DLT pipeline drawers arrived (024 T006): `Field`, `MiniKpi` and the whole
 * trend block were about to be copied a third and fourth time.
 *
 * Primitives only — **not** a generic drawer. Each grain keeps its own component:
 * the sections it shows, its labels and its links are what differ between an
 * all-purpose cluster, a job, a pipeline and a SQL warehouse (024 R9).
 */

/** Label above a single-line value, truncated with the full value as `title`. */
export function DrawerField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] font-black uppercase tracking-[1.2px] text-muted-foreground">
        {label}
      </div>
      <div className="truncate text-sm font-semibold text-foreground" title={value}>
        {value}
      </div>
    </div>
  );
}

/**
 * Headline metric card. `valueNode` carries a badge or any richer value; `value`
 * is the plain-text form — pass the formatter's output, so an unmeasured metric
 * shows "—" rather than a fabricated `0 %`.
 */
export function DrawerMiniKpi({
  label,
  value,
  valueNode,
}: {
  label: string;
  value?: string;
  valueNode?: ReactNode;
}) {
  return (
    <div className="rounded-[var(--radius)] border border-border bg-card px-3 py-2.5 shadow-[var(--card-shadow)]">
      <div className="text-[10px] font-black uppercase tracking-[1.1px] text-muted-foreground">
        {label}
      </div>
      <div className="mt-1">
        {valueNode ?? <span className="text-base font-extrabold text-foreground">{value}</span>}
      </div>
    </div>
  );
}

function GranularityPills({
  ariaLabel,
  value,
  onChange,
}: {
  ariaLabel: string;
  value: ComputeMetricTrendGranularity;
  onChange: (granularity: ComputeMetricTrendGranularity) => void;
}) {
  return (
    <div
      className="flex shrink-0 items-center gap-0.5 rounded-full border border-border bg-muted/30 p-0.5"
      role="group"
      aria-label={ariaLabel}
    >
      {(['day', 'week', 'month'] as const).map((granularity) => (
        <button
          key={granularity}
          type="button"
          onClick={() => onChange(granularity)}
          className={cn(
            'min-w-[3.25rem] rounded-full px-3 py-1.5 text-xs font-bold capitalize transition-colors',
            value === granularity
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-card hover:text-foreground'
          )}
          aria-pressed={value === granularity}
        >
          {granularity}
        </button>
      ))}
    </div>
  );
}

function pointCountLabel(count: number): string {
  if (count === 0) return '—';
  return `${count.toLocaleString('en-US')} point${count === 1 ? '' : 's'}`;
}

function renderTrendBody({
  points,
  variant,
  loading,
  emptyMessage,
  title,
}: {
  points: ComputeTrendPoint[];
  variant: 'bar' | 'line';
  loading: boolean;
  emptyMessage: string;
  title: string;
}) {
  if (loading && points.length === 0) return <Skeleton className="h-[88px] w-full" />;
  if (points.length > 0) {
    return <ComputeTrendChart points={points} variant={variant} ariaLabel={title} />;
  }
  return (
    <div className="flex h-[88px] flex-col items-center justify-center gap-1 rounded-[var(--radius)] border border-dashed border-border/80 bg-muted/20 text-xs text-muted-foreground">
      <span>{emptyMessage}</span>
      <span className="font-mono text-[10px]">Try day, week, or month</span>
    </div>
  );
}

/**
 * One trend block: headline, its own day/week/month switch, the chart, and the
 * period the series actually covers.
 */
export function DrawerTrendSection({
  title,
  headline,
  granularityAriaLabel,
  granularity,
  onGranularityChange,
  points,
  variant,
  loading,
  emptyMessage,
  period,
}: {
  title: string;
  headline: ReactNode;
  granularityAriaLabel: string;
  granularity: ComputeMetricTrendGranularity;
  onGranularityChange: (granularity: ComputeMetricTrendGranularity) => void;
  points: ComputeTrendPoint[];
  variant: 'bar' | 'line';
  loading: boolean;
  emptyMessage: string;
  period: { from: string; to: string } | null | undefined;
}) {
  return (
    <section className="mt-6">
      <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="text-[10px] font-black uppercase tracking-[1.5px] text-muted-foreground">
            {title}
          </div>
          <div className="mt-1 text-lg font-extrabold tracking-tight text-foreground">
            {headline}
          </div>
        </div>
        <GranularityPills
          ariaLabel={granularityAriaLabel}
          value={granularity}
          onChange={onGranularityChange}
        />
      </div>

      <div className="rounded-[var(--card-radius)] border border-border bg-card px-4 py-3 shadow-[var(--card-shadow)]">
        {renderTrendBody({ points, variant, loading, emptyMessage, title })}
        <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
          <span>{pointCountLabel(points.length)}</span>
          <span className="font-mono">{period?.from ? `${period.from} → ${period.to}` : ''}</span>
        </div>
      </div>
    </section>
  );
}
