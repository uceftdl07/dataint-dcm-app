import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  Cpu,
  DollarSign,
  Info,
  RefreshCw,
  ShieldAlert,
  Snowflake,
  Tag,
} from 'lucide-react';
import { ComputeClusterDrawer } from '../components/domain/compute/compute-cluster-drawer';
import {
  ComputeDataTable,
  type ComputeDataTableColumn,
  type SortDirection,
} from '../components/domain/compute/compute-data-table';
import { COLUMN_WIDTH } from '../components/domain/compute/compute-column-widths';
import { ComputeEmptyState } from '../components/domain/compute/compute-empty-state';
import { ComputeKpiCard } from '../components/domain/compute/compute-kpi-card';
import { ComputeTabs, type ComputeClustersTabKey } from '../components/domain/compute/compute-tabs';
import { Content, ContentHeader, ContentMain, ContentTitle } from '../components/layout/content';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Skeleton } from '../components/ui/skeleton';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { useWorkspaceLabelResolver } from '../hooks/useWorkspaceLabelResolver';
import {
  useComputeClusterCostTrend,
  useComputeClusterDetail,
  useComputeClusterLifetimeTrend,
  useComputeClustersCostData,
  useComputeClustersEfficiencyData,
  useComputeClustersGovernanceData,
  useComputeClustersOverviewData,
} from '../hooks/useComputeClustersQueries';
import { severityBadgeVariant, utilizationBadgeVariant } from '../lib/compute/badges';
import {
  computeClusterFieldDescriptions,
  computeClusterKpiDescriptions,
} from '../lib/compute/field-descriptions';
import {
  autoscalingLabel,
  formatDeltaPct,
  formatDeltaPts,
  formatHours,
  formatNumber,
  formatPct,
  formatUsd,
  formatWorkerBounds,
  severityLabel,
  subtractDaysIso,
  todayIsoUtc,
  utilizationLabel,
} from '../lib/compute/format';
import { countActiveColumnFilters, withColumnFilter } from '../lib/compute/column-filters';
import { serverPaginationProps } from '../lib/compute/server-pagination';
import { cn } from '../lib/utils';
import type {
  ComputeClusterCostItem,
  ComputeClusterEfficiencyItem,
  ComputeClusterGovernanceItem,
  ComputeClustersOverviewItem,
  ComputeClusterWindow,
  ComputeClusterWindowDays,
  ComputeColumnFilterValues,
  ComputeMetricTrendGranularity,
} from '../types/api';

const OVERVIEW_PAGE_SIZE = 25;

/** Une seule instance vide, pour ne pas relancer les mémos à chaque remise à zéro. */
const NO_FILTERS: ComputeColumnFilterValues = {};

/**
 * Statuts d'utilisation proposés par les barres d'outils — `''` étant « tous ».
 * Le serveur, lui, liste ceux qui existent réellement dans le périmètre.
 */
const UTILIZATION_FILTERS = ['', 'OVER', 'UNDER', 'OPTIMAL', 'ZOMBIE'];

/** Groupes SKU proposés par la barre d'outils de l'onglet Coût. */
const SKU_GROUP_OPTIONS = ['Classic', 'Photon', 'Serverless'];

/** Sévérités proposées par la barre d'outils de l'onglet Gouvernance. */
const SEVERITY_OPTIONS: { value: string; label: string }[] = [
  { value: 'HIGH', label: 'High' },
  { value: 'MEDIUM', label: 'Medium' },
  { value: 'LOW', label: 'Low' },
];

/**
 * The four windows materialized in gold. They are static by design: the page
 * reads a pre-aggregated snapshot per window, it does not compose a free range.
 */
const ROLLING_WINDOWS: { value: ComputeClusterWindowDays; label: string }[] = [
  { value: 1, label: 'Daily' },
  { value: 7, label: 'Last 7d' },
  { value: 30, label: 'Last 30d' },
  { value: 90, label: 'Last 90d' },
];

