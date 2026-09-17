import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react';
import { AlertTriangle, Archive, Flag, ShieldAlert } from 'lucide-react';
import { ComputeDataTable } from '../components/domain/compute/compute-data-table';
import { ComputeKpiCard } from '../components/domain/compute/compute-kpi-card';
import { UcUsageDeletedBadge } from '../components/domain/uc-usage/uc-usage-deleted-badge';
import { UcUsageFilters } from '../components/domain/uc-usage/uc-usage-filters';
import { UcUsageWelcome } from '../components/domain/uc-usage/uc-usage-welcome';
import { UcUsageRecommendationCard } from '../components/domain/uc-usage/uc-usage-recommendation-card';
import { UcGovernanceChartsPanel } from '../components/domain/uc-usage/uc-governance-charts';
import { UcRecommendationChartsPanel } from '../components/domain/uc-usage/uc-recommendation-charts';
import {
  governanceIdentity,
  governanceSnapshotLabel,
  type UcGovernanceFocus,
  type UcRecommendationFocus,
} from '../components/domain/uc-usage/uc-governance-chart-utils';
import { Content, ContentHeader, ContentMain, ContentTitle } from '../components/layout/content';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Skeleton } from '../components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '../components/ui/tabs';
import {
  UC_USAGE_PAGE_SIZE,
  useUcUsageGovernanceKpis,
  useUcUsageGovernanceCharts,
  useUcUsageRecommendationCharts,
  useUcUsageRecommendations,
  useUcUsageRegistry,
  type UcUsageFilters as UcUsageFilterValues,
} from '../hooks/useUcUsageQueries';
import { formatNumber, formatUsd } from '../lib/compute/format';
import {
  UC_USAGE_EMPTY_DRAFT,
  hasUcUsageScope,
  type UcUsageFilterDraft,
} from '../lib/uc-usage/filters';
import {
  UC_USAGE_RECOMMENDATION_CATEGORIES,
  formatIsoDate,
  ucUsageCategoryLabel,
  ucUsageOperationLabel,
  ucUsageOwnerLabel,
  ucUsageRegistryStatus,
} from '../lib/uc-usage/labels';
import { ucUsageSeverityBadgeVariant, ucUsageSeverityLabel } from '../lib/uc-usage/severity';
import type { UcUsageRegistryRow } from '../types/api';

type TabKey = 'governance' | 'recommendations';
const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'governance', label: 'Governance' },
  { key: 'recommendations', label: 'Recommendations' },
];

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <h2 className="text-[11px] font-semibold uppercase tracking-[1.2px] text-muted-foreground">
      {children}
    </h2>
  );
}

function QueryError({ message, retry }: { message: string; retry: () => unknown }) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-3"
    >
      <p className="text-sm">{message}</p>
      <Button
        variant="outline"
        size="sm"
        onClick={() => {
          retry();
        }}
      >
        Retry
      </Button>
    </div>
  );
}

function PageControls({
  page,
  total,
  onPage,
}: {
  page: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / UC_USAGE_PAGE_SIZE));
  if (pages <= 1) return null;
  return (
    <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
      <Button
        variant="outline"
        size="sm"
        disabled={page <= 1}
        onClick={() => onPage(Math.max(1, page - 1))}
      >
        Previous
      </Button>
      <span>
        Page {page} / {pages}
      </span>
      <Button
        variant="outline"
        size="sm"
        disabled={page >= pages}
        onClick={() => onPage(Math.min(pages, page + 1))}
      >
        Next
      </Button>
    </div>
  );
}

/** Consumer alerts carry no table attribution. Keep them available in their own
 * explicitly global section, outside table counters, charts and list filters. */
