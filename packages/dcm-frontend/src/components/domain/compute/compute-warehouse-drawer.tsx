import { useEffect } from 'react';
import { ExternalLink, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '../../ui/button';
import { Skeleton } from '../../ui/skeleton';
import { cn } from '../../../lib/utils';
import { formatDeltaPct, formatNumber, formatPct, formatUsd } from '../../../lib/compute/format';
import type {
  ComputeMetricTrendGranularity,
  ComputeWarehouseCostTrendResponse,
  ComputeWarehouseDetailResponse,
} from '../../../types/api';
import { costTrendPoints } from '../../../lib/compute/trend-points';
import { ComputeTrendChart } from './compute-trend-chart';

function Field({ label, value }: { label: string; value: string }) {
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

function MiniKpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius)] border border-border bg-card px-3 py-2">
      <div className="text-[10px] font-black uppercase tracking-[1.1px] text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5 text-base font-extrabold text-foreground">{value}</div>
    </div>
  );
}

export function ComputeWarehouseDrawer({
  open,
  onClose,
  title,
  detail,
  detailLoading,
  detailError,
  trend,
  trendLoading,
  trendError,
  granularity,
  onGranularityChange,
  workspaceLabel,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  detail: ComputeWarehouseDetailResponse | null;
  detailLoading: boolean;
  detailError: unknown;
  trend: ComputeWarehouseCostTrendResponse | null;
  trendLoading: boolean;
  trendError: unknown;
  granularity: ComputeMetricTrendGranularity;
  onGranularityChange: (g: ComputeMetricTrendGranularity) => void;
  workspaceLabel?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const cost = detail?.cost ?? null;
  const perf = detail?.query_performance ?? null;
  const costValue = formatUsd(cost?.cost_usd ?? null);
  const costDelta = formatDeltaPct(cost?.cost_delta_pct ?? null);
  const showError = Boolean(detailError || trendError);

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-40 bg-black/40 transition-opacity"
        onClick={onClose}
        aria-label="Close warehouse details"
      />
      <aside
        className="fixed right-0 top-0 z-50 h-full w-[460px] max-w-[92vw] overflow-hidden border-l border-border bg-[var(--card-background)] shadow-[0_18px_42px_#0f172a1f]"
        role="dialog"
        aria-modal="true"
        aria-label="SQL Warehouse details"
      >
        <header className="flex items-start justify-between gap-3 border-b border-border px-6 py-5">
          <div className="min-w-0">
            <div className="text-[10px] font-black uppercase tracking-[1.5px] text-muted-foreground">
              SQL Warehouse
            </div>
            <h3 className="mt-1 truncate text-lg font-extrabold tracking-tight text-foreground">
              {title}
            </h3>
          </div>
          <Button variant="outline" size="icon" onClick={onClose} aria-label="Close drawer">
            <X />
          </Button>
        </header>

        <div className="flex h-full flex-col overflow-y-auto px-6 py-5 pb-24">
          {showError ? (
            <div className="mb-4 rounded-[var(--radius)] border border-danger-border bg-danger-subtle px-4 py-3 text-sm text-danger">
              Unable to load warehouse details.
            </div>
          ) : null}

          <section className="rounded-[var(--radius)] border border-border bg-card px-4 py-4">
            <div className="grid grid-cols-2 gap-x-4 gap-y-4">
              <Field label="Cloud" value={detail?.cloud_provider ?? '—'} />
              <Field label="Workspace" value={workspaceLabel ?? detail?.workspace_id ?? '—'} />
              <Field label="Warehouse ID" value={detail?.warehouse_id ?? '—'} />
              <Field label="Size" value={cost?.warehouse_size ?? '—'} />
            </div>
          </section>

          <section className="mt-5 grid grid-cols-2 gap-3">
            {detailLoading && !detail ? (
              <>
                <Skeleton className="h-[62px]" />
                <Skeleton className="h-[62px]" />
                <Skeleton className="h-[62px]" />
                <Skeleton className="h-[62px]" />
              </>
            ) : (
              <>
                <MiniKpi
                  label="Queries"
                  value={formatNumber(perf?.query_count ?? cost?.query_count ?? null)}
                />
                <MiniKpi
                  label="Failure rate"
                  value={formatPct(perf?.failure_rate_pct ?? null, 1)}
                />
                <MiniKpi
                  label="Latency p95"
                  value={formatDurationMs(perf?.latency_p95_ms ?? null)}
                />
                <MiniKpi label="Cache hit" value={formatPct(perf?.cache_hit_pct ?? null, 1)} />
              </>
            )}
          </section>

          <section className="mt-6">
            <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
              <div>
                <div className="text-[10px] font-black uppercase tracking-[1.5px] text-muted-foreground">
                  Cost trend (≈90 days)
                </div>
                <div className="mt-1 text-lg font-extrabold tracking-tight text-foreground">
                  {costValue}{' '}
                  <span className="text-xs font-bold text-muted-foreground">({costDelta})</span>
                </div>
              </div>
              <div
                className="flex shrink-0 items-center gap-0.5 rounded-full border border-border bg-muted/30 p-0.5"
                role="group"
                aria-label="Drawer cost trend granularity"
              >
                {(['day', 'week', 'month'] as const).map((g) => (
                  <button
                    key={g}
                    type="button"
                    onClick={() => onGranularityChange(g)}
                    className={cn(
                      'min-w-[3.25rem] rounded-full px-3 py-1.5 text-xs font-bold capitalize transition-colors',
                      granularity === g
                        ? 'bg-primary text-primary-foreground shadow-sm'
                        : 'text-muted-foreground hover:bg-card hover:text-foreground'
                    )}
                    aria-pressed={granularity === g}
                  >
                    {g}
                  </button>
                ))}
              </div>
            </div>
            <div className="rounded-[var(--card-radius)] border border-border bg-card px-4 py-3 shadow-[var(--card-shadow)]">
              {trendLoading && !trend ? (
                <Skeleton className="h-[88px] w-full" />
              ) : trend?.items?.length ? (
                <ComputeTrendChart
                  points={costTrendPoints(trend.items)}
                  variant="bar"
                  ariaLabel="Warehouse cost trend"
                />
              ) : (
                <div className="flex h-[88px] flex-col items-center justify-center gap-1 rounded-[var(--radius)] border border-dashed border-border/80 bg-muted/20 text-xs text-muted-foreground">
                  <span>No trend data for this granularity</span>
                  <span className="font-mono text-[10px]">Try day, week, or month</span>
                </div>
              )}
            </div>
          </section>

          <section className="mt-6">
            <Link
              to={`/databricks/compute/recommendations?object_type=WAREHOUSE&search=${encodeURIComponent(cost?.warehouse_id ?? '')}`}
              className="inline-flex items-center gap-2 text-sm font-semibold text-primary hover:underline"
            >
              View in Recommendations & Forecast
              <ExternalLink className="size-4" />
            </Link>
          </section>
        </div>
      </aside>
    </>
  );
}

function formatDurationMs(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  if (value >= 60_000) return `${(value / 60_000).toFixed(1)} min`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)} s`;
  return `${Math.round(value)} ms`;
}
