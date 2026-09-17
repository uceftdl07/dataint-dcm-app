/**
 * Lakeflow Jobs (N1) — workflow list aligned with Compute pages (DataTable, KPIs, tooltips).
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  DollarSign,
  GitBranch,
  RefreshCw,
  Search,
  X,
} from 'lucide-react';
import { format, parseISO } from 'date-fns';
import {
  ComputeDataTable,
  type ComputeDataTableColumn,
  type SortDirection,
} from '../components/domain/compute/compute-data-table';
import { COLUMN_WIDTH } from '../components/domain/compute/compute-column-widths';
import { ComputeKpiCard } from '../components/domain/compute/compute-kpi-card';
import { LakeflowHistoryBars } from '../components/domain/lakeflow/history-bars';
import { Content, ContentMain, ContentTitle } from '../components/layout/content';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Skeleton } from '../components/ui/skeleton';
import { useGlobalTimeRange } from '../contexts/time-range';
import { useLakeflowJobsList } from '../hooks/useLakeflowJobsData';
import {
  lakeflowJobFieldDescriptions,
  lakeflowJobKpiDescriptions,
} from '../lib/lakeflow/field-descriptions';
import {
  formatDataFreshness,
  formatDurationSeconds,
  formatPct,
  lakeflowStatusColor,
  lakeflowStatusLabel,
} from '../lib/lakeflow/format';
import { countActiveColumnFilters } from '../lib/compute/column-filters';
import { cn, formatCompactCurrency, formatCurrency } from '../lib/utils';
import type { ComputeColumnFilterValues, LakeflowJobListItem } from '../types/api';

/** Une seule instance vide, pour ne pas relancer les mémos à chaque remise à zéro. */
const NO_FILTERS: ComputeColumnFilterValues = {};

const STATUS_OPTIONS = [
  { value: 'failed', label: 'Failed' },
  { value: 'timed_out', label: 'Timed out' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: 'succeeded', label: 'Succeeded' },
  { value: 'running', label: 'Running' },
] as const;

type SortKey =
  | 'problems'
  | 'alpha'
  | 'status'
  | 'runs'
  | 'success'
  | 'success_24h'
  | 'success_7d'
  | 'duration'
  | 'drift'
  | 'p50'
  | 'p95'
  | 'p99'
  | 'retries'
  | 'trigger'
  | 'run_type'
  | 'last_duration'
  | 'last_run';

const ASC_SORT_KEYS = new Set<SortKey>(['alpha', 'status', 'trigger', 'run_type']);

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
  if (label === 'Inconnu') {
    return <span className="text-muted-foreground">—</span>;
  }
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

function SuccessBar({ pct }: { pct: number | null }) {
  if (pct == null) return <span className="text-muted-foreground">—</span>;
  const tone = pct >= 95 ? 'bg-success' : pct >= 90 ? 'bg-warning' : 'bg-danger';
  return (
    <div className="flex min-w-[72px] items-center gap-1.5">
      <span className="w-11 text-right text-xs font-semibold tabular-nums">{formatPct(pct)}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <div
          className={cn('h-full rounded-full', tone)}
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>
    </div>
  );
}

function DriftCell({ avg, drift }: { avg: number | null; drift: number | null }) {
  const driftNum = drift == null ? null : Number(drift);
  const up = driftNum != null && driftNum > 0;
  const down = driftNum != null && driftNum < 0;
  const warn = driftNum != null && Math.abs(driftNum) > 20;
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-semibold tabular-nums">{formatDurationSeconds(avg)}</span>
      {driftNum != null ? (
        <span
          className={cn(
            'inline-flex items-center gap-0.5 text-[10px] font-bold',
            warn ? 'text-danger' : 'text-muted-foreground'
          )}
        >
          {up ? <ArrowUp size={10} /> : null}
          {down ? <ArrowDown size={10} /> : null}
          {formatPct(driftNum, 0)}
        </span>
      ) : null}
    </div>
  );
}

function formatRunTs(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return format(parseISO(iso), 'dd/MM HH:mm');
  } catch {
    return iso.slice(0, 16).replace('T', ' ');
  }
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

