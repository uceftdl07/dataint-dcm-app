import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { X } from 'lucide-react';
import { Button } from '../../ui/button';
import { Badge } from '../../ui/badge';
import { Skeleton } from '../../ui/skeleton';
import { cn } from '../../../lib/utils';
import {
  autoscalingLabel,
  formatDeltaPct,
  formatHours,
  formatNumber,
  formatPct,
  formatUsd,
  formatWorkerBounds,
  utilizationLabel,
} from '../../../lib/compute/format';
import { utilizationBadgeVariant } from '../../../lib/compute/badges';
import type {
  ComputeJobCostTrendResponse,
  ComputeJobDetailResponse,
  ComputeJobUptimeTrendResponse,
  ComputeMetricTrendGranularity,
} from '../../../types/api';
import { costTrendPoints } from '../../../lib/compute/trend-points';
import { type ComputeTrendPoint } from './compute-trend-chart';
import {
  DrawerField as Field,
  DrawerMiniKpi as MiniKpi,
  DrawerTrendSection as TrendSection,
} from './compute-drawer-sections';

/**
 * Detail of one job: what the all-purpose drawer shows, at the stable grain.
 *
 * Two deliberate differences with {@link ComputeClusterDrawer}:
 * - **no governance block** — tags, DBR version and oversizing are cluster-level
 *   and stay on the all-purpose grain (024 C2); the payload has no such key;
 * - the second trend is the **cumulated uptime** of the job's runs, not a lifetime:
 *   a job cluster is destroyed at the end of every run.
 *
 * `efficiency` is `null` for a job billed with no `node_timeline` row. Every metric
 * then reads "—" and the drawer stays usable: the cost above is real, and a `0 %`
 * would invent a measure.
 */
