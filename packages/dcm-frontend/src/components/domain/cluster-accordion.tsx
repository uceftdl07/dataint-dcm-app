import { ChevronDown, Tags } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import type { DatabricksComputeMetric } from '../../lib/databricks/view-data';
import {
  formatCurrency,
  formatDateTime,
  formatWorkers,
  getClusterCreator,
  getClusterHourlyCost,
  getClusterStartTime,
  getClusterTerminatedTime,
  normalizeTags,
  pct,
} from '../../lib/databricks/view-data';
import { cn } from '../../lib/utils';
import { Badge } from '../ui/badge';
import { Skeleton } from '../ui/skeleton';
import { StatusBadge } from '../ui/status';

function DetailItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl border border-border/70 bg-background/70 px-3 py-2">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <div className="mt-1 break-words text-sm font-medium text-foreground">{value}</div>
    </div>
  );
}

function ClusterDetails({ cluster }: { cluster: DatabricksComputeMetric }) {
  const tags = normalizeTags(cluster.tags);

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <DetailItem label="Workspace" value={cluster.workspace_id ?? '—'} />
        <DetailItem label="Landing zone" value={cluster.source_lz_id} />
        <DetailItem label="Subscription/account" value={cluster.subscription_or_account_id ?? '—'} />
        <DetailItem label="Cloud" value={cluster.cloud_provider.toUpperCase()} />
        <DetailItem label="Node type" value={cluster.node_type ?? '—'} />
        <DetailItem label="Spark version" value={cluster.spark_version ?? '—'} />
        <DetailItem label="Workers" value={formatWorkers(cluster)} />
        <DetailItem label="Created by" value={getClusterCreator(cluster) ?? 'Not collected by backend'} />
        <DetailItem label="Start/created date" value={formatDateTime(getClusterStartTime(cluster))} />
        <DetailItem label="Terminated date" value={formatDateTime(getClusterTerminatedTime(cluster))} />
        <DetailItem label="Estimated hourly cost" value={formatCurrency(getClusterHourlyCost(cluster))} />
        <DetailItem label="CPU" value={pct(cluster.avg_cpu_utilization_pct ?? null)} />
        <DetailItem label="Memory" value={pct(cluster.avg_mem_utilization_pct ?? null)} />
        <DetailItem label="Collected" value={formatDateTime(cluster.collected_at)} />
      </div>
      <div className="rounded-2xl border border-border/70 bg-background/70 p-3">
        <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
          <Tags size={12} />
          Tags
        </div>
        {Object.keys(tags).length === 0 ? (
          <p className="text-sm text-muted-foreground">No tag captured for this cluster.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {Object.entries(tags).slice(0, 12).map(([key, value]) => (
              <Badge key={key} variant="outline">
                {key}: {String(value)}
              </Badge>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function ClusterAccordion({
  clusters,
  loading,
  emptyMessage = 'No cluster matches the selected filters.',
  resetKey,
}: {
  clusters: DatabricksComputeMetric[];
  loading: boolean;
  emptyMessage?: string;
  resetKey?: string | number;
}) {
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    setOpenId(null);
  }, [resetKey]);

  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-14" />
        ))}
      </div>
    );
  }

  if (clusters.length === 0) {
    return (
      <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {clusters.map((cluster) => {
        const isOpen = openId === cluster.compute_resource_id;

        return (
          <div
            key={cluster.compute_resource_id}
            className={cn(
              'overflow-hidden rounded-2xl border border-border/70 bg-background/70 transition-colors',
              isOpen && 'border-primary/35 bg-primary/[0.02]',
            )}
          >
            <button
              type="button"
              aria-expanded={isOpen}
              className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() =>
                setOpenId((current) =>
                  current === cluster.compute_resource_id ? null : cluster.compute_resource_id,
                )
              }
            >
              <ChevronDown
                size={18}
                className={cn(
                  'mt-0.5 shrink-0 text-muted-foreground transition-transform duration-200',
                  isOpen && 'rotate-180',
                )}
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="truncate font-medium text-foreground">{cluster.resource_name}</p>
                  <StatusBadge value={cluster.state} />
                </div>
                <p className="mt-1 truncate text-xs text-muted-foreground">
                  {cluster.workspace_id ?? '—'} · {cluster.source_lz_id} · {cluster.compute_resource_id}
                </p>
                <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                  <span>CPU {pct(cluster.avg_cpu_utilization_pct ?? null)}</span>
                  <span>Memory {pct(cluster.avg_mem_utilization_pct ?? null)}</span>
                  <span>{formatCurrency(getClusterHourlyCost(cluster))}/h</span>
                </div>
              </div>
            </button>
            {isOpen && (
              <div className="border-t border-border/60 px-4 py-4">
                <ClusterDetails cluster={cluster} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
