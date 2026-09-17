/**
 * Lakeflow run detail (N3) — duration breakdown, task Gantt, tasks table.
 */
import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { format, parseISO } from 'date-fns';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { Content, ContentMain, ContentTitle } from '../components/layout/content';
import { Skeleton } from '../components/ui/skeleton';
import { LakeflowBreadcrumb } from '../components/domain/lakeflow/breadcrumb';
import { ExpandableError } from '../components/domain/lakeflow/expandable-error';
import { useLakeflowJobDetail, useLakeflowRunTasks } from '../hooks/useLakeflowJobsData';
import { cn } from '../lib/utils';
import {
  formatDurationSeconds,
  formatRelativeTime,
  lakeflowStatusColor,
} from '../lib/lakeflow/format';
import type { LakeflowJobTask } from '../types/api';

function formatShortRunDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  try {
    return format(parseISO(iso), 'dd/MM HH:mm');
  } catch {
    return null;
  }
}

function TaskGantt({ tasks }: { tasks: LakeflowJobTask[] }) {
  const bounds = useMemo(() => {
    let min = Number.POSITIVE_INFINITY;
    let max = Number.NEGATIVE_INFINITY;
    for (const t of tasks) {
      const s = t.start_time ? Date.parse(t.start_time) : NaN;
      const e = t.end_time
        ? Date.parse(t.end_time)
        : t.start_time && t.duration_seconds != null
          ? Date.parse(t.start_time) + Number(t.duration_seconds) * 1000
          : NaN;
      if (!Number.isNaN(s)) min = Math.min(min, s);
      if (!Number.isNaN(e)) max = Math.max(max, e);
      else if (!Number.isNaN(s)) max = Math.max(max, s);
    }
    if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) {
      return null;
    }
    return { min, max, span: max - min };
  }, [tasks]);

  if (!bounds || tasks.length === 0) {
    return (
      <div className="px-4 py-8 text-center text-sm text-muted-foreground">
        Pas de timeline disponible pour ces tâches.
      </div>
    );
  }

  return (
    <div className="space-y-1.5 px-4 py-3">
      {tasks.map((t) => {
        const s = t.start_time ? Date.parse(t.start_time) : bounds.min;
        const e = t.end_time
          ? Date.parse(t.end_time)
          : s + (Number(t.duration_seconds) || 0) * 1000;
        const left = ((s - bounds.min) / bounds.span) * 100;
        const width = Math.max(0.8, ((Math.max(e, s) - s) / bounds.span) * 100);
        return (
          <div
            key={`${t.task_id ?? t.task_key}-${t.attempt_number}`}
            className="flex items-center gap-3"
          >
            <div className="w-40 shrink-0 truncate font-mono text-[11px]" title={t.task_key ?? ''}>
              {t.task_key ?? t.task_id ?? '—'}
              {t.attempt_number != null && t.attempt_number > 0 ? (
                <span className="ml-1 text-muted-foreground">#{t.attempt_number}</span>
              ) : null}
            </div>
            <div className="relative h-5 flex-1 rounded bg-muted/50">
              <div
                className="absolute top-0.5 h-4 rounded-sm"
                style={{
                  left: `${left}%`,
                  width: `${width}%`,
                  background: lakeflowStatusColor(t.status),
                }}
                title={`${t.status ?? ''} · ${formatDurationSeconds(t.duration_seconds)}`}
              />
            </div>
            <div className="w-16 shrink-0 text-right text-[10px] tabular-nums text-muted-foreground">
              {formatDurationSeconds(t.duration_seconds)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function LakeflowRunDetail() {
  const { workflowId, runId } = useParams<{ workflowId: string; runId: string }>();
  const [failedOnly, setFailedOnly] = useState(false);
  const jobDetail = useLakeflowJobDetail(workflowId);
  const { data, loading, error, refetch } = useLakeflowRunTasks(workflowId, runId, failedOnly);
  const run = data?.run;
  const jobName = jobDetail.data?.workflow?.workflow_name;
  const runLabel = formatShortRunDate(run?.start_time) ?? runId ?? null;

  return (
    <Content className="mx-auto max-w-[1440px] gap-0 p-4 pb-24 lg:px-6 lg:pb-28">
      <ContentTitle>Lakeflow — Run</ContentTitle>

      <LakeflowBreadcrumb jobName={jobName} jobId={workflowId} runLabel={runLabel} />

      <div className="mb-4 flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          {loading && !run ? (
            <Skeleton className="h-8 w-64" />
          ) : (
            <>
              <h2 className="m-0 flex flex-wrap items-center gap-2 text-xl font-extrabold tracking-tight">
                <span className="font-mono text-base">{runId}</span>
                <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-0.5 text-xs font-bold capitalize">
                  <span
                    className="size-2 rounded-full"
                    style={{ background: lakeflowStatusColor(run?.status) }}
                  />
                  {(run?.status ?? '—').toLowerCase()}
                </span>
              </h2>
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span>
                  {formatRelativeTime(run?.start_time)}
                  {run?.end_time ? ` → ${formatRelativeTime(run.end_time)}` : ''}
                </span>
                <span>{formatDurationSeconds(run?.duration_seconds)}</span>
                {run?.trigger_type ? (
                  <span className="capitalize">
                    {run.trigger_type.toLowerCase().replace(/_/g, ' ')}
                  </span>
                ) : null}
                {run?.retry_count != null ? <span>retries {run.retry_count}</span> : null}
                {run?.cluster_instance_id ? (
                  <span className="font-mono">{run.cluster_instance_id}</span>
                ) : null}
              </div>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          {run?.run_page_url ? (
            <a
              href={run.run_page_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-8 items-center gap-1.5 rounded-full border border-border bg-card px-3 text-xs font-semibold hover:bg-accent"
            >
              Databricks
              <ExternalLink size={12} />
            </a>
          ) : null}
          <button
            type="button"
            onClick={() => refetch()}
            className="rounded p-1.5 text-muted-foreground hover:text-foreground"
            aria-label="Rafraîchir"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {error ? (
        <div className="mb-4 rounded-[var(--card-radius)] border border-danger-border bg-danger-subtle px-4 py-3 text-sm text-danger">
          Impossible de charger les tâches du run.
        </div>
      ) : null}

      <ContentMain className="mb-4 rounded-[var(--card-radius)] border border-border bg-[var(--card-background)] px-4 py-4 shadow-[var(--card-shadow)]">
        <h3 className="mb-3 mt-0 text-sm font-extrabold">Durée du run</h3>
        {run ? (
          <div className="text-2xl font-extrabold tabular-nums">
            {formatDurationSeconds(run.duration_seconds)}
          </div>
        ) : (
          <Skeleton className="h-10 w-full" />
        )}
      </ContentMain>

      <ContentMain className="mb-4 overflow-hidden rounded-[var(--card-radius)] border border-border bg-[var(--card-background)] shadow-[var(--card-shadow)]">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
          <h3 className="m-0 text-sm font-extrabold">Timeline des tasks</h3>
          <button
            type="button"
            onClick={() => setFailedOnly((v) => !v)}
            className={cn(
              'rounded-full border px-3 py-1 text-[11px] font-bold',
              failedOnly
                ? 'border-danger bg-danger text-white'
                : 'border-border text-muted-foreground hover:text-foreground'
            )}
          >
            Tâches en échec uniquement
          </button>
        </div>
        {loading && !data ? (
          <div className="p-4">
            <Skeleton className="h-32 w-full" />
          </div>
        ) : (
          <TaskGantt tasks={data?.items ?? []} />
        )}
      </ContentMain>

      <ContentMain className="overflow-hidden rounded-[var(--card-radius)] border border-border bg-[var(--card-background)] shadow-[var(--card-shadow)]">
        <div className="border-b border-border px-4 py-2.5">
          <h3 className="m-0 text-sm font-extrabold">Tasks{data ? ` (${data.total})` : ''}</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[800px] border-collapse text-left">
            <thead>
              <tr className="border-b border-border bg-muted/40 text-[10px] font-black uppercase tracking-[1.2px] text-muted-foreground">
                <th className="px-3 py-2">Tâche</th>
                <th className="px-3 py-2">Statut</th>
                <th className="px-3 py-2">Début</th>
                <th className="px-3 py-2">Fin</th>
                <th className="px-3 py-2">Durée</th>
                <th className="px-3 py-2">Tentative</th>
                <th className="px-3 py-2">Cluster</th>
                <th className="px-3 py-2">Code de terminaison</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((t) => (
                <tr
                  key={`${t.task_id ?? t.task_key}-${t.attempt_number}-${t.start_time}`}
                  className="border-b border-border/70"
                >
                  <td className="px-3 py-2 font-mono text-xs">{t.task_key ?? t.task_id ?? '—'}</td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1.5 text-xs font-semibold capitalize">
                      <span
                        className="size-2 rounded-full"
                        style={{ background: lakeflowStatusColor(t.status) }}
                      />
                      {(t.status ?? '—').toLowerCase()}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {formatRelativeTime(t.start_time)}
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {formatRelativeTime(t.end_time)}
                  </td>
                  <td className="px-3 py-2 text-xs tabular-nums">
                    {formatDurationSeconds(t.duration_seconds)}
                  </td>
                  <td className="px-3 py-2 text-xs tabular-nums">{t.attempt_number ?? '—'}</td>
                  <td className="max-w-[120px] truncate px-3 py-2 font-mono text-[10px] text-muted-foreground">
                    {t.cluster_instance_id ?? '—'}
                  </td>
                  <td className="px-3 py-2">
                    <ExpandableError message={t.error_message} />
                  </td>
                </tr>
              ))}
              {!loading && (data?.items.length ?? 0) === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-sm text-muted-foreground">
                    Aucune tâche.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </ContentMain>
    </Content>
  );
}
