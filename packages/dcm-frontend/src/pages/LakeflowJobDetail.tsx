/**
 * Lakeflow Job detail (N2) — KPIs, runs×tasks matrix, runs DataTable.
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { format, parseISO } from 'date-fns';
import { Clock, ExternalLink, Gauge, RefreshCw, Search, Timer, TrendingUp, X } from 'lucide-react';
import {
  ComputeDataTable,
  type ComputeDataTableColumn,
  type SortDirection,
} from '../components/domain/compute/compute-data-table';
import { COLUMN_WIDTH } from '../components/domain/compute/compute-column-widths';
import { ComputeKpiCard } from '../components/domain/compute/compute-kpi-card';
import { LakeflowBreadcrumb } from '../components/domain/lakeflow/breadcrumb';
import { ExpandableError } from '../components/domain/lakeflow/expandable-error';
import { Content, ContentMain, ContentTitle } from '../components/layout/content';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Skeleton } from '../components/ui/skeleton';
import { useGlobalTimeRange } from '../contexts/time-range';
import { useLakeflowJobDetail, useLakeflowJobRuns } from '../hooks/useLakeflowJobsData';
import {
  lakeflowJobFieldDescriptions,
  lakeflowJobKpiDescriptions,
  lakeflowRunFieldDescriptions,
} from '../lib/lakeflow/field-descriptions';
import {
  formatDurationSeconds,
  formatPct,
  formatRelativeTime,
  lakeflowStatusColor,
  lakeflowStatusLabel,
} from '../lib/lakeflow/format';
import { countActiveColumnFilters } from '../lib/compute/column-filters';
import { cn } from '../lib/utils';
import type { ComputeColumnFilterValues, LakeflowJobRun } from '../types/api';

/** Une seule instance vide, pour ne pas relancer les mémos à chaque remise à zéro. */
const NO_FILTERS: ComputeColumnFilterValues = {};

const STATUS_OPTIONS = [
  { value: 'failed', label: 'Failed' },
  { value: 'timed_out', label: 'Timed out' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: 'succeeded', label: 'Succeeded' },
  { value: 'running', label: 'Running' },
] as const;

type RunSortKey =
  | 'start_time'
  | 'end_time'
  | 'run_id'
  | 'run_type'
  | 'trigger'
  | 'duration'
  | 'lag'
  | 'status'
  | 'tasks'
  | 'retries';

const ASC_SORT_KEYS = new Set<RunSortKey>(['run_id', 'run_type', 'trigger', 'status']);

function formatMatrixDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return format(parseISO(iso), 'dd/MM HH:mm');
  } catch {
    return formatRelativeTime(iso);
  }
}

function statusBadgeVariant(
  status: string | null | undefined
): 'success' | 'destructive' | 'warning' | 'secondary' | 'info' | 'outline' {
  const s = (status || '').trim().toLowerCase();
  if (s === 'succeeded') return 'success';
  if (s === 'failed') return 'destructive';
  if (s === 'timed_out') return 'warning';
  if (s === 'running') return 'info';
  if (s === 'cancelled') return 'secondary';
  return 'outline';
}

function StatusBadge({ status }: { status: string | null | undefined }) {
  const label = lakeflowStatusLabel(status);
  if (label === 'Inconnu') return <span className="text-muted-foreground">—</span>;
  return (
    <Badge variant={statusBadgeVariant(status)} className="gap-1.5">
      <span
        className="inline-block size-1.5 rounded-full"
        style={{ background: lakeflowStatusColor(status) }}
        aria-hidden
      />
      {label}
    </Badge>
  );
}

function ToggleChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-full border px-2.5 py-1 text-xs font-bold transition-colors',
        active
          ? 'border-primary bg-primary text-primary-foreground'
          : 'border-border bg-card text-muted-foreground hover:text-foreground'
      )}
      aria-pressed={active}
    >
      {children}
    </button>
  );
}

