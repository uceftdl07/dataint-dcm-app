import { ChevronDown, Server, Users } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { cn } from '../../lib/utils';
import type { ComputeMetric } from '../../types/api';
import { Badge } from '../ui/badge';
import { Skeleton } from '../ui/skeleton';

function DetailItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl border border-border/70 bg-background/70 px-3 py-2">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <div className="mt-1 break-words text-sm font-medium text-foreground">{value}</div>
    </div>
  );
}

function stateBadge(state: string) {
  if (state === 'running') return <Badge variant="success">Running</Badge>;
  if (state === 'error') return <Badge variant="destructive">Error</Badge>;
  if (state === 'terminated') return <Badge variant="secondary">Terminated</Badge>;
  return <Badge variant="warning">Unknown</Badge>;
}

function formatPct(value: number | null | undefined) {
  return value == null ? '—' : `${Math.round(value)}%`;
}

export function ComputeAccordion({
  computes,
  loading,
  emptyMessage = 'No compute matches the selected filters.',
  resetKey,
}: {
  computes: ComputeMetric[];
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

  if (computes.length === 0) {
    return <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">{emptyMessage}</div>;
  }

  return (
    <div className="space-y-2">
      {computes.map((compute) => {
        const isOpen = openId === compute.compute_resource_id;
        return (
          <div
            key={compute.compute_resource_id}
            className={cn(
              'overflow-hidden rounded-2xl border border-border/70 bg-background/70 transition-colors',
              isOpen && 'border-primary/35 bg-primary/[0.02]',
            )}
          >
            <button
              type="button"
              aria-expanded={isOpen}
              className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setOpenId((current) => (current === compute.compute_resource_id ? null : compute.compute_resource_id))}
            >
              <ChevronDown size={18} className={cn('mt-0.5 shrink-0 text-muted-foreground transition-transform duration-200', isOpen && 'rotate-180')} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Server size={14} className="text-muted-foreground" />
                  <p className="truncate font-medium">{compute.resource_name}</p>
                  {stateBadge(compute.state)}
                </div>
                <p className="mt-1 truncate text-xs text-muted-foreground">
                  {compute.cloud_provider.toUpperCase()} · {compute.workspace_id ?? '—'} · {compute.compute_resource_id}
                </p>
                <p className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1"><Users size={12} />{compute.num_workers ?? '—'} workers</span>
                  <span>CPU {formatPct(compute.avg_cpu_utilization_pct)}</span>
                  <span>Mem {formatPct(compute.avg_mem_utilization_pct)}</span>
                </p>
              </div>
            </button>
            {isOpen && (
              <div className="border-t border-border/60 px-4 py-4">
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  <DetailItem label="Type" value={compute.compute_type ?? '—'} />
                  <DetailItem label="Node" value={compute.node_type ?? '—'} />
                  <DetailItem label="Spark" value={compute.spark_version ?? '—'} />
                  <DetailItem label="Workspace" value={compute.workspace_id ?? '—'} />
                  <DetailItem label="Landing zone" value={compute.source_lz_id} />
                  <DetailItem label="Subscription" value={compute.subscription_or_account_id ?? '—'} />
                  <DetailItem label="CPU" value={formatPct(compute.avg_cpu_utilization_pct)} />
                  <DetailItem label="Memory" value={formatPct(compute.avg_mem_utilization_pct)} />
                  <DetailItem label="Collected" value={compute.collected_at ? new Date(compute.collected_at).toLocaleString('en-GB') : '—'} />
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
