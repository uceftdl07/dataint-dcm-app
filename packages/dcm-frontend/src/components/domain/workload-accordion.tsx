import { ChevronDown } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { cn } from '../../lib/utils';
import { Skeleton } from '../ui/skeleton';
import { StatusBadge } from '../ui/status';

export interface WorkloadAccordionRow {
  id: string;
  name: string;
  type: string;
  status: string;
  durationSeconds: number | null;
  startTime: string | null;
  endTime: string | null;
  errorMessage: string | null;
  source: 'Pipeline' | 'Activity';
  parentName: string | null;
  sourceLzId: string | null;
  subscriptionOrAccountId: string | null;
  rowsRead?: number | null;
  rowsWritten?: number | null;
  dataReadBytes?: number | null;
  dataWrittenBytes?: number | null;
}

function formatDuration(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return '—';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)} min`;
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('en-GB');
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('en-GB').format(value);
}

function formatBytes(value: number | null | undefined) {
  if (value === null || value === undefined) return '—';
  if (value < 1024) return `${value} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let size = value / 1024;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(size >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

function DetailItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl border border-border/70 bg-background/70 px-3 py-2">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <div className="mt-1 break-words text-sm font-medium text-foreground">{value}</div>
    </div>
  );
}

export function WorkloadAccordion({
  workloads,
  loading,
  emptyMessage = 'No workloads match the selected filters.',
}: {
  workloads: WorkloadAccordionRow[];
  loading: boolean;
  emptyMessage?: string;
}) {
  const [openId, setOpenId] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-14" />
        ))}
      </div>
    );
  }

  if (workloads.length === 0) {
    return (
      <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {workloads.map((workload) => {
        const isOpen = openId === workload.id;

        return (
          <div
            key={workload.id}
            className={cn(
              'overflow-hidden rounded-2xl border border-border/70 bg-background/70 transition-colors',
              isOpen && 'border-primary/35 bg-primary/[0.02]',
            )}
          >
            <button
              type="button"
              aria-expanded={isOpen}
              className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setOpenId((current) => (current === workload.id ? null : workload.id))}
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
                  <p className="truncate font-medium text-foreground">{workload.name}</p>
                  <StatusBadge value={workload.status} />
                  <span className="text-xs text-muted-foreground">{workload.source}</span>
                </div>
                <p className="mt-1 truncate text-xs text-muted-foreground">
                  {workload.type} · {formatDuration(workload.durationSeconds)} · {workload.id}
                </p>
              </div>
            </button>
            {isOpen && (
              <div className="space-y-3 border-t border-border/60 px-4 py-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <DetailItem label="Start" value={formatDateTime(workload.startTime)} />
                  <DetailItem label="End" value={formatDateTime(workload.endTime)} />
                  <DetailItem label="Duration" value={formatDuration(workload.durationSeconds)} />
                  <DetailItem label="Type" value={workload.type} />
                  <DetailItem label="Source" value={workload.source} />
                  <DetailItem label="Parent" value={workload.parentName ?? '—'} />
                  <DetailItem label="Landing zone" value={workload.sourceLzId ?? '—'} />
                  <DetailItem label="Account" value={workload.subscriptionOrAccountId ?? '—'} />
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <DetailItem
                    label="Rows"
                    value={`${formatNumber(workload.rowsRead)} read / ${formatNumber(workload.rowsWritten)} written`}
                  />
                  <DetailItem
                    label="Data volume"
                    value={`${formatBytes(workload.dataReadBytes)} read / ${formatBytes(workload.dataWrittenBytes)} written`}
                  />
                </div>
                <DetailItem
                  label="Error"
                  value={
                    workload.errorMessage ? (
                      <span className="font-normal text-destructive">{workload.errorMessage}</span>
                    ) : (
                      '—'
                    )
                  }
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
