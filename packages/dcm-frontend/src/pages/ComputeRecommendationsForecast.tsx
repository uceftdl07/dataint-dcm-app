import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { CheckCircle2, DollarSign, Flag, RefreshCw, Search, Target, X } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { ForecastWidget } from '../components/domain/compute/forecast-widget';
import { RecommendationMiniDrawer } from '../components/domain/compute/recommendation-mini-drawer';
import {
  RecommendationsTable,
  type RecommendationSortKey,
} from '../components/domain/compute/recommendations-table';
import { ComputeKpiCard } from '../components/domain/compute/compute-kpi-card';
import type { SortDirection } from '../components/domain/compute/compute-data-table';
import { Content, ContentMain, ContentTitle } from '../components/layout/content';
import { Input } from '../components/ui/input';
import { Skeleton } from '../components/ui/skeleton';
import { useGlobalTimeRange } from '../contexts/time-range';
import { useComputeForecastData } from '../hooks/useComputeForecast';
import {
  useComputeRecommendationsData,
  useComputeRecommendationsSummaryData,
} from '../hooks/useComputeRecommendations';
import { computeRecommendationsKpiDescriptions } from '../lib/compute/field-descriptions';
import { RECOMMENDATION_CATEGORIES, categoryLabel } from '../lib/compute/recommendations';
import { countActiveColumnFilters } from '../lib/compute/column-filters';
import { formatNumber, formatUsd } from '../lib/compute/format';
import { cn } from '../lib/utils';
import type {
  ComputeColumnFilterValues,
  ComputeForecastMetricName,
  ComputeRecommendationItem,
} from '../types/api';

/** Une seule instance vide, pour ne pas relancer les mémos à chaque remise à zéro. */
const NO_FILTERS: ComputeColumnFilterValues = {};

const PAGE_SIZE = 25;

type ObjectTypeFilter = '' | 'CLUSTER' | 'WAREHOUSE' | 'JOB' | 'PIPELINE';

const STATUS_OPTIONS = [
  { value: 'OPEN', label: 'Open' },
  { value: 'RESOLVED', label: 'Resolved' },
  { value: 'DISMISSED', label: 'Dismissed' },
] as const;

const ASC_SORT_KEYS = new Set<RecommendationSortKey>(['object', 'category', 'status', 'since']);

