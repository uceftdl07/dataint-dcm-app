import { UcUsageColumnFilter } from '../components/domain/uc-usage/uc-usage-column-filter';
import {
  UC_TABLE_FILTERS,
  UC_CONSUMER_FILTERS,
  UC_COST_FILTERS,
} from '../lib/uc-usage/column-filters';
import { withColumnFilter } from '../lib/compute/column-filters';
import { UcUsageDetailDrawer } from '../components/domain/uc-usage/uc-usage-detail-drawer';
import {
  UcUsageWriteChartsPanel,
  UcUsageCostChangesPanel,
  UcUsageCostCoverage,
} from '../components/domain/uc-usage/uc-usage-exploration-charts';
import {
  useUcUsageWriteCharts,
  useUcUsageCostChanges,
  useUcUsageEntityDetail,
} from '../hooks/useUcUsageQueries';
import type { UcUsageEntitySelection } from '../types/api';
import { useMemo, useRef, useState, type ReactNode } from 'react';
import {
  AlertTriangle,
  ChevronRight,
  DollarSign,
  Database,
  Gauge,
  Table2,
  Users,
} from 'lucide-react';
import { ComputeDataTable } from '../components/domain/compute/compute-data-table';
import { ComputeInfoTip } from '../components/domain/compute/compute-info-tip';
import { ComputeKpiCard } from '../components/domain/compute/compute-kpi-card';
import { UcUsageDeletedBadge } from '../components/domain/uc-usage/uc-usage-deleted-badge';
import { UcUsageFilters } from '../components/domain/uc-usage/uc-usage-filters';
import { UcUsageWelcome } from '../components/domain/uc-usage/uc-usage-welcome';
import { UcUsageTrendCards } from '../components/domain/uc-usage/uc-usage-trend-cards';
import {
  UcUsageTableChartsPanel,
  UcUsageConsumerChartsPanel,
  UcUsageFinopsChartsPanel,
} from '../components/domain/uc-usage/uc-usage-charts';
import { Content, ContentHeader, ContentMain, ContentTitle } from '../components/layout/content';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Skeleton } from '../components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '../components/ui/tabs';
import { useGlobalTimeRange } from '../contexts/time-range';
import {
  UC_USAGE_PAGE_SIZE,
  useUcUsageConsumers,
  useUcUsageCostByTable,
  useUcUsageFinopsKpis,
  useUcUsageOverview,
  useUcUsageTableCharts,
  useUcUsageConsumerCharts,
  useUcUsageFinopsCharts,
  useUcUsageTables,
  useUcUsageTrends,
  type UcUsageAppliedPeriod,
  type UcUsageFilters as UcUsageFilterValues,
} from '../hooks/useUcUsageQueries';
import type {
  UcUsageConsumersParams,
  UcUsageCostByTableParams,
  UcUsageTablesParams,
} from '../api/dcmApiClient';
import { formatDeltaPct, formatNumber, formatPct, formatUsd } from '../lib/compute/format';
import {
  UC_USAGE_CONSUMER_TYPES,
  UC_USAGE_FAILURE_RATE_ALERT_PCT,
  formatBytes,
  formatIsoDate,
  formatMilliseconds,
  ucUsageConsumerTypeBadgeClass,
  ucUsageFreshnessIsEstimate,
  ucUsageFreshnessLabel,
} from '../lib/uc-usage/labels';
import {
  hasUcUsageScope,
  UC_USAGE_EMPTY_DRAFT,
  type UcUsageFilterDraft,
} from '../lib/uc-usage/filters';
import { cn } from '../lib/utils';
import type {
  UcUsageConsumerRow,
  UcUsageCostByTableRow,
  UcUsageForecastMetric,
  UcUsageTableRow,
} from '../types/api';

type ViewKey = 'tables' | 'consumers' | 'finops';

const VIEWS: Array<{ key: ViewKey; label: string }> = [
  { key: 'tables', label: 'By table' },
  { key: 'consumers', label: 'By consumer' },
  { key: 'finops', label: 'FinOps' },
];

/** Les 3 tendances de la vue d'ensemble (FR-001) ; `data_read_bytes` reste une mesure FinOps. */
const OVERVIEW_TREND_METRICS: UcUsageForecastMetric[] = [
  'request_count',
  'estimated_cost_usd',
  'distinct_consumers',
];

/** Les 2 tendances de la vue FinOps, comme au mockup. */
const FINOPS_TREND_METRICS: UcUsageForecastMetric[] = ['estimated_cost_usd', 'data_read_bytes'];

/** Intertitre de section, repris du mockup. */
function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <h2 className="text-[10px] font-black uppercase tracking-[1.2px] text-muted-foreground">
      {children}
    </h2>
  );
}

