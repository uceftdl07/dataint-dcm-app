import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  Cpu,
  Database,
  DollarSign,
  ExternalLink,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react';
import { ComputeWarehouseDrawer } from '../components/domain/compute/compute-warehouse-drawer';
import {
  ComputeWarehouseTabs,
  type ComputeWarehousesTabKey,
} from '../components/domain/compute/compute-warehouse-tabs';
import {
  ComputeDataTable,
  type ComputeDataTableColumn,
  type SortDirection,
} from '../components/domain/compute/compute-data-table';
import { COLUMN_WIDTH } from '../components/domain/compute/compute-column-widths';
import { ComputeEmptyState } from '../components/domain/compute/compute-empty-state';
import { ComputeKpiCard } from '../components/domain/compute/compute-kpi-card';
import { Content, ContentHeader, ContentMain, ContentTitle } from '../components/layout/content';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Skeleton } from '../components/ui/skeleton';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { useWorkspaceLabelResolver } from '../hooks/useWorkspaceLabelResolver';
import {
  useComputeWarehouseCostTrend,
  useComputeWarehouseDetail,
  useComputeWarehousesCostData,
  useComputeWarehousesOverviewData,
  useComputeWarehousesQueryPerformanceData,
  useComputeWarehousesSlowQueriesData,
  SLOW_QUERIES_DEFAULT_DAYS,
} from '../hooks/useComputeWarehousesQueries';
import {
  computeWarehouseFieldDescriptions,
  computeWarehouseKpiDescriptions,
} from '../lib/compute/field-descriptions';
import { countActiveColumnFilters, withColumnFilter } from '../lib/compute/column-filters';
import { resolveQueryProfileUrl } from '../lib/compute/query-profile-url';
import {
  formatDeltaPct,
  formatNumber,
  formatPct,
  formatUsd,
  lastNDaysPeriodIso,
  subtractDaysIso,
  todayIsoUtc,
} from '../lib/compute/format';
import { serverPaginationProps } from '../lib/compute/server-pagination';
import { cn } from '../lib/utils';
import type {
  ComputeColumnFilterValues,
  ComputeMetricTrendGranularity,
  ComputeWarehouseCostItem,
  ComputeWarehouseQueryPerformanceItem,
  ComputeWarehousesOverviewItem,
  ComputeWarehouseSlowQueryItem,
  ComputeWarehouseWindow,
  ComputeWarehouseWindowDays,
} from '../types/api';

const OVERVIEW_PAGE_SIZE = 25;
const FAILURE_FILTER_PCT = 1;

/** Une seule instance vide, pour ne pas relancer les mémos à chaque remise à zéro. */
const NO_FILTERS: ComputeColumnFilterValues = {};

/** Tailles proposées par la barre d'outils. Le serveur, lui, liste celles qui existent. */
const WAREHOUSE_SIZE_OPTIONS: { value: string; label: string }[] = [
  { value: 'small', label: 'Small' },
  { value: 'medium', label: 'Medium' },
  { value: 'large', label: 'Large' },
  { value: 'x-large', label: 'X-Large' },
];

/** Seuils de latence proposés par la barre d'outils, en millisecondes. */
const PERF_LATENCY_OPTIONS = ['10000', '30000'];

/**
 * The four windows materialized in gold, the same four as the clusters page. They
 * are static by design: each tab reads a pre-aggregated snapshot per window, it
 * does not compose a free range.
 */
const ROLLING_WINDOWS: { value: ComputeWarehouseWindowDays; label: string }[] = [
  { value: 1, label: 'Daily' },
  { value: 7, label: 'Last 7d' },
  { value: 30, label: 'Last 30d' },
  { value: 90, label: 'Last 90d' },
];

/**
 * Plages de l'onglet Slow queries, seul onglet à lire une table de statements et
 * non un instantané pré-agrégé : ses bornes sont donc des dates, calculées depuis
 * aujourd'hui.
 *
 * Pas de « Daily » ici, malgré les quatre chips des autres onglets : une journée
 * unique sur cette table rendrait « aucune requête lente » alors qu'il faut lire
 * « pas encore de données » — l'instantané quotidien des autres onglets, lui, n'est
 * jamais vide.
 */
const SLOW_QUERIES_RANGES: { value: number; label: string }[] = [
  { value: 7, label: 'Last 7d' },
  { value: 30, label: 'Last 30d' },
  { value: 90, label: 'Last 90d' },
];