function ConsumerRecommendations() {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(1);
  const query = useUcUsageRecommendations(
    {},
    {
      object_type: 'CONSUMER',
      category: 'FINOPS',
      sort: 'age',
      page,
      enabled: open,
    }
  );
  return (
    <details
      className="border-t border-border pt-4"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="cursor-pointer text-sm font-semibold">
        Consumer FinOps · outside the selected table scope
      </summary>
      {open ? (
        <div className="mt-4 space-y-4">
          <p className="text-xs text-muted-foreground">
            Recommendations across all consumers. They are excluded from table counts and charts
            because their connection to the selected tables is unknown.
          </p>
          {query.error ? (
            <QueryError message="Unable to load consumer recommendations." retry={query.refetch} />
          ) : query.loading ? (
            <Skeleton className="h-40" />
          ) : !query.data?.items.length ? (
            <p className="text-sm text-muted-foreground">
              No open FinOps recommendations for consumers.
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {query.data.items.map((item) => (
                <UcUsageRecommendationCard key={item.recommendation_id} item={item} />
              ))}
            </div>
          )}
          <PageControls page={page} total={query.data?.total ?? 0} onPage={setPage} />
        </div>
      ) : null}
    </details>
  );
}

export default function UsageGovernance() {
  const [draft, setDraft] = useState<UcUsageFilterDraft>(UC_USAGE_EMPTY_DRAFT);
  const [filters, setFilters] = useState<UcUsageFilterValues>({});
  // Aucun appel avant un clic sur Appliquer : à l'arrivée la page ne montre pas
  // l'état de tous les catalogues, elle demande d'abord un périmètre. Écart assumé
  // avec la dernière phrase de FR-017 (« les endpoints snapshot chargent
  // immédiatement ») : demande utilisateur d'aligner l'entrée sur UC table usage.
  const [applied, setApplied] = useState(false);
  const [tab, setTab] = useState<TabKey>('governance');
  const [category, setCategory] = useState('');
  const [severity, setSeverity] = useState('');
  const [registryPage, setRegistryPage] = useState(1);
  const [recommendationsPage, setRecommendationsPage] = useState(1);
  const [registryFocus, setRegistryFocus] = useState<UcGovernanceFocus | null>(null);
  const [recommendationFocus, setRecommendationFocus] = useState<UcRecommendationFocus | null>(
    null
  );
  const registryRef = useRef<HTMLDivElement>(null);
  const recommendationsRef = useRef<HTMLDivElement>(null);
  const catalogTriggerRef = useRef<HTMLButtonElement>(null);
  const hasScope = hasUcUsageScope(draft);
  const scopeChanged =
    applied &&
    (draft.catalog.trim() !== (filters.catalog ?? '') ||
      draft.schema.trim() !== (filters.schema ?? '') ||
      draft.includeDeleted !== Boolean(filters.includeDeleted) ||
      [...draft.tables].sort().join('\n') !== [...(filters.tables ?? [])].sort().join('\n'));

  const applyFilters = () => {
    if (!hasScope) return;
    setApplied(true);
    setFilters({
      catalog: draft.catalog.trim() || undefined,
      schema: draft.schema.trim() || undefined,
      tables: draft.tables,
      includeDeleted: draft.includeDeleted,
    });
    setRegistryPage(1);
    setRecommendationsPage(1);
    setRegistryFocus(null);
    setRecommendationFocus(null);
    setCategory('');
    setSeverity('');
  };
  const selectGovernanceFocus = useCallback((focus: UcGovernanceFocus) => {
    setRegistryFocus(focus);
    setRegistryPage(1);
    setTab('governance');
    requestAnimationFrame(() => registryRef.current?.scrollIntoView?.({ block: 'start' }));
  }, []);
  const selectRecommendationFocus = useCallback((focus: UcRecommendationFocus) => {
    setRecommendationFocus(focus);
    setCategory(focus.category ?? '');
    setSeverity('');
    setRecommendationsPage(1);
    setTab('recommendations');
    requestAnimationFrame(() => recommendationsRef.current?.scrollIntoView?.({ block: 'start' }));
  }, []);
  const openTableRecommendations = useCallback(
    (name: string) => {
      selectRecommendationFocus({ table: name, label: `${name} · all clouds` });
    },
    [selectRecommendationFocus]
  );

  // Applied scope drives charts/KPIs. A chart focus narrows only its paginated
  // detail, and applying another scope clears all focus and pagination state.
  const registryFilters = useMemo(
    () => ({ ...filters, ...registryFocus?.scope }),
    [filters, registryFocus]
  );
  const recommendationFilters = useMemo(
    () => ({
      ...filters,
      ...(recommendationFocus?.table ? { tables: [recommendationFocus.table] } : {}),
    }),
    [filters, recommendationFocus]
  );
  const kpis = useUcUsageGovernanceKpis(filters, applied);
  const governanceCharts = useUcUsageGovernanceCharts(filters, applied && tab === 'governance');
  const recommendationCharts = useUcUsageRecommendationCharts(
    filters,
    applied && tab === 'recommendations'
  );
  const registry = useUcUsageRegistry(registryFilters, {
    page: registryPage,
    enabled: applied && tab === 'governance',
    signal: registryFocus?.signal,
    inactivity: registryFocus?.inactivity,
    missingTag: registryFocus?.missingTag,
  });
  const recommendations = useUcUsageRecommendations(recommendationFilters, {
    object_type: 'DATA_PRODUCT',
    category: category || undefined,
    severity: severity || undefined,
    age_bucket: recommendationFocus?.ageBucket,
    sort: 'age',
    page: recommendationsPage,
    enabled: applied && tab === 'recommendations',
  });
  const appliedKey = JSON.stringify(filters);
  const counts = recommendationCharts.data?.summary;
  const snapshot =
    tab === 'governance' ? governanceCharts.data?.as_of : recommendationCharts.data?.as_of;

  const registryColumns = useMemo(
    () => [
      {
        id: 'table_full_name',
        header: 'Table',
        width: 360,
        cell: (row: UcUsageRegistryRow) => (
          <div className="min-w-0">
            <span className="flex min-w-0 items-center gap-1">
              <span className="truncate font-medium" title={row.table_full_name}>
                {row.table_full_name}
              </span>
              <UcUsageDeletedBadge row={row} />
            </span>
            {row.cloud_provider ? (
              <span className="text-[11px] text-muted-foreground">{row.cloud_provider}</span>
            ) : null}
          </div>
        ),
      },
      {
        id: 'owner',
        header: 'Owner (UC tag)',
        width: 190,
        cell: (row: UcUsageRegistryRow) => ucUsageOwnerLabel(row.owner),
      },
      {
        id: 'status',
        header: 'Points to review',
        width: 250,
        cell: (row: UcUsageRegistryRow) => {
          const status = ucUsageRegistryStatus(row);
          return (
            <div className="flex flex-wrap gap-1">
              <Badge variant={status.variant}>{status.label}</Badge>
              {row.is_critical ? <Badge variant="info">Critical</Badge> : null}
              {row.is_orphan && status.label !== 'Orphaned' ? (
                <Badge variant="warning">Missing tags</Badge>
              ) : null}
              {row.is_stale_but_consumed && status.label !== 'Stale but consumed' ? (
                <Badge variant="info">Stale but read</Badge>
              ) : null}
            </div>
          );
        },
      },
      {
        id: 'severity',
        header: 'Severity',
        width: 110,
        cell: (row: UcUsageRegistryRow) => (
          <Badge variant={ucUsageSeverityBadgeVariant(row.severity)}>
            {ucUsageSeverityLabel(row.severity)}
          </Badge>
        ),
      },
      {
        id: 'last_operation',
        header: 'Last operation',
        width: 170,
        cell: (row: UcUsageRegistryRow) => (
          <span title={row.last_operation_by ?? ''}>
            {ucUsageOperationLabel(row.last_operation)}
          </span>
        ),
      },
      {
        id: 'last_operation_at',
        header: 'On',
        width: 130,
        cell: (row: UcUsageRegistryRow) => formatIsoDate(row.last_operation_at),
      },
      {
        id: 'downstream_fanout',
        header: 'Observed downstream objects',
        align: 'right' as const,
        width: 155,
        cell: (row: UcUsageRegistryRow) => formatNumber(row.downstream_fanout),
      },
      {
        id: 'days_since_last_read',
        header: 'Days since last read',
        align: 'right' as const,
        width: 160,
        cell: (row: UcUsageRegistryRow) =>
          row.days_since_last_read == null
            ? 'No read observed'
            : formatNumber(row.days_since_last_read),
      },
      {
        id: 'recommendations',
        header: 'Recommendations',
        width: 170,
        cell: (row: UcUsageRegistryRow) => (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => openTableRecommendations(row.table_full_name)}
          >
            View recommendations
          </Button>
        ),
      },
    ],
    [openTableRecommendations]
  );

  const registryPagination = useMemo(() => {
    const total = registry.data?.total ?? 0;
    if (!total) return undefined;
    const totalPages = Math.max(1, Math.ceil(total / UC_USAGE_PAGE_SIZE));
    return {
      currentPage: registryPage,
      totalPages,
      totalItems: total,
      startIndex: (registryPage - 1) * UC_USAGE_PAGE_SIZE,
      endIndex: Math.min(registryPage * UC_USAGE_PAGE_SIZE, total),
      hasPreviousPage: registryPage > 1,
      hasNextPage: registryPage < totalPages,
      onPrevious: () => setRegistryPage((page) => Math.max(1, page - 1)),
      onNext: () => setRegistryPage((page) => Math.min(totalPages, page + 1)),
    };
  }, [registry.data?.total, registryPage]);
  // Le périmètre est obligatoire pour appliquer : pas de repli « tous les catalogues ».
  const scopeLabel = [
    filters.catalog,
    filters.schema,
    filters.tables?.length ? `${filters.tables.length} selected table(s)` : null,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <Content className="mx-auto max-w-[1600px] gap-0 p-4 pb-24 lg:px-6 lg:pb-28">
      <ContentHeader>
        <div>
          <ContentTitle>Governance &amp; Recommendations</ContentTitle>
          <p className="mt-2 text-sm text-muted-foreground">
            Unity Catalog table registry and open recommendations · latest known state
          </p>
        </div>
      </ContentHeader>
      <ContentMain className="gap-5">
        <UcUsageFilters
          draft={draft}
          onDraftChange={setDraft}
          onApply={applyFilters}
          periodPrefix="State"
          periodLabel="current snapshot · independent of the usage period"
          requireScope
          catalogTriggerRef={catalogTriggerRef}
        />
        {!applied ? (
          <UcUsageWelcome
            variant="governance"
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
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
              <p aria-live="polite">Applied scope: {scopeLabel}</p>
              <p>{governanceSnapshotLabel(snapshot)}</p>
            </div>
            <Tabs>
              <TabsList aria-label="Governance views">
                {TABS.map((entry) => (
                  <TabsTrigger
                    key={entry.key}
                    active={tab === entry.key}
                    onClick={() => setTab(entry.key)}
                  >
                    {entry.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            {tab === 'governance' ? (
              <>
                <SectionLabel>Lifecycle — overview</SectionLabel>
                {kpis.error ? (
                  <QueryError
                    message="Unable to load governance indicators."
                    retry={kpis.refetch}
                  />
                ) : kpis.loading ? (
                  <Skeleton className="h-[120px]" />
                ) : (
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                    <ComputeKpiCard
                      title="Unused tables"
                      description="More than 90 days since the last read, or no read observed."
                      value={formatNumber(kpis.data?.unused_tables ?? null)}
                      tone="warning"
                      icon={Archive}
                    />
                    <ComputeKpiCard
                      title="Stale but consumed"
                      description="Last write more than 24 hours ago and last read within 7 days, using existing rules."
                      value={formatNumber(kpis.data?.stale_but_consumed_tables ?? null)}
                      tone="danger"
                      icon={AlertTriangle}
                    />
                    <ComputeKpiCard
                      title="Critical tables"
                      description="At least 5 downstream objects observed on the latest known day."
                      value={formatNumber(kpis.data?.critical_tables ?? null)}
                      tone="info"
                      icon={ShieldAlert}
                    />
                  </div>
                )}
                <SectionLabel>Which tables need review?</SectionLabel>
                <UcGovernanceChartsPanel
                  key={appliedKey}
                  data={governanceCharts.data}
                  loading={governanceCharts.loading}
                  error={governanceCharts.error}
                  onRetry={governanceCharts.refetch}
                  onFocus={selectGovernanceFocus}
                />
                <div ref={registryRef} className="scroll-mt-6 space-y-3">
                  {registryFocus ? (
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                      <p aria-live="polite">
                        Registry focus: <strong>{registryFocus.label}</strong>
                      </p>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setRegistryFocus(null);
                          setRegistryPage(1);
                        }}
                      >
                        Clear registry focus
                      </Button>
                    </div>
                  ) : null}
                  {registry.error ? (
                    <QueryError
                      message="Unable to load the table registry."
                      retry={registry.refetch}
                    />
                  ) : (
                    <ComputeDataTable<UcUsageRegistryRow>
                      locale="en"
                      tableId="uc-usage-registry"
                      toolbar={
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <h3 className="text-sm font-semibold text-foreground">
                            Table registry — current state
                          </h3>
                          <p className="text-xs text-muted-foreground">
                            {formatNumber(registry.data?.total ?? null)} tables
                          </p>
                        </div>
                      }
                      columns={registryColumns}
                      rows={registry.data?.items ?? []}
                      rowKey={(row) => governanceIdentity(row.cloud_provider, row.table_full_name)}
                      loading={registry.loading}
                      emptyTitle="No tables in this scope"
                      emptyDescription={
                        registryFocus
                          ? 'No tables match this chart focus. Clear the focus to return to the applied scope.'
                          : 'Adjust the catalog, schema or table filters, then click Apply.'
                      }
                      pagination={registryPagination}
                    />
                  )}
                  <p className="px-1 text-[11px] text-muted-foreground">
                    Signals can overlap. Orphaned means the owner, domain and cost center tags are
                    missing. A table in two clouds counts once in each cloud. Last operation
                    describes a catalog change; write freshness is available in UC table usage.
                  </p>
                </div>
              </>
            ) : (
              <>
                <SectionLabel>Open table recommendations</SectionLabel>
                {recommendationCharts.loading ? (
                  <Skeleton className="h-[120px]" />
                ) : (
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                    <ComputeKpiCard
                      title="Open — High"
                      description="High recommendations across all tables in the applied scope."
                      value={formatNumber(counts?.open_high ?? null)}
                      tone="danger"
                      icon={Flag}
                    />
                    <ComputeKpiCard
                      title="Open — Medium"
                      description="Medium recommendations across all tables in the applied scope."
                      value={formatNumber(counts?.open_medium ?? null)}
                      tone="warning"
                      icon={Flag}
                    />
                    <ComputeKpiCard
                      title="Open — Total"
                      description="All table categories; consumer recommendations are shown separately."
                      value={formatNumber(counts?.open_total ?? null)}
                      subtitle={
                        counts
                          ? `${formatNumber(counts.affected_tables)} affected tables`
                          : undefined
                      }
                      tone="info"
                      icon={Flag}
                    />
                    <ComputeKpiCard
                      title="Daily reference cost"
                      description="Latest known daily cost for non-critical LIFECYCLE candidates. This amount is not a proven saving."
                      value={formatUsd(counts?.reference_cost_usd ?? null)}
                      subtitle={
                        counts
                          ? `${counts.cost_measured_tables} / ${counts.cost_candidates} costed LIFECYCLE candidates`
                          : 'Unused LIFECYCLE candidates only'
                      }
                      tone="success"
                      icon={Archive}
                    />
                  </div>
                )}
                <SectionLabel>Which recommendations should be addressed first?</SectionLabel>
                <UcRecommendationChartsPanel
                  data={recommendationCharts.data}
                  loading={recommendationCharts.loading}
                  error={recommendationCharts.error}
                  onRetry={recommendationCharts.refetch}
                  onFocus={selectRecommendationFocus}
                />
                <div ref={recommendationsRef} className="scroll-mt-6 space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold">Recommendation details</h3>
                    <span className="text-xs text-muted-foreground">
                      {formatNumber(recommendations.data?.total ?? null)} recommendations
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <label
                      className="text-xs font-semibold text-muted-foreground"
                      htmlFor="uc-usage-category"
                    >
                      Category
                    </label>
                    <select
                      id="uc-usage-category"
                      className="h-9 rounded-md border border-border bg-card px-2 text-xs"
                      value={category}
                      onChange={(event) => {
                        setCategory(event.target.value);
                        setRecommendationsPage(1);
                      }}
                    >
                      <option value="">All categories</option>
                      {UC_USAGE_RECOMMENDATION_CATEGORIES.map((entry) => (
                        <option key={entry} value={entry}>
                          {ucUsageCategoryLabel(entry)}
                        </option>
                      ))}
                    </select>
                    <label
                      className="text-xs font-semibold text-muted-foreground"
                      htmlFor="uc-usage-severity"
                    >
                      Severity
                    </label>
                    <select
                      id="uc-usage-severity"
                      className="h-9 rounded-md border border-border bg-card px-2 text-xs"
                      value={severity}
                      onChange={(event) => {
                        setSeverity(event.target.value);
                        setRecommendationsPage(1);
                      }}
                    >
                      <option value="">All severities</option>
                      <option value="HIGH">High</option>
                      <option value="MEDIUM">Medium</option>
                      <option value="LOW">Low</option>
                    </select>
                    {category || severity || recommendationFocus ? (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setCategory('');
                          setSeverity('');
                          setRecommendationFocus(null);
                          setRecommendationsPage(1);
                        }}
                      >
                        Clear card filters
                      </Button>
                    ) : null}
                  </div>
                  <p className="text-xs text-muted-foreground" aria-live="polite">
                    {recommendationFocus?.table || recommendationFocus?.ageBucket
                      ? `Card focus: ${recommendationFocus.label}. `
                      : ''}
                    Charts and counts retain the whole applied scope. Cards are sorted by severity,
                    then age.
                  </p>
                  {recommendations.error ? (
                    <QueryError
                      message="Unable to load recommendations."
                      retry={recommendations.refetch}
                    />
                  ) : recommendations.loading ? (
                    <Skeleton className="h-[200px]" />
                  ) : !recommendations.data?.items.length ? (
                    <p className="text-sm text-muted-foreground">
                      No open recommendations in this scope.
                    </p>
                  ) : (
                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                      {recommendations.data.items.map((item) => (
                        <UcUsageRecommendationCard
                          key={item.recommendation_id}
                          item={item}
                          onViewTable={() =>
                            selectGovernanceFocus({
                              label: `${item.object_id} · all clouds`,
                              scope: { tables: [item.object_id] },
                            })
                          }
                        />
                      ))}
                    </div>
                  )}
                  <PageControls
                    page={recommendationsPage}
                    total={recommendations.data?.total ?? 0}
                    onPage={setRecommendationsPage}
                  />
                </div>
                <ConsumerRecommendations />
              </>
            )}
          </>
        )}
      </ContentMain>
    </Content>
  );
}
