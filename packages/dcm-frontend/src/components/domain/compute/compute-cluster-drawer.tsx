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
  formatPct,
  formatUsd,
  formatWorkerBounds,
  clusterTypeLabel,
  severityLabel,
  utilizationLabel,
} from '../../../lib/compute/format';
import {
  clusterTypeBadgeVariant,
  severityBadgeVariant,
  utilizationBadgeVariant,
} from '../../../lib/compute/badges';
import type {
  ComputeClusterCostTrendResponse,
  ComputeClusterDetailResponse,
  ComputeClusterLifetimeTrendResponse,
  ComputeMetricTrendGranularity,
} from '../../../types/api';
import { costTrendPoints } from '../../../lib/compute/trend-points';
import { type ComputeTrendPoint } from './compute-trend-chart';
import {
  DrawerField as Field,
  DrawerMiniKpi as MiniKpi,
  DrawerTrendSection as TrendSection,
} from './compute-drawer-sections';

function TagFieldValue({ ok }: { ok: boolean | null | undefined }) {
  if (ok == null) return <span className="text-sm font-semibold text-muted-foreground">—</span>;
  return (
    <Badge variant={ok ? 'success' : 'warning'} className="mt-0.5">
      {ok ? 'OK' : 'Missing'}
    </Badge>
  );
}

