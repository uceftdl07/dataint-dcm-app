import { useEffect } from 'react';
import { X } from 'lucide-react';
import { Button } from '../../ui/button';
import { Skeleton } from '../../ui/skeleton';
import { cn } from '../../../lib/utils';
import { formatDeltaPct, formatNumber, formatUsd } from '../../../lib/compute/format';
import {
  costPerRunBucketContains,
  costPerRunBucketLabel,
  serverlessSurfaceLabel,
} from '../../../lib/compute/serverless-surfaces';
import type {
  ComputeMetricTrendGranularity,
  ComputeServerlessObjectCostTrendResponse,
  ComputeServerlessObjectDetailResponse,
} from '../../../types/api';
import { ComputeTrendChart, type ComputeTrendPoint } from './compute-trend-chart';
import {
  DrawerField as Field,
  DrawerMiniKpi as MiniKpi,
  DrawerTrendSection as TrendSection,
} from './compute-drawer-sections';

/**
 * Surfaces where `query_source` really attaches a warehouse query to the object — jobs
 * (89.9 % of attached queries) and DLT (0.7 %).
 *
 * Kept here to say what the drawer does **not** show: per-query metrics are attachable at
 * these two grains but no serverless endpoint serves them yet, and a notebook is excluded
 * outright because `notebook_id` overlaps `job_info.job_id` and does not mean
 * "interactive" (025, out of scope).
 */
const QUERY_ATTACHED_SURFACES = new Set<string>(['JOB', 'DLT_PIPELINE']);

/** The four windows gold materializes, in the order the page's chips show them. */
const WINDOW_LABELS: Record<number, string> = {
  1: 'Daily',
  7: 'Last 7d',
  30: 'Last 30d',
  90: 'Last 90d',
};

/**
 * Detail of one serverless object, at the (`serverless_surface`, `object_id`) grain.
 *
 * That pair is the identity and not a label: a handful of objects are billed under two
 * surfaces, so the same id alone would fold two different things into one drawer.
 *
 * No CPU, memory, idle or node-rightsizing section — and none pending either:
 * `node_timeline` does not exist for serverless, so those metrics have no serverless
 * grain at all. The page's blind-spot callout says so once, rather than each drawer
 * showing four columns of dashes.
 */
