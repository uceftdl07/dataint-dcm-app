import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Activity, Boxes, Cpu, DollarSign, RefreshCw, ShieldAlert } from 'lucide-react';
import {
  ComputeCostGrainTabs,
  type ComputeCostGrainTabKey,
} from '../components/domain/compute/compute-cost-tabs';
import {
  ComputeDataTable,
  type ComputeDataTableColumn,
} from '../components/domain/compute/compute-data-table';
import { COLUMN_WIDTH } from '../components/domain/compute/compute-column-widths';
import { ComputeEmptyState } from '../components/domain/compute/compute-empty-state';
import { ComputeJobDrawer } from '../components/domain/compute/compute-job-drawer';
import { ComputeKpiCard } from '../components/domain/compute/compute-kpi-card';
import { Content, ContentHeader, ContentMain, ContentTitle } from '../components/layout/content';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Skeleton } from '../components/ui/skeleton';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { useWorkspaceLabelResolver } from '../hooks/useWorkspaceLabelResolver';
import {
  useComputeJobCostTrend,
  useComputeJobDetail,
  useComputeJobUptimeTrend,
  useComputeJobsCostData,
  useComputeJobsEfficiencyData,
  useComputeJobsOverviewData,
} from '../hooks/useComputeJobsQueries';
import { utilizationBadgeVariant } from '../lib/compute/badges';
import {
  autoscalingLabel,
  formatDeltaPct,
  formatDeltaPts,
  formatHours,
  formatNumber,
  formatPct,
  formatUsd,
  lastNDaysPeriodIso,
  utilizationLabel,
} from '../lib/compute/format';
import { serverPaginationProps } from '../lib/compute/server-pagination';
import { cn } from '../lib/utils';
import type {
  ComputeJobCostItem,
  ComputeJobEfficiencyItem,
  ComputeJobsOverviewItem,
  ComputeJobWindow,
  ComputeJobWindowDays,
  ComputeMetricTrendGranularity,
} from '../types/api';

const PAGE_SIZE = 25;

/** Days of history the drawer trends cover, both granularities included. */
const DRAWER_TREND_DAYS = 90;

/** Sort accepted by the efficiency endpoint → the column that carries it. */
const EFF_SORT_COLUMN = {
  savings_desc: 'savings',
  uptime: 'uptime',
  name: 'job',
} as const;

/** The covered window as reported by the API — read from the response, never recomputed. */
function coveredPeriodLabel(window: ComputeJobWindow | null | undefined): string {
  if (!window?.from_date || !window?.to_date) return '—';
  return `${window.from_date} → ${window.to_date}`;
}

/**
 * The four windows materialized in gold, the same four as the clusters and
 * warehouses pages. Static by design: each read hits a pre-aggregated snapshot per
 * window, it does not compose a free range.
 */
const ROLLING_WINDOWS: { value: ComputeJobWindowDays; label: string }[] = [
  { value: 1, label: 'Daily' },
  { value: 7, label: 'Last 7d' },
  { value: 30, label: 'Last 30d' },
  { value: 90, label: 'Last 90d' },
];