export function ComputeClusterDrawer({
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
  lifetimeTrend,
  lifetimeTrendLoading,
  lifetimeTrendError,
  lifetimeGranularity,
  onLifetimeGranularityChange,
  workspaceLabel,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  detail: ComputeClusterDetailResponse | null;
  detailLoading: boolean;
  detailError: unknown;
  trend: ComputeClusterCostTrendResponse | null;
  trendLoading: boolean;
  trendError: unknown;
  granularity: ComputeMetricTrendGranularity;
  onGranularityChange: (g: ComputeMetricTrendGranularity) => void;
  lifetimeTrend: ComputeClusterLifetimeTrendResponse | null;
  lifetimeTrendLoading: boolean;
  lifetimeTrendError: unknown;
  lifetimeGranularity: ComputeMetricTrendGranularity;
  onLifetimeGranularityChange: (g: ComputeMetricTrendGranularity) => void;
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

  const identity = detail?.cost ?? null;
  const efficiency = detail?.efficiency ?? null;
  const governance = detail?.governance ?? null;

  const costValue = formatUsd(identity?.cost_usd ?? null);
  const costDelta = formatDeltaPct(identity?.cost_delta_pct ?? null);
  const costDeltaPct = identity?.cost_delta_pct ?? null;
  const utilizationStatus = efficiency?.utilization_status ?? null;
  const utilizationIsZombie = (utilizationStatus || '').toUpperCase() === 'ZOMBIE';
  const clusterType =
    identity?.cluster_type ?? efficiency?.cluster_type ?? governance?.cluster_type ?? null;
  const clusterTypeText = clusterTypeLabel(clusterType);

  const showError = Boolean(detailError || trendError || lifetimeTrendError);

  const costPoints = costTrendPoints(trend?.items);

  const lifetimePoints: ComputeTrendPoint[] = (lifetimeTrend?.items ?? []).map((point) => ({
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
        aria-label="Close cluster details"
      />
      <aside
        className={cn(
          'fixed right-0 top-0 z-50 h-full w-[460px] max-w-[92vw] overflow-hidden border-l border-border bg-[var(--card-background)] shadow-[0_18px_42px_#0f172a1f] transition-transform duration-200',
          open ? 'translate-x-0' : 'translate-x-full'
        )}
        role="dialog"
        aria-modal="true"
        aria-label="Cluster details"
      >
        <header className="flex items-start justify-between gap-3 border-b border-border px-6 py-5">
          <div className="min-w-0">
            <div className="text-[10px] font-black uppercase tracking-[1.5px] text-muted-foreground">
              Cluster
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
              Unable to load cluster details.
            </div>
          ) : null}

          <section className="rounded-[var(--card-radius)] border border-border bg-card px-4 py-4 shadow-[var(--card-shadow)]">
            <div className="grid grid-cols-2 gap-x-4 gap-y-4">
              <Field label="Cloud" value={detail?.cloud_provider ?? '—'} />
              <Field label="Workspace" value={workspaceLabel ?? detail?.workspace_id ?? '—'} />
              <div className="min-w-0">
                <div className="text-[10px] font-black uppercase tracking-[1.2px] text-muted-foreground">
                  Cluster type
                </div>
                <div className="mt-1">
                  {clusterTypeText === '—' ? (
                    <span className="text-sm font-semibold text-muted-foreground">—</span>
                  ) : (
                    <Badge variant={clusterTypeBadgeVariant(clusterType)}>{clusterTypeText}</Badge>
                  )}
                </div>
              </div>
              <Field label="Cluster ID" value={detail?.cluster_id ?? '—'} />
              <Field label="SKU group" value={identity?.sku_group ?? '—'} />
              <Field label="Owner" value={identity?.owner ?? '—'} />
              <Field label="Cost center" value={identity?.cost_center ?? '—'} />
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
                    <Badge
                      variant={utilizationBadgeVariant(utilizationStatus, utilizationIsZombie)}
                      className="mt-0.5"
                    >
                      {utilizationLabel(utilizationStatus)}
                    </Badge>
                  }
                />
              </>
            )}
          </section>

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
            title="Lifetime trend (≈90 days)"
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
            granularityAriaLabel="Drawer lifetime trend granularity"
            granularity={lifetimeGranularity}
            onGranularityChange={onLifetimeGranularityChange}
            points={lifetimePoints}
            variant="line"
            loading={lifetimeTrendLoading && !lifetimeTrend}
            emptyMessage="No lifetime data for this granularity"
            period={lifetimeTrend?.period}
          />

          <section className="mt-6">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="text-[10px] font-black uppercase tracking-[1.5px] text-muted-foreground">
                Governance
              </div>
              {governance?.severity ? (
                <Badge variant={severityBadgeVariant(governance.severity)}>
                  {severityLabel(governance.severity)}
                </Badge>
              ) : null}
            </div>
            <div className="rounded-[var(--card-radius)] border border-border bg-card px-4 py-3 text-sm shadow-[var(--card-shadow)]">
              <div className="grid grid-cols-2 gap-3">
                <div className="min-w-0">
                  <div className="text-[10px] font-black uppercase tracking-[1.2px] text-muted-foreground">
                    Owner tag
                  </div>
                  <TagFieldValue
                    ok={
                      governance?.has_owner_tag === false
                        ? false
                        : governance?.has_owner_tag === true
                          ? true
                          : null
                    }
                  />
                </div>
                <div className="min-w-0">
                  <div className="text-[10px] font-black uppercase tracking-[1.2px] text-muted-foreground">
                    Cost-center tag
                  </div>
                  <TagFieldValue
                    ok={
                      governance?.has_cost_center_tag === false
                        ? false
                        : governance?.has_cost_center_tag === true
                          ? true
                          : null
                    }
                  />
                </div>
                <Field label="DBR" value={governance?.dbr_version ?? '—'} />
                <Field
                  label="DBR LTS"
                  value={
                    governance?.dbr_is_lts_current == null
                      ? '—'
                      : governance.dbr_is_lts_current
                        ? 'Current'
                        : 'Obsolete'
                  }
                />
              </div>

              <div className="mt-3 border-t border-border/70 pt-3 text-xs leading-relaxed text-muted-foreground">
                <span className="font-semibold text-foreground">Recommended action:</span>{' '}
                {governance?.recommended_action || '—'}
              </div>
            </div>
          </section>

          <section className="mt-6 pb-6">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[1.5px] text-muted-foreground">
              Recommendations
            </div>
            <div className="rounded-[var(--radius)] border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
              View open recommendations for this cluster on the dedicated page.
              <div className="mt-3">
                <Link
                  to={`/databricks/compute/recommendations?object_type=CLUSTER&search=${encodeURIComponent(identity?.cluster_id ?? '')}`}
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
