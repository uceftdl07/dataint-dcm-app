import { ChevronDown } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { cn } from '../../lib/utils';
import type { PipelineRun } from '../../types/api';
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

function formatDuration(seconds: number | null) {
  if (seconds === null) return '—';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)} min`;
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('en-GB');
}

function RunDetails({ run }: { run: PipelineRun }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <DetailItem label="Run ID" value={run.run_id} />
      <DetailItem label="Pipeline ID" value={run.pipeline_id ?? '—'} />
      <DetailItem label="Type" value={run.pipeline_type ?? '—'} />
      <DetailItem label="Cloud" value={run.cloud_provider.toUpperCase()} />
      <DetailItem label="Landing zone" value={run.source_lz_id ?? '—'} />
      <DetailItem label="Duration" value={formatDuration(run.duration_seconds)} />
      <DetailItem label="Start" value={formatDateTime(run.start_time)} />
      <DetailItem label="End" value={formatDateTime(run.end_time)} />
      <DetailItem
        label="Error"
        value={run.error_message ? <span className="font-normal text-destructive">{run.error_message}</span> : '—'}
      />
    </div>
  );
}

export function PipelineRunAccordion({
  runs,
  loading,
  emptyMessage = 'No pipeline runs match the selected filters.',
  resetKey,
}: {
  runs: PipelineRun[];
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

  if (runs.length === 0) {
    return <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">{emptyMessage}</div>;
  }

  return (
    <div className="space-y-2">
      {runs.map((run) => {
        const isOpen = openId === run.run_id;
        return (
          <div
            key={run.run_id}
            className={cn(
              'overflow-hidden rounded-2xl border border-border/70 bg-background/70 transition-colors',
              isOpen && 'border-primary/35 bg-primary/[0.02]',
            )}
          >
            <button
              type="button"
              aria-expanded={isOpen}
              className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setOpenId((current) => (current === run.run_id ? null : run.run_id))}
            >
              <ChevronDown
                size={18}
                className={cn('mt-0.5 shrink-0 text-muted-foreground transition-transform duration-200', isOpen && 'rotate-180')}
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="truncate font-medium text-foreground">{run.pipeline_name}</p>
                  <StatusBadge value={run.status} />
                </div>
                <p className="mt-1 truncate text-xs text-muted-foreground">
                  {run.run_id} · {formatDuration(run.duration_seconds)} · {formatDateTime(run.start_time)}
                </p>
              </div>
            </button>
            {isOpen && (
              <div className="border-t border-border/60 px-4 py-4">
                <RunDetails run={run} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