/** Groupe de chips exclusives. Deux plages coexistent sur la page, une par grain. */
function WindowChipGroup<T extends number>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (next: T) => void;
}) {
  return (
    <div
      className="flex shrink-0 items-center gap-0.5 rounded-full border border-border bg-muted/30 p-0.5"
      role="group"
      aria-label={label}
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

/**
 * Sélecteur de taille de la barre d'outils. Il lit et écrit le **même** état que la
 * combo de la colonne « Size » : le serveur refuse un `warehouse_size` qui contredit
 * `column_filter=size:…`, et deux contrôles indépendants pour un seul prédicat
 * finissent toujours par diverger.
 */
function WarehouseSizeSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  const known = WAREHOUSE_SIZE_OPTIONS.some(
    (option) => option.value === value.trim().toLowerCase()
  );
  return (
    <select
      className="h-8 rounded-full border border-border bg-card px-3 text-xs text-foreground"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      aria-label="Filter by warehouse size"
    >
      <option value="">All sizes</option>
      {WAREHOUSE_SIZE_OPTIONS.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
      {/* La combo de colonne propose toutes les tailles présentes en gold, pas
          seulement les quatre d'ici. Sans cette option, le sélecteur retomberait sur
          « All sizes » alors qu'un filtre de taille est bel et bien actif. */}
      {value && !known ? <option value={value}>{value}</option> : null}
    </select>
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

function WarehouseCell({ name, id }: { name: string | null | undefined; id: string }) {
  // `truncate` par ligne : les points de suspension d'un bloc ne s'appliquent pas à
  // ses enfants de type bloc, seulement à son texte direct.
  return (
    <div className="min-w-0">
      <div className="truncate font-semibold text-foreground">{name || id}</div>
      <div className="truncate font-mono text-[10px] text-muted-foreground">{id}</div>
    </div>
  );
}

/**
 * Valeur numérique d'un filtre de colonne, pour le paramètre historique qu'il double.
 * `undefined` plutôt que `NaN` : un seuil illisible n'a rien à faire dans une requête.
 */
function numericFilter(value: string | undefined): number | undefined {
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function failureBadgeVariant(rate: number | null | undefined): 'success' | 'warning' | 'danger' {
  if (rate == null) return 'success';
  if (rate >= 5) return 'danger';
  if (rate >= FAILURE_FILTER_PCT) return 'warning';
  return 'success';
}

function reasonLabel(reason: string | null | undefined): string {
  const r = (reason || '').trim().toUpperCase();
  if (r === 'FAILURE') return 'Failure';
  if (r === 'SLOW') return 'Slow';
  if (r === 'SPILL') return 'Spill';
  return reason || '—';
}

function formatDurationMs(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  if (value >= 60_000) return `${(value / 60_000).toFixed(1)} min`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)} s`;
  return `${Math.round(value)} ms`;
}

export default function ComputeSqlWarehouses() {
  const { scope } = useMonitoringScope();
  const { resolveWithId } = useWorkspaceLabelResolver(true);

  const slowProbe = useComputeWarehousesSlowQueriesData({ pageSize: 1 });
  const slowQueriesEnabled = slowProbe.data?.enabled ?? false;

  const [tab, setTab] = useState<ComputeWarehousesTabKey>('overview');
  // Deliberately not reset when the tab changes: the range is a page-level
  // reading choice, it must survive Overview → Cost → Query performance.
  const [windowDays, setWindowDays] = useState<ComputeWarehouseWindowDays>(1);
  const [drawerGranularity, setDrawerGranularity] = useState<ComputeMetricTrendGranularity>('week');

  const [costSearchInput, setCostSearchInput] = useState('');
  const [costSearch, setCostSearch] = useState('');
  const [costSort, setCostSort] = useState<'cost_desc' | 'name'>('cost_desc');
  const [costPage, setCostPage] = useState(1);

  const [perfPage, setPerfPage] = useState(1);

  const [slowWarehouseId, setSlowWarehouseId] = useState('');
  const [slowWindowDays, setSlowWindowDays] = useState<number>(SLOW_QUERIES_DEFAULT_DAYS);
  const [slowPage, setSlowPage] = useState(1);

  // Un état de filtres par tableau. Il porte les combos d'en-tête **et** les
  // contrôles de la barre d'outils qui pilotent le même prédicat côté serveur : ce
  // sont les seuls filtres envoyés, donc les deux ne peuvent pas se contredire.
  const [overviewFilters, setOverviewFilters] = useState<ComputeColumnFilterValues>(NO_FILTERS);
  const [costColumnFilters, setCostColumnFilters] = useState<ComputeColumnFilterValues>(NO_FILTERS);
  const [perfFilters, setPerfFilters] = useState<ComputeColumnFilterValues>(NO_FILTERS);
  const [slowFilters, setSlowFilters] = useState<ComputeColumnFilterValues>(NO_FILTERS);

  const [overviewSearchInput, setOverviewSearchInput] = useState('');
  const [overviewSearch, setOverviewSearch] = useState('');
  type OverviewSortKey =
    | 'warehouse'
    | 'workspace'
    | 'size'
    | 'type'
    | 'cost'
    | 'queries'
    | 'failure'
    | 'latency';
  const [overviewSortKey, setOverviewSortKey] = useState<OverviewSortKey>('cost');
  const [overviewSortDirection, setOverviewSortDirection] = useState<SortDirection>('desc');
  const [overviewPage, setOverviewPage] = useState(1);

  const [selectedWarehouse, setSelectedWarehouse] = useState<{ id: string; title: string } | null>(
    null
  );

  useEffect(() => {
    const t = window.setTimeout(() => {
      setOverviewSearch(overviewSearchInput.trim());
      // The page is cut server-side: a narrower search can leave page 7 empty.
      setOverviewPage(1);
    }, 300);
    return () => window.clearTimeout(t);
  }, [overviewSearchInput]);

  // Re-filtering or re-sorting changes what page 2 even means.
  useEffect(() => {
    setOverviewPage(1);
  }, [overviewFilters, overviewSortKey, overviewSortDirection]);

  useEffect(() => {
    setPerfPage(1);
  }, [perfFilters]);

  useEffect(() => {
    setSlowPage(1);
  }, [slowFilters]);

  // Another range is another population, on all three windowed tabs: page 7 of the
  // daily window may not exist over 90 days, and the reverse.
  useEffect(() => {
    setOverviewPage(1);
    setCostPage(1);
    setPerfPage(1);
  }, [windowDays]);

  useEffect(() => {
    setCostSearchInput('');
    setCostSearch('');
    setCostColumnFilters(NO_FILTERS);
    setCostSort('cost_desc');
    setCostPage(1);
    setOverviewSearchInput('');
    setOverviewSearch('');
    setOverviewFilters(NO_FILTERS);
    setOverviewSortKey('cost');
    setOverviewSortDirection('desc');
    setOverviewPage(1);
    setPerfFilters(NO_FILTERS);
    setPerfPage(1);
    setSlowFilters(NO_FILTERS);
    setSlowWarehouseId('');
    setSlowPage(1);
  }, [tab]);

  useEffect(() => {
    const t = window.setTimeout(() => {
      setCostSearch(costSearchInput.trim());
      setCostPage(1);
    }, 300);
    return () => window.clearTimeout(t);
  }, [costSearchInput]);

  useEffect(() => {
    setCostPage(1);
  }, [costColumnFilters]);

  useEffect(() => {
    if (tab === 'slow-queries' && !slowQueriesEnabled) setTab('overview');
  }, [tab, slowQueriesEnabled]);

  // Les 90 jours du tiroir finissent **aujourd'hui**, pas sur une plage d'en-tête :
  // cette page n'en expose plus, et lire une plage invisible laisserait une page
  // voisine décaler ces courbes sans que rien ne l'indique.
  const drawerPeriod = useMemo(() => {
    const trendEnd = todayIsoUtc();
    return { period_start: subtractDaysIso(trendEnd, 89), period_end: trendEnd };
  }, []);

  // Seul onglet dont l'endpoint filtre vraiment sur des bornes : il porte donc sa
  // propre plage, à la place du sélecteur de dates retiré de l'en-tête.
  const slowPeriod = useMemo(() => lastNDaysPeriodIso(slowWindowDays), [slowWindowDays]);

  // Les combos interrogent le serveur dans le périmètre du tableau : sans la
  // fenêtre, elles listeraient les valeurs du jour pour un tableau en 90 jours.
  const overviewFilterScope = useMemo(() => ({ windowDays }), [windowDays]);

  // Les valeurs des paramètres historiques sont **dérivées** des filtres, jamais
  // stockées à part : c'est ce qui garantit qu'un `warehouse_size` et un
  // `column_filter=size:…` divergents ne partent jamais ensemble (réponse 422).
  const overviewSizeFilter = overviewFilters.size ?? '';
  const overviewFailureThreshold = numericFilter(overviewFilters.failure);
  const costSize = costColumnFilters.size ?? '';
  const perfFailureThreshold = numericFilter(perfFilters.failure);
  const perfLatencyThreshold = numericFilter(perfFilters.p95);
  const perfSpill = perfFilters.spill === 'with';
  const slowReason = slowFilters.reason ?? '';

  // La colonne « Warehouse » de l'onglet Coût et la barre de recherche pilotent le
  // même prédicat (`search`). La barre reste maîtresse de la valeur ; la combo
  // l'alimente, et le filtre exposé au tableau la reflète pour que l'entonnoir
  // s'affiche actif.
  const costFilters = useMemo(
    () => withColumnFilter(costColumnFilters, 'warehouse', costSearch),
    [costColumnFilters, costSearch]
  );
  const changeCostFilters = (next: ComputeColumnFilterValues) => {
    const { warehouse, ...rest } = next;
    const search = warehouse ?? '';
    if (search !== costSearch) {
      setCostSearchInput(search);
      setCostSearch(search);
    }
    setCostColumnFilters(rest);
  };

  // Window, search, filters, sort and paging all happen server-side: the window
  // selects a pre-aggregated row in gold, and 1 824 warehouses do not fit in one
  // response, so a client-side pass would only see the first slice.
  const overview = useComputeWarehousesOverviewData({
    window_days: windowDays,
    search: overviewSearch,
    warehouse_size: overviewSizeFilter || undefined,
    min_failure_rate_pct: overviewFailureThreshold,
    filters: overviewFilters,
    sort: overviewSortKey,
    sort_direction: overviewSortDirection,
    page: overviewPage,
    pageSize: OVERVIEW_PAGE_SIZE,
  });
  const cost = useComputeWarehousesCostData({
    window_days: windowDays,
    search: costSearch,
    warehouse_size: costSize,
    filters: costFilters,
    sort: costSort,
    page: costPage,
    enabled: tab === 'cost' || tab === 'overview',
  });
  const queryPerf = useComputeWarehousesQueryPerformanceData({
    window_days: windowDays,
    min_failure_rate_pct: perfFailureThreshold,
    // `has_spill=false` n'est pas « sans spill » côté serveur, c'est « pas de
    // filtre » : seul `spill:without` peut exprimer l'autre moitié.
    has_spill: perfSpill ? true : undefined,
    min_latency_p95_ms: perfLatencyThreshold,
    filters: perfFilters,
    page: perfPage,
    enabled: tab === 'query-performance',
  });
  const slowQueries = useComputeWarehousesSlowQueriesData({
    windowDays: slowWindowDays,
    warehouse_id: slowWarehouseId || undefined,
    reason: slowReason || undefined,
    filters: slowFilters,
    page: slowPage,
    enabled: tab === 'slow-queries' && slowQueriesEnabled,
  });

  const detail = useComputeWarehouseDetail(selectedWarehouse?.id ?? null);
  const trend = useComputeWarehouseCostTrend({
    warehouseId: selectedWarehouse?.id ?? null,
    granularity: drawerGranularity,
    ...drawerPeriod,
  });

  const overviewItems = useMemo(() => overview.data?.items ?? [], [overview.data?.items]);

  /** The window the API reports as covered — never recomputed from the chip. */
  const activeWindow: ComputeWarehouseWindow | null = useMemo(() => {
    if (tab === 'cost') return cost.data?.window ?? overview.data?.window ?? null;
    if (tab === 'query-performance') return queryPerf.data?.window ?? overview.data?.window ?? null;
    return overview.data?.window ?? null;
  }, [tab, cost.data?.window, queryPerf.data?.window, overview.data?.window]);

  // An empty window has no bounds in gold, and none are invented from `today`.
  const coveredPeriodLabel =
    activeWindow?.from_date && activeWindow.to_date
      ? `${activeWindow.from_date} → ${activeWindow.to_date}`
      : 'no data over this range';

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
    // Text columns open ascending, metrics descending: "biggest first" is what a user wants
    // from a cost, and A→Z is what they want from a name or a category.
    setOverviewSortDirection(
      nextKey === 'warehouse' || nextKey === 'workspace' || nextKey === 'type' ? 'asc' : 'desc'
    );
  };

  const openDrawer = (id: string, title: string) => setSelectedWarehouse({ id, title });

  const overviewColumns = useMemo(
    (): ComputeDataTableColumn<ComputeWarehousesOverviewItem>[] => [
      // Workspace first, warehouse second: a warehouse name is only unique inside
      // its workspace, so the reading order goes from the container to the object.
      {
        id: 'workspace',
        filterKey: 'workspace',
        width: COLUMN_WIDTH.identifier,
        header: 'Workspace',
        description: computeWarehouseFieldDescriptions.workspace,
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
        id: 'warehouse',
        filterKey: 'warehouse',
        width: COLUMN_WIDTH.name,
        header: 'Warehouse',
        description: computeWarehouseFieldDescriptions.warehouse,
        sortable: true,
        cell: (row) => (
          <button
            type="button"
            className="text-left"
            onClick={() => openDrawer(row.warehouse_id, row.warehouse_name || row.warehouse_id)}
          >
            <WarehouseCell name={row.warehouse_name} id={row.warehouse_id} />
          </button>
        ),
      },
      {
        id: 'size',
        filterKey: 'size',
        width: COLUMN_WIDTH.label,
        header: 'Size',
        description: computeWarehouseFieldDescriptions.warehouseSize,
        sortable: true,
        cell: (row) => row.warehouse_size || '—',
      },
      // Next to the size, because the two together are the configuration of the warehouse:
      // the size says how big, the type says what kind. Rendered as the value the API
      // returns rather than a prettified label — SERVERLESS, PRO and CLASSIC are the words
      // Databricks itself uses, and the filter dropdown offers the same three.
      //
      // One neutral variant for all three: a warehouse type is a fact, not a verdict.
      // Colouring serverless green would advise a migration this cell is not measuring.
      {
        id: 'type',
        filterKey: 'type',
        width: COLUMN_WIDTH.label,
        header: 'Type',
        description: computeWarehouseFieldDescriptions.warehouseType,
        sortable: true,
        cell: (row) =>
          row.warehouse_type ? (
            <Badge variant="secondary">{row.warehouse_type}</Badge>
          ) : (
            '—'
          ),
      },
      {
        id: 'cost',
        filterKey: 'cost',
        width: COLUMN_WIDTH.metric,
        header: 'Cost',
        description: computeWarehouseFieldDescriptions.cost,
        align: 'right',
        sortable: true,
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatUsd(row.cost_usd)}</span>
        ),
      },
      {
        id: 'queries',
        filterKey: 'queries',
        width: COLUMN_WIDTH.number,
        header: 'Queries',
        description: computeWarehouseFieldDescriptions.queries,
        align: 'right',
        sortable: true,
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatNumber(row.query_count)}</span>
        ),
      },
      {
        id: 'failure',
        filterKey: 'failure',
        width: COLUMN_WIDTH.badge,
        header: 'Failure rate',
        description: computeWarehouseFieldDescriptions.failureRate,
        sortable: true,
        cell: (row) => (
          <Badge variant={failureBadgeVariant(row.failure_rate_pct)}>
            {formatPct(row.failure_rate_pct, 1)}
          </Badge>
        ),
      },
      {
        id: 'latency',
        filterKey: 'latency',
        width: COLUMN_WIDTH.metric,
        header: 'Latency p95',
        description: computeWarehouseFieldDescriptions.latencyP95,
        align: 'right',
        sortable: true,
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatDurationMs(row.latency_p95_ms)}</span>
        ),
      },
    ],
    [resolveWithId]
  );

  const costColumns = useMemo(
    (): ComputeDataTableColumn<ComputeWarehouseCostItem>[] => [
      {
        id: 'warehouse',
        filterKey: 'warehouse',
        width: COLUMN_WIDTH.name,
        header: 'Warehouse',
        description: computeWarehouseFieldDescriptions.warehouse,
        cell: (row) => (
          <button
            type="button"
            className="text-left"
            onClick={() => openDrawer(row.warehouse_id, row.warehouse_name || row.warehouse_id)}
          >
            <WarehouseCell name={row.warehouse_name} id={row.warehouse_id} />
          </button>
        ),
      },
      {
        id: 'size',
        filterKey: 'size',
        width: COLUMN_WIDTH.label,
        header: 'Size',
        description: computeWarehouseFieldDescriptions.warehouseSize,
        cell: (row) => row.warehouse_size || '—',
      },
      {
        id: 'dbu',
        filterKey: 'dbu',
        width: COLUMN_WIDTH.number,
        header: 'DBU',
        description: computeWarehouseFieldDescriptions.dbu,
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatNumber(row.dbu_quantity)}</span>
        ),
      },
      {
        id: 'cost',
        filterKey: 'cost',
        width: COLUMN_WIDTH.metric,
        header: 'Cost',
        description: computeWarehouseFieldDescriptions.cost,
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatUsd(row.cost_usd)}</span>
        ),
      },
      {
        id: 'delta',
        width: COLUMN_WIDTH.metric,
        header: 'Δ vs prev window',
        description: computeWarehouseFieldDescriptions.costDelta,
        align: 'right',
        // No predecessor window is not a 0 % variation: the backend nulls both
        // fields together, and this column must read as "nothing to compare".
        cell: (row) =>
          row.cost_usd_prev_window == null || row.cost_delta_pct == null ? (
            <span className="text-muted-foreground">—</span>
          ) : (
            <div>
              <span
                className={cn(
                  'font-semibold tabular-nums',
                  row.cost_delta_pct > 0
                    ? 'text-danger'
                    : row.cost_delta_pct < 0
                      ? 'text-success'
                      : 'text-muted-foreground'
                )}
              >
                {formatDeltaPct(row.cost_delta_pct)}
              </span>
              <div className="text-[10px] font-bold tabular-nums text-muted-foreground">
                {formatUsd(row.cost_usd_prev_window)}
              </div>
            </div>
          ),
      },
      {
        id: 'queries',
        filterKey: 'queries',
        width: COLUMN_WIDTH.number,
        header: 'Queries',
        description: computeWarehouseFieldDescriptions.queries,
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatNumber(row.query_count)}</span>
        ),
      },
      {
        id: 'cost_per_query',
        filterKey: 'cost_per_query',
        width: COLUMN_WIDTH.metric,
        header: 'Cost / query',
        description: computeWarehouseFieldDescriptions.costPerQuery,
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatUsd(row.cost_per_query_usd, 3)}</span>
        ),
      },
    ],
    []
  );

  const perfColumns = useMemo(
    (): ComputeDataTableColumn<ComputeWarehouseQueryPerformanceItem>[] => [
      {
        id: 'warehouse',
        filterKey: 'warehouse',
        width: COLUMN_WIDTH.name,
        header: 'Warehouse',
        description: computeWarehouseFieldDescriptions.warehouse,
        cell: (row) => (
          <button
            type="button"
            className="text-left"
            onClick={() => openDrawer(row.warehouse_id, row.warehouse_name || row.warehouse_id)}
          >
            <WarehouseCell name={row.warehouse_name} id={row.warehouse_id} />
          </button>
        ),
      },
      {
        id: 'queries',
        filterKey: 'queries',
        width: COLUMN_WIDTH.number,
        header: 'Queries',
        description: computeWarehouseFieldDescriptions.queries,
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatNumber(row.query_count)}</span>
        ),
      },
      {
        id: 'failure',
        filterKey: 'failure',
        width: COLUMN_WIDTH.badge,
        header: 'Failure %',
        description: computeWarehouseFieldDescriptions.failureRate,
        cell: (row) => (
          <Badge variant={failureBadgeVariant(row.failure_rate_pct)}>
            {formatPct(row.failure_rate_pct, 1)}
          </Badge>
        ),
      },
      {
        id: 'p50',
        filterKey: 'p50',
        width: COLUMN_WIDTH.number,
        header: 'p50',
        description: computeWarehouseFieldDescriptions.latencyP50,
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatDurationMs(row.latency_p50_ms)}</span>
        ),
      },
      {
        id: 'p95',
        filterKey: 'p95',
        width: COLUMN_WIDTH.number,
        header: 'p95',
        description: computeWarehouseFieldDescriptions.latencyP95,
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatDurationMs(row.latency_p95_ms)}</span>
        ),
      },
      {
        id: 'p99',
        filterKey: 'p99',
        width: COLUMN_WIDTH.number,
        header: 'p99',
        description: computeWarehouseFieldDescriptions.latencyP99,
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatDurationMs(row.latency_p99_ms)}</span>
        ),
      },
      {
        id: 'queue',
        filterKey: 'queue',
        width: COLUMN_WIDTH.metric,
        header: 'Queue p95',
        description: computeWarehouseFieldDescriptions.queueP95,
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">
            {formatDurationMs(row.queue_time_p95_ms)}
          </span>
        ),
      },
      {
        id: 'spill',
        filterKey: 'spill',
        width: COLUMN_WIDTH.number,
        header: 'Spill',
        description: computeWarehouseFieldDescriptions.spillCount,
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatNumber(row.spill_query_count)}</span>
        ),
      },
      {
        id: 'cache',
        filterKey: 'cache',
        width: COLUMN_WIDTH.metric,
        header: 'Cache hit',
        description: computeWarehouseFieldDescriptions.cacheHit,
        align: 'right',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatPct(row.cache_hit_pct, 1)}</span>
        ),
      },
    ],
    []
  );

  const slowColumns = useMemo(
    (): ComputeDataTableColumn<ComputeWarehouseSlowQueryItem>[] => [
      {
        id: 'statement',
        width: COLUMN_WIDTH.identifier,
        header: 'Statement ID',
        description: computeWarehouseFieldDescriptions.statementId,
        cell: (row) => <span className="font-mono text-xs">{row.statement_id}</span>,
      },
      {
        id: 'warehouse',
        filterKey: 'warehouse',
        width: COLUMN_WIDTH.name,
        header: 'Warehouse',
        description: computeWarehouseFieldDescriptions.warehouse,
        cell: (row) => row.warehouse_name || row.warehouse_id,
      },
      {
        id: 'user',
        filterKey: 'user',
        width: COLUMN_WIDTH.tag,
        header: 'Executed by',
        description: computeWarehouseFieldDescriptions.executedBy,
        cell: (row) => row.executed_by || '—',
      },
      {
        id: 'start',
        width: COLUMN_WIDTH.timestamp,
        header: 'Start',
        description: computeWarehouseFieldDescriptions.startTime,
        cell: (row) => (row.start_time ? new Date(row.start_time).toLocaleString('en-US') : '—'),
      },
      {
        id: 'duration',
        filterKey: 'duration',
        width: COLUMN_WIDTH.number,
        header: 'Duration',
        description: computeWarehouseFieldDescriptions.duration,
        cell: (row) => formatDurationMs(row.duration_ms),
      },
      {
        id: 'status',
        filterKey: 'status',
        width: COLUMN_WIDTH.status,
        header: 'Status',
        description: computeWarehouseFieldDescriptions.status,
        cell: (row) => row.status || '—',
      },
      {
        id: 'reason',
        filterKey: 'reason',
        width: COLUMN_WIDTH.identifier,
        header: 'Reason',
        description: computeWarehouseFieldDescriptions.reason,
        cell: (row) => <Badge variant="secondary">{reasonLabel(row.reason)}</Badge>,
      },
      {
        id: 'error',
        width: COLUMN_WIDTH.composite,
        header: 'Error',
        description: computeWarehouseFieldDescriptions.errorMessage,
        cell: (row) => row.error_message || '—',
      },
      {
        id: 'open',
        width: COLUMN_WIDTH.action,
        resizable: false,
        header: 'Open',
        cell: (row) => {
          const href = resolveQueryProfileUrl(row);
          if (!href) return '—';
          return (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
            >
              Open
              <ExternalLink className="size-3" />
            </a>
          );
        },
      },
    ],
    []
  );

  const selectedWorkspaceLabel = selectedWarehouse
    ? resolveWithId(
        detail.data?.workspace_id ??
          overviewItems.find((item) => item.warehouse_id === selectedWarehouse.id)?.workspace_id
      ).label
    : undefined;

  const warehouseOptions = useMemo(() => {
    const ids = new Set<string>();
    for (const item of overviewItems) ids.add(item.warehouse_id);
    for (const item of cost.data?.items ?? []) ids.add(item.warehouse_id);
    return [...ids].sort();
  }, [overviewItems, cost.data?.items]);

  const totalCostUsd = overview.data?.kpis?.total_cost_usd ?? 0;
  const topCostItem = cost.data?.items?.[0] ?? null;
  const topCostLabel = topCostItem?.warehouse_name || topCostItem?.warehouse_id || '—';
  const topCostShare =
    topCostItem?.cost_usd != null && totalCostUsd > 0
      ? `${Math.round((topCostItem.cost_usd / totalCostUsd) * 100)}% of total`
      : '';

  const perfItems = queryPerf.data?.items ?? [];
  const perfFailureAvg =
    perfItems.length > 0
      ? perfItems.reduce((sum, it) => sum + (Number(it.failure_rate_pct) || 0), 0) /
        perfItems.length
      : null;
  const perfLatencyAvg =
    perfItems.length > 0
      ? perfItems.reduce((sum, it) => sum + (Number(it.latency_p95_ms) || 0), 0) / perfItems.length
      : null;
  const perfSpillTotal = perfItems.reduce(
    (sum, it) => sum + (Number(it.spill_query_count) || 0),
    0
  );
  const perfFailedTotal = perfItems.reduce((sum, it) => sum + (Number(it.failed_count) || 0), 0);

  return (
    <Content className="mx-auto max-w-[1600px] gap-0 p-4 pb-24 lg:px-6 lg:pb-28">
      <ContentHeader>
        <div>
          <ContentTitle>SQL Warehouses</ContentTitle>
          {/* Aucun onglet n'honore plus de plage d'en-tête — la page n'en expose plus.
              Les trois onglets à fenêtre lisent un instantané pré-agrégé ; Slow
              queries garde des dates, celles de ses propres chips. */}
          <p className="mt-2 text-sm text-muted-foreground">
            {tab === 'slow-queries'
              ? `Inspect slow statements from ${slowPeriod.period_start} to ${slowPeriod.period_end} — ${scope.label}.`
              : `Explore warehouse costs and query performance over a rolling window — ${scope.label}.`}
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            void overview.refetch();
            void cost.refetch();
            void queryPerf.refetch();
            void slowQueries.refetch();
          }}
          disabled={overview.fetching}
        >
          <RefreshCw />
          Refresh
        </Button>
      </ContentHeader>

      <ContentMain className="gap-5">
        <ComputeWarehouseTabs value={tab} onChange={setTab} showSlowQueries={slowQueriesEnabled} />

        {/* Une plage par grain, jamais les deux : les trois onglets à instantané
            choisissent une fenêtre pré-agrégée, Slow queries des dates. Les dates
            de cet onglet sont dans le sous-titre de la page, pas répétées ici. */}
        <div className="flex flex-wrap items-center gap-3">
          {tab === 'slow-queries' ? (
            <WindowChipGroup
              label="Slow queries range"
              options={SLOW_QUERIES_RANGES}
              value={slowWindowDays}
              onChange={(next) => {
                setSlowWindowDays(next);
                setSlowPage(1);
              }}
            />
          ) : (
            <>
              <WindowChipGroup
                label="Rolling window"
                options={ROLLING_WINDOWS}
                value={windowDays}
                onChange={setWindowDays}
              />
              <span className="text-xs text-muted-foreground">
                Covered period{' '}
                <span className="font-mono font-semibold text-foreground">
                  {coveredPeriodLabel}
                </span>
              </span>
            </>
          )}
        </div>

        {tab === 'overview' ? (
          <>
            <div className="grid grid-cols-1 gap-4 overflow-visible sm:grid-cols-2 xl:grid-cols-5">
              {overview.loading && !overview.data ? (
                Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-32" />)
              ) : (
                <>
                  <ComputeKpiCard
                    title="Total cost"
                    description={computeWarehouseKpiDescriptions.totalCost}
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
                    title="Active warehouses"
                    description={computeWarehouseKpiDescriptions.activeWarehouses}
                    value={formatNumber(overview.data?.kpis.active_warehouses ?? null)}
                    subtitle="Billed over the window"
                    tone="success"
                    icon={Database}
                  />
                  <ComputeKpiCard
                    title="Queries executed"
                    description={computeWarehouseKpiDescriptions.queryCount}
                    value={formatNumber(overview.data?.kpis.query_count ?? null)}
                    subtitle="All warehouses"
                    tone="info"
                    icon={Activity}
                  />
                  <ComputeKpiCard
                    title="Failed queries"
                    description={computeWarehouseKpiDescriptions.failedQueries}
                    value={formatNumber(overview.data?.kpis.failed_count ?? null)}
                    subtitle="Across warehouses"
                    tone="warning"
                    icon={AlertTriangle}
                  />
                  <Link
                    to="/databricks/compute/recommendations?object_type=WAREHOUSE"
                    className="block overflow-hidden rounded-[var(--card-radius)] transition-shadow hover:shadow-[var(--card-hover-shadow)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    aria-label="View warehouse recommendations"
                  >
                    <ComputeKpiCard
                      title="Open recommendations"
                      description={computeWarehouseKpiDescriptions.openRecommendations}
                      value={formatNumber(overview.data?.kpis.open_recommendations ?? null)}
                      subtitle="Warehouses only · click to open list"
                      tone="purple"
                      icon={ShieldAlert}
                    />
                  </Link>
                </>
              )}
            </div>

            {overviewItems.length || overviewFiltersActive ? (
              <ComputeDataTable
                tableId="compute-warehouses-overview"
                columns={overviewColumns}
                rows={overviewItems}
                rowKey={(row) => `${row.workspace_id}-${row.warehouse_id}`}
                loading={overview.loading && !overview.data}
                onRowClick={(row) =>
                  openDrawer(row.warehouse_id, row.warehouse_name || row.warehouse_id)
                }
                sort={{ key: overviewSortKey, direction: overviewSortDirection }}
                onSortChange={handleOverviewSort}
                toolbar={
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="relative w-full max-w-[280px] shrink-0">
                      <Input
                        value={overviewSearchInput}
                        onChange={(e) => setOverviewSearchInput(e.target.value)}
                        placeholder="Search warehouse, workspace, size…"
                        className="h-8 rounded-full text-xs"
                        aria-label="Search overview warehouses"
                      />
                    </div>
                    <WarehouseSizeSelect
                      value={overviewSizeFilter}
                      onChange={(next) =>
                        setOverviewFilters((current) => withColumnFilter(current, 'size', next))
                      }
                    />
                    <FilterChip
                      active={overviewFailureThreshold != null}
                      onClick={() =>
                        setOverviewFilters((current) =>
                          withColumnFilter(
                            current,
                            'failure',
                            current.failure ? '' : String(FAILURE_FILTER_PCT)
                          )
                        )
                      }
                    >
                      With failures
                    </FilterChip>
                  </div>
                }
                filterView="warehouses-overview"
                filterScope={overviewFilterScope}
                filters={overviewFilters}
                onFiltersChange={setOverviewFilters}
                pagination={overviewPagination}
                minWidthClassName="min-w-[1180px]"
                emptyTitle="No warehouses match these filters"
                emptyDescription="Try clearing search, size, or failure filters."
              />
            ) : overview.loading ? (
              <Skeleton className="h-[280px]" />
            ) : (
              <ComputeEmptyState
                title="No warehouses found"
                description="No warehouse metrics are available for the selected scope and time range."
              />
            )}
          </>
        ) : null}

        {tab === 'cost' ? (
          <>
            <div className="grid grid-cols-1 gap-4 overflow-visible sm:grid-cols-2 xl:grid-cols-3">
              <ComputeKpiCard
                title="Total cost"
                description={computeWarehouseKpiDescriptions.totalCost}
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
                description={computeWarehouseKpiDescriptions.dbuPage}
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
                description={computeWarehouseKpiDescriptions.topCostly}
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
              tableId="compute-warehouses-cost"
              columns={costColumns}
              rows={cost.data?.items ?? []}
              rowKey={(row) => `${row.workspace_id}-${row.warehouse_id}`}
              loading={cost.loading && !cost.data}
              onRowClick={(row) =>
                openDrawer(row.warehouse_id, row.warehouse_name || row.warehouse_id)
              }
              toolbar={
                <div className="flex flex-wrap items-center gap-2">
                  <div className="relative w-full max-w-[260px] shrink-0">
                    <Input
                      value={costSearchInput}
                      onChange={(e) => setCostSearchInput(e.target.value)}
                      placeholder="Search warehouses…"
                      className="h-8 rounded-full text-xs"
                      aria-label="Search warehouses"
                    />
                  </div>
                  <WarehouseSizeSelect
                    value={costSize}
                    onChange={(next) =>
                      setCostColumnFilters((current) => withColumnFilter(current, 'size', next))
                    }
                  />
                  <select
                    className="h-8 rounded-full border border-border bg-card px-3 text-xs text-foreground"
                    value={costSort}
                    onChange={(e) => {
                      setCostSort(e.target.value as 'cost_desc' | 'name');
                      setCostPage(1);
                    }}
                    aria-label="Sort warehouses"
                  >
                    <option value="cost_desc">Sort by cost</option>
                    <option value="name">Sort by name</option>
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
              filterView="warehouses-cost"
              filterScope={overviewFilterScope}
              filters={costFilters}
              onFiltersChange={changeCostFilters}
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
              emptyTitle="No warehouses match these filters"
              emptyDescription="Try clearing search, size, or sorting options."
            />
          </>
        ) : null}

        {tab === 'query-performance' ? (
          <>
            <div className="grid grid-cols-1 gap-4 overflow-visible sm:grid-cols-2 xl:grid-cols-4">
              <ComputeKpiCard
                title="Avg failure rate (page)"
                description={computeWarehouseKpiDescriptions.avgFailureRate}
                value={perfFailureAvg == null ? '—' : formatPct(perfFailureAvg, 1)}
                subtitle="Average over visible rows"
                tone="warning"
                icon={AlertTriangle}
              />
              <ComputeKpiCard
                title="Avg p95 latency (page)"
                description={computeWarehouseKpiDescriptions.avgLatencyP95}
                value={perfLatencyAvg == null ? '—' : formatDurationMs(perfLatencyAvg)}
                subtitle="Average over visible rows"
                tone="info"
                icon={Activity}
              />
              <ComputeKpiCard
                title="Spill queries (page)"
                description={computeWarehouseKpiDescriptions.spillQueriesPage}
                value={formatNumber(perfSpillTotal)}
                subtitle="Sum over visible rows"
                tone="success"
                icon={Database}
              />
              <ComputeKpiCard
                title="Failed queries (page)"
                description={computeWarehouseKpiDescriptions.failedQueriesPage}
                value={formatNumber(perfFailedTotal)}
                subtitle="Sum over visible rows"
                tone="purple"
                icon={ShieldAlert}
              />
            </div>

            <ComputeDataTable
              tableId="compute-warehouses-query-performance"
              columns={perfColumns}
              rows={queryPerf.data?.items ?? []}
              rowKey={(row) => `${row.workspace_id}-${row.warehouse_id}`}
              loading={queryPerf.loading && !queryPerf.data}
              onRowClick={(row) =>
                openDrawer(row.warehouse_id, row.warehouse_name || row.warehouse_id)
              }
              toolbar={
                <div className="flex flex-wrap items-center gap-2">
                  <FilterChip
                    active={perfFailureThreshold != null}
                    onClick={() =>
                      setPerfFilters((current) =>
                        withColumnFilter(
                          current,
                          'failure',
                          current.failure ? '' : String(FAILURE_FILTER_PCT)
                        )
                      )
                    }
                  >
                    With failures
                  </FilterChip>
                  <FilterChip
                    active={perfSpill}
                    onClick={() =>
                      setPerfFilters((current) =>
                        withColumnFilter(current, 'spill', current.spill === 'with' ? '' : 'with')
                      )
                    }
                  >
                    With spill
                  </FilterChip>
                  <select
                    value={perfFilters.p95 ?? ''}
                    onChange={(e) =>
                      setPerfFilters((current) => withColumnFilter(current, 'p95', e.target.value))
                    }
                    className="h-8 rounded-full border border-border bg-card px-3 text-xs text-foreground"
                    aria-label="Latency p95 threshold"
                  >
                    <option value="">All latency</option>
                    <option value="10000">p95 &gt; 10s</option>
                    <option value="30000">p95 &gt; 30s</option>
                    {/* Le serveur propose d'autres seuils dans la combo de la colonne p95.
                        Sans cette option, le sélecteur afficherait « All latency » alors
                        qu'un seuil est actif. */}
                    {perfFilters.p95 && !PERF_LATENCY_OPTIONS.includes(perfFilters.p95) ? (
                      <option value={perfFilters.p95}>
                        p95 &gt; {formatDurationMs(Number(perfFilters.p95))}
                      </option>
                    ) : null}
                  </select>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="ml-auto"
                    onClick={() => void queryPerf.refetch()}
                    disabled={queryPerf.fetching}
                    aria-label="Refresh query performance table"
                  >
                    <RefreshCw />
                  </Button>
                </div>
              }
              filterView="warehouses-query-performance"
              filterScope={overviewFilterScope}
              filters={perfFilters}
              onFiltersChange={setPerfFilters}
              pagination={{
                currentPage: queryPerf.data?.page ?? perfPage,
                totalPages: queryPerf.data
                  ? Math.max(1, Math.ceil(queryPerf.data.total / queryPerf.data.page_size))
                  : 1,
                totalItems: queryPerf.data?.total ?? 0,
                startIndex: ((queryPerf.data?.page ?? perfPage) - 1) * 25,
                endIndex: Math.min(
                  ((queryPerf.data?.page ?? perfPage) - 1) * 25 +
                    (queryPerf.data?.items?.length ?? 0),
                  queryPerf.data?.total ?? 0
                ),
                hasPreviousPage: (queryPerf.data?.page ?? perfPage) > 1,
                hasNextPage: queryPerf.data
                  ? queryPerf.data.page * queryPerf.data.page_size < queryPerf.data.total
                  : false,
                onPrevious: () => setPerfPage((p) => Math.max(1, p - 1)),
                onNext: () => setPerfPage((p) => p + 1),
              }}
              emptyTitle="No warehouses match these filters"
              emptyDescription="Adjust failure, spill, or latency filters."
            />
          </>
        ) : null}

        {tab === 'slow-queries' && slowQueriesEnabled ? (
          <>
            <div className="rounded-[var(--radius)] border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
              SQL statement text is never displayed here — use the Open link to inspect the query in
              the native Databricks query profile.
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {(['FAILURE', 'SLOW', 'SPILL'] as const).map((reason) => (
                <FilterChip
                  key={reason}
                  active={slowReason === reason}
                  onClick={() =>
                    setSlowFilters((current) =>
                      withColumnFilter(current, 'reason', current.reason === reason ? '' : reason)
                    )
                  }
                >
                  {reasonLabel(reason)}
                </FilterChip>
              ))}
              <select
                value={slowWarehouseId}
                onChange={(e) => {
                  setSlowWarehouseId(e.target.value);
                  setSlowPage(1);
                }}
                className="h-10 rounded-[var(--radius)] border border-border bg-card px-3 text-sm"
                aria-label="Filter slow queries by warehouse"
              >
                <option value="">All warehouses</option>
                {warehouseOptions.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            </div>

            <ComputeDataTable
              tableId="compute-warehouses-slow-queries"
              columns={slowColumns}
              rows={slowQueries.data?.items ?? []}
              rowKey={(row) => row.statement_id}
              loading={slowQueries.loading && !slowQueries.data}
              filterView="warehouses-slow-queries"
              filters={slowFilters}
              onFiltersChange={setSlowFilters}
              pagination={{
                currentPage: slowQueries.data?.page ?? slowPage,
                totalPages: slowQueries.data
                  ? Math.max(1, Math.ceil(slowQueries.data.total / slowQueries.data.page_size))
                  : 1,
                totalItems: slowQueries.data?.total ?? 0,
                startIndex: ((slowQueries.data?.page ?? slowPage) - 1) * 25,
                endIndex: Math.min(
                  ((slowQueries.data?.page ?? slowPage) - 1) * 25 +
                    (slowQueries.data?.items?.length ?? 0),
                  slowQueries.data?.total ?? 0
                ),
                hasPreviousPage: (slowQueries.data?.page ?? slowPage) > 1,
                hasNextPage: slowQueries.data
                  ? slowQueries.data.page * slowQueries.data.page_size < slowQueries.data.total
                  : false,
                onPrevious: () => setSlowPage((p) => Math.max(1, p - 1)),
                onNext: () => setSlowPage((p) => p + 1),
              }}
              emptyTitle="No queries match this filter"
              emptyDescription="Adjust reason or warehouse filter."
            />
          </>
        ) : null}
      </ContentMain>

      <ComputeWarehouseDrawer
        open={Boolean(selectedWarehouse)}
        onClose={() => setSelectedWarehouse(null)}
        title={selectedWarehouse?.title ?? ''}
        detail={detail.data}
        detailLoading={detail.loading}
        detailError={detail.error}
        trend={trend.data}
        trendLoading={trend.loading}
        trendError={trend.error}
        granularity={drawerGranularity}
        onGranularityChange={setDrawerGranularity}
        workspaceLabel={selectedWorkspaceLabel}
      />
    </Content>
  );
}