export function ComputeServerlessDrawer({
  open,
  onClose,
  title,
  surface,
  detail,
  detailLoading,
  detailError,
  trend,
  trendLoading,
  trendError,
  granularity,
  onGranularityChange,
  resolveWorkspaceLabel,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  surface: string | null;
  detail: ComputeServerlessObjectDetailResponse | null;
  detailLoading: boolean;
  detailError: unknown;
  trend: ComputeServerlessObjectCostTrendResponse | null;
  trendLoading: boolean;
  trendError: unknown;
  granularity: ComputeMetricTrendGranularity;
  onGranularityChange: (granularity: ComputeMetricTrendGranularity) => void;
  resolveWorkspaceLabel: (workspaceId: string) => string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const identity = detail?.object ?? null;
  const totals = detail?.totals ?? null;
  const workspaces = detail?.workspaces ?? [];
  const histogram = detail?.cost_per_run_histogram ?? [];
  const windows = detail?.windows ?? [];

  // `null` runs means the surface does not count runs at all — Genie, apps, warehouses —
  // so every per-run figure below reads "—" rather than a fabricated 0.
  const countsRuns = totals?.run_count != null;
  const showError = Boolean(detailError || trendError);

  const costPoints: ComputeTrendPoint[] = (trend?.items ?? []).map((point) => ({
    label: point.bucket,
    value: point.cost_usd,
    tooltip: `${point.bucket} · ${formatUsd(point.cost_usd)} · ${formatNumber(
      point.dbu_quantity
    )} DBU${point.run_count == null ? '' : ` · ${formatNumber(point.run_count)} runs`}`,
  }));

  const histogramPoints: ComputeTrendPoint[] = histogram.map((bucket) => ({
    label: costPerRunBucketLabel(bucket),
    value: bucket.run_count,
    tooltip: `${costPerRunBucketLabel(bucket)} · ${formatNumber(bucket.run_count)} runs`,
  }));

  const p99 = totals?.max_object_p99_usd ?? null;
  const p99Bucket = histogram.find((bucket) => costPerRunBucketContains(bucket, p99)) ?? null;

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-40 bg-black/40 transition-opacity"
        onClick={onClose}
        aria-label="Close serverless object details"
      />
      <aside
        className={cn(
          'fixed right-0 top-0 z-50 h-full w-[460px] max-w-[92vw] overflow-hidden border-l border-border bg-[var(--card-background)] shadow-[0_18px_42px_#0f172a1f] transition-transform duration-200',
          open ? 'translate-x-0' : 'translate-x-full'
        )}
        role="dialog"
        aria-modal="true"
        aria-label="Serverless object details"
      >
        <header className="flex items-start justify-between gap-3 border-b border-border px-6 py-5">
          <div className="min-w-0">
            <div className="text-[10px] font-black uppercase tracking-[1.5px] text-muted-foreground">
              {serverlessSurfaceLabel(surface ?? identity?.serverless_surface)}
            </div>
            <h3 className="mt-1 truncate text-lg font-extrabold tracking-tight text-foreground">
              {title}
            </h3>
          </div>
          <Button variant="outline" size="icon" onClick={onClose} aria-label="Close drawer">
            <X />
          </Button>
        </header>

        <div className="flex h-[calc(100%-5.5rem)] flex-col overflow-y-auto px-6 py-5 pb-28">
          {showError ? (
            <div className="mb-4 rounded-[var(--radius)] border border-danger-border bg-danger-subtle px-4 py-3 text-sm text-danger">
              Unable to load serverless object details.
            </div>
          ) : null}

          <section className="rounded-[var(--card-radius)] border border-border bg-card px-4 py-4 shadow-[var(--card-shadow)]">
            <div className="grid grid-cols-2 gap-x-4 gap-y-4">
              <Field
                label="Surface"
                value={serverlessSurfaceLabel(surface ?? identity?.serverless_surface)}
              />
              <Field label="Object ID" value={identity?.object_id ?? '—'} />
              <Field label="Object name" value={identity?.object_name ?? '—'} />
              <Field label="Billing product" value={identity?.billing_origin_product ?? '—'} />
              {/* Several workspaces for one object is normal, not a duplicate: the
                  workspace is part of the billing key. */}
              <Field label="Workspaces" value={formatNumber(identity?.workspace_count ?? null)} />
              <Field
                label="Clouds"
                value={
                  identity?.cloud_providers?.length ? identity.cloud_providers.join(', ') : '—'
                }
              />
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
                <MiniKpi label="Cost" value={formatUsd(totals?.cost_usd ?? null)} />
                <MiniKpi
                  label="Δ vs previous"
                  value={formatDeltaPct(totals?.cost_delta_pct ?? null)}
                />
                <MiniKpi label="DBU" value={formatNumber(totals?.dbu_quantity ?? null)} />
                <MiniKpi label="Runs" value={formatNumber(totals?.run_count ?? null)} />
                <MiniKpi
                  label="Mean $/run"
                  value={
                    totals?.cost_per_run_mean_usd == null
                      ? '—'
                      : formatUsd(totals.cost_per_run_mean_usd, 3)
                  }
                />
                <MiniKpi label="p99 $/run" value={p99 == null ? '—' : formatUsd(p99, 3)} />
              </>
            )}
          </section>

          {detail && !detailLoading && !countsRuns ? (
            <p className="mt-3 rounded-[var(--radius)] border border-dashed border-border/80 bg-muted/20 px-4 py-3 text-xs leading-relaxed text-muted-foreground">
              This surface does not count runs, so every per-run figure above reads “—”. Its cost is
              unaffected: it is billed, just not per execution.
            </p>
          ) : null}

          <TrendSection
            title="Cost trend (≈30 days)"
            headline={formatUsd(totals?.cost_usd ?? null)}
            granularityAriaLabel="Drawer cost trend granularity"
            granularity={granularity}
            onGranularityChange={onGranularityChange}
            points={costPoints}
            variant="bar"
            loading={trendLoading && !trend}
            emptyMessage="No trend data for this granularity"
            period={trend?.period}
          />

          {histogramPoints.length > 0 ? (
            <section className="mt-6">
              <div className="mb-2 text-[10px] font-black uppercase tracking-[1.5px] text-muted-foreground">
                Cost per run — distribution
              </div>
              <div className="rounded-[var(--card-radius)] border border-border bg-card px-4 py-3 shadow-[var(--card-shadow)]">
                <ComputeTrendChart
                  points={histogramPoints}
                  variant="bar"
                  ariaLabel="Cost per run distribution of this object"
                />
                <ul className="mt-2 space-y-0.5 text-[11px] text-muted-foreground">
                  {histogram.map((bucket) => (
                    <li
                      key={`${bucket.from_usd}-${bucket.to_usd ?? 'open'}`}
                      className="flex justify-between gap-2"
                    >
                      <span className="font-mono">
                        {costPerRunBucketLabel(bucket)}
                        {p99Bucket === bucket ? (
                          <span className="ml-1.5 font-sans font-bold text-foreground">p99</span>
                        ) : null}
                      </span>
                      <span className="tabular-nums">{formatNumber(bucket.run_count)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </section>
          ) : null}

          {windows.length > 0 ? (
            <section className="mt-6">
              <div className="mb-2 text-[10px] font-black uppercase tracking-[1.5px] text-muted-foreground">
                Rolling windows
              </div>
              <div className="overflow-hidden rounded-[var(--card-radius)] border border-border bg-card shadow-[var(--card-shadow)]">
                <table className="w-full text-xs">
                  <caption className="sr-only">
                    Cost of this object over each materialized rolling window
                  </caption>
                  <thead>
                    <tr className="border-b border-border/70 text-left text-[10px] font-black uppercase tracking-[1.1px] text-muted-foreground">
                      <th scope="col" className="px-3 py-2">
                        Window
                      </th>
                      <th scope="col" className="px-3 py-2 text-right">
                        Cost
                      </th>
                      <th scope="col" className="px-3 py-2 text-right">
                        DBU
                      </th>
                      <th scope="col" className="px-3 py-2 text-right">
                        Runs
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {windows.map((row) => (
                      <tr key={row.window_days} className="border-b border-border/40 last:border-0">
                        <th scope="row" className="px-3 py-2 text-left font-semibold">
                          {WINDOW_LABELS[row.window_days] ?? `${row.window_days}d`}
                        </th>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {formatUsd(row.cost_usd)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {formatNumber(row.dbu_quantity)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {formatNumber(row.run_count)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          {workspaces.length > 0 ? (
            <section className="mt-6">
              <div className="mb-2 text-[10px] font-black uppercase tracking-[1.5px] text-muted-foreground">
                Per workspace
              </div>
              <ul className="space-y-2">
                {workspaces.map((row) => (
                  <li
                    key={`${row.cloud_provider}-${row.workspace_id}`}
                    className="rounded-[var(--radius)] border border-border bg-card px-3 py-2.5 shadow-[var(--card-shadow)]"
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-sm font-semibold text-foreground">
                        {resolveWorkspaceLabel(row.workspace_id)}
                      </span>
                      <span className="shrink-0 text-sm font-bold tabular-nums">
                        {formatUsd(row.cost_usd)}
                      </span>
                    </div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">
                      {row.cloud_provider} · {formatNumber(row.dbu_quantity)} DBU ·{' '}
                      {row.run_count == null ? '—' : `${formatNumber(row.run_count)} runs`}
                      {row.as_of_date ? ` · as of ${row.as_of_date}` : ''}
                    </div>
                    {/* The name can differ between workspaces; showing the row's own name
                        avoids passing off the heaviest workspace's name as the object's. */}
                    {row.object_name && row.object_name !== identity?.object_name ? (
                      <div className="mt-0.5 truncate text-[11px] italic text-muted-foreground">
                        {row.object_name}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {surface && QUERY_ATTACHED_SURFACES.has(surface) ? (
            <p className="mt-6 rounded-[var(--radius)] border border-dashed border-border/80 bg-muted/20 px-4 py-3 text-xs leading-relaxed text-muted-foreground">
              Warehouse queries do attach to this grain through <code>query_source</code> — jobs
              carry 89.9 % of attached queries, DLT 0.7 % — but no serverless endpoint serves
              per-query metrics yet, so none are shown here rather than shown empty.
            </p>
          ) : null}
        </div>
      </aside>
    </>
  );
}