function parseObjectType(value: string | null): ObjectTypeFilter {
  const normalized = (value || '').trim().toUpperCase();
  if (
    normalized === 'CLUSTER' ||
    normalized === 'WAREHOUSE' ||
    normalized === 'JOB' ||
    normalized === 'PIPELINE'
  ) {
    return normalized;
  }
  return '';
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

export default function ComputeRecommendationsForecast() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { getApiParams, getDisplayRange } = useGlobalTimeRange();
  const { end_date } = getApiParams();
  const display = getDisplayRange();
  const periodLabel = `${display.startDate} → ${display.endDate}`;

  const [objectType, setObjectType] = useState<ObjectTypeFilter>(() =>
    parseObjectType(searchParams.get('object_type'))
  );
  const [category, setCategory] = useState(() => searchParams.get('category')?.toUpperCase() ?? '');
  const [severity, setSeverity] = useState(() => searchParams.get('severity')?.toUpperCase() ?? '');
  const [statusFilter, setStatusFilter] = useState(
    () => searchParams.get('status')?.toUpperCase() ?? 'OPEN'
  );
  const [searchInput, setSearchInput] = useState(() => searchParams.get('search') ?? '');
  const [debouncedSearch, setDebouncedSearch] = useState(
    () => searchParams.get('search')?.trim() ?? ''
  );
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<RecommendationSortKey>('severity');
  const [order, setOrder] = useState<SortDirection>('desc');
  const [selected, setSelected] = useState<ComputeRecommendationItem | null>(null);
  // Les colonnes sans paramètre historique (`object`, `title`, `savings`) vivent ici ;
  // `category`, `severity` et `status` restent dans l'URL, qui doit rester partageable.
  const [columnFilters, setColumnFilters] = useState<ComputeColumnFilterValues>(NO_FILTERS);
  const [forecastMetric, setForecastMetric] = useState<ComputeForecastMetricName>('cost_usd');

  useEffect(() => {
    setObjectType(parseObjectType(searchParams.get('object_type')));
    setCategory(searchParams.get('category')?.toUpperCase() ?? '');
    setSeverity(searchParams.get('severity')?.toUpperCase() ?? '');
    setStatusFilter(searchParams.get('status')?.toUpperCase() ?? 'OPEN');
    const nextSearch = searchParams.get('search')?.trim() ?? '';
    setSearchInput(nextSearch);
    setDebouncedSearch(nextSearch);
    setPage(1);
  }, [searchParams]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const syncSearchParams = (patch: {
    object_type?: ObjectTypeFilter;
    category?: string;
    severity?: string;
    status?: string;
    search?: string;
  }) => {
    const next = new URLSearchParams(searchParams);
    const objectTypeValue = patch.object_type ?? objectType;
    const categoryValue = patch.category ?? category;
    const severityValue = patch.severity ?? severity;
    const statusValue = patch.status ?? statusFilter;
    const searchValue = patch.search ?? debouncedSearch;

    if (objectTypeValue) next.set('object_type', objectTypeValue);
    else next.delete('object_type');
    if (categoryValue) next.set('category', categoryValue);
    else next.delete('category');
    if (severityValue) next.set('severity', severityValue);
    else next.delete('severity');
    if (statusValue) next.set('status', statusValue);
    else next.delete('status');
    if (searchValue.trim()) next.set('search', searchValue.trim());
    else next.delete('search');
    setSearchParams(next, { replace: true });
  };

  // Le tableau ne voit qu'un objet de filtres, réassemblé depuis les deux sources.
  // Les paramètres historiques restent dérivés de la même valeur : un `severity=HIGH`
  // contredisant `column_filter=severity:LOW` est une 422, par construction.
  const filters = useMemo<ComputeColumnFilterValues>(
    () => ({
      ...columnFilters,
      ...(category ? { category } : {}),
      ...(severity ? { severity } : {}),
      ...(statusFilter ? { status: statusFilter } : {}),
    }),
    [columnFilters, category, severity, statusFilter]
  );

  const changeFilters = (next: ComputeColumnFilterValues) => {
    const {
      category: nextCategory = '',
      severity: nextSeverity = '',
      status: nextStatus = '',
      ...rest
    } = next;
    setColumnFilters(rest);
    setPage(1);
    if (nextCategory === category && nextSeverity === severity && nextStatus === statusFilter) {
      return;
    }
    setCategory(nextCategory);
    setSeverity(nextSeverity);
    setStatusFilter(nextStatus);
    syncSearchParams({ category: nextCategory, severity: nextSeverity, status: nextStatus });
  };

  const summary = useComputeRecommendationsSummaryData();
  const recommendations = useComputeRecommendationsData({
    object_type: objectType || undefined,
    category: category || undefined,
    severity: severity || undefined,
    status: statusFilter || undefined,
    search: debouncedSearch || undefined,
    filters,
    sort,
    order,
    page,
    pageSize: PAGE_SIZE,
  });
  const forecast = useComputeForecastData({ metric_name: forecastMetric });

  const rows = recommendations.data?.items ?? [];
  const total = recommendations.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const startIndex = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const endIndex = Math.min(page * PAGE_SIZE, total);

  const hasActiveFilters = Boolean(
    objectType ||
    category ||
    severity ||
    (statusFilter && statusFilter !== 'OPEN') ||
    debouncedSearch ||
    countActiveColumnFilters(columnFilters) > 0 ||
    sort !== 'severity' ||
    order !== 'desc'
  );

  const emptyTitle = hasActiveFilters
    ? 'No recommendations match this filter'
    : 'No recommendations in this scope';
  const emptyDescription = hasActiveFilters
    ? 'Try adjusting filters or reset to see all recommendations.'
    : 'Recommendations appear when gold rules detect FinOps, rightsizing, governance, or reliability issues.';

  const pagination = useMemo(
    () =>
      total > 0
        ? {
            currentPage: page,
            totalPages,
            totalItems: total,
            startIndex,
            endIndex,
            hasPreviousPage: page > 1,
            hasNextPage: page < totalPages,
            onPrevious: () => setPage((p) => Math.max(1, p - 1)),
            onNext: () => setPage((p) => Math.min(totalPages, p + 1)),
          }
        : undefined,
    [page, totalPages, total, startIndex, endIndex]
  );

  const handleSortChange = (columnId: RecommendationSortKey) => {
    if (sort === columnId) {
      setOrder((current) => (current === 'asc' ? 'desc' : 'asc'));
    } else {
      setSort(columnId);
      setOrder(ASC_SORT_KEYS.has(columnId) ? 'asc' : 'desc');
    }
    setPage(1);
  };

  const clearFilters = () => {
    setObjectType('');
    setCategory('');
    setSeverity('');
    setStatusFilter('OPEN');
    setColumnFilters(NO_FILTERS);
    setSearchInput('');
    setDebouncedSearch('');
    setSort('severity');
    setOrder('desc');
    setPage(1);
    setSearchParams({ status: 'OPEN' }, { replace: true });
  };

  const refetchAll = () => {
    void summary.refetch();
    void recommendations.refetch();
    void forecast.refetch();
  };

  const isFetching = summary.fetching || recommendations.fetching || forecast.fetching;

  const toolbar = (
    <div className="flex flex-wrap items-center gap-x-1.5 gap-y-2">
      <div className="relative w-full max-w-[240px] shrink-0 sm:w-[220px]">
        <Search
          size={14}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Search object or title…"
          className="h-8 rounded-full pl-9 text-xs"
          aria-label="Search recommendations"
        />
      </div>

      <ToggleChip
        active={objectType === ''}
        onClick={() => {
          setObjectType('');
          setPage(1);
          syncSearchParams({ object_type: '' });
        }}
      >
        All
      </ToggleChip>
      <ToggleChip
        active={objectType === 'CLUSTER'}
        onClick={() => {
          setObjectType('CLUSTER');
          setPage(1);
          syncSearchParams({ object_type: 'CLUSTER' });
        }}
      >
        Clusters
      </ToggleChip>
      <ToggleChip
        active={objectType === 'WAREHOUSE'}
        onClick={() => {
          setObjectType('WAREHOUSE');
          setPage(1);
          syncSearchParams({ object_type: 'WAREHOUSE' });
        }}
      >
        Warehouses
      </ToggleChip>
      <ToggleChip
        active={objectType === 'JOB'}
        onClick={() => {
          setObjectType('JOB');
          setPage(1);
          syncSearchParams({ object_type: 'JOB' });
        }}
      >
        Jobs
      </ToggleChip>
      <ToggleChip
        active={objectType === 'PIPELINE'}
        onClick={() => {
          setObjectType('PIPELINE');
          setPage(1);
          syncSearchParams({ object_type: 'PIPELINE' });
        }}
      >
        Pipelines
      </ToggleChip>

      <span className="mx-0.5 hidden h-4 w-px shrink-0 bg-border sm:block" aria-hidden />

      {STATUS_OPTIONS.map((opt) => (
        <ToggleChip
          key={opt.value}
          active={statusFilter === opt.value}
          onClick={() => {
            // Default is OPEN: toggling the active chip returns to OPEN (not "all").
            const next = statusFilter === opt.value ? 'OPEN' : opt.value;
            setStatusFilter(next);
            setPage(1);
            syncSearchParams({ status: next });
          }}
        >
          {opt.label}
        </ToggleChip>
      ))}

      <select
        className="h-8 rounded-full border border-border bg-background px-3 text-xs font-semibold text-foreground"
        value={category}
        onChange={(e) => {
          const value = e.target.value.toUpperCase();
          setCategory(value);
          setPage(1);
          syncSearchParams({ category: value });
        }}
        aria-label="Filter by category"
      >
        <option value="">All categories</option>
        {RECOMMENDATION_CATEGORIES.map((value) => (
          <option key={value} value={value}>
            {categoryLabel(value)}
          </option>
        ))}
        {/* La combo de colonne propose toutes les catégories présentes en gold.
            Sans cette option, le sélecteur afficherait « All categories » alors
            qu'un filtre de catégorie est bel et bien actif. */}
        {category && !RECOMMENDATION_CATEGORIES.some((value) => value === category) ? (
          <option value={category}>{category}</option>
        ) : null}
      </select>

      <select
        className="h-8 rounded-full border border-border bg-background px-3 text-xs font-semibold text-foreground"
        value={severity}
        onChange={(e) => {
          const value = e.target.value.toUpperCase();
          setSeverity(value);
          setPage(1);
          syncSearchParams({ severity: value });
        }}
        aria-label="Filter by severity"
      >
        <option value="">All severities</option>
        <option value="LOW">Low</option>
        <option value="MEDIUM">Medium</option>
        <option value="HIGH">High</option>
        {severity && !['LOW', 'MEDIUM', 'HIGH'].includes(severity) ? (
          <option value={severity}>{severity}</option>
        ) : null}
      </select>

      <ToggleChip
        active={sort === 'severity' && order === 'desc'}
        onClick={() => {
          setSort('severity');
          setOrder('desc');
          setPage(1);
        }}
      >
        High severity first
      </ToggleChip>

      {hasActiveFilters ? (
        <button
          type="button"
          onClick={clearFilters}
          className="inline-flex h-8 items-center gap-1 rounded-full border border-border px-2.5 text-[10.5px] font-bold text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground"
        >
          <X size={11} aria-hidden />
          Reset
        </button>
      ) : null}

      <button
        type="button"
        onClick={refetchAll}
        className="ml-auto rounded p-1.5 text-muted-foreground hover:text-foreground"
        aria-label="Refresh recommendations and forecast"
        disabled={isFetching}
      >
        <RefreshCw size={14} />
      </button>
    </div>
  );

  return (
    <Content className="mx-auto max-w-[1600px] gap-0 p-4 pb-24 lg:px-6 lg:pb-28">
      <ContentTitle>Recommendations &amp; Forecast</ContentTitle>
      <p className="mb-4 text-sm text-muted-foreground">
        Cross-cutting compute recommendations and AI forecast · {display.description}
      </p>

      {(summary.error || recommendations.error) && (
        <div className="mb-4 rounded-[var(--card-radius)] border border-danger-border bg-danger-subtle px-4 py-3 text-sm text-danger">
          Unable to load recommendations.{' '}
          <button type="button" onClick={refetchAll} className="underline">
            Retry
          </button>
        </div>
      )}

      <ContentMain className="gap-4">
        {summary.loading && !summary.data ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-[120px]" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <ComputeKpiCard
              title="Open recommendations"
              description={computeRecommendationsKpiDescriptions.openCount}
              value={formatNumber(summary.data?.open_count ?? null)}
              subtitle={`Clusters + warehouses · ${periodLabel}`}
              tone="warning"
              icon={Target}
            />
            <ComputeKpiCard
              title="Potential savings"
              description={computeRecommendationsKpiDescriptions.openSavings}
              value={formatUsd(summary.data?.open_savings_usd ?? null)}
              subtitle="Quantifiable open recommendations"
              tone="success"
              icon={DollarSign}
            />
            <ComputeKpiCard
              title="Actual cost (period)"
              description={computeRecommendationsKpiDescriptions.periodActualCost}
              value={formatUsd(summary.data?.period_actual_cost_usd ?? null)}
              subtitle="Clusters + warehouses spend"
              tone="purple"
              icon={DollarSign}
            />
            <ComputeKpiCard
              title="Resolved (30d)"
              description={computeRecommendationsKpiDescriptions.resolved30d}
              value={formatNumber(summary.data?.resolved_30d_count ?? null)}
              subtitle="Status resolved"
              tone="info"
              icon={CheckCircle2}
            />
            <ComputeKpiCard
              title="High severity"
              description={computeRecommendationsKpiDescriptions.highSeverityOpen}
              value={formatNumber(summary.data?.high_severity_open_count ?? null)}
              subtitle="Priority open items"
              tone="danger"
              icon={Flag}
            />
          </div>
        )}

        <RecommendationsTable
          rows={rows}
          loading={recommendations.loading && !recommendations.data}
          periodEnd={end_date}
          onRowClick={setSelected}
          emptyTitle={emptyTitle}
          emptyDescription={emptyDescription}
          pagination={pagination}
          sort={{ key: sort, direction: order }}
          onSortChange={handleSortChange}
          filters={filters}
          onFiltersChange={changeFilters}
          toolbar={toolbar}
        />

        <ForecastWidget
          items={forecast.data?.items ?? []}
          actuals={forecast.data?.actuals ?? []}
          loading={forecast.loading}
          metric={forecastMetric}
          onMetricChange={setForecastMetric}
          periodEnd={end_date}
        />
      </ContentMain>

      <RecommendationMiniDrawer
        open={selected != null}
        onClose={() => setSelected(null)}
        item={selected}
        periodEnd={end_date}
      />
    </Content>
  );
}