function FilterChip({
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

function WorkspaceCell({
  name,
  workspaceId,
  resolveWithId,
}: {
  /** `workspace_name` as joined in gold — authoritative when present. */
  name?: string | null;
  workspaceId: string;
  resolveWithId: ReturnType<typeof useWorkspaceLabelResolver>['resolveWithId'];
}) {
  const workspace = resolveWithId(workspaceId);
  const label = name?.trim() || workspace.label;
  // L'infobulle porte le libellé **complet** avant l'identifiant : la colonne est
  // coupée à sa largeur, et n'annoncer que l'id rendrait le nom illisible.
  return (
    <div
      className="truncate font-medium text-foreground"
      title={workspace.id ? `${label} · ${workspace.id}` : label}
    >
      {label}
    </div>
  );
}

/**
 * Value over the previous window of the same length. A cluster that did not
 * exist then has nothing to compare against: that reads `—`, never `0`.
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

function NumberCell({ value }: { value: string }) {
  return <span className="font-semibold tabular-nums">{value}</span>;
}

function utilizationStatusBadge(status: string | null | undefined) {
  const normalized = (status || '').trim().toUpperCase();
  const isZombie = normalized === 'ZOMBIE';
  return (
    <Badge variant={utilizationBadgeVariant(normalized || null, isZombie)}>
      {utilizationLabel(normalized || null)}
    </Badge>
  );
}

function ClusterCell({ name, id }: { name: string | null | undefined; id: string }) {
  // `truncate` par ligne : les points de suspension d'un bloc ne s'appliquent pas à
  // ses enfants de type bloc, seulement à son texte direct.
  return (
    <div className="min-w-0">
      <div className="truncate font-semibold text-foreground">{name || id}</div>
      <div className="truncate font-mono text-[10px] text-muted-foreground">{id}</div>
    </div>
  );
}

export default function ComputeClusters() {
  const { scope } = useMonitoringScope();
  const { resolveWithId } = useWorkspaceLabelResolver(true);

  const [tab, setTab] = useState<ComputeClustersTabKey>('overview');
  // Deliberately not reset when the tab changes: the range is a page-level
  // reading choice, it must survive Overview → Cost → Efficiency.
  const [windowDays, setWindowDays] = useState<ComputeClusterWindowDays>(1);
  const [drawerGranularity, setDrawerGranularity] = useState<ComputeMetricTrendGranularity>('week');
  const [drawerLifetimeGranularity, setDrawerLifetimeGranularity] =
    useState<ComputeMetricTrendGranularity>('week');

  const [costSearchInput, setCostSearchInput] = useState('');
  const [costSearch, setCostSearch] = useState('');
  const [costSort, setCostSort] = useState<'cost_desc' | 'name' | 'rank'>('cost_desc');
  const [costPage, setCostPage] = useState(1);

  const [effPage, setEffPage] = useState(1);

  const [govMissingTags, setGovMissingTags] = useState(false);
  const [govDbrObsolete, setGovDbrObsolete] = useState(false);
  const [govPage, setGovPage] = useState(1);

  const [overviewSearchInput, setOverviewSearchInput] = useState('');
  const [overviewSearch, setOverviewSearch] = useState('');
  type OverviewSortKey =
    | 'cluster'
    | 'workspace'
    | 'cluster_lifetime'
    | 'cluster_lifetime_prev'
    | 'cost'
    | 'cost_prev'
    | 'utilization'
    | 'governance';
  const [overviewSortKey, setOverviewSortKey] = useState<OverviewSortKey>('cost');
  const [overviewSortDirection, setOverviewSortDirection] = useState<SortDirection>('desc');
  const [overviewPage, setOverviewPage] = useState(1);

  const [selectedCluster, setSelectedCluster] = useState<{ id: string; title: string } | null>(
    null
  );

  // Un état de filtres par tableau. Il est la **seule** source des prédicats de
  // colonne : les paramètres historiques (`utilization_status`, `sku_group`,
  // `severity`, `search`) en sont dérivés, jamais stockés à part, faute de quoi le
  // serveur reçoit deux valeurs pour un même prédicat et répond 422.
  const [overviewFilters, setOverviewFilters] = useState<ComputeColumnFilterValues>(NO_FILTERS);
  const [costColumnFilters, setCostColumnFilters] = useState<ComputeColumnFilterValues>(NO_FILTERS);
  const [effFilters, setEffFilters] = useState<ComputeColumnFilterValues>(NO_FILTERS);
  const [govFilters, setGovFilters] = useState<ComputeColumnFilterValues>(NO_FILTERS);

  useEffect(() => {
    const t = window.setTimeout(() => {
      setCostSearch(costSearchInput.trim());
      setCostPage(1);
    }, 300);
    return () => window.clearTimeout(t);
  }, [costSearchInput]);

  useEffect(() => {
    const t = window.setTimeout(() => {
      setOverviewSearch(overviewSearchInput.trim());
      // The page is cut server-side: a narrower search can leave page 7 empty.
      setOverviewPage(1);
    }, 300);
    return () => window.clearTimeout(t);
  }, [overviewSearchInput]);

  // Changing the range changes the whole population, so does re-sorting it.
  useEffect(() => {
    setOverviewPage(1);
  }, [windowDays, overviewFilters, overviewSortKey, overviewSortDirection]);

  // Un filtre plus étroit peut laisser la page 7 vide : chaque tableau revient à 1.
  useEffect(() => {
    setCostPage(1);
  }, [costColumnFilters]);

  useEffect(() => {
    setEffPage(1);
  }, [effFilters]);

  useEffect(() => {
    setGovPage(1);
  }, [govFilters]);

  useEffect(() => {
    setCostSearchInput('');
    setCostSearch('');
    setCostSort('cost_desc');
    setCostPage(1);
    setOverviewSearchInput('');
    setOverviewSearch('');
    setOverviewSortKey('cost');
    setOverviewSortDirection('desc');
    setOverviewPage(1);
    setEffPage(1);
    setGovMissingTags(false);
    setGovDbrObsolete(false);
    setGovPage(1);
    setOverviewFilters(NO_FILTERS);
    setCostColumnFilters(NO_FILTERS);
    setEffFilters(NO_FILTERS);
    setGovFilters(NO_FILTERS);
  }, [tab]);

  // Les 90 jours du tiroir finissent **aujourd'hui**, pas sur une plage d'en-tête :
  // cette page n'en expose plus, et lire une plage invisible laisserait une page
  // voisine décaler ces courbes sans que rien ne l'indique.
  const drawerPeriod = useMemo(() => {
    const trendEnd = todayIsoUtc();
    return { period_start: subtractDaysIso(trendEnd, 89), period_end: trendEnd };
  }, []);

  // Les combos interrogent le serveur dans le périmètre du tableau : sans la
  // fenêtre, elles listeraient les valeurs du jour pour un tableau en 90 jours.
  const filterScope = useMemo(() => ({ windowDays }), [windowDays]);

  // Valeurs des paramètres historiques, dérivées des filtres de colonne.
  const overviewUtilFilter = overviewFilters.utilization ?? '';
  const costSkuGroup = costColumnFilters.sku_group ?? '';
  const effFilter = effFilters.status ?? '';
  const govSeverity = govFilters.severity ?? '';

  // La colonne « Cluster » de l'onglet Coût et la barre de recherche pilotent le
  // même prédicat (`search`). La barre reste maîtresse de la valeur ; la combo
  // l'alimente, et le filtre exposé au tableau la reflète pour que l'entonnoir
  // s'affiche actif.
  const costFilters = useMemo(
    () => withColumnFilter(costColumnFilters, 'cluster', costSearch),
    [costColumnFilters, costSearch]
  );
  const changeCostFilters = (next: ComputeColumnFilterValues) => {
    const { cluster, ...rest } = next;
    const search = cluster ?? '';
    if (search !== costSearch) {
      setCostSearchInput(search);
      setCostSearch(search);
    }
    setCostColumnFilters(rest);
  };

  // Search, status filter, sort and paging all happen server-side: at `window_days`
  // 90 the rolling table holds ~1.4 M rows, so a client-side pass would only ever
  // see the slice the server had already chosen.
  const overview = useComputeClustersOverviewData({
    window_days: windowDays,
    search: overviewSearch,
    utilization_status: overviewUtilFilter || undefined,
    filters: overviewFilters,
    sort: overviewSortKey,
    sort_direction: overviewSortDirection,
    page: overviewPage,
    pageSize: OVERVIEW_PAGE_SIZE,
  });
  const cost = useComputeClustersCostData({
    window_days: windowDays,
    search: costSearch,
    sku_group: costSkuGroup || undefined,
    filters: costFilters,
    sort: costSort,
    page: costPage,
    pageSize: 25,
    enabled: tab === 'cost',
  });
  const efficiency = useComputeClustersEfficiencyData({
    window_days: windowDays,
    // `ZOMBIE` n'est pas une valeur de `utilization_status` côté endpoint : c'est
    // le drapeau `is_zombie`. La colonne `status` sait l'exprimer (surcharge
    // serveur), d'où la même bascule ici — un seul état, deux paramètres.
    utilization_status: effFilter && effFilter !== 'ZOMBIE' ? effFilter : undefined,
    is_zombie: effFilter === 'ZOMBIE' ? true : undefined,
    filters: effFilters,
    page: effPage,
    pageSize: 25,
    enabled: tab === 'efficiency',
  });
  const governance = useComputeClustersGovernanceData({
    severity: govSeverity || undefined,
    missing_tags: govMissingTags || undefined,
    dbr_obsolete: govDbrObsolete || undefined,
    filters: govFilters,
    page: govPage,
    pageSize: 25,
    enabled: tab === 'governance',
  });

  const overviewItems = useMemo(() => overview.data?.items ?? [], [overview.data?.items]);

  // Now that the server applies them, an over-narrow search returns zero rows. The
  // table has to stay mounted in that case — its toolbar holds the search box the
  // user must reach to widen the query again.
  const overviewFiltersActive = Boolean(
    overviewSearch || countActiveColumnFilters(overviewFilters) > 0
  );

  const overviewPagination = useMemo(
    () =>
      serverPaginationProps(
        overview.data ? { ...overview.data, itemCount: overviewItems.length } : null,
        overviewPage,
        setOverviewPage
      ),
    [overview.data, overviewItems.length, overviewPage]
  );

  const handleOverviewSort = (key: string) => {
    const nextKey = key as OverviewSortKey;
    if (overviewSortKey === nextKey) {
      setOverviewSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setOverviewSortKey(nextKey);
    setOverviewSortDirection(nextKey === 'cluster' || nextKey === 'workspace' ? 'asc' : 'desc');
  };

  const detail = useComputeClusterDetail(selectedCluster?.id ?? null, windowDays);
  const trend = useComputeClusterCostTrend({
    clusterId: selectedCluster?.id ?? null,
    granularity: drawerGranularity,
    ...drawerPeriod,
  });
  // Both trends read the `*_daily` tables over ≈90 days and follow their own
  // granularity: a rolling row is a single point, it cannot draw a curve.
  const lifetimeTrend = useComputeClusterLifetimeTrend({
    clusterId: selectedCluster?.id ?? null,
    granularity: drawerLifetimeGranularity,
    ...drawerPeriod,
  });

  /** The window the API reports as covered — never recomputed from the chip. */
  const activeWindow: ComputeClusterWindow | null = useMemo(() => {
    if (tab === 'cost') return cost.data?.window ?? overview.data?.window ?? null;
    if (tab === 'efficiency') return efficiency.data?.window ?? overview.data?.window ?? null;
    return overview.data?.window ?? null;
  }, [tab, cost.data?.window, efficiency.data?.window, overview.data?.window]);

  const coveredPeriodLabel =
    activeWindow?.from_date && activeWindow.to_date
      ? `${activeWindow.from_date} → ${activeWindow.to_date}`
      : '—';

  /**
   * A Lifetime/IDLE comparison needs twice the window in the efficiency tables, and
   * their source — the `system.compute.node_timeline` system table — is currently
   * shallower than that on the 90-day range, so every previous value is `null`
   * (research.md R7). Showing "—" in a whole column reads as a breakage, hence the
   * notice.
   *
   * Derived from the rows actually returned, not from `window_days === 90`: the day the
   * upstream history gets deep enough, previous values appear and this notice stops
   * rendering on its own, with no code to revisit. `every` on a non-empty array also
   * keeps it from firing on a filter that legitimately matched nothing.
   */
  const lifetimeComparisonUnavailable = useMemo(() => {
    // Cost has its own, much deeper history: its comparison is unaffected.
    if (tab !== 'overview' && tab !== 'efficiency') return false;
    const rows = tab === 'overview' ? overview.data?.items : efficiency.data?.items;
    if (!rows?.length) return false;
    return rows.every((row) => row.uptime_hours_prev_window == null);
  }, [tab, overview.data?.items, efficiency.data?.items]);

  const openCluster = (row: { cluster_id: string; cluster_name?: string | null }) => {
    setSelectedCluster({
      id: row.cluster_id,
      title: row.cluster_name || row.cluster_id,
    });
  };

  const overviewColumns = useMemo(
    (): ComputeDataTableColumn<ComputeClustersOverviewItem>[] => [
      {
        id: 'workspace',
        filterKey: 'workspace',
        width: COLUMN_WIDTH.identifier,
        header: 'Workspace',
        description: computeClusterFieldDescriptions.workspace,
        sortable: true,
        cell: (row) => (
          <WorkspaceCell
            name={row.workspace_name}
            workspaceId={row.workspace_id}
            resolveWithId={resolveWithId}
          />
        ),
      },
      {
        id: 'cluster',
        filterKey: 'cluster',
        width: COLUMN_WIDTH.name,
        header: 'Cluster',
        description: computeClusterFieldDescriptions.cluster,
        sortable: true,
        cell: (row) => <ClusterCell name={row.cluster_name} id={row.cluster_id} />,
      },
      {
        id: 'cost',
        filterKey: 'cost',
        width: COLUMN_WIDTH.metric,
        header: 'Cost',
        description: computeClusterFieldDescriptions.cost,
        align: 'right',
        sortable: true,
        cell: (row) => <NumberCell value={formatUsd(row.cost_usd)} />,
      },
      {
        id: 'cost_prev',
        width: COLUMN_WIDTH.metric,
        header: 'Prev cost',
        description: computeClusterFieldDescriptions.costPrev,
        align: 'right',
        sortable: true,
        cell: (row) => (
          <PrevWindowCell
            value={row.cost_usd_prev_window == null ? null : formatUsd(row.cost_usd_prev_window)}
            delta={row.cost_delta_pct == null ? null : formatDeltaPct(row.cost_delta_pct)}
          />
        ),
      },
      {
        id: 'cluster_lifetime',
        width: COLUMN_WIDTH.duration,
        header: 'Lifetime',
        description: computeClusterFieldDescriptions.clusterLifetime,
        align: 'right',
        sortable: true,
        cell: (row) => <NumberCell value={formatHours(row.uptime_hours)} />,
      },
      {
        id: 'cluster_lifetime_prev',
        width: COLUMN_WIDTH.duration,
        header: 'Prev lifetime',
        description: computeClusterFieldDescriptions.clusterLifetimePrev,
        align: 'right',
        sortable: true,
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
        filterKey: 'utilization',
        width: COLUMN_WIDTH.status,
        header: 'Utilization',
        description: computeClusterFieldDescriptions.utilizationStatus,
        sortable: true,
        cell: (row) => utilizationStatusBadge(row.utilization_status),
      },
      {
        id: 'governance',
        filterKey: 'governance',
        width: COLUMN_WIDTH.status,
        header: 'Governance',
        description: computeClusterFieldDescriptions.governance,
        sortable: true,
        cell: (row) => (
          <Badge variant={severityBadgeVariant(row.severity)}>{severityLabel(row.severity)}</Badge>
        ),
      },
    ],
    [resolveWithId]
  );

  const costColumns = useMemo(
    (): ComputeDataTableColumn<ComputeClusterCostItem>[] => [
      {
        id: 'workspace',
        filterKey: 'workspace',
        width: COLUMN_WIDTH.identifier,
        header: 'Workspace',
        description: computeClusterFieldDescriptions.workspace,
        cell: (row) => (
          <WorkspaceCell
            name={row.workspace_name}
            workspaceId={row.workspace_id}
            resolveWithId={resolveWithId}
          />
        ),
      },
      {
        id: 'cluster',
        filterKey: 'cluster',
        width: COLUMN_WIDTH.name,
        header: 'Cluster',
        description: computeClusterFieldDescriptions.cluster,
        cell: (row) => <ClusterCell name={row.cluster_name} id={row.cluster_id} />,
      },
      {
        id: 'cost',
        filterKey: 'cost',
        width: COLUMN_WIDTH.metric,
        header: 'Cost',
        description: computeClusterFieldDescriptions.cost,
        align: 'right',
        cell: (row) => <NumberCell value={formatUsd(row.cost_usd)} />,
      },
      {
        id: 'cost_prev',
        width: COLUMN_WIDTH.metric,
        header: 'Prev cost',
        description: computeClusterFieldDescriptions.costPrev,
        align: 'right',
        cell: (row) => (
          <PrevWindowCell
            value={row.cost_usd_prev_window == null ? null : formatUsd(row.cost_usd_prev_window)}
            delta={row.cost_delta_pct == null ? null : formatDeltaPct(row.cost_delta_pct)}
          />
        ),
      },
      {
        id: 'sku_group',
        filterKey: 'sku_group',
        width: COLUMN_WIDTH.label,
        header: 'SKU group',
        description: computeClusterFieldDescriptions.skuGroup,
        cell: (row) => row.sku_group || '—',
      },
      {
        id: 'dbu_cost',
        width: COLUMN_WIDTH.metric,
        header: 'DBU cost',
        description: computeClusterFieldDescriptions.dbuCost,
        align: 'right',
        // A unit cost lives in the cents: rounding it to the dollar reads $0.
        cell: (row) => <NumberCell value={formatUsd(row.dbu_cost, 3)} />,
      },
      {
        id: 'dbu',
        filterKey: 'dbu',
        width: COLUMN_WIDTH.number,
        header: 'DBU',
        description: computeClusterFieldDescriptions.dbu,
        align: 'right',
        cell: (row) => <NumberCell value={formatNumber(row.dbu_quantity)} />,
      },
    ],
    [resolveWithId]
  );

  const efficiencyColumns = useMemo(
    (): ComputeDataTableColumn<ComputeClusterEfficiencyItem>[] => [
      {
        id: 'workspace',
        filterKey: 'workspace',
        width: COLUMN_WIDTH.identifier,
        header: 'Workspace',
        description: computeClusterFieldDescriptions.workspace,
        cell: (row) => (
          <WorkspaceCell
            name={row.workspace_name}
            workspaceId={row.workspace_id}
            resolveWithId={resolveWithId}
          />
        ),
      },
      {
        id: 'cluster',
        filterKey: 'cluster',
        width: COLUMN_WIDTH.name,
        header: 'Cluster',
        description: computeClusterFieldDescriptions.cluster,
        cell: (row) => <ClusterCell name={row.cluster_name} id={row.cluster_id} />,
      },
      {
        id: 'driver_node',
        filterKey: 'driver_node',
        width: COLUMN_WIDTH.timestamp,
        header: 'Driver node',
        description: computeClusterFieldDescriptions.driverNode,
        cell: (row) => row.driver_node_type || '—',
      },
      {
        id: 'worker_node',
        filterKey: 'worker_node',
        width: COLUMN_WIDTH.timestamp,
        header: 'Worker node',
        description: computeClusterFieldDescriptions.workerNode,
        cell: (row) => row.worker_node_type || '—',
      },
      {
        id: 'autoscaling',
        filterKey: 'autoscaling',
        width: COLUMN_WIDTH.badge,
        header: 'Autoscaling',
        description: computeClusterFieldDescriptions.autoscaling,
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
        id: 'nodes',
        filterKey: 'nodes',
        width: COLUMN_WIDTH.number,
        header: 'Nodes',
        description: computeClusterFieldDescriptions.nodes,
        align: 'right',
        cell: (row) => <NumberCell value={formatWorkerBounds(row)} />,
      },
      {
        id: 'cluster_lifetime',
        filterKey: 'cluster_lifetime',
        width: COLUMN_WIDTH.duration,
        header: 'Lifetime',
        description: computeClusterFieldDescriptions.clusterLifetime,
        align: 'right',
        cell: (row) => <NumberCell value={formatHours(row.uptime_hours)} />,
      },
      {
        id: 'cluster_lifetime_prev',
        width: COLUMN_WIDTH.duration,
        header: 'Prev lifetime',
        description: computeClusterFieldDescriptions.clusterLifetimePrev,
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
        id: 'idle',
        filterKey: 'idle',
        width: COLUMN_WIDTH.metric,
        header: 'Idle',
        description: computeClusterFieldDescriptions.idlePct,
        align: 'right',
        cell: (row) => <NumberCell value={formatPct(row.idle_pct)} />,
      },
      {
        id: 'idle_prev',
        width: COLUMN_WIDTH.metric,
        header: 'Prev idle',
        description: computeClusterFieldDescriptions.idlePctPrev,
        align: 'right',
        cell: (row) => (
          <PrevWindowCell
            value={row.idle_pct_prev_window == null ? null : formatPct(row.idle_pct_prev_window)}
            // A percentage variation reads in points, not in per cent.
            delta={row.idle_pct_delta_pts == null ? null : formatDeltaPts(row.idle_pct_delta_pts)}
          />
        ),
      },
      {
        id: 'cpu_avg',
        filterKey: 'cpu_avg',
        width: COLUMN_WIDTH.number,
        header: 'CPU avg',
        description: computeClusterFieldDescriptions.cpuAvg,
        align: 'right',
        cell: (row) => <NumberCell value={formatPct(row.cpu_util_avg_pct)} />,
      },
      {
        id: 'cpu_p95',
        filterKey: 'cpu_p95',
        width: COLUMN_WIDTH.number,
        header: 'CPU p95',
        description: computeClusterFieldDescriptions.cpuP95,
        align: 'right',
        cell: (row) => <NumberCell value={formatPct(row.cpu_util_p95_pct)} />,
      },
      {
        id: 'mem_avg',
        filterKey: 'mem_avg',
        width: COLUMN_WIDTH.number,
        header: 'Mem avg',
        description: computeClusterFieldDescriptions.memAvg,
        align: 'right',
        cell: (row) => <NumberCell value={formatPct(row.mem_util_avg_pct)} />,
      },
      {
        id: 'mem_p95',
        filterKey: 'mem_p95',
        width: COLUMN_WIDTH.number,
        header: 'Mem p95',
        description: computeClusterFieldDescriptions.memP95,
        align: 'right',
        cell: (row) => <NumberCell value={formatPct(row.mem_util_p95_pct)} />,
      },
      {
        id: 'status',
        filterKey: 'status',
        width: COLUMN_WIDTH.status,
        header: 'Status',
        description: computeClusterFieldDescriptions.status,
        cell: (row) =>
          utilizationStatusBadge(row.utilization_status || (row.is_zombie ? 'ZOMBIE' : null)),
      },
      {
        id: 'recommended_node',
        filterKey: 'recommended_node',
        width: COLUMN_WIDTH.timestamp,
        header: 'Recommended node',
        description: computeClusterFieldDescriptions.recommendedNode,
        cell: (row) => row.recommended_node_type || '—',
      },
      {
        id: 'estimated_savings',
        filterKey: 'estimated_savings',
        width: COLUMN_WIDTH.metric,
        header: 'Est. savings',
        description: computeClusterFieldDescriptions.estimatedSavings,
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">
            {row.estimated_savings_usd ? formatUsd(row.estimated_savings_usd) : '—'}
          </span>
        ),
      },
    ],
    [resolveWithId]
  );

  const governanceColumns = useMemo(
    (): ComputeDataTableColumn<ComputeClusterGovernanceItem>[] => [
      {
        id: 'cluster',
        filterKey: 'cluster',
        width: COLUMN_WIDTH.name,
        header: 'Cluster',
        description: computeClusterFieldDescriptions.cluster,
        cell: (row) => <ClusterCell name={row.cluster_name} id={row.cluster_id} />,
      },
      {
        id: 'owner_tag',
        filterKey: 'owner_tag',
        width: COLUMN_WIDTH.tag,
        header: 'Owner tag',
        description: computeClusterFieldDescriptions.ownerTag,
        cell: (row) => (
          <Badge variant={row.has_owner_tag === false ? 'warning' : 'success'}>
            {row.has_owner_tag === false ? 'Missing' : 'OK'}
          </Badge>
        ),
      },
      {
        id: 'cost_center_tag',
        filterKey: 'cost_center_tag',
        width: COLUMN_WIDTH.tag,
        header: 'Cost-center tag',
        description: computeClusterFieldDescriptions.costCenterTag,
        cell: (row) => (
          <Badge variant={row.has_cost_center_tag === false ? 'warning' : 'success'}>
            {row.has_cost_center_tag === false ? 'Missing' : 'OK'}
          </Badge>
        ),
      },
      {
        id: 'dbr',
        filterKey: 'dbr',
        width: COLUMN_WIDTH.label,
        header: 'DBR',
        description: computeClusterFieldDescriptions.dbr,
        cell: (row) => (
          <>
            {row.dbr_version || '—'}{' '}
            {row.dbr_is_lts_current === false ? (
              <Badge variant="warning" className="ml-2">
                Obsolete
              </Badge>
            ) : null}
          </>
        ),
      },
      {
        id: 'action',
        width: COLUMN_WIDTH.action,
        resizable: false,
        header: 'Action',
        description: computeClusterFieldDescriptions.recommendedAction,
        cell: (row) => row.recommended_action || '—',
      },
      {
        id: 'severity',
        filterKey: 'severity',
        width: COLUMN_WIDTH.badge,
        header: 'Severity',
        description: computeClusterFieldDescriptions.severity,
        cell: (row) => (
          <Badge variant={severityBadgeVariant(row.severity)}>{severityLabel(row.severity)}</Badge>
        ),
      },
    ],
    []
  );

  const totalCostUsd = overview.data?.kpis?.total_cost_usd ?? 0;
  const topCostItem = cost.data?.items?.[0] ?? null;
  const topCostLabel = topCostItem?.cluster_name || topCostItem?.cluster_id || '—';
  const topCostShare =
    topCostItem?.cost_usd != null && totalCostUsd > 0
      ? `${Math.round((topCostItem.cost_usd / totalCostUsd) * 100)}% of total`
      : '';

  const effItems = efficiency.data?.items ?? [];
  const effCpuAvg =
    effItems.length > 0
      ? effItems.reduce((sum, it) => sum + (Number(it.cpu_util_p95_pct) || 0), 0) / effItems.length
      : null;
  const effMemAvg =
    effItems.length > 0
      ? effItems.reduce((sum, it) => sum + (Number(it.mem_util_p95_pct) || 0), 0) / effItems.length
      : null;
  const effZombieCount = effItems.filter((it) => it.is_zombie).length;
  const effSavings = effItems.reduce((sum, it) => sum + (Number(it.estimated_savings_usd) || 0), 0);

  const govItems = governance.data?.items ?? [];
  const missingTagsCount = govItems.filter(
    (it) => it.has_owner_tag === false || it.has_cost_center_tag === false
  ).length;
  const dbrObsoleteCount = govItems.filter((it) => it.dbr_is_lts_current === false).length;
  const highSeverityCount = govItems.filter(
    (it) => (it.severity || '').toUpperCase() === 'HIGH'
  ).length;

  const selectedWorkspaceLabel = selectedCluster
    ? resolveWithId(
        detail.data?.workspace_id ??
          overviewItems.find((item) => item.cluster_id === selectedCluster.id)?.workspace_id
      ).label
    : undefined;

  return (
    <Content className="mx-auto max-w-[1600px] gap-0 p-4 pb-24 lg:px-6 lg:pb-28">
      <ContentHeader>
        <div>
          <ContentTitle>All-purpose clusters</ContentTitle>
          <p className="mt-2 text-sm text-muted-foreground">
            Explore cluster costs, efficiency signals, and governance issues over a rolling window —{' '}
            {scope.label}.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            void overview.refetch();
            void cost.refetch();
            void efficiency.refetch();
            void governance.refetch();
          }}
          disabled={overview.fetching}
        >
          <RefreshCw />
          Refresh
        </Button>
      </ContentHeader>

      <ContentMain className="gap-5">
        <ComputeTabs value={tab} onChange={setTab} ariaLabel="Clusters tabs" />

        {tab === 'governance' ? null : (
          <div className="flex flex-wrap items-center gap-3">
            <div
              className="flex shrink-0 items-center gap-0.5 rounded-full border border-border bg-muted/30 p-0.5"
              role="group"
              aria-label="Rolling window"
            >
              {ROLLING_WINDOWS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setWindowDays(option.value)}
                  className={cn(
                    'rounded-full px-3 py-1.5 text-xs font-bold transition-colors',
                    windowDays === option.value
                      ? 'bg-primary text-primary-foreground shadow-sm'
                      : 'text-muted-foreground hover:bg-card hover:text-foreground'
                  )}
                  aria-pressed={windowDays === option.value}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <span className="text-xs text-muted-foreground">
              Covered period{' '}
              <span className="font-mono font-semibold text-foreground">{coveredPeriodLabel}</span>
            </span>
          </div>
        )}

        {lifetimeComparisonUnavailable && (
          <p
            className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground"
            role="note"
          >
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span>
              Lifetime and IDLE have no previous period to compare against over{' '}
              {activeWindow?.window_days ?? windowDays} days — comparing two consecutive windows
              needs twice that much history, and the upstream cluster metrics do not go back that
              far yet. Cost comparisons are unaffected.
            </span>
          </p>
        )}

        {tab === 'overview' ? (
          <>
            <div className="grid grid-cols-1 gap-4 overflow-visible sm:grid-cols-2 xl:grid-cols-4">
              {overview.loading && !overview.data ? (
                <>
                  <Skeleton className="h-32" />
                  <Skeleton className="h-32" />
                  <Skeleton className="h-32" />
                  <Skeleton className="h-32" />
                </>
              ) : (
                <>
                  <ComputeKpiCard
                    title="Total cost"
                    description={computeClusterKpiDescriptions.totalCost}
                    value={formatUsd(overview.data?.kpis.total_cost_usd)}
                    subtitle={
                      overview.data?.kpis.cost_delta_pct == null
                        ? '—'
                        : `${formatDeltaPct(overview.data.kpis.cost_delta_pct)} vs previous period`
                    }
                    tone="info"
                    icon={DollarSign}
                  />
                  <ComputeKpiCard
                    title="Active clusters"
                    description={computeClusterKpiDescriptions.activeClusters}
                    value={formatNumber(overview.data?.kpis.active_clusters ?? null)}
                    subtitle="Distinct clusters in period"
                    tone="success"
                    icon={Activity}
                  />
                  <ComputeKpiCard
                    title="Zombies"
                    description={computeClusterKpiDescriptions.zombies}
                    value={formatNumber(overview.data?.kpis.zombie_count ?? null)}
                    subtitle="Low usage & long uptime"
                    tone="warning"
                    icon={Snowflake}
                  />
                  <Link
                    to="/databricks/compute/recommendations?object_type=CLUSTER"
                    className="block overflow-hidden rounded-[var(--card-radius)] transition-shadow hover:shadow-[var(--card-hover-shadow)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    aria-label="View cluster recommendations"
                  >
                    <ComputeKpiCard
                      title="Open recommendations"
                      description={computeClusterKpiDescriptions.openRecommendations}
                      value={formatNumber(overview.data?.kpis.open_recommendations ?? null)}
                      subtitle="Clusters only · click to open list"
                      tone="purple"
                      icon={ShieldAlert}
                    />
                  </Link>
                </>
              )}
            </div>

            {overviewItems.length || overviewFiltersActive ? (
              <ComputeDataTable
                tableId="compute-clusters-overview"
                columns={overviewColumns}
                rows={overviewItems}
                rowKey={(row) => `${row.workspace_id}-${row.cluster_id}`}
                loading={overview.loading && !overview.data}
                onRowClick={openCluster}
                sort={{ key: overviewSortKey, direction: overviewSortDirection }}
                onSortChange={handleOverviewSort}
                toolbar={
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="relative w-full max-w-[280px] shrink-0">
                      <Input
                        value={overviewSearchInput}
                        onChange={(e) => setOverviewSearchInput(e.target.value)}
                        placeholder="Search cluster, workspace, owner…"
                        className="h-8 rounded-full text-xs"
                        aria-label="Search overview clusters"
                      />
                    </div>
                    {UTILIZATION_FILTERS.map((value) => (
                      <FilterChip
                        key={value || 'all'}
                        active={overviewUtilFilter === value}
                        onClick={() =>
                          setOverviewFilters((current) =>
                            withColumnFilter(current, 'utilization', value)
                          )
                        }
                      >
                        {value === ''
                          ? 'All statuses'
                          : value === 'OVER'
                            ? 'Overprovisioned'
                            : value === 'UNDER'
                              ? 'Underprovisioned'
                              : value === 'OPTIMAL'
                                ? 'Optimal'
                                : 'Zombie'}
                      </FilterChip>
                    ))}
                  </div>
                }
                filterView="clusters-overview"
                filterScope={filterScope}
                filters={overviewFilters}
                onFiltersChange={setOverviewFilters}
                pagination={overviewPagination}
                minWidthClassName="min-w-[1048px]"
                emptyTitle="No clusters match these filters"
                emptyDescription="Try clearing search or utilization status filters."
              />
            ) : overview.loading ? (
              <Skeleton className="h-[280px]" />
            ) : (
              <ComputeEmptyState
                title="No clusters found"
                description="No cluster metrics are available for the selected scope and time range."
              />
            )}
          </>
        ) : null}

        {tab === 'cost' ? (
          <>
            <div className="grid grid-cols-1 gap-4 overflow-visible sm:grid-cols-2 xl:grid-cols-3">
              <ComputeKpiCard
                title="Total cost"
                description={computeClusterKpiDescriptions.totalCost}
                value={formatUsd(overview.data?.kpis.total_cost_usd)}
                subtitle={
                  overview.data?.kpis.cost_delta_pct == null
                    ? '—'
                    : `${formatDeltaPct(overview.data.kpis.cost_delta_pct)} vs previous period`
                }
                tone="info"
                icon={DollarSign}
              />
              <ComputeKpiCard
                title="DBU (current page)"
                description={computeClusterKpiDescriptions.dbuPage}
                value={formatNumber(
                  (cost.data?.items ?? []).reduce(
                    (sum, it) => sum + (Number(it.dbu_quantity) || 0),
                    0
                  )
                )}
                subtitle="Sum over visible rows"
                tone="success"
                icon={Cpu}
              />
              <ComputeKpiCard
                title="Top costly"
                description={computeClusterKpiDescriptions.topCostly}
                value={topCostLabel}
                subtitle={
                  topCostItem?.cost_usd != null
                    ? `${formatUsd(topCostItem.cost_usd)}${topCostShare ? ` · ${topCostShare}` : ''}`
                    : '—'
                }
                tone="warning"
                icon={DollarSign}
              />
            </div>

            <ComputeDataTable
              tableId="compute-clusters-cost"
              columns={costColumns}
              rows={cost.data?.items ?? []}
              rowKey={(row) => `${row.workspace_id}-${row.cluster_id}`}
              loading={cost.loading && !cost.data}
              onRowClick={openCluster}
              toolbar={
                <div className="flex flex-wrap items-center gap-2">
                  <div className="relative w-full max-w-[260px] shrink-0">
                    <Input
                      value={costSearchInput}
                      onChange={(e) => setCostSearchInput(e.target.value)}
                      placeholder="Search clusters…"
                      className="h-8 rounded-full text-xs"
                      aria-label="Search clusters"
                    />
                  </div>
                  <select
                    className="h-8 rounded-full border border-border bg-card px-3 text-xs text-foreground"
                    value={costSkuGroup}
                    onChange={(e) =>
                      setCostColumnFilters((current) =>
                        withColumnFilter(current, 'sku_group', e.target.value)
                      )
                    }
                    aria-label="Filter by SKU group"
                  >
                    <option value="">All SKU groups</option>
                    {SKU_GROUP_OPTIONS.map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                    {/* La combo de colonne propose tous les groupes présents en gold,
                        pas seulement ces trois. Sans cette option, le sélecteur
                        afficherait « All SKU groups » alors qu'un filtre est actif. */}
                    {costSkuGroup && !SKU_GROUP_OPTIONS.includes(costSkuGroup) ? (
                      <option value={costSkuGroup}>{costSkuGroup}</option>
                    ) : null}
                  </select>
                  <select
                    className="h-8 rounded-full border border-border bg-card px-3 text-xs text-foreground"
                    value={costSort}
                    onChange={(e) => {
                      setCostSort(e.target.value as 'cost_desc' | 'name' | 'rank');
                      setCostPage(1);
                    }}
                    aria-label="Sort clusters"
                  >
                    <option value="cost_desc">Sort by cost</option>
                    <option value="name">Sort by name</option>
                    <option value="rank">Sort by rank</option>
                  </select>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="ml-auto"
                    onClick={() => void cost.refetch()}
                    disabled={cost.fetching}
                    aria-label="Refresh cost table"
                  >
                    <RefreshCw />
                  </Button>
                </div>
              }
              pagination={{
                currentPage: cost.data?.page ?? costPage,
                totalPages: cost.data
                  ? Math.max(1, Math.ceil(cost.data.total / cost.data.page_size))
                  : 1,
                totalItems: cost.data?.total ?? 0,
                startIndex: ((cost.data?.page ?? costPage) - 1) * 25,
                endIndex: Math.min(
                  ((cost.data?.page ?? costPage) - 1) * 25 + (cost.data?.items?.length ?? 0),
                  cost.data?.total ?? 0
                ),
                hasPreviousPage: (cost.data?.page ?? costPage) > 1,
                hasNextPage: cost.data
                  ? cost.data.page * cost.data.page_size < cost.data.total
                  : false,
                onPrevious: () => setCostPage((p) => Math.max(1, p - 1)),
                onNext: () => setCostPage((p) => p + 1),
              }}
              filterView="clusters-cost"
              filterScope={filterScope}
              filters={costFilters}
              onFiltersChange={changeCostFilters}
              emptyTitle="No clusters match these filters"
              emptyDescription="Try clearing search, SKU group, or sorting options."
            />
          </>
        ) : null}

        {tab === 'efficiency' ? (
          <>
            <div className="grid grid-cols-1 gap-4 overflow-visible sm:grid-cols-2 xl:grid-cols-4">
              <ComputeKpiCard
                title="Avg CPU p95 (page)"
                description={computeClusterKpiDescriptions.avgCpuP95}
                value={effCpuAvg == null ? '—' : formatPct(effCpuAvg, 0)}
                subtitle="Average over visible rows"
                tone="info"
                icon={Cpu}
              />
              <ComputeKpiCard
                title="Avg Mem p95 (page)"
                description={computeClusterKpiDescriptions.avgMemP95}
                value={effMemAvg == null ? '—' : formatPct(effMemAvg, 0)}
                subtitle="Average over visible rows"
                tone="success"
                icon={Activity}
              />
              <ComputeKpiCard
                title="Zombies (page)"
                description={computeClusterKpiDescriptions.zombiesPage}
                value={formatNumber(effZombieCount)}
                subtitle="Rows with is_zombie=true"
                tone="warning"
                icon={Snowflake}
              />
              <ComputeKpiCard
                title="Est. savings (page)"
                description={computeClusterKpiDescriptions.estimatedSavingsPage}
                value={formatUsd(effSavings)}
                subtitle="Sum over visible rows"
                tone="purple"
                icon={DollarSign}
              />
            </div>

            <ComputeDataTable
              tableId="compute-clusters-efficiency"
              columns={efficiencyColumns}
              rows={efficiency.data?.items ?? []}
              rowKey={(row) => `${row.workspace_id}-${row.cluster_id}`}
              loading={efficiency.loading && !efficiency.data}
              onRowClick={openCluster}
              toolbar={
                <div className="flex flex-wrap items-center gap-2">
                  {UTILIZATION_FILTERS.map((value) => (
                    <FilterChip
                      key={value || 'all'}
                      active={effFilter === value}
                      onClick={() =>
                        setEffFilters((current) => withColumnFilter(current, 'status', value))
                      }
                    >
                      {value === ''
                        ? 'All'
                        : value === 'OVER'
                          ? 'Overprovisioned'
                          : value === 'UNDER'
                            ? 'Underprovisioned'
                            : value === 'OPTIMAL'
                              ? 'Optimal'
                              : 'Zombie'}
                    </FilterChip>
                  ))}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="ml-auto"
                    onClick={() => void efficiency.refetch()}
                    disabled={efficiency.fetching}
                    aria-label="Refresh efficiency table"
                  >
                    <RefreshCw />
                  </Button>
                </div>
              }
              pagination={{
                currentPage: efficiency.data?.page ?? effPage,
                totalPages: efficiency.data
                  ? Math.max(1, Math.ceil(efficiency.data.total / efficiency.data.page_size))
                  : 1,
                totalItems: efficiency.data?.total ?? 0,
                startIndex: ((efficiency.data?.page ?? effPage) - 1) * 25,
                endIndex: Math.min(
                  ((efficiency.data?.page ?? effPage) - 1) * 25 +
                    (efficiency.data?.items?.length ?? 0),
                  efficiency.data?.total ?? 0
                ),
                hasPreviousPage: (efficiency.data?.page ?? effPage) > 1,
                hasNextPage: efficiency.data
                  ? efficiency.data.page * efficiency.data.page_size < efficiency.data.total
                  : false,
                onPrevious: () => setEffPage((p) => Math.max(1, p - 1)),
                onNext: () => setEffPage((p) => p + 1),
              }}
              filterView="clusters-efficiency"
              filterScope={filterScope}
              filters={effFilters}
              onFiltersChange={setEffFilters}
              minWidthClassName="min-w-[1968px]"
              emptyTitle="No clusters match these filters"
              emptyDescription="Try switching utilization status or clearing filters."
            />
          </>
        ) : null}

        {tab === 'governance' ? (
          <>
            <div className="grid grid-cols-1 gap-4 overflow-visible sm:grid-cols-2 xl:grid-cols-3">
              <ComputeKpiCard
                title="Missing tags (page)"
                description={computeClusterKpiDescriptions.missingTags}
                value={formatNumber(missingTagsCount)}
                subtitle="Owner or cost-center missing"
                tone="warning"
                icon={Tag}
              />
              <ComputeKpiCard
                title="DBR obsolete (page)"
                description={computeClusterKpiDescriptions.dbrObsolete}
                value={formatNumber(dbrObsoleteCount)}
                subtitle="Not on current LTS"
                tone="danger"
                icon={ShieldAlert}
              />
              <ComputeKpiCard
                title="High severity (page)"
                description={computeClusterKpiDescriptions.highSeverity}
                value={formatNumber(highSeverityCount)}
                subtitle="HIGH severity issues"
                tone="info"
                icon={ShieldAlert}
              />
            </div>

            <ComputeDataTable
              tableId="compute-clusters-governance"
              columns={governanceColumns}
              rows={governance.data?.items ?? []}
              rowKey={(row) => `${row.workspace_id}-${row.cluster_id}`}
              loading={governance.loading && !governance.data}
              onRowClick={openCluster}
              toolbar={
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    className="h-8 rounded-full border border-border bg-card px-3 text-xs text-foreground"
                    value={govSeverity}
                    onChange={(e) =>
                      setGovFilters((current) =>
                        withColumnFilter(current, 'severity', e.target.value)
                      )
                    }
                    aria-label="Filter by severity"
                  >
                    <option value="">All severities</option>
                    {SEVERITY_OPTIONS.map(({ value, label }) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                    {govSeverity && !SEVERITY_OPTIONS.some((o) => o.value === govSeverity) ? (
                      <option value={govSeverity}>{govSeverity}</option>
                    ) : null}
                  </select>
                  <FilterChip
                    active={govMissingTags}
                    onClick={() => {
                      setGovMissingTags((v) => !v);
                      setGovPage(1);
                    }}
                  >
                    Missing tags
                  </FilterChip>
                  <FilterChip
                    active={govDbrObsolete}
                    onClick={() => {
                      setGovDbrObsolete((v) => !v);
                      setGovPage(1);
                    }}
                  >
                    DBR obsolete
                  </FilterChip>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="ml-auto"
                    onClick={() => void governance.refetch()}
                    disabled={governance.fetching}
                    aria-label="Refresh governance table"
                  >
                    <RefreshCw />
                  </Button>
                </div>
              }
              pagination={{
                currentPage: governance.data?.page ?? govPage,
                totalPages: governance.data
                  ? Math.max(1, Math.ceil(governance.data.total / governance.data.page_size))
                  : 1,
                totalItems: governance.data?.total ?? 0,
                startIndex: ((governance.data?.page ?? govPage) - 1) * 25,
                endIndex: Math.min(
                  ((governance.data?.page ?? govPage) - 1) * 25 +
                    (governance.data?.items?.length ?? 0),
                  governance.data?.total ?? 0
                ),
                hasPreviousPage: (governance.data?.page ?? govPage) > 1,
                hasNextPage: governance.data
                  ? governance.data.page * governance.data.page_size < governance.data.total
                  : false,
                onPrevious: () => setGovPage((p) => Math.max(1, p - 1)),
                onNext: () => setGovPage((p) => p + 1),
              }}
              filterView="clusters-governance"
              filters={govFilters}
              onFiltersChange={setGovFilters}
              minWidthClassName="min-w-[968px]"
              emptyTitle="No clusters match these filters"
              emptyDescription="Try adjusting severity, missing tags, or DBR obsolete filters."
            />
          </>
        ) : null}
      </ContentMain>

      <ComputeClusterDrawer
        open={Boolean(selectedCluster)}
        onClose={() => setSelectedCluster(null)}
        title={selectedCluster?.title ?? '—'}
        detail={detail.data}
        detailLoading={detail.loading}
        detailError={detail.error}
        trend={trend.data}
        trendLoading={trend.loading}
        trendError={trend.error}
        granularity={drawerGranularity}
        onGranularityChange={setDrawerGranularity}
        lifetimeTrend={lifetimeTrend.data}
        lifetimeTrendLoading={lifetimeTrend.loading}
        lifetimeTrendError={lifetimeTrend.error}
        lifetimeGranularity={drawerLifetimeGranularity}
        onLifetimeGranularityChange={setDrawerLifetimeGranularity}
        workspaceLabel={selectedWorkspaceLabel}
      />
    </Content>
  );
}