export function ComputeJobDrawer({
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
  uptimeTrend,
  uptimeTrendLoading,
  uptimeTrendError,
  uptimeGranularity,
  onUptimeGranularityChange,
  workspaceLabel,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  detail: ComputeJobDetailResponse | null;
  detailLoading: boolean;
  detailError: unknown;
  trend: ComputeJobCostTrendResponse | null;
  trendLoading: boolean;
  trendError: unknown;
  granularity: ComputeMetricTrendGranularity;
  onGranularityChange: (g: ComputeMetricTrendGranularity) => void;
  uptimeTrend: ComputeJobUptimeTrendResponse | null;
  uptimeTrendLoading: boolean;
  uptimeTrendError: unknown;
  uptimeGranularity: ComputeMetricTrendGranularity;
  onUptimeGranularityChange: (g: ComputeMetricTrendGranularity) => void;
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
  const efficiency = detail?.efficiency ?? null;

  const costValue = formatUsd(cost?.cost_usd ?? null);
  const costDelta = formatDeltaPct(cost?.cost_delta_pct ?? null);
  const costDeltaPct = cost?.cost_delta_pct ?? null;
  const utilizationStatus = efficiency?.utilization_status ?? null;

  const showError = Boolean(detailError || trendError || uptimeTrendError);
  // A job billed but never measured — shown, never hidden: the most expensive such
  // grain measured in dev was billed $941 over 30 days (024 SC-005).
  const unmeasured = Boolean(detail && !detailLoading && !efficiency);

  const costPoints = costTrendPoints(trend?.items);

  const uptimePoints: ComputeTrendPoint[] = (uptimeTrend?.items ?? []).map((point) => ({
    label: point.bucket,
    value: point.uptime_hours,
    tooltip: `${point.bucket} · ${formatHours(point.uptime_hours)} · idle ${formatPct(
      point.idle_pct
    )}`,
  }));

  const uptimeHours = efficiency?.uptime_hours ?? null;
  const uptimeDeltaPct = efficiency?.uptime_hours_delta_pct ?? null;

  return (
    <>
      <button
        type="button"
        className={cn(
          'fixed inset-0 z-40 bg-black/40 transition-opacity',
          open ? 'opacity-100' : 'opacity-0'
        )}
        onClick={onClose}
        aria-label="Close job details"
      />
      <aside
        className={cn(
          'fixed right-0 top-0 z-50 h-full w-[460px] max-w-[92vw] overflow-hidden border-l border-border bg-[var(--card-background)] shadow-[0_18px_42px_#0f172a1f] transition-transform duration-200',
          open ? 'translate-x-0' : 'translate-x-full'
        )}
        role="dialog"
        aria-modal="true"
        aria-label="Job details"
      >
        <header className="flex items-start justify-between gap-3 border-b border-border px-6 py-5">
          <div className="min-w-0">
            <div className="text-[10px] font-black uppercase tracking-[1.5px] text-muted-foreground">
              Job
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
              Unable to load job details.
            </div>
          ) : null}

          <section className="rounded-[var(--card-radius)] border border-border bg-card px-4 py-4 shadow-[var(--card-shadow)]">
            <div className="grid grid-cols-2 gap-x-4 gap-y-4">
              <Field label="Cloud" value={detail?.cloud_provider ?? '—'} />
              <Field label="Workspace" value={workspaceLabel ?? detail?.workspace_id ?? '—'} />
              <Field label="Job ID" value={detail?.job_id ?? '—'} />
              <Field label="Job name" value={cost?.job_name ?? efficiency?.job_name ?? '—'} />
              <Field label="Runs (clusters)" value={formatNumber(cost?.cluster_count ?? null)} />
              <Field label="DBU" value={formatNumber(cost?.dbu_quantity ?? null)} />
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
                <MiniKpi label="CPU p95" value={formatPct(efficiency?.cpu_util_p95_pct ?? null)} />
                <MiniKpi label="Mem p95" value={formatPct(efficiency?.mem_util_p95_pct ?? null)} />
                <MiniKpi label="Idle" value={formatPct(efficiency?.idle_pct ?? null)} />
                <MiniKpi
                  label="Status"
                  valueNode={
                    <Badge variant={utilizationBadgeVariant(utilizationStatus)} className="mt-0.5">
                      {utilizationLabel(utilizationStatus)}
                    </Badge>
                  }
                />
              </>
            )}
          </section>

          {unmeasured ? (
            <p className="mt-3 rounded-[var(--radius)] border border-dashed border-border/80 bg-muted/20 px-4 py-3 text-xs leading-relaxed text-muted-foreground">
              No utilization measured over this window: this job ran on compute with no node
              timeline. Its cost above is unaffected.
            </p>
          ) : null}

          <section className="mt-5 rounded-[var(--card-radius)] border border-border bg-card px-4 py-4 shadow-[var(--card-shadow)]">
            <div className="mb-3 text-[10px] font-black uppercase tracking-[1.5px] text-muted-foreground">
              Technical specs
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-4">
              <Field label="Driver node" value={efficiency?.driver_node_type ?? '—'} />
              <Field label="Worker node" value={efficiency?.worker_node_type ?? '—'} />
              <div className="min-w-0">
                <div className="text-[10px] font-black uppercase tracking-[1.2px] text-muted-foreground">
                  Autoscaling
                </div>
                <div className="mt-1">
                  {efficiency?.autoscale_enabled == null ? (
                    <span className="text-sm font-semibold text-muted-foreground">—</span>
                  ) : (
                    <Badge variant={efficiency.autoscale_enabled ? 'success' : 'outline'}>
                      {autoscalingLabel(efficiency.autoscale_enabled)}
                    </Badge>
                  )}
                </div>
              </div>
              <Field label="Workers" value={efficiency ? formatWorkerBounds(efficiency) : '—'} />
              <Field label="Recommended node" value={efficiency?.recommended_node_type ?? '—'} />
              <Field
                label="Est. savings"
                value={
                  efficiency?.estimated_savings_usd == null
                    ? '—'
                    : formatUsd(efficiency.estimated_savings_usd)
                }
              />
            </div>
          </section>

          <TrendSection
            title="Cost trend (≈90 days)"
            headline={
              <>
                {costValue}{' '}
                <span
                  className={cn(
                    'text-xs font-bold',
                    costDeltaPct == null
                      ? 'text-muted-foreground'
                      : costDeltaPct > 0
                        ? 'text-danger'
                        : costDeltaPct < 0
                          ? 'text-success'
                          : 'text-muted-foreground'
                  )}
                >
                  ({costDelta})
                </span>
              </>
            }
            granularityAriaLabel="Drawer cost trend granularity"
            granularity={granularity}
            onGranularityChange={onGranularityChange}
            points={costPoints}
            variant="bar"
            loading={trendLoading && !trend}
            emptyMessage="No trend data for this granularity"
            period={trend?.period}
          />

          <TrendSection
            title="Uptime trend (≈90 days)"
            headline={
              <>
                {formatHours(uptimeHours)}{' '}
                <span
                  className={cn(
                    'text-xs font-bold',
                    uptimeDeltaPct == null ? 'text-muted-foreground' : 'text-foreground'
                  )}
                >
                  ({formatDeltaPct(uptimeDeltaPct)})
                </span>
              </>
            }
            granularityAriaLabel="Drawer uptime trend granularity"
            granularity={uptimeGranularity}
            onGranularityChange={onUptimeGranularityChange}
            points={uptimePoints}
            variant="line"
            loading={uptimeTrendLoading && !uptimeTrend}
            emptyMessage="No uptime data for this granularity"
            period={uptimeTrend?.period}
          />

          <section className="mt-6 pb-6">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[1.5px] text-muted-foreground">
              Recommendations
            </div>
            <div className="rounded-[var(--radius)] border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
              View open recommendations for this job on the dedicated page.
              <div className="mt-3">
                <Link
                  to={`/databricks/compute/recommendations?object_type=JOB&search=${encodeURIComponent(detail?.job_id ?? '')}`}
                  className="inline-flex items-center font-bold text-primary underline-offset-4 hover:underline"
                >
                  Go to Recommendations &amp; Forecast →
                </Link>
              </div>
            </div>
          </section>
        </div>
      </aside>
    </>
  );
}