/** Exclusive chip group for the rolling window. */
function WindowChipGroup({
  options,
  value,
  onChange,
}: {
  options: { value: ComputeJobWindowDays; label: string }[];
  value: ComputeJobWindowDays;
  onChange: (next: ComputeJobWindowDays) => void;
}) {
  return (
    <div
      className="flex shrink-0 items-center gap-0.5 rounded-full border border-border bg-muted/30 p-0.5"
      role="group"
      aria-label="Rolling window"
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={cn(
            'rounded-full px-3 py-1.5 text-xs font-bold transition-colors',
            value === option.value
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-card hover:text-foreground'
          )}
          aria-pressed={value === option.value}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function WorkspaceCell({
  workspaceId,
  resolveWithId,
}: {
  workspaceId: string;
  resolveWithId: ReturnType<typeof useWorkspaceLabelResolver>['resolveWithId'];
}) {
  const workspace = resolveWithId(workspaceId);
  return (
    <div
      className="truncate font-medium text-foreground"
      title={workspace.id ? `${workspace.label} · ${workspace.id}` : workspace.label}
    >
      {workspace.label}
    </div>
  );
}

/** The job name, with the stable id below and as fallback when the name is empty. */
function JobCell({ name, id }: { name: string | null | undefined; id: string }) {
  return (
    <div className="min-w-0">
      <div className="truncate font-semibold text-foreground">{name || id}</div>
      <div className="truncate font-mono text-[10px] text-muted-foreground">{id}</div>
    </div>
  );
}

/** Cost rank within the window, with a badge on the top-cost job. */
function RankCell({ item }: { item: ComputeJobCostItem }): ReactNode {
  return (
    <div className="flex items-center gap-2">
      <span className="font-semibold tabular-nums">{item.cost_rank ?? '—'}</span>
      {item.is_top_cost ? <Badge variant="warning">Top</Badge> : null}
    </div>
  );
}

/**
 * Value of the previous window, with its variation underneath.
 *
 * An absent value is "not measured", never `0`: the first window of a job has no
 * predecessor, and the backend nulls the value and its delta together.
 */
function PrevWindowCell({ value, delta }: { value: string | null; delta?: string | null }) {
  if (value == null) return <span className="text-muted-foreground">—</span>;
  return (
    <div>
      <div className="font-semibold tabular-nums">{value}</div>
      {delta ? (
        <div className="text-[10px] font-bold tabular-nums text-muted-foreground">{delta}</div>
      ) : null}
    </div>
  );
}

/**
 * Sizing verdict as a badge, rendered like the all-purpose page: an unmeasured job
 * reads `—` in an outline badge rather than being dropped from the column. No
 * zombie variant at this grain — a job cluster dies with its run (024 R8).
 */
function utilizationStatusBadge(status: string | null | undefined) {
  return <Badge variant={utilizationBadgeVariant(status)}>{utilizationLabel(status)}</Badge>;
}

export default function ComputeJobs() {
  const { scope } = useMonitoringScope();
  const { resolveWithId } = useWorkspaceLabelResolver(true);

  const [tab, setTab] = useState<ComputeCostGrainTabKey>('overview');
  const [windowDays, setWindowDays] = useState<ComputeJobWindowDays>(1);

  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<'cost_desc' | 'name'>('cost_desc');
  const [page, setPage] = useState(1);

  const [costSearchInput, setCostSearchInput] = useState('');
  const [costSearch, setCostSearch] = useState('');
  const [costSort, setCostSort] = useState<'cost_desc' | 'name'>('cost_desc');
  const [costPage, setCostPage] = useState(1);

  const [effSearchInput, setEffSearchInput] = useState('');
  const [effSearch, setEffSearch] = useState('');
  const [effSort, setEffSort] = useState<'savings_desc' | 'uptime' | 'name'>('savings_desc');
  const [effPage, setEffPage] = useState(1);

  // The drawer is keyed on the stable id; the title is carried along so the header
  // stays readable while the detail request is still in flight.
  const [selectedJob, setSelectedJob] = useState<{ id: string; title: string } | null>(null);
  const [drawerGranularity, setDrawerGranularity] = useState<ComputeMetricTrendGranularity>('week');
  const [drawerUptimeGranularity, setDrawerUptimeGranularity] =
    useState<ComputeMetricTrendGranularity>('week');

  useEffect(() => {
    const t = window.setTimeout(() => {
      setSearch(searchInput.trim());
      // The page is cut server-side: a narrower search can leave page 7 empty.
      setPage(1);
    }, 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    const t = window.setTimeout(() => {
      setCostSearch(costSearchInput.trim());
      setCostPage(1);
    }, 300);
    return () => window.clearTimeout(t);
  }, [costSearchInput]);

  useEffect(() => {
    const t = window.setTimeout(() => {
      setEffSearch(effSearchInput.trim());
      setEffPage(1);
    }, 300);
    return () => window.clearTimeout(t);
  }, [effSearchInput]);

  // Another window is another population: page 7 of the daily window may not exist
  // over 90 days, and the reverse.
  useEffect(() => {
    setPage(1);
  }, [windowDays, sort]);

  useEffect(() => {
    setCostPage(1);
  }, [windowDays, costSort]);

  useEffect(() => {
    setEffPage(1);
  }, [windowDays, effSort]);

  const overview = useComputeJobsOverviewData({
    window_days: windowDays,
    search,
    sort,
    page,
    pageSize: PAGE_SIZE,
  });

  const cost = useComputeJobsCostData({
    window_days: windowDays,
    search: costSearch,
    sort: costSort,
    page: costPage,
    pageSize: PAGE_SIZE,
    enabled: tab === 'cost',
  });

  const efficiency = useComputeJobsEfficiencyData({
    window_days: windowDays,
    search: effSearch,
    sort: effSort,
    page: effPage,
    pageSize: PAGE_SIZE,
    enabled: tab === 'efficiency',
  });

  // Frozen at mount: a range recomputed each render would churn the trend cache keys.
  const drawerPeriod = useMemo(() => lastNDaysPeriodIso(DRAWER_TREND_DAYS), []);
  const jobDetail = useComputeJobDetail(selectedJob?.id ?? null, windowDays);
  const jobCostTrend = useComputeJobCostTrend({
    jobId: selectedJob?.id ?? null,
    granularity: drawerGranularity,
    ...drawerPeriod,
  });
  const jobUptimeTrend = useComputeJobUptimeTrend({
    jobId: selectedJob?.id ?? null,
    granularity: drawerUptimeGranularity,
    ...drawerPeriod,
  });

  // Both row shapes carry the stable id and its name: one opener for the 3 tabs.
  const openJob = useCallback((row: { job_id: string; job_name: string | null }) => {
    setSelectedJob({ id: row.job_id, title: row.job_name || row.job_id });
  }, []);
  const closeJob = useCallback(() => setSelectedJob(null), []);

  const items = useMemo(() => overview.data?.items ?? [], [overview.data?.items]);
  const searchActive = Boolean(search);
  const costItems = useMemo(() => cost.data?.items ?? [], [cost.data?.items]);
  const costSearchActive = Boolean(costSearch);
  const effItems = useMemo(() => efficiency.data?.items ?? [], [efficiency.data?.items]);
  const effSearchActive = Boolean(effSearch);

  // Each tab echoes the window of its own read; the overview one is the fallback
  // while a lazily-enabled tab has not answered yet.
  const tabWindow = {
    overview: overview.data?.window,
    cost: cost.data?.window,
    efficiency: efficiency.data?.window,
  }[tab];
  const coveredPeriod = coveredPeriodLabel(tabWindow ?? overview.data?.window);

  const topCostItem = useMemo(
    () => costItems.find((it) => it.is_top_cost) ?? costItems[0] ?? null,
    [costItems]
  );
  const dbuOnPage = useMemo(
    () => costItems.reduce((sum, it) => sum + (Number(it.dbu_quantity) || 0), 0),
    [costItems]
  );

  /**
   * Averages over the visible page, computed on measured rows only: a job with no
   * `node_timeline` sample must not pull the average toward 0.
   */
  const effAverages = useMemo(() => {
    const mean = (values: (number | null)[]) => {
      const measured = values.filter((v): v is number => v != null);
      if (!measured.length) return null;
      return measured.reduce((sum, v) => sum + v, 0) / measured.length;
    };
    return {
      cpuP95: mean(effItems.map((it) => it.cpu_util_p95_pct)),
      memP95: mean(effItems.map((it) => it.mem_util_p95_pct)),
      savings: effItems.reduce((sum, it) => sum + (Number(it.estimated_savings_usd) || 0), 0),
    };
  }, [effItems]);

  const pagination = useMemo(
    () =>
      serverPaginationProps(
        overview.data ? { ...overview.data, itemCount: items.length } : null,
        page,
        setPage
      ),
    [overview.data, items.length, page]
  );

  const costPagination = useMemo(
    () =>
      serverPaginationProps(
        cost.data ? { ...cost.data, itemCount: costItems.length } : null,
        costPage,
        setCostPage
      ),
    [cost.data, costItems.length, costPage]
  );

  const effPagination = useMemo(
    () =>
      serverPaginationProps(
        efficiency.data ? { ...efficiency.data, itemCount: effItems.length } : null,
        effPage,
        setEffPage
      ),
    [efficiency.data, effItems.length, effPage]
  );

  const workspaceColumn = useMemo(
    (): ComputeDataTableColumn<ComputeJobCostItem> => ({
      id: 'workspace',
      width: COLUMN_WIDTH.identifier,
      header: 'Workspace',
      description: 'Databricks workspace the job runs in.',
      cell: (row) => <WorkspaceCell workspaceId={row.workspace_id} resolveWithId={resolveWithId} />,
    }),
    [resolveWithId]
  );

  const columns = useMemo(
    (): ComputeDataTableColumn<ComputeJobsOverviewItem>[] => [
      workspaceColumn,
      {
        id: 'job',
        width: COLUMN_WIDTH.name,
        header: 'Job',
        description: 'Stable job — the ephemeral run clusters are aggregated to it.',
        sortable: true,
        cell: (row) => <JobCell name={row.job_name} id={row.job_id} />,
      },
      {
        id: 'cost',
        width: COLUMN_WIDTH.metric,
        header: 'Cost',
        description: 'Total cost of the job clusters over the window.',
        align: 'right',
        sortable: true,
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatUsd(row.cost_usd)}</span>
        ),
      },
      {
        id: 'cost_prev',
        width: COLUMN_WIDTH.metric,
        header: 'Prev cost',
        description:
          'Cost over the previous window of the same length, with its variation underneath.',
        align: 'right',
        cell: (row) => (
          <PrevWindowCell
            value={row.cost_usd_prev_window == null ? null : formatUsd(row.cost_usd_prev_window)}
            delta={row.cost_delta_pct == null ? null : formatDeltaPct(row.cost_delta_pct)}
          />
        ),
      },
      {
        id: 'lifetime',
        width: COLUMN_WIDTH.duration,
        header: 'Lifetime',
        description: 'Cumulated uptime of the job clusters over the window.',
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatHours(row.uptime_hours)}</span>
        ),
      },
      {
        id: 'lifetime_prev',
        width: COLUMN_WIDTH.duration,
        header: 'Prev lifetime',
        description: 'Cumulated uptime over the previous window, with its variation underneath.',
        align: 'right',
        cell: (row) => (
          <PrevWindowCell
            value={
              row.uptime_hours_prev_window == null
                ? null
                : formatHours(row.uptime_hours_prev_window)
            }
            delta={
              row.uptime_hours_delta_pct == null ? null : formatDeltaPct(row.uptime_hours_delta_pct)
            }
          />
        ),
      },
      {
        id: 'utilization',
        width: COLUMN_WIDTH.status,
        header: 'Utilization',
        description:
          'Sizing verdict of the run clusters. A job billed without a node timeline is unmeasured and reads “—”.',
        cell: (row) => utilizationStatusBadge(row.utilization_status),
      },
      {
        id: 'clusters',
        width: COLUMN_WIDTH.number,
        header: 'Clusters',
        description: 'Distinct ephemeral job clusters seen over the window (run count).',
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatNumber(row.cluster_count)}</span>
        ),
      },
    ],
    [workspaceColumn]
  );

  const costColumns = useMemo(
    (): ComputeDataTableColumn<ComputeJobCostItem>[] => [
      {
        id: 'rank',
        width: COLUMN_WIDTH.number,
        header: 'Rank',
        description: 'Cost rank within the window — 1 is the most expensive job.',
        cell: (row) => <RankCell item={row} />,
      },
      workspaceColumn,
      {
        id: 'job',
        width: COLUMN_WIDTH.name,
        header: 'Job',
        description: 'Stable job — the ephemeral run clusters are aggregated to it.',
        sortable: true,
        cell: (row) => <JobCell name={row.job_name} id={row.job_id} />,
      },
      {
        id: 'cost',
        width: COLUMN_WIDTH.metric,
        header: 'Cost',
        description: 'Total cost of the job clusters over the window.',
        align: 'right',
        sortable: true,
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatUsd(row.cost_usd)}</span>
        ),
      },
      {
        id: 'cost_prev',
        width: COLUMN_WIDTH.metric,
        header: 'Prev cost',
        description:
          'Cost over the previous window of the same length, with its variation underneath.',
        align: 'right',
        cell: (row) => (
          <PrevWindowCell
            value={row.cost_usd_prev_window == null ? null : formatUsd(row.cost_usd_prev_window)}
            delta={row.cost_delta_pct == null ? null : formatDeltaPct(row.cost_delta_pct)}
          />
        ),
      },
      {
        id: 'dbu',
        width: COLUMN_WIDTH.number,
        header: 'DBU',
        description: 'Databricks Units consumed by the job clusters over the window.',
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatNumber(row.dbu_quantity)}</span>
        ),
      },
    ],
    [workspaceColumn]
  );

  const effColumns = useMemo(
    (): ComputeDataTableColumn<ComputeJobEfficiencyItem>[] => [
      {
        id: 'workspace',
        width: COLUMN_WIDTH.identifier,
        header: 'Workspace',
        description: 'Databricks workspace the job runs in.',
        cell: (row) => (
          <WorkspaceCell workspaceId={row.workspace_id} resolveWithId={resolveWithId} />
        ),
      },
      {
        id: 'job',
        width: COLUMN_WIDTH.name,
        header: 'Job',
        description: 'Stable job — the utilization of its run clusters is aggregated to it.',
        sortable: true,
        cell: (row) => <JobCell name={row.job_name} id={row.job_id} />,
      },
      {
        id: 'clusters',
        width: COLUMN_WIDTH.number,
        header: 'Clusters',
        description:
          'Job clusters measured over the window. May differ from the Cost tab: cost comes from billing, utilization from the node timeline.',
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatNumber(row.cluster_count)}</span>
        ),
      },
      {
        id: 'driver_node',
        width: COLUMN_WIDTH.timestamp,
        header: 'Driver node',
        description: 'Driver instance type of the run clusters over the window.',
        cell: (row) => (
          <div className="truncate" title={row.driver_node_type ?? undefined}>
            {row.driver_node_type ?? '—'}
          </div>
        ),
      },
      {
        id: 'worker_node',
        width: COLUMN_WIDTH.timestamp,
        header: 'Worker node',
        description: 'Worker instance type of the run clusters over the window.',
        cell: (row) => (
          <div className="truncate" title={row.worker_node_type ?? undefined}>
            {row.worker_node_type ?? '—'}
          </div>
        ),
      },
      {
        id: 'autoscaling',
        width: COLUMN_WIDTH.badge,
        header: 'Autoscaling',
        description: 'Whether the run clusters autoscale.',
        cell: (row) =>
          row.autoscale_enabled == null ? (
            <span className="text-muted-foreground">—</span>
          ) : (
            <Badge variant={row.autoscale_enabled ? 'success' : 'outline'}>
              {autoscalingLabel(row.autoscale_enabled)}
            </Badge>
          ),
      },
      {
        id: 'workers_avg',
        width: COLUMN_WIDTH.number,
        header: 'Workers avg',
        description: 'Average worker count observed per minute over the window.',
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatNumber(row.worker_count_avg)}</span>
        ),
      },
      {
        id: 'workers_max',
        width: COLUMN_WIDTH.number,
        header: 'Workers max',
        description: 'Highest worker count observed per minute — not the configured bound.',
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatNumber(row.worker_count_max)}</span>
        ),
      },
      {
        id: 'uptime',
        width: COLUMN_WIDTH.duration,
        header: 'Uptime',
        description: 'Uptime cumulated over the job runs of the window — not a cluster lifetime.',
        align: 'right',
        sortable: true,
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatHours(row.uptime_hours)}</span>
        ),
      },
      {
        id: 'uptime_prev',
        width: COLUMN_WIDTH.duration,
        header: 'Uptime prev',
        description: 'Cumulated uptime over the previous window of the same length.',
        align: 'right',
        cell: (row) => (
          <PrevWindowCell
            value={
              row.uptime_hours_prev_window == null
                ? null
                : formatHours(row.uptime_hours_prev_window)
            }
            delta={formatDeltaPct(row.uptime_hours_delta_pct)}
          />
        ),
      },
      {
        id: 'idle',
        width: COLUMN_WIDTH.metric,
        header: 'Idle',
        description: 'Share of the measured uptime with no work on the run clusters.',
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatPct(row.idle_pct)}</span>
        ),
      },
      {
        id: 'idle_prev',
        width: COLUMN_WIDTH.metric,
        header: 'Idle prev',
        description: 'Idle share over the previous window, and its variation in percentage points.',
        align: 'right',
        cell: (row) => (
          <PrevWindowCell
            value={row.idle_pct_prev_window == null ? null : formatPct(row.idle_pct_prev_window)}
            delta={formatDeltaPts(row.idle_pct_delta_pts)}
          />
        ),
      },
      {
        id: 'cpu_avg',
        width: COLUMN_WIDTH.number,
        header: 'CPU avg',
        description: 'Average CPU utilization of the run clusters over the window.',
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatPct(row.cpu_util_avg_pct)}</span>
        ),
      },
      {
        id: 'cpu_p95',
        width: COLUMN_WIDTH.number,
        header: 'CPU p95',
        description: '95th percentile of CPU utilization — the peak load, outliers excluded.',
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatPct(row.cpu_util_p95_pct)}</span>
        ),
      },
      {
        id: 'mem_avg',
        width: COLUMN_WIDTH.number,
        header: 'Mem avg',
        description: 'Average memory utilization of the run clusters over the window.',
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatPct(row.mem_util_avg_pct)}</span>
        ),
      },
      {
        id: 'mem_p95',
        width: COLUMN_WIDTH.number,
        header: 'Mem p95',
        description: '95th percentile of memory utilization over the window.',
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatPct(row.mem_util_p95_pct)}</span>
        ),
      },
      {
        id: 'status',
        width: COLUMN_WIDTH.status,
        header: 'Status',
        description: 'Sizing verdict derived from the CPU, memory and idle metrics.',
        cell: (row) => (
          <Badge variant={utilizationBadgeVariant(row.utilization_status)}>
            {utilizationLabel(row.utilization_status)}
          </Badge>
        ),
      },
      {
        id: 'recommended_node',
        width: COLUMN_WIDTH.timestamp,
        header: 'Recommended node',
        description: 'Instance type the rightsizing rule suggests for the run clusters.',
        cell: (row) => (
          <div className="truncate" title={row.recommended_node_type ?? undefined}>
            {row.recommended_node_type ?? '—'}
          </div>
        ),
      },
      {
        id: 'savings',
        width: COLUMN_WIDTH.metric,
        header: 'Est. savings',
        description: 'Cost the suggested resizing would avoid over the window.',
        align: 'right',
        sortable: true,
        cell: (row) => (
          <span className="font-semibold tabular-nums">
            {row.estimated_savings_usd == null ? '—' : formatUsd(row.estimated_savings_usd)}
          </span>
        ),
      },
    ],
    [resolveWithId]
  );

  const sortKey = sort === 'name' ? 'job' : 'cost';
  const handleSortChange = (key: string) => {
    setSort(key === 'job' ? 'name' : 'cost_desc');
  };

  const costSortKey = costSort === 'name' ? 'job' : 'cost';
  const handleCostSortChange = (key: string) => {
    setCostSort(key === 'job' ? 'name' : 'cost_desc');
  };

  // The endpoint only sorts on these three; any other header click falls back to
  // the default rather than sending a value the backend would reject.
  const effSortKey = EFF_SORT_COLUMN[effSort];
  const handleEffSortChange = (key: string) => {
    if (key === 'job') return setEffSort('name');
    if (key === 'uptime') return setEffSort('uptime');
    return setEffSort('savings_desc');
  };

  return (
    <Content className="mx-auto max-w-[1600px] gap-0 p-4 pb-24 lg:px-6 lg:pb-28">
      <ContentHeader>
        <div>
          <ContentTitle>Job clusters</ContentTitle>
          <p className="mt-2 text-sm text-muted-foreground">
            Job cluster cost aggregated to the stable job — {scope.label}.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            void overview.refetch();
            if (tab === 'cost') void cost.refetch();
            if (tab === 'efficiency') void efficiency.refetch();
          }}
          disabled={overview.fetching}
        >
          <RefreshCw />
          Refresh
        </Button>
      </ContentHeader>

      <ContentMain className="gap-5">
        <ComputeCostGrainTabs value={tab} onChange={setTab} ariaLabel="Job clusters tabs" />

        <div className="flex flex-wrap items-center gap-3">
          <WindowChipGroup options={ROLLING_WINDOWS} value={windowDays} onChange={setWindowDays} />
          <span className="text-xs text-muted-foreground">
            Covered period{' '}
            <span className="font-mono font-semibold text-foreground">{coveredPeriod}</span>
          </span>
        </div>

        {tab === 'overview' ? (
          <>
            <div className="grid grid-cols-1 gap-4 overflow-visible sm:grid-cols-2 xl:grid-cols-3">
              {overview.loading && !overview.data ? (
                Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-32" />)
              ) : (
                <>
                  <ComputeKpiCard
                    title="Total cost"
                    description="Total job cluster cost over the selected window."
                    value={formatUsd(overview.data?.kpis.total_cost_usd)}
                    subtitle={
                      overview.data?.kpis.cost_delta_pct == null
                        ? '—'
                        : `${formatDeltaPct(overview.data.kpis.cost_delta_pct)} vs previous window`
                    }
                    tone="info"
                    icon={DollarSign}
                  />
                  <ComputeKpiCard
                    title="Active jobs"
                    description="Jobs billed over the window."
                    value={formatNumber(overview.data?.kpis.active_jobs ?? null)}
                    subtitle="Billed over the window"
                    tone="success"
                    icon={Boxes}
                  />
                  <Link
                    to="/databricks/compute/recommendations?object_type=JOB"
                    className="block overflow-hidden rounded-[var(--card-radius)] transition-shadow hover:shadow-[var(--card-hover-shadow)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    aria-label="View job recommendations"
                  >
                    <ComputeKpiCard
                      title="Recommendations & forecast"
                      description="Open the cost recommendations and forecast for jobs."
                      value="View"
                      subtitle="Jobs only · click to open"
                      tone="purple"
                      icon={ShieldAlert}
                    />
                  </Link>
                </>
              )}
            </div>

            {items.length || searchActive ? (
              <ComputeDataTable
                tableId="compute-jobs-overview"
                columns={columns}
                rows={items}
                rowKey={(row) => `${row.workspace_id}-${row.job_id}`}
                loading={overview.loading && !overview.data}
                emptyTitle="No jobs"
                emptyDescription="No job cluster cost over this window and perimeter."
                onRowClick={openJob}
                sort={{ key: sortKey, direction: sort === 'name' ? 'asc' : 'desc' }}
                onSortChange={handleSortChange}
                pagination={pagination}
                toolbar={
                  <div className="relative w-full max-w-[280px] shrink-0">
                    <Input
                      value={searchInput}
                      onChange={(e) => setSearchInput(e.target.value)}
                      placeholder="Search job name or id…"
                      className="h-8 rounded-full text-xs"
                      aria-label="Search jobs"
                    />
                  </div>
                }
              />
            ) : (
              <ComputeEmptyState
                title="No jobs"
                description="No job cluster cost over this window and perimeter."
              />
            )}
          </>
        ) : null}

        {tab === 'cost' ? (
          <>
            <div className="grid grid-cols-1 gap-4 overflow-visible sm:grid-cols-2 xl:grid-cols-3">
              <ComputeKpiCard
                title="Total cost"
                description="Total job cluster cost over the selected window."
                value={formatUsd(overview.data?.kpis.total_cost_usd)}
                subtitle={
                  overview.data?.kpis.cost_delta_pct == null
                    ? '—'
                    : `${formatDeltaPct(overview.data.kpis.cost_delta_pct)} vs previous window`
                }
                tone="info"
                icon={DollarSign}
              />
              <ComputeKpiCard
                title="DBU (current page)"
                description="Databricks Units summed over the rows visible on this page."
                value={formatNumber(dbuOnPage)}
                subtitle="Sum over visible rows"
                tone="success"
                icon={Cpu}
              />
              <ComputeKpiCard
                title="Top costly"
                description="Most expensive job over the window."
                value={topCostItem ? topCostItem.job_name || topCostItem.job_id : '—'}
                subtitle={topCostItem?.cost_usd != null ? formatUsd(topCostItem.cost_usd) : '—'}
                tone="warning"
                icon={DollarSign}
              />
            </div>

            {costItems.length || costSearchActive ? (
              <ComputeDataTable
                tableId="compute-jobs-cost"
                columns={costColumns}
                rows={costItems}
                rowKey={(row) => `${row.workspace_id}-${row.job_id}`}
                loading={cost.loading && !cost.data}
                emptyTitle="No jobs"
                emptyDescription="No job cluster cost over this window and perimeter."
                onRowClick={openJob}
                sort={{ key: costSortKey, direction: costSort === 'name' ? 'asc' : 'desc' }}
                onSortChange={handleCostSortChange}
                pagination={costPagination}
                toolbar={
                  <div className="relative w-full max-w-[280px] shrink-0">
                    <Input
                      value={costSearchInput}
                      onChange={(e) => setCostSearchInput(e.target.value)}
                      placeholder="Search job name or id…"
                      className="h-8 rounded-full text-xs"
                      aria-label="Search jobs cost"
                    />
                  </div>
                }
              />
            ) : (
              <ComputeEmptyState
                title="No jobs"
                description="No job cluster cost over this window and perimeter."
              />
            )}
          </>
        ) : null}

        {tab === 'efficiency' ? (
          <>
            <div className="grid grid-cols-1 gap-4 overflow-visible sm:grid-cols-2 xl:grid-cols-3">
              <ComputeKpiCard
                title="Avg CPU p95 (current page)"
                description="CPU peak averaged over the measured rows visible on this page."
                value={formatPct(effAverages.cpuP95, 1)}
                subtitle="Measured rows only"
                tone="info"
                icon={Cpu}
              />
              <ComputeKpiCard
                title="Avg Mem p95 (current page)"
                description="Memory peak averaged over the measured rows visible on this page."
                value={formatPct(effAverages.memP95, 1)}
                subtitle="Measured rows only"
                tone="success"
                icon={Activity}
              />
              <ComputeKpiCard
                title="Est. savings (current page)"
                description="Cost the suggested resizings would avoid, summed over the visible rows."
                value={formatUsd(effAverages.savings)}
                subtitle="Sum over visible rows"
                tone="warning"
                icon={DollarSign}
              />
            </div>

            {effItems.length || effSearchActive ? (
              <ComputeDataTable
                tableId="compute-jobs-efficiency"
                columns={effColumns}
                rows={effItems}
                rowKey={(row) => `${row.workspace_id}-${row.job_id}`}
                loading={efficiency.loading && !efficiency.data}
                emptyTitle="No measured jobs"
                emptyDescription="No job utilization over this window and perimeter."
                onRowClick={openJob}
                sort={{ key: effSortKey, direction: effSort === 'name' ? 'asc' : 'desc' }}
                onSortChange={handleEffSortChange}
                pagination={effPagination}
                minWidthClassName="min-w-[2700px]"
                toolbar={
                  <div className="relative w-full max-w-[280px] shrink-0">
                    <Input
                      value={effSearchInput}
                      onChange={(e) => setEffSearchInput(e.target.value)}
                      placeholder="Search job name or id…"
                      className="h-8 rounded-full text-xs"
                      aria-label="Search jobs efficiency"
                    />
                  </div>
                }
              />
            ) : (
              <ComputeEmptyState
                title="No measured jobs"
                description="No job utilization over this window and perimeter. A job billed without a node timeline is only listed on the Cost tab."
              />
            )}
          </>
        ) : null}
      </ContentMain>

      <ComputeJobDrawer
        open={Boolean(selectedJob)}
        onClose={closeJob}
        title={selectedJob?.title ?? ''}
        detail={jobDetail.data}
        detailLoading={jobDetail.loading}
        detailError={jobDetail.error}
        trend={jobCostTrend.data}
        trendLoading={jobCostTrend.loading}
        trendError={jobCostTrend.error}
        granularity={drawerGranularity}
        onGranularityChange={setDrawerGranularity}
        uptimeTrend={jobUptimeTrend.data}
        uptimeTrendLoading={jobUptimeTrend.loading}
        uptimeTrendError={jobUptimeTrend.error}
        uptimeGranularity={drawerUptimeGranularity}
        onUptimeGranularityChange={setDrawerUptimeGranularity}
        workspaceLabel={
          jobDetail.data?.workspace_id
            ? resolveWithId(jobDetail.data.workspace_id).label
            : undefined
        }
      />
    </Content>
  );
}