/** Titre + intention d'un tableau, dans la barre d'outils de la carte. */
function TableToolbar({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}

/** Provenance des chiffres, comme la footnote du mockup. */
function TableFootnote({ children }: { children: ReactNode }) {
  return <p className="px-1 text-[11px] text-muted-foreground">{children}</p>;
}

/**
 * Column click selects the server sort; a second click reverses its direction.
 */
const TABLE_SORT_BY_COLUMN: Record<string, UcUsageTablesParams['sort']> = {
  request_count: 'popularity',
  table_full_name: 'table_name',
  data_written_bytes: 'writes',
  rows_written: 'rows_written',
  distinct_consumers: 'consumers',
  data_read_bytes: 'read_bytes',
  freshness_lag_hours: 'freshness',
  estimated_cost_usd: 'cost',
  latency_p95_ms: 'latency',
  failure_rate_pct: 'failure_rate',
};

const CONSUMER_SORT_BY_COLUMN: Record<string, UcUsageConsumersParams['sort']> = {
  estimated_cost_usd: 'cost',
  request_count: 'requests',
  consumer_name: 'name',
  data_written_bytes: 'writes',
  rows_written: 'rows_written',
  data_read_bytes: 'read_bytes',
  distinct_tables: 'distinct_tables',
};

const COST_SORT_BY_COLUMN: Record<string, UcUsageCostByTableParams['sort']> = {
  estimated_cost_usd: 'cost',
  cost_per_request_usd: 'cost_per_request',
  request_count: 'requests',
  data_read_bytes: 'read_bytes',
  forecast_cost_usd_7d: 'forecast',
  table_full_name: 'table_name',
};

function columnOfSort(map: Record<string, string | undefined>, sort: string): string | undefined {
  return Object.keys(map).find((column) => map[column] === sort);
}

/**
 * Infobulle du coût : `equal_parts_fallback` répartit à parts égales entre les
 * tables d'une requête, ce qui n'est pas une mesure par table (FR-009).
 */
const COST_TOOLTIP =
  'Estimated attributed cost. The allocation method is shown on each row. Some costs are shared equally between the tables referenced by a query or allocated from warehouse billing.';

/** Une hausse se lit en vert, une baisse en rouge — sans jamais juger la mesure. */
function DeltaPct({ value }: { value: number | null | undefined }) {
  if (value == null) return null;
  const rising = value > 0;
  const falling = value < 0;
  return (
    <span
      className={cn(
        'ml-1 text-[10px] font-bold tabular-nums',
        rising && 'text-success',
        falling && 'text-danger',
        !rising && !falling && 'text-muted-foreground'
      )}
    >
      {rising ? '▲' : falling ? '▼' : ''} {formatDeltaPct(value)}
    </span>
  );
}

function paginationOf(total: number, page: number, onPage: (next: number) => void) {
  if (total === 0) return undefined;
  const totalPages = Math.max(1, Math.ceil(total / UC_USAGE_PAGE_SIZE));
  return {
    currentPage: page,
    totalPages,
    totalItems: total,
    startIndex: (page - 1) * UC_USAGE_PAGE_SIZE,
    endIndex: Math.min(page * UC_USAGE_PAGE_SIZE, total),
    hasPreviousPage: page > 1,
    hasNextPage: page < totalPages,
    onPrevious: () => onPage(Math.max(1, page - 1)),
    onNext: () => onPage(Math.min(totalPages, page + 1)),
  };
}

export default function UsageTablesUc() {
  const { getApiParams, getDisplayRange } = useGlobalTimeRange();
  const display = getDisplayRange();

  const [draft, setDraft] = useState<UcUsageFilterDraft>(UC_USAGE_EMPTY_DRAFT);
  const catalogTriggerRef = useRef<HTMLButtonElement>(null);
  const [filters, setFilters] = useState<UcUsageFilterValues>({});
  // `null` tant qu'aucun clic sur Appliquer : c'est ce qui garde les endpoints
  // datés silencieux au chargement (FR-017).
  const [appliedPeriod, setAppliedPeriod] = useState<UcUsageAppliedPeriod | null>(null);
  const [view, setView] = useState<ViewKey>('tables');
  const [search, setSearch] = useState('');
  const [consumerType, setConsumerType] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [tablesSort, setTablesSort] = useState<UcUsageTablesParams['sort']>('popularity');
  const [consumersSort, setConsumersSort] = useState<UcUsageConsumersParams['sort']>('cost');
  const [costSort, setCostSort] = useState<UcUsageCostByTableParams['sort']>('cost');
  const [tablesPage, setTablesPage] = useState(1);
  const [consumersPage, setConsumersPage] = useState(1);
  const [finopsPage, setFinopsPage] = useState(1);
  const [selectedEntity, setSelectedEntity] = useState<UcUsageEntitySelection | null>(null);
  const [tableDirection, setTableDirection] = useState<'asc' | 'desc'>('desc');
  const [consumerDirection, setConsumerDirection] = useState<'asc' | 'desc'>('desc');
  const [costDirection, setCostDirection] = useState<'asc' | 'desc'>('desc');
  const [tableColumnFilters, setTableColumnFilters] = useState<Record<string, string>>({});
  const [consumerColumnFilters, setConsumerColumnFilters] = useState<Record<string, string>>({});
  const [costColumnFilters, setCostColumnFilters] = useState<Record<string, string>>({});
  const periodApplied = appliedPeriod != null;
  const hasScope = hasUcUsageScope(draft);
  const scopeChanged =
    periodApplied &&
    (draft.catalog.trim() !== (filters.catalog ?? '') ||
      draft.schema.trim() !== (filters.schema ?? '') ||
      draft.includeDeleted !== Boolean(filters.includeDeleted) ||
      [...draft.tables].sort().join('\n') !== [...(filters.tables ?? [])].sort().join('\n'));

  const applyFilters = () => {
    if (!hasScope) return;
    const { start_date, end_date } = getApiParams();
    setFilters({
      catalog: draft.catalog.trim() || undefined,
      schema: draft.schema.trim() || undefined,
      tables: draft.tables,
      includeDeleted: draft.includeDeleted,
    });
    setAppliedSearch(search.trim());
    setAppliedPeriod({ start: start_date, end: end_date });
    setTablesPage(1);
    setConsumersPage(1);
    setFinopsPage(1);
    setSelectedEntity(null);
    setTableColumnFilters({});
    setConsumerColumnFilters({});
    setCostColumnFilters({});
  };

  const overview = useUcUsageOverview(filters, appliedPeriod);
  const trends = useUcUsageTrends(filters, appliedPeriod, {
    metrics: OVERVIEW_TREND_METRICS,
    enabled: periodApplied,
  });

  const tables = useUcUsageTables(filters, appliedPeriod, {
    search: appliedSearch,
    sort: tablesSort,
    direction: tableDirection,
    columnFilters: tableColumnFilters,
    page: tablesPage,
    enabled: view === 'tables',
  });
  const consumers = useUcUsageConsumers(filters, appliedPeriod, {
    search: appliedSearch,
    consumerType,
    sort: consumersSort,
    direction: consumerDirection,
    columnFilters: consumerColumnFilters,
    page: consumersPage,
    enabled: view === 'consumers',
  });
  const finopsKpis = useUcUsageFinopsKpis(filters, appliedPeriod, {
    enabled: view === 'finops',
  });
  const costByTable = useUcUsageCostByTable(filters, appliedPeriod, {
    search: appliedSearch,
    sort: costSort,
    direction: costDirection,
    columnFilters: costColumnFilters,
    page: finopsPage,
    enabled: view === 'finops',
  });
  const finopsTrends = useUcUsageTrends(filters, appliedPeriod, {
    metrics: FINOPS_TREND_METRICS,
    enabled: periodApplied && view === 'finops',
  });
  const writeCharts = useUcUsageWriteCharts(filters, appliedPeriod, view === 'tables');
  const costChanges = useUcUsageCostChanges(filters, appliedPeriod, view === 'finops');
  const entityDetail = useUcUsageEntityDetail(filters, appliedPeriod, selectedEntity);
  const tableCharts = useUcUsageTableCharts(filters, appliedPeriod, view === 'tables');
  const consumerCharts = useUcUsageConsumerCharts(filters, appliedPeriod, view === 'consumers');
  const finopsCharts = useUcUsageFinopsCharts(filters, appliedPeriod, view === 'finops');

  const periodLabel = periodApplied
    ? `${appliedPeriod.start} → ${appliedPeriod.end}`
    : `${display.startDate} → ${display.endDate} (not applied)`;

  const tableColumns = useMemo(
    () => [
      {
        id: 'table_full_name',
        header: 'Table',
        // Nom qualifié complet : le catalogue et le schéma se lisent dedans, deux
        // colonnes de plus ne feraient que reprendre ses deux premiers segments.
        width: 420,
        cell: (row: UcUsageTableRow) => (
          <span className="inline-flex min-w-0 items-center gap-1">
            <ChevronRight size={13} className="shrink-0 text-muted-foreground" aria-hidden />
            <span className="truncate font-medium" title={row.table_full_name}>
              {row.table_full_name}
            </span>
            <UcUsageDeletedBadge row={row} />
          </span>
        ),
      },
      {
        id: 'table_type',
        header: 'Type',
        width: 125,
        cell: (row: UcUsageTableRow) => row.table_type ?? '—',
      },
      {
        id: 'request_count',
        header: 'Read accesses',
        align: 'right' as const,
        sortable: true,
        width: 150,
        cell: (row: UcUsageTableRow) => (
          <span className="font-semibold tabular-nums">
            {formatNumber(row.request_count)}
            <DeltaPct value={row.request_delta_pct} />
          </span>
        ),
      },
      {
        id: 'distinct_consumers',
        header: 'Consumers',
        align: 'right' as const,
        width: 140,
        cell: (row: UcUsageTableRow) => formatNumber(row.distinct_consumers),
      },
      {
        id: 'data_read_bytes',
        header: 'Bytes read',
        align: 'right' as const,
        width: 130,
        cell: (row: UcUsageTableRow) => formatBytes(row.data_read_bytes),
      },
      {
        id: 'data_written_bytes',
        header: 'Bytes written',
        width: 145,
        align: 'right' as const,
        cell: (row: UcUsageTableRow) => formatBytes(row.data_written_bytes),
      },
      {
        id: 'rows_written',
        header: 'Rows written',
        width: 135,
        align: 'right' as const,
        cell: (row: UcUsageTableRow) => formatNumber(row.rows_written, 1),
      },
      {
        id: 'estimated_cost_usd',
        header: (
          <span className="inline-flex items-center gap-1">
            Estimated cost
            <ComputeInfoTip description={COST_TOOLTIP} label="About estimated cost" />
          </span>
        ),
        headerLabel: 'Estimated cost',
        align: 'right' as const,
        sortable: true,
        width: 150,
        cell: (row: UcUsageTableRow) => (
          <span
            title={`cost_attribution_method: ${row.cost_attribution_method ?? '—'} · cost_basis: ${
              row.cost_basis ?? '—'
            }`}
          >
            {formatUsd(row.estimated_cost_usd)}
          </span>
        ),
      },
      {
        id: 'latency_p95_ms',
        header: 'P95 latency',
        align: 'right' as const,
        sortable: true,
        width: 130,
        cell: (row: UcUsageTableRow) => formatMilliseconds(row.latency_p95_ms),
      },
      {
        id: 'failure_rate_pct',
        header: 'Failure rate',
        align: 'right' as const,
        sortable: true,
        width: 130,
        cell: (row: UcUsageTableRow) => (
          <span
            className={cn(
              (row.failure_rate_pct ?? 0) >= UC_USAGE_FAILURE_RATE_ALERT_PCT &&
                'font-bold text-danger'
            )}
          >
            {formatPct(row.failure_rate_pct, 1)}
          </span>
        ),
      },
      {
        id: 'freshness_lag_hours',
        header: 'Write freshness',
        width: 200,
        cell: (row: UcUsageTableRow) =>
          row.freshness_lag_hours == null ? (
            '—'
          ) : (
            <span className="text-muted-foreground">
              {ucUsageFreshnessLabel(row.freshness_lag_hours)}
              {ucUsageFreshnessIsEstimate(row.freshness_basis) ? (
                <span className="ml-1 text-xs">(estimate)</span>
              ) : null}
            </span>
          ),
      },
    ],
    []
  );

  const consumerColumns = useMemo(
    () => [
      {
        id: 'rank',
        header: 'Rank',
        width: 80,
        // Les cinq premiers portent la pastille : c'est le classement que la page
        // met en avant, le reste se lit comme un rang ordinaire.
        cell: (row: UcUsageConsumerRow) =>
          row.rank != null && row.rank <= 5 ? (
            <Badge>{row.rank}</Badge>
          ) : (
            <span className="text-muted-foreground">{formatNumber(row.rank)}</span>
          ),
      },
      {
        id: 'consumer_name',
        header: 'Consumer',
        width: 320,
        cell: (row: UcUsageConsumerRow) => (
          <span className="truncate font-medium" title={row.consumer_id}>
            {row.consumer_name?.trim() || row.consumer_id}
          </span>
        ),
      },
      {
        id: 'consumer_type',
        header: 'Type',
        width: 180,
        // Vocabulaire ouvert : une valeur inconnue s'affiche telle quelle.
        cell: (row: UcUsageConsumerRow) =>
          row.consumer_type?.trim() ? (
            <Badge variant="outline" className={ucUsageConsumerTypeBadgeClass(row.consumer_type)}>
              {row.consumer_type.trim()}
            </Badge>
          ) : (
            '—'
          ),
      },
      {
        id: 'distinct_tables',
        header: 'Tables accessed',
        align: 'right' as const,
        sortable: true,
        width: 130,
        cell: (row: UcUsageConsumerRow) => formatNumber(row.distinct_tables),
      },
      {
        id: 'request_count',
        header: 'Read accesses',
        align: 'right' as const,
        sortable: true,
        width: 130,
        cell: (row: UcUsageConsumerRow) => formatNumber(row.request_count),
      },
      {
        id: 'data_read_bytes',
        header: 'Bytes read',
        align: 'right' as const,
        width: 130,
        cell: (row: UcUsageConsumerRow) => formatBytes(row.data_read_bytes),
      },
      {
        id: 'data_written_bytes',
        header: 'Bytes written',
        width: 145,
        align: 'right' as const,
        cell: (row: UcUsageConsumerRow) => formatBytes(row.data_written_bytes),
      },
      {
        id: 'rows_written',
        header: 'Rows written',
        width: 135,
        align: 'right' as const,
        cell: (row: UcUsageConsumerRow) => formatNumber(row.rows_written, 1),
      },
      {
        id: 'estimated_cost_usd',
        header: 'Estimated cost',
        align: 'right' as const,
        sortable: true,
        width: 140,
        cell: (row: UcUsageConsumerRow) => formatUsd(row.estimated_cost_usd),
      },
      {
        id: 'last_used_at',
        header: 'Last access',
        width: 140,
        cell: (row: UcUsageConsumerRow) => formatIsoDate(row.last_used_at),
      },
    ],
    []
  );

  const costColumns = useMemo(
    () => [
      {
        id: 'table_full_name',
        header: 'Table',
        width: 420,
        cell: (row: UcUsageCostByTableRow) => (
          <span className="inline-flex min-w-0 items-center gap-1">
            <span className="truncate font-medium" title={row.table_full_name}>
              {row.table_full_name}
            </span>
            <UcUsageDeletedBadge row={row} />
          </span>
        ),
      },
      {
        id: 'estimated_cost_usd',
        header: 'Estimated cost',
        align: 'right' as const,
        width: 150,
        cell: (row: UcUsageCostByTableRow) => formatUsd(row.estimated_cost_usd),
      },
      {
        id: 'cost_per_request_usd',
        header: 'Cost / access',
        align: 'right' as const,
        width: 150,
        cell: (row: UcUsageCostByTableRow) => formatUsd(row.cost_per_request_usd, 4),
      },
      {
        id: 'request_count',
        header: 'Read accesses',
        align: 'right' as const,
        width: 130,
        cell: (row: UcUsageCostByTableRow) => formatNumber(row.request_count),
      },
      {
        id: 'data_read_bytes',
        header: 'Bytes read',
        align: 'right' as const,
        width: 130,
        cell: (row: UcUsageCostByTableRow) => formatBytes(row.data_read_bytes),
      },
      {
        id: 'forecast_cost_usd_7d',
        header: 'Forecast +7d',
        align: 'right' as const,
        width: 150,
        // `null` = pas de ligne de prévision ; `formatUsd` rend un tiret (SC-005).
        cell: (row: UcUsageCostByTableRow) => formatUsd(row.forecast_cost_usd_7d),
      },
    ],
    []
  );

  const searchSlot = (
    <Input
      className="h-8 pl-9 text-xs"
      value={search}
      onChange={(event) => setSearch(event.target.value)}
      placeholder="Table or consumer name…"
      aria-label="Search by name"
    />
  );

  return (
    <Content className="mx-auto max-w-[1600px] gap-0 p-4 pb-24 lg:px-6 lg:pb-28">
      <ContentHeader>
        <div>
          <ContentTitle>UC table usage</ContentTitle>
          <p className="mt-2 text-sm text-muted-foreground">
            Usage, cost and write freshness of Unity Catalog tables · AWS and Azure combined
          </p>
        </div>
      </ContentHeader>

      <ContentMain className="gap-5">
        <UcUsageFilters
          draft={draft}
          onDraftChange={setDraft}
          onApply={applyFilters}
          periodLabel={periodLabel}
          searchSlot={periodApplied ? searchSlot : undefined}
          requireScope
          catalogTriggerRef={catalogTriggerRef}
        />

        {!periodApplied ? (
          <UcUsageWelcome
            hasScope={hasScope}
            onChooseScope={() => {
              catalogTriggerRef.current?.focus();
              catalogTriggerRef.current?.click();
            }}
          />
        ) : (
          <>
            {scopeChanged ? (
              <p
                role="status"
                className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground"
              >
                Selection changed: results still reflect the last applied scope. Click Apply to
                update the analysis.
              </p>
            ) : null}
            <section aria-label="Overview" className="space-y-4">
              <SectionLabel>Overview — period</SectionLabel>
              {overview.loading ? (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-6">
                  {Array.from({ length: 6 }).map((_, index) => (
                    <Skeleton key={index} className="h-[120px]" />
                  ))}
                </div>
              ) : overview.error ? (
                <p className="text-sm text-danger">Unable to load the overview.</p>
              ) : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-6">
                  <ComputeKpiCard
                    title="Tracked tables"
                    description="Distinct tables with an observed usage record in the period."
                    value={formatNumber(overview.data?.tracked_tables ?? null)}
                    tone="info"
                    icon={Table2}
                  />
                  <ComputeKpiCard
                    title="Read accesses"
                    description="Total read accesses in the period, compared with the previous period."
                    value={formatNumber(overview.data?.request_count ?? null)}
                    subtitle={formatDeltaPct(overview.data?.request_count_delta_pct ?? null)}
                    tone="info"
                    icon={Database}
                  />
                  <ComputeKpiCard
                    title="Consumers"
                    description="Distinct consumers across the whole period, counted once across days."
                    value={formatNumber(overview.data?.distinct_consumers ?? null)}
                    tone="purple"
                    icon={Users}
                  />
                  <ComputeKpiCard
                    title="Estimated cost"
                    description={COST_TOOLTIP}
                    value={formatUsd(overview.data?.estimated_cost_usd ?? null)}
                    subtitle={formatDeltaPct(overview.data?.estimated_cost_usd_delta_pct ?? null)}
                    tone="success"
                    icon={DollarSign}
                  />
                  <ComputeKpiCard
                    title="Unused tables"
                    description="Current governance snapshot, independent of the usage period."
                    value={formatNumber(overview.data?.unused_tables ?? null)}
                    tone="warning"
                    icon={AlertTriangle}
                  />
                  <ComputeKpiCard
                    title="Access failure rate"
                    description="Failed queries as a share of all queries in the period."
                    value={formatPct(overview.data?.access_failure_rate_pct ?? null, 2)}
                    tone="danger"
                    icon={Gauge}
                  />
                </div>
              )}

              <SectionLabel>Observed usage & 7-day outlook</SectionLabel>
              <div className="grid grid-cols-1 gap-4">
                <div>
                  {trends.loading ? (
                    <Skeleton className="h-[180px]" />
                  ) : (
                    <UcUsageTrendCards series={trends.data?.series ?? []} />
                  )}
                </div>
              </div>
            </section>

            <Tabs>
              <TabsList aria-label="Usage views">
                {VIEWS.map((entry) => (
                  <TabsTrigger
                    key={entry.key}
                    active={view === entry.key}
                    // Les filtres vivent au niveau de la page : changer de vue ne les remet pas à zéro (FR-002).
                    onClick={() => {
                      setView(entry.key);
                      setSelectedEntity(null);
                    }}
                  >
                    {entry.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>

            {view === 'tables' ? (
              <div className="space-y-2">
                <UcUsageTableChartsPanel {...tableCharts} onRetry={tableCharts.refetch} />
                <UcUsageWriteChartsPanel {...writeCharts} onRetry={writeCharts.refetch} />
                <ComputeDataTable<UcUsageTableRow>
                  tableId="uc-usage-tables"
                  toolbar={
                    <TableToolbar
                      title="Table popularity & performance"
                      hint="Click a row for trends and details · Filter columns across all results"
                    />
                  }
                  columns={tableColumns.map((column) => ({
                    ...column,
                    sortable: Boolean(TABLE_SORT_BY_COLUMN[column.id]),
                  }))}
                  locale="en"
                  filters={tableColumnFilters}
                  onFiltersChange={(next) => {
                    setTableColumnFilters(next);
                    setTablesPage(1);
                  }}
                  renderColumnFilter={(column) =>
                    UC_TABLE_FILTERS[column.id] ? (
                      <UcUsageColumnFilter
                        label={column.headerLabel ?? String(column.header)}
                        definition={UC_TABLE_FILTERS[column.id]}
                        value={tableColumnFilters[column.id]}
                        onChange={(value) => {
                          setTableColumnFilters((previous) =>
                            withColumnFilter(previous, column.id, value)
                          );
                          setTablesPage(1);
                        }}
                      />
                    ) : null
                  }
                  rows={tables.data?.items ?? []}
                  rowKey={(row) => row.table_full_name}
                  loading={tables.loading}
                  emptyTitle={tables.error ? 'Unable to load tables' : 'No tables in this scope'}
                  emptyDescription={
                    tables.error
                      ? 'Loading failed. Reapply the period to try again.'
                      : 'Adjust the filters or period, then click Apply.'
                  }
                  sort={{
                    key: columnOfSort(TABLE_SORT_BY_COLUMN, tablesSort ?? 'popularity') ?? '',
                    direction: tableDirection,
                  }}
                  onSortChange={(key) => {
                    const next = TABLE_SORT_BY_COLUMN[key];
                    if (!next) return;
                    setTableDirection((current) =>
                      next === tablesSort && current === 'desc' ? 'asc' : 'desc'
                    );
                    setTablesSort(next);
                    setTablesPage(1);
                  }}
                  onRowClick={(row) =>
                    setSelectedEntity({
                      kind: 'table',
                      id: row.table_full_name,
                      label: row.table_full_name,
                    })
                  }
                  pagination={paginationOf(tables.data?.total ?? 0, tablesPage, setTablesPage)}
                />
                <TableFootnote>
                  Observed usage within the applied scope and period. Missing measures remain
                  unknown.
                </TableFootnote>
              </div>
            ) : view === 'consumers' ? (
              <div className="space-y-4">
                <UcUsageConsumerChartsPanel {...consumerCharts} onRetry={consumerCharts.refetch} />
                <div className="flex flex-wrap items-center gap-2">
                  <label
                    className="text-xs font-semibold text-muted-foreground"
                    htmlFor="uc-usage-consumer-type"
                  >
                    Consumer type
                  </label>
                  <select
                    id="uc-usage-consumer-type"
                    className="h-8 rounded-md border border-border bg-card px-2 text-xs"
                    value={consumerType}
                    onChange={(event) => {
                      setConsumerType(event.target.value);
                      setConsumersPage(1);
                    }}
                  >
                    <option value="">All types</option>
                    {UC_USAGE_CONSUMER_TYPES.map((entry) => (
                      <option key={entry} value={entry}>
                        {entry}
                      </option>
                    ))}
                    {/* Vocabulaire ouvert : garder sélectionnable une valeur venue de l'URL ou d'un run futur. */}
                    {consumerType &&
                    !UC_USAGE_CONSUMER_TYPES.includes(
                      consumerType as (typeof UC_USAGE_CONSUMER_TYPES)[number]
                    ) ? (
                      <option value={consumerType}>{consumerType}</option>
                    ) : null}
                  </select>
                </div>

                <ComputeDataTable<UcUsageConsumerRow>
                  tableId="uc-usage-consumers"
                  toolbar={
                    <TableToolbar
                      title="Top consumers"
                      hint="Click a row for consumer trends · Filter columns across all results"
                    />
                  }
                  columns={consumerColumns.map((column) => ({
                    ...column,
                    sortable: Boolean(CONSUMER_SORT_BY_COLUMN[column.id]),
                  }))}
                  locale="en"
                  filters={consumerColumnFilters}
                  onFiltersChange={(next) => {
                    setConsumerColumnFilters(next);
                    setConsumersPage(1);
                  }}
                  renderColumnFilter={(column) =>
                    UC_CONSUMER_FILTERS[column.id] ? (
                      <UcUsageColumnFilter
                        label={column.headerLabel ?? String(column.header)}
                        definition={UC_CONSUMER_FILTERS[column.id]}
                        value={consumerColumnFilters[column.id]}
                        onChange={(value) => {
                          setConsumerColumnFilters((previous) =>
                            withColumnFilter(previous, column.id, value)
                          );
                          setConsumersPage(1);
                        }}
                      />
                    ) : null
                  }
                  rows={consumers.data?.items ?? []}
                  rowKey={(row) => row.consumer_id}
                  onRowClick={(row) =>
                    setSelectedEntity({
                      kind: 'consumer',
                      id: row.consumer_id,
                      label: row.consumer_name || row.consumer_id,
                    })
                  }
                  loading={consumers.loading}
                  emptyTitle={
                    consumers.error ? 'Unable to load consumers' : 'No consumers in this scope'
                  }
                  emptyDescription={
                    consumers.error
                      ? 'Loading failed. Reapply the period to try again.'
                      : 'Consumers must have an observed usage record for at least one selected table.'
                  }
                  sort={{
                    key: columnOfSort(CONSUMER_SORT_BY_COLUMN, consumersSort ?? 'cost') ?? '',
                    direction: consumerDirection,
                  }}
                  onSortChange={(key) => {
                    const next = CONSUMER_SORT_BY_COLUMN[key];
                    if (!next) return;
                    setConsumerDirection((current) =>
                      next === consumersSort && current === 'desc' ? 'asc' : 'desc'
                    );
                    setConsumersSort(next);
                    setConsumersPage(1);
                  }}
                  pagination={paginationOf(
                    consumers.data?.total ?? 0,
                    consumersPage,
                    setConsumersPage
                  )}
                />
                <TableFootnote>
                  Observed usage within the applied scope and period. Missing measures remain
                  unknown.
                </TableFootnote>
              </div>
            ) : (
              <div className="space-y-4">
                <SectionLabel>FinOps — overview</SectionLabel>
                {finopsKpis.loading ? (
                  <Skeleton className="h-[120px]" />
                ) : (
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    <ComputeKpiCard
                      title="Total cost"
                      description={COST_TOOLTIP}
                      value={formatUsd(finopsKpis.data?.total_cost_usd ?? null)}
                      tone="success"
                      icon={DollarSign}
                    />
                    <ComputeKpiCard
                      title="Average cost / access"
                      description="Potential lower bound: the denominator includes accesses without an attributed cost."
                      value={formatUsd(finopsKpis.data?.avg_cost_per_request_usd ?? null, 4)}
                      subtitle={
                        finopsKpis.data?.is_lower_bound ? 'Potential lower bound' : undefined
                      }
                      tone="info"
                      icon={DollarSign}
                    />
                    <ComputeKpiCard
                      title="Most costly table"
                      description="The table with the highest total attributed cost across the period."
                      value={finopsKpis.data?.top_costly_table?.table_full_name ?? '—'}
                      subtitle={formatUsd(
                        finopsKpis.data?.top_costly_table?.estimated_cost_usd ?? null
                      )}
                      tone="warning"
                      icon={Table2}
                    />
                  </div>
                )}

                {finopsTrends.loading ? (
                  <Skeleton className="h-[180px]" />
                ) : (
                  <UcUsageTrendCards series={finopsTrends.data?.series ?? []} />
                )}

                <UcUsageFinopsChartsPanel {...finopsCharts} onRetry={finopsCharts.refetch} />
                <UcUsageCostChangesPanel {...costChanges} onRetry={costChanges.refetch} />
                {finopsCharts.data && !finopsCharts.loading && !finopsCharts.error && (
                  <UcUsageCostCoverage data={finopsCharts.data} />
                )}
                <ComputeDataTable<UcUsageCostByTableRow>
                  tableId="uc-usage-cost-by-table"
                  // Six colonnes seulement (1130 px) : sans colonne élastique, ce
                  // tableau s'arrête bien avant le bord de sa carte là où « By table »
                  // (1855 px) la remplit. Le nom de table absorbe l'écart — c'est la
                  // seule colonne tronquée, et celle qu'on cherche à lire en entier.
                  stretchColumnId="table_full_name"
                  toolbar={
                    <TableToolbar
                      title="Cost by table"
                      hint="Click a row for details · Sort and filter columns across all results"
                    />
                  }
                  locale="en"
                  onRowClick={(row) =>
                    setSelectedEntity({
                      kind: 'table',
                      id: row.table_full_name,
                      label: row.table_full_name,
                    })
                  }
                  columns={costColumns.map((column) => ({
                    ...column,
                    sortable: Boolean(COST_SORT_BY_COLUMN[column.id]),
                  }))}
                  filters={costColumnFilters}
                  onFiltersChange={(next) => {
                    setCostColumnFilters(next);
                    setFinopsPage(1);
                  }}
                  renderColumnFilter={(column) =>
                    UC_COST_FILTERS[column.id] ? (
                      <UcUsageColumnFilter
                        label={column.headerLabel ?? String(column.header)}
                        definition={UC_COST_FILTERS[column.id]}
                        value={costColumnFilters[column.id]}
                        onChange={(value) => {
                          setCostColumnFilters((previous) =>
                            withColumnFilter(previous, column.id, value)
                          );
                          setFinopsPage(1);
                        }}
                      />
                    ) : null
                  }
                  rows={costByTable.data?.items ?? []}
                  rowKey={(row) => row.table_full_name}
                  loading={costByTable.loading}
                  emptyTitle={costByTable.error ? 'Unable to load costs' : 'No cost in this scope'}
                  emptyDescription={
                    costByTable.error
                      ? 'Loading failed. Reapply the period to try again.'
                      : 'Adjust the filters or period, then click Apply.'
                  }
                  sort={{
                    key: columnOfSort(COST_SORT_BY_COLUMN, costSort ?? 'cost') ?? '',
                    direction: costDirection,
                  }}
                  onSortChange={(key) => {
                    const next = COST_SORT_BY_COLUMN[key];
                    if (!next) return;
                    setCostDirection((current) =>
                      next === costSort && current === 'desc' ? 'asc' : 'desc'
                    );
                    setCostSort(next);
                    setFinopsPage(1);
                  }}
                  pagination={paginationOf(costByTable.data?.total ?? 0, finopsPage, setFinopsPage)}
                />
                <TableFootnote>
                  Observed usage within the applied scope and period. Missing measures remain
                  unknown.
                </TableFootnote>
              </div>
            )}
          </>
        )}
        {selectedEntity && (
          <UcUsageDetailDrawer
            key={`${selectedEntity.kind}:${selectedEntity.id}`}
            selection={selectedEntity}
            {...entityDetail}
            onRetry={entityDetail.refetch}
            onClose={() => setSelectedEntity(null)}
          />
        )}
      </ContentMain>
    </Content>
  );
}