export default function LakeflowJobs() {
  const { getDisplayRange } = useGlobalTimeRange();
  const display = getDisplayRange();
  const periodLabel = `${display.startDate} → ${display.endDate}`;

  const [searchParams, setSearchParams] = useSearchParams();
  const [searchInput, setSearchInput] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<SortKey>('problems');
  const [order, setOrder] = useState<SortDirection>('desc');
  const [driftOnly, setDriftOnly] = useState(false);
  const [noRuns, setNoRuns] = useState(false);
  const [withRetries, setWithRetries] = useState(false);
  // Les colonnes sans paramètre historique vivent ici ; `status` reste dans l'URL
  // (partage de lien) et `alpha` dans la barre de recherche.
  const [columnFilters, setColumnFilters] = useState<ComputeColumnFilterValues>(NO_FILTERS);

  const statusFromUrl = searchParams.get('status') ?? '';
  const selectedStatuses = useMemo(
    () =>
      statusFromUrl
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    [statusFromUrl]
  );

  const hasActiveFilters =
    Boolean(searchInput.trim()) ||
    countActiveColumnFilters(columnFilters) > 0 ||
    selectedStatuses.length > 0 ||
    driftOnly ||
    noRuns ||
    withRetries ||
    sort !== 'problems';

  useEffect(() => {
    const t = window.setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  // Le tableau ne voit qu'un objet de filtres, réassemblé depuis les trois sources.
  // `status` n'y figure que si une seule valeur est cochée : le serveur applique
  // alors le `IN (…)` de la liste et ignore le prédicat mono-valeur, si bien que
  // deux statuts cochés ne peuvent pas être représentés par la combo.
  const singleStatus = selectedStatuses.length === 1 ? selectedStatuses[0] : '';
  const filters = useMemo<ComputeColumnFilterValues>(
    () => ({
      ...columnFilters,
      ...(debouncedSearch ? { alpha: debouncedSearch } : {}),
      ...(singleStatus ? { status: singleStatus } : {}),
    }),
    [columnFilters, debouncedSearch, singleStatus]
  );

  const changeFilters = (next: ComputeColumnFilterValues) => {
    const { alpha = '', status = '', ...rest } = next;
    setColumnFilters(rest);
    setPage(1);
    if (alpha !== debouncedSearch) {
      setSearchInput(alpha);
      setDebouncedSearch(alpha);
    }
    // La liste de l'URL est réécrite sur la seule valeur choisie : sans cela, le
    // `IN (…)` déjà en place l'emporterait et le filtre serait sans effet.
    if (status !== singleStatus) {
      const params = new URLSearchParams(searchParams);
      if (status) params.set('status', status);
      else params.delete('status');
      setSearchParams(params, { replace: true });
    }
  };

  const { data, loading, error, refetch } = useLakeflowJobsList({
    search: debouncedSearch,
    filters,
    page,
    pageSize: 25,
    sort,
    order,
    driftOnly,
    noRuns,
    withRetries,
  });

  const items = data?.items ?? [];
  const freshness = formatDataFreshness(data?.as_of ?? null);
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const startIndex = data && data.total > 0 ? (data.page - 1) * data.page_size + 1 : 0;
  const endIndex = data ? Math.min(data.page * data.page_size, data.total) : 0;

  const pageKpis = useMemo(() => {
    const rows = data?.items ?? [];
    if (rows.length === 0) {
      return { terminalRuns: 0, avgSuccess: null as number | null, driftCount: 0 };
    }
    const terminalRuns = rows.reduce((sum, row) => sum + row.terminal_runs, 0);
    const successValues = rows
      .map((row) => row.success_rate_pct)
      .filter((v): v is number => v != null);
    const avgSuccess =
      successValues.length > 0
        ? successValues.reduce((a, b) => a + b, 0) / successValues.length
        : null;
    const driftCount = rows.filter(
      (row) => row.duration_drift_pct != null && Math.abs(row.duration_drift_pct) > 20
    ).length;
    return { terminalRuns, avgSuccess, driftCount };
  }, [data?.items]);

  const toggleStatus = (value: string) => {
    const next = new Set(selectedStatuses);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    const params = new URLSearchParams(searchParams);
    if (next.size === 0) params.delete('status');
    else params.set('status', [...next].join(','));
    setSearchParams(params, { replace: true });
    setPage(1);
  };

  const handleSortChange = (columnId: string) => {
    const nextSort = columnId as SortKey;
    if (sort === nextSort) {
      setOrder((current) => (current === 'asc' ? 'desc' : 'asc'));
    } else {
      setSort(nextSort);
      setOrder(ASC_SORT_KEYS.has(nextSort) ? 'asc' : 'desc');
    }
    setPage(1);
  };

  const clearFilters = () => {
    setSearchInput('');
    setDebouncedSearch('');
    setColumnFilters(NO_FILTERS);
    setDriftOnly(false);
    setNoRuns(false);
    setWithRetries(false);
    setSort('problems');
    setOrder('desc');
    setPage(1);
    if (searchParams.has('status')) {
      const params = new URLSearchParams(searchParams);
      params.delete('status');
      setSearchParams(params, { replace: true });
    }
  };

  const columns = useMemo(
    (): ComputeDataTableColumn<LakeflowJobListItem>[] => [
      {
        id: 'status',
        filterKey: 'status',
        width: COLUMN_WIDTH.badge,
        header: 'Statut',
        description: lakeflowJobFieldDescriptions.status,
        sortable: true,
        cell: (row) => <StatusBadge status={row.last_status} />,
      },
      {
        id: 'alpha',
        filterKey: 'alpha',
        width: COLUMN_WIDTH.longName,
        header: 'Job',
        description: lakeflowJobFieldDescriptions.job,
        sortable: true,
        // `min-w-0` et non une largeur en dur : la colonne est redimensionnable, une
        // borne fixe couperait à 240 px une colonne élargie à 400.
        cell: (row) => (
          <Link
            to={`/databricks/workflows/${encodeURIComponent(row.workflow_id)}`}
            className="group block min-w-0"
          >
            <div className="truncate text-sm font-semibold text-foreground group-hover:text-[var(--tdf-blue)]">
              {row.workflow_name || row.workflow_id}
            </div>
            <div className="truncate font-mono text-[10px] text-muted-foreground">
              {row.workflow_id}
            </div>
          </Link>
        ),
      },
      {
        id: 'history',
        width: COLUMN_WIDTH.composite,
        header: 'Historique',
        description: lakeflowJobFieldDescriptions.history,
        cell: (row) => (
          <LakeflowHistoryBars
            workflowId={row.workflow_id}
            history={row.history ?? []}
            periodLabel={periodLabel}
          />
        ),
      },
      {
        id: 'runs',
        filterKey: 'runs',
        width: COLUMN_WIDTH.number,
        header: 'Runs',
        description: lakeflowJobFieldDescriptions.runs,
        align: 'right',
        sortable: true,
        cell: (row) => (
          <span className="font-semibold tabular-nums">
            {row.terminal_runs.toLocaleString('fr-FR')}
          </span>
        ),
      },
      {
        id: 'cost',
        width: COLUMN_WIDTH.number,
        header: 'Coût',
        description: lakeflowJobFieldDescriptions.cost,
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">
            {row.execution_cost_usd == null ? '—' : formatCurrency(row.execution_cost_usd)}
          </span>
        ),
      },
      {
        id: 'success_24h',
        filterKey: 'success_24h',
        width: COLUMN_WIDTH.badge,
        header: 'Succès 24h',
        description: lakeflowJobFieldDescriptions.success24h,
        sortable: true,
        cell: (row) => <SuccessBar pct={row.success_rate_24h_pct} />,
      },
      {
        id: 'success_7d',
        filterKey: 'success_7d',
        width: COLUMN_WIDTH.badge,
        header: 'Succès 7j',
        description: lakeflowJobFieldDescriptions.success7d,
        sortable: true,
        cell: (row) => <SuccessBar pct={row.success_rate_7d_pct} />,
      },
      {
        id: 'success',
        filterKey: 'success',
        width: COLUMN_WIDTH.badge,
        header: 'Succès',
        description: lakeflowJobFieldDescriptions.success,
        sortable: true,
        cell: (row) => <SuccessBar pct={row.success_rate_pct} />,
      },
      {
        id: 'duration',
        filterKey: 'duration',
        width: COLUMN_WIDTH.timestamp,
        header: 'Durée / drift',
        description: lakeflowJobFieldDescriptions.durationDrift,
        sortable: true,
        cell: (row) => <DriftCell avg={row.avg_duration_seconds} drift={row.duration_drift_pct} />,
      },
      {
        id: 'p50',
        filterKey: 'p50',
        width: COLUMN_WIDTH.number,
        header: 'p50',
        description: lakeflowJobFieldDescriptions.p50,
        sortable: true,
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatDurationSeconds(row.p50)}</span>
        ),
      },
      {
        id: 'p95',
        filterKey: 'p95',
        width: COLUMN_WIDTH.number,
        header: 'p95',
        description: lakeflowJobFieldDescriptions.p95,
        sortable: true,
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatDurationSeconds(row.p95)}</span>
        ),
      },
      {
        id: 'p99',
        filterKey: 'p99',
        width: COLUMN_WIDTH.number,
        header: 'p99',
        description: lakeflowJobFieldDescriptions.p99,
        sortable: true,
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatDurationSeconds(row.p99)}</span>
        ),
      },
      {
        id: 'retries',
        filterKey: 'retries',
        width: COLUMN_WIDTH.number,
        header: 'Retries',
        description: lakeflowJobFieldDescriptions.retries,
        align: 'right',
        sortable: true,
        cell: (row) => (
          <span className="font-semibold tabular-nums">
            {row.avg_retry_count == null ? '—' : Number(row.avg_retry_count).toFixed(1)}
          </span>
        ),
      },
      {
        id: 'trigger',
        filterKey: 'trigger',
        width: COLUMN_WIDTH.label,
        header: 'Trigger',
        description: lakeflowJobFieldDescriptions.trigger,
        sortable: true,
        cell: (row) => (
          <span className="capitalize text-muted-foreground">
            {row.last_trigger_type?.toLowerCase().replace(/_/g, ' ') ?? '—'}
          </span>
        ),
      },
      {
        id: 'run_type',
        filterKey: 'run_type',
        width: COLUMN_WIDTH.label,
        header: 'Run type',
        description: lakeflowJobFieldDescriptions.runType,
        sortable: true,
        cell: (row) => (
          <span className="capitalize text-muted-foreground">
            {row.last_run_type?.toLowerCase().replace(/_/g, ' ') ?? '—'}
          </span>
        ),
      },
      {
        id: 'last_duration',
        filterKey: 'last_duration',
        width: COLUMN_WIDTH.number,
        header: 'Last dur.',
        description: lakeflowJobFieldDescriptions.lastDuration,
        sortable: true,
        cell: (row) => (
          <span className="font-semibold tabular-nums">
            {formatDurationSeconds(row.last_duration_seconds)}
          </span>
        ),
      },
      {
        id: 'last_run',
        width: COLUMN_WIDTH.identifier,
        header: 'Start / End',
        description: lakeflowJobFieldDescriptions.lastRun,
        sortable: true,
        cell: (row) => (
          <div className="text-xs text-muted-foreground">
            <div>{formatRunTs(row.last_start_time)}</div>
            <div className="text-[10px]">{formatRunTs(row.last_end_time)}</div>
          </div>
        ),
      },
    ],
    [periodLabel]
  );

  const toolbar = (
    <div className="flex flex-wrap items-center gap-x-1.5 gap-y-2">
      <div className="relative w-full max-w-[220px] shrink-0 sm:w-[200px]">
        <Search
          size={14}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Rechercher un job…"
          className="h-8 rounded-full pl-9 text-xs"
          aria-label="Rechercher un job"
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

      <span className="mx-0.5 hidden h-4 w-px shrink-0 bg-border sm:block" aria-hidden />

      <ToggleChip
        active={driftOnly}
        onClick={() => {
          setDriftOnly((v) => !v);
          setPage(1);
        }}
      >
        En dérive
      </ToggleChip>
      <ToggleChip
        active={noRuns}
        onClick={() => {
          setNoRuns((v) => !v);
          setPage(1);
        }}
      >
        Sans exécution
      </ToggleChip>
      <ToggleChip
        active={withRetries}
        onClick={() => {
          setWithRetries((v) => !v);
          setPage(1);
        }}
      >
        Avec retries
      </ToggleChip>

      <ToggleChip
        active={sort === 'problems'}
        onClick={() => {
          setSort('problems');
          setOrder('desc');
          setPage(1);
        }}
      >
        Problèmes d’abord
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

      <button
        type="button"
        onClick={() => refetch()}
        className="ml-auto rounded p-1.5 text-muted-foreground hover:text-foreground"
        aria-label="Rafraîchir"
      >
        <RefreshCw size={14} />
      </button>
    </div>
  );

  return (
    <Content className="mx-auto max-w-[1600px] gap-0 p-4 pb-24 lg:px-6 lg:pb-28">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <ContentTitle>Jobs & Pipelines</ContentTitle>
        {freshness ? (
          <span
            className="text-[11px] font-semibold text-muted-foreground"
            title={data?.as_of ?? undefined}
          >
            {freshness}
          </span>
        ) : null}
      </div>

      {error ? (
        <div className="mb-4 rounded-[var(--card-radius)] border border-danger-border bg-danger-subtle px-4 py-3 text-sm text-danger">
          Impossible de charger les jobs.{' '}
          <button type="button" onClick={() => refetch()} className="underline">
            Réessayer
          </button>
        </div>
      ) : null}

      <ContentMain className="gap-4">
        {loading && !data ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-[120px]" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <ComputeKpiCard
              title="Workflows"
              description={lakeflowJobKpiDescriptions.totalWorkflows}
              value={(data?.total ?? 0).toLocaleString('fr-FR')}
              subtitle={`Période ${periodLabel}`}
              tone="info"
              icon={GitBranch}
            />
            <ComputeKpiCard
              title="Runs terminés"
              description={lakeflowJobKpiDescriptions.terminalRuns}
              value={pageKpis.terminalRuns.toLocaleString('fr-FR')}
              subtitle="Somme sur la page courante"
              tone="purple"
              icon={CheckCircle2}
            />
            <ComputeKpiCard
              title="Succès moyen"
              description={lakeflowJobKpiDescriptions.avgSuccess}
              value={pageKpis.avgSuccess == null ? '—' : formatPct(pageKpis.avgSuccess)}
              subtitle="Moyenne page courante · période header"
              tone="success"
              icon={CheckCircle2}
            />
            <ComputeKpiCard
              title="En dérive"
              description={lakeflowJobKpiDescriptions.driftCount}
              value={pageKpis.driftCount.toLocaleString('fr-FR')}
              subtitle="Durée > 20 % vs baseline 14 j"
              tone="warning"
              icon={AlertTriangle}
            />
            <ComputeKpiCard
              title="Coût total"
              description={lakeflowJobKpiDescriptions.totalCost}
              value={formatCompactCurrency(data?.total_cost_usd ?? null)}
              subtitle={
                data?.jobs_with_cost
                  ? `${data.jobs_with_cost.toLocaleString('fr-FR')} jobs avec coût connu`
                  : 'Aucun job sur cluster JOB'
              }
              tone="purple"
              icon={DollarSign}
            />
          </div>
        )}

        <ComputeDataTable
          tableId="lakeflow-jobs-list"
          columns={columns}
          rows={items}
          rowKey={(row) => `${row.workspace_id}-${row.workflow_id}`}
          loading={loading && !data}
          emptyTitle="Aucun job sur cette fenêtre"
          emptyDescription="Élargissez la période dans le header ou réinitialisez les filtres."
          toolbar={toolbar}
          sort={{ key: sort, direction: order }}
          onSortChange={handleSortChange}
          filterView="lakeflow-jobs"
          filters={filters}
          onFiltersChange={changeFilters}
          minWidthClassName="min-w-[1480px]"
          pagination={
            data
              ? {
                  currentPage: data.page,
                  totalPages,
                  totalItems: data.total,
                  startIndex,
                  endIndex,
                  hasPreviousPage: data.page > 1,
                  hasNextPage: data.page < totalPages,
                  onPrevious: () => setPage((p) => Math.max(1, p - 1)),
                  onNext: () => setPage((p) => p + 1),
                }
              : undefined
          }
        />
      </ContentMain>
    </Content>
  );
}