function MatrixRunHeader({ workflowId, run }: { workflowId: string; run: LakeflowJobRun }) {
  let day = '—';
  let time = '';
  const src = run.start_time || run.execution_date;
  if (src) {
    try {
      const d = parseISO(src);
      day = format(d, 'dd/MM');
      if (run.start_time) time = format(d, 'HH:mm');
    } catch {
      day = formatMatrixDate(src);
    }
  }
  return (
    <Link
      to={`/databricks/workflows/${encodeURIComponent(workflowId)}/runs/${encodeURIComponent(run.run_id)}`}
      className="inline-flex min-w-[52px] flex-col items-center leading-tight text-[9px] hover:text-[var(--tdf-blue)]"
      title={`${run.run_id}${run.start_time ? ` · ${run.start_time}` : ''}`}
    >
      <span className="font-bold tabular-nums">{day}</span>
      {time ? <span className="font-medium tabular-nums text-muted-foreground">{time}</span> : null}
    </Link>
  );
}

function DurationStack({ run }: { run: LakeflowJobRun }) {
  return (
    <span className="text-xs font-semibold tabular-nums">
      {formatDurationSeconds(run.duration_seconds)}
    </span>
  );
}

function TaskMatrix({
  workflowId,
  taskKeys,
  matrixRuns,
  cells,
}: {
  workflowId: string;
  taskKeys: string[];
  matrixRuns: LakeflowJobRun[];
  cells: Array<{
    run_id: string;
    task_key: string;
    status: string | null;
    duration_seconds: number | null;
  }>;
}) {
  const cellMap = useMemo(() => {
    const m = new Map<string, (typeof cells)[0]>();
    for (const c of cells) m.set(`${c.run_id}::${c.task_key}`, c);
    return m;
  }, [cells]);

  if (matrixRuns.length === 0) {
    return (
      <div className="px-4 py-8 text-center text-sm text-muted-foreground">
        Pas assez de runs pour la matrice.
      </div>
    );
  }

  const runsChrono = [...matrixRuns].reverse();

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-left">
        <thead>
          <tr className="border-b border-border text-[10px] font-black uppercase tracking-[1px] text-muted-foreground">
            <th className="sticky left-0 z-10 bg-[var(--card-background)] px-3 py-2">Task / Run</th>
            {runsChrono.map((r) => (
              <th key={r.run_id} className="px-1 py-2 text-center normal-case tracking-normal">
                <MatrixRunHeader workflowId={workflowId} run={r} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="border-b border-border/80 bg-muted/30">
            <td className="sticky left-0 z-10 bg-muted/30 px-3 py-1.5 text-xs font-bold">
              Run total
            </td>
            {runsChrono.map((r) => (
              <td key={r.run_id} className="px-1 py-1.5 text-center">
                <Link
                  to={`/databricks/workflows/${encodeURIComponent(workflowId)}/runs/${encodeURIComponent(r.run_id)}`}
                  className="inline-block size-3 rounded-sm"
                  style={{ background: lakeflowStatusColor(r.status) }}
                  title={`${lakeflowStatusLabel(r.status)} · ${formatDurationSeconds(r.duration_seconds)}`}
                />
              </td>
            ))}
          </tr>
          {taskKeys.map((tk) => (
            <tr key={tk} className="border-b border-border/50">
              <td className="sticky left-0 z-10 max-w-[180px] truncate bg-[var(--card-background)] px-3 py-1.5 font-mono text-[11px]">
                {tk}
              </td>
              {runsChrono.map((r) => {
                const cell = cellMap.get(`${r.run_id}::${tk}`);
                return (
                  <td key={r.run_id} className="px-1 py-1.5 text-center">
                    <span
                      className="inline-block size-3 rounded-sm"
                      style={{
                        background: cell ? lakeflowStatusColor(cell.status) : 'var(--muted)',
                        opacity: cell ? 1 : 0.35,
                      }}
                      title={
                        cell
                          ? `${lakeflowStatusLabel(cell.status)} · ${formatDurationSeconds(cell.duration_seconds)}`
                          : '—'
                      }
                    />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function LakeflowJobDetail() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const { getDisplayRange } = useGlobalTimeRange();
  const display = getDisplayRange();
  const periodLabel = `${display.startDate} → ${display.endDate}`;

  const [searchInput, setSearchInput] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [runsPage, setRunsPage] = useState(1);
  const [sort, setSort] = useState<RunSortKey>('start_time');
  const [order, setOrder] = useState<SortDirection>('desc');
  const [selectedStatuses, setSelectedStatuses] = useState<string[]>([]);
  const [withRetries, setWithRetries] = useState(false);
  // Les colonnes sans paramètre historique vivent ici ; `status` reste la liste de
  // puces, qui est le paramètre `status` de l'endpoint.
  const [columnFilters, setColumnFilters] = useState<ComputeColumnFilterValues>(NO_FILTERS);

  useEffect(() => {
    const t = window.setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      setRunsPage(1);
    }, 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  // Le tableau ne voit qu'un objet de filtres. `status` n'y figure que si une seule
  // puce est cochée : le serveur applique alors le `IN (…)` de la liste et ignore le
  // prédicat mono-valeur, si bien que deux statuts ne peuvent pas venir de la combo.
  const singleStatus = selectedStatuses.length === 1 ? selectedStatuses[0] : '';
  const filters = useMemo<ComputeColumnFilterValues>(
    () => ({ ...columnFilters, ...(singleStatus ? { status: singleStatus } : {}) }),
    [columnFilters, singleStatus]
  );

  const changeFilters = (next: ComputeColumnFilterValues) => {
    const { status = '', ...rest } = next;
    setColumnFilters(rest);
    setRunsPage(1);
    // La liste de puces est réécrite sur la seule valeur choisie : sans cela, le
    // `IN (…)` déjà en place l'emporterait et le filtre serait sans effet.
    if (status !== singleStatus) setSelectedStatuses(status ? [status] : []);
  };

  // Les combos interrogent le serveur dans le périmètre du tableau : les statuts et
  // déclencheurs listés sont ceux de **ce** workflow, pas de tous.
  const runsFilterScope = useMemo(() => ({ workflowId }), [workflowId]);

  const detail = useLakeflowJobDetail(workflowId);
  const runs = useLakeflowJobRuns(workflowId, {
    page: runsPage,
    pageSize: 25,
    search: debouncedSearch,
    status: selectedStatuses.length ? selectedStatuses : undefined,
    filters,
    withRetries,
    sort,
    order,
  });

  const wf = detail.data?.workflow;
  const runItems = runs.data?.items ?? [];
  const databricksUrl = wf?.last_run_page_url;

  const hasActiveFilters =
    Boolean(searchInput.trim()) ||
    countActiveColumnFilters(columnFilters) > 0 ||
    selectedStatuses.length > 0 ||
    withRetries ||
    sort !== 'start_time';

  const totalPages = runs.data ? Math.max(1, Math.ceil(runs.data.total / runs.data.page_size)) : 1;
  const startIndex =
    runs.data && runs.data.total > 0 ? (runs.data.page - 1) * runs.data.page_size + 1 : 0;
  const endIndex = runs.data ? Math.min(runs.data.page * runs.data.page_size, runs.data.total) : 0;

  const toggleStatus = (value: string) => {
    setSelectedStatuses((current) => {
      const next = new Set(current);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return [...next];
    });
    setRunsPage(1);
  };

  const handleSortChange = (columnId: string) => {
    const nextSort = columnId as RunSortKey;
    if (sort === nextSort) {
      setOrder((current) => (current === 'asc' ? 'desc' : 'asc'));
    } else {
      setSort(nextSort);
      setOrder(ASC_SORT_KEYS.has(nextSort) ? 'asc' : 'desc');
    }
    setRunsPage(1);
  };

  const clearFilters = () => {
    setSearchInput('');
    setDebouncedSearch('');
    setColumnFilters(NO_FILTERS);
    setSelectedStatuses([]);
    setWithRetries(false);
    setSort('start_time');
    setOrder('desc');
    setRunsPage(1);
  };

  const runColumns = useMemo(
    (): ComputeDataTableColumn<LakeflowJobRun>[] => [
      {
        id: 'start_time',
        width: COLUMN_WIDTH.timestamp,
        header: 'Début',
        description: lakeflowRunFieldDescriptions.startTime,
        sortable: true,
        cell: (run) => (
          <span className="text-xs text-muted-foreground">{formatMatrixDate(run.start_time)}</span>
        ),
      },
      {
        id: 'end_time',
        width: COLUMN_WIDTH.timestamp,
        header: 'Fin',
        description: lakeflowRunFieldDescriptions.endTime,
        sortable: true,
        cell: (run) => (
          <span className="text-xs text-muted-foreground">{formatMatrixDate(run.end_time)}</span>
        ),
      },
      {
        id: 'run_id',
        width: COLUMN_WIDTH.identifier,
        header: 'Run',
        description: lakeflowRunFieldDescriptions.runId,
        sortable: true,
        cell: (run) => (
          <Link
            to={`/databricks/workflows/${encodeURIComponent(workflowId!)}/runs/${encodeURIComponent(run.run_id)}`}
            className="font-mono text-xs font-semibold hover:text-[var(--tdf-blue)]"
          >
            {run.run_id}
          </Link>
        ),
      },
      {
        id: 'run_type',
        filterKey: 'run_type',
        width: COLUMN_WIDTH.label,
        header: 'Type',
        description: lakeflowRunFieldDescriptions.runType,
        sortable: true,
        cell: (run) => (
          <span className="capitalize text-muted-foreground">
            {(run.run_type ?? '—').toLowerCase().replace(/_/g, ' ')}
          </span>
        ),
      },
      {
        id: 'trigger',
        filterKey: 'trigger',
        width: COLUMN_WIDTH.label,
        header: 'Déclencheur',
        description: lakeflowRunFieldDescriptions.trigger,
        sortable: true,
        cell: (run) => (
          <span className="capitalize text-muted-foreground">
            {(run.trigger_type ?? '—').toLowerCase().replace(/_/g, ' ')}
          </span>
        ),
      },
      {
        id: 'duration',
        filterKey: 'duration',
        width: COLUMN_WIDTH.number,
        header: 'Durée',
        description: lakeflowRunFieldDescriptions.duration,
        sortable: true,
        cell: (run) => <DurationStack run={run} />,
      },
      {
        id: 'lag',
        filterKey: 'lag',
        width: COLUMN_WIDTH.number,
        header: 'Retard',
        description: lakeflowRunFieldDescriptions.lag,
        sortable: true,
        align: 'right',
        cell: (run) => (
          <span className="font-semibold tabular-nums">
            {formatDurationSeconds(run.schedule_lag_seconds)}
          </span>
        ),
      },
      {
        id: 'status',
        filterKey: 'status',
        width: COLUMN_WIDTH.status,
        header: 'Statut',
        description: lakeflowRunFieldDescriptions.status,
        sortable: true,
        cell: (run) => <StatusBadge status={run.status} />,
      },
      {
        id: 'tasks',
        filterKey: 'tasks',
        width: COLUMN_WIDTH.number,
        header: 'Tâches',
        description: lakeflowRunFieldDescriptions.tasks,
        sortable: true,
        align: 'right',
        cell: (run) => (
          <span className="font-semibold tabular-nums">
            {run.tasks_total != null ? `${run.tasks_failed ?? 0}/${run.tasks_total}` : '—'}
          </span>
        ),
      },
      {
        id: 'retries',
        filterKey: 'retries',
        width: COLUMN_WIDTH.number,
        header: 'Retries',
        description: lakeflowRunFieldDescriptions.retries,
        sortable: true,
        align: 'right',
        cell: (run) => <span className="font-semibold tabular-nums">{run.retry_count ?? '—'}</span>,
      },
      {
        id: 'error',
        width: COLUMN_WIDTH.composite,
        header: 'Erreur',
        description: lakeflowRunFieldDescriptions.error,
        cell: (run) => <ExpandableError message={run.error_message} />,
      },
      {
        id: 'actions',
        width: COLUMN_WIDTH.action,
        resizable: false,
        header: '',
        cell: (run) =>
          run.run_page_url ? (
            <a
              href={run.run_page_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex text-muted-foreground hover:text-foreground"
              aria-label="Ouvrir dans Databricks"
              onClick={(e) => e.stopPropagation()}
            >
              <ExternalLink size={12} />
            </a>
          ) : null,
      },
    ],
    [workflowId]
  );

  const runsToolbar = (
    <div className="flex flex-wrap items-center gap-x-1.5 gap-y-2">
      <div className="relative w-full max-w-[220px] shrink-0 sm:w-[200px]">
        <Search
          size={14}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Rechercher un run_id…"
          className="h-8 rounded-full pl-9 text-xs"
          aria-label="Rechercher un run"
        />
      </div>

      {STATUS_OPTIONS.map((opt) => (
        <ToggleChip
          key={opt.value}
          active={selectedStatuses.includes(opt.value)}
          onClick={() => toggleStatus(opt.value)}
        >
          {opt.label}
        </ToggleChip>
      ))}

      <ToggleChip
        active={withRetries}
        onClick={() => {
          setWithRetries((v) => !v);
          setRunsPage(1);
        }}
      >
        Avec retries
      </ToggleChip>

      {hasActiveFilters ? (
        <button
          type="button"
          onClick={clearFilters}
          className="inline-flex h-7 items-center gap-1 rounded-full border border-border px-2 text-[10.5px] font-bold text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground"
        >
          <X size={11} />
          Réinitialiser
        </button>
      ) : null}
    </div>
  );

  return (
    <Content className="mx-auto max-w-[1440px] gap-0 p-4 pb-24 lg:px-6 lg:pb-28">
      <ContentTitle>Lakeflow — Job</ContentTitle>

      <LakeflowBreadcrumb jobName={wf?.workflow_name} jobId={workflowId} />

      <div className="mb-4 flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          {detail.loading && !wf ? (
            <Skeleton className="h-8 w-72" />
          ) : (
            <>
              <h2 className="m-0 truncate text-xl font-extrabold tracking-tight">
                {wf?.workflow_name || workflowId}
              </h2>
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span className="font-mono">{workflowId}</span>
                {wf?.workspace_name || wf?.workspace_id ? (
                  <span>{wf?.workspace_name || wf?.workspace_id}</span>
                ) : null}
                {wf?.owner ? <span>{wf.owner}</span> : null}
                {wf?.last_trigger_type ? (
                  <span className="capitalize">
                    {wf.last_trigger_type.toLowerCase().replace(/_/g, ' ')}
                  </span>
                ) : null}
              </div>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          {databricksUrl ? (
            <a
              href={databricksUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-8 items-center gap-1.5 rounded-full border border-border bg-card px-3 text-xs font-semibold hover:bg-accent"
            >
              Ouvrir dans Databricks
              <ExternalLink size={12} />
            </a>
          ) : null}
          <button
            type="button"
            onClick={() => {
              void detail.refetch();
              void runs.refetch();
            }}
            className="rounded p-1.5 text-muted-foreground hover:text-foreground"
            aria-label="Rafraîchir"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {(detail.error || runs.error) && (
        <div className="mb-4 rounded-[var(--card-radius)] border border-danger-border bg-danger-subtle px-4 py-3 text-sm text-danger">
          Impossible de charger le détail du job.
        </div>
      )}

      <ContentMain className="gap-4">
        {detail.loading && !wf ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
            {Array.from({ length: 7 }).map((_, i) => (
              <Skeleton key={i} className="h-[120px]" />
            ))}
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
            <ComputeKpiCard
              title="Succès 24h"
              description={lakeflowJobKpiDescriptions.detailSuccess24h}
              value={formatPct(wf?.success_rate_24h_pct ?? null)}
              subtitle={`n = ${(wf?.success_rate_24h_n ?? 0).toLocaleString('fr-FR')}`}
              tone="success"
              icon={TrendingUp}
            />
            <ComputeKpiCard
              title="Succès 7j"
              description={lakeflowJobKpiDescriptions.detailSuccess7d}
              value={formatPct(wf?.success_rate_7d_pct ?? null)}
              subtitle={`n = ${(wf?.success_rate_7d_n ?? 0).toLocaleString('fr-FR')}`}
              tone="info"
              icon={TrendingUp}
            />
            <ComputeKpiCard
              title="Durée moyenne"
              description={lakeflowJobKpiDescriptions.detailAvgDuration}
              value={formatDurationSeconds(wf?.avg_duration_seconds)}
              subtitle={
                <>
                  drift {formatPct(wf?.duration_drift_pct ?? null, 0)}
                  {wf?.baseline_avg_14d != null
                    ? ` · base ${formatDurationSeconds(wf.baseline_avg_14d)}`
                    : ''}
                </>
              }
              tone={
                wf?.duration_drift_pct != null && Math.abs(Number(wf.duration_drift_pct)) > 20
                  ? 'warning'
                  : 'purple'
              }
              icon={Timer}
            />
            <ComputeKpiCard
              title="p50"
              description={lakeflowJobFieldDescriptions.p50}
              value={formatDurationSeconds(wf?.p50)}
              subtitle={`Période ${periodLabel}`}
              tone="info"
              icon={Gauge}
            />
            <ComputeKpiCard
              title="p95"
              description={lakeflowJobFieldDescriptions.p95}
              value={formatDurationSeconds(wf?.p95)}
              subtitle={`Période ${periodLabel}`}
              tone="info"
              icon={Gauge}
            />
            <ComputeKpiCard
              title="p99"
              description={lakeflowJobFieldDescriptions.p99}
              value={formatDurationSeconds(wf?.p99)}
              subtitle={`Période ${periodLabel}`}
              tone="info"
              icon={Gauge}
            />
            <ComputeKpiCard
              title="Last run"
              description={lakeflowJobKpiDescriptions.detailLastRun}
              value={formatDurationSeconds(wf?.last_duration_seconds)}
              subtitle={
                <>
                  {formatMatrixDate(wf?.last_start_time)}
                  {wf?.last_end_time ? ` → ${formatMatrixDate(wf.last_end_time)}` : ''}
                </>
              }
              tone="purple"
              icon={Clock}
            />
          </div>
        )}

        <div className="overflow-hidden rounded-[var(--card-radius)] border border-border bg-[var(--card-background)] shadow-[var(--card-shadow)]">
          <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
            <h3 className="m-0 text-sm font-extrabold">Matrice runs × tasks</h3>
            {runs.data?.task_health?.length ? (
              <span className="text-[11px] text-muted-foreground">
                {runs.data.task_health.length} tâche
                {runs.data.task_health.length === 1 ? '' : 's'} · 20 derniers runs page 1
              </span>
            ) : (
              <span className="text-[11px] text-muted-foreground">
                20 derniers runs de la page courante
              </span>
            )}
          </div>
          {runs.loading && !runs.data ? (
            <div className="p-4">
              <Skeleton className="h-40 w-full" />
            </div>
          ) : (
            <TaskMatrix
              workflowId={workflowId ?? ''}
              taskKeys={runs.data?.matrix.task_keys ?? []}
              matrixRuns={runs.data?.matrix.runs ?? []}
              cells={runs.data?.matrix.cells ?? []}
            />
          )}
        </div>

        <ComputeDataTable
          tableId="lakeflow-job-runs"
          columns={runColumns}
          rows={runItems}
          rowKey={(run) => run.run_id}
          loading={runs.loading && !runs.data}
          emptyTitle="Aucun run sur cette fenêtre"
          emptyDescription="Élargissez la période dans le header ou réinitialisez les filtres."
          toolbar={runsToolbar}
          sort={{ key: sort, direction: order }}
          onSortChange={handleSortChange}
          filterView="lakeflow-job-runs"
          filterScope={runsFilterScope}
          filters={filters}
          onFiltersChange={changeFilters}
          minWidthClassName="min-w-[1180px]"
          pagination={
            runs.data
              ? {
                  currentPage: runs.data.page,
                  totalPages,
                  totalItems: runs.data.total,
                  startIndex,
                  endIndex,
                  hasPreviousPage: runs.data.page > 1,
                  hasNextPage: runs.data.page < totalPages,
                  onPrevious: () => setRunsPage((p) => Math.max(1, p - 1)),
                  onNext: () => setRunsPage((p) => p + 1),
                }
              : undefined
          }
        />
      </ContentMain>
    </Content>
  );
}
