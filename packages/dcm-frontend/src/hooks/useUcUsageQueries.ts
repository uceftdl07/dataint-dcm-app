import { toColumnFilterParam } from '../lib/compute/column-filters';
import type { UcUsageEntitySelection } from '../types/api';
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getUcUsageAttention,
  getUcUsageFilterOptions,
  getUcUsageFinopsKpis,
  getUcUsageFinopsTrends,
  getUcUsageGovernanceKpis,
  getUcUsageGovernanceCharts,
  getUcUsageRecommendationCharts,
  getUcUsageOverview,
  getUcUsageWriteCharts,
  getUcUsageCostChanges,
  getUcUsageEntityDetail,
  getUcUsageTableCharts,
  getUcUsageConsumerCharts,
  getUcUsageFinopsCharts,
  getUcUsageTableTopConsumers,
  listUcUsageConsumers,
  listUcUsageCostByTable,
  listUcUsageGovernanceRegistry,
  listUcUsageRecommendations,
  listUcUsageTables,
  type UcUsageConsumersParams,
  type UcUsageCostByTableParams,
  type UcUsageRegistryParams,
  type UcUsageRecommendationsParams,
  type UcUsageTablesParams,
} from '../api/dcmApiClient';
import type { UcUsageForecastMetric } from '../types/api';
import { ucUsageQueryKeys } from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';

/**
 * Période **appliquée**, distincte de celle affichée dans le bandeau : tant
 * qu'elle vaut `null`, aucun appel daté ne part (FR-017). C'est le seul état
 * qui pilote `enabled` sur les endpoints datés.
 */
export interface UcUsageAppliedPeriod {
  start: string;
  end: string;
}

export interface UcUsageFilters {
  catalog?: string;
  schema?: string;
  tables?: string[];
  /**
   * Case « Include deleted tables » appliquée avec le reste du périmètre
   * (spec 027). Décochée, l'analyse ignore les tables supprimées de UC.
   */
  includeDeleted?: boolean;
}

const PAGE_SIZE = 25;

/** Un tableau vide part en `tables=` côté client : c'est « aucune table », pas « aucun filtre ». */
function tablesParam(tables: string[] | undefined): string[] | undefined {
  return tables && tables.length > 0 ? tables : undefined;
}

function useScopeParams(filters: UcUsageFilters) {
  return useMemo(
    () => ({
      catalog: filters.catalog?.trim() || undefined,
      schema: filters.schema?.trim() || undefined,
      tables: tablesParam(filters.tables),
      // Omis quand la case est décochée : c'est déjà le défaut du serveur, et la
      // clé TanStack de l'exclusion reste celle des vues d'avant la spec 027.
      // Présent, il entre dans la clé : basculer la case relance les requêtes au
      // lieu de resservir un cache filtré autrement.
      include_deleted: filters.includeDeleted || undefined,
    }),
    [filters.catalog, filters.schema, filters.tables, filters.includeDeleted]
  );
}

/**
 * Périmètre des deux vues de grain consommateur, qui n'ont aucune clé table à
 * filtrer : le contrat les déclare exemptes, donc le drapeau ne part pas et
 * n'entre pas dans leur clé — la case ne doit pas les recharger pour rien.
 */
function useConsumerScopeParams(filters: UcUsageFilters) {
  const scope = useScopeParams(filters);
  return useMemo(
    () => ({ catalog: scope.catalog, schema: scope.schema, tables: scope.tables }),
    [scope]
  );
}

function usePeriodParams(filters: UcUsageFilters, period: UcUsageAppliedPeriod | null) {
  const scope = useScopeParams(filters);
  return useMemo(
    () => ({
      ...scope,
      period_start: period?.start ?? '',
      period_end: period?.end ?? '',
    }),
    [scope, period?.start, period?.end]
  );
}

function useConsumerPeriodParams(filters: UcUsageFilters, period: UcUsageAppliedPeriod | null) {
  const scope = useConsumerScopeParams(filters);
  return useMemo(
    () => ({
      ...scope,
      period_start: period?.start ?? '',
      period_end: period?.end ?? '',
    }),
    [scope, period?.start, period?.end]
  );
}

function datedQueryOptions(period: UcUsageAppliedPeriod | null, enabled = true) {
  return {
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled: enabled && Boolean(period?.start && period?.end),
  };
}

function snapshotQueryOptions(enabled = true) {
  return { staleTime: QUERY_STALE_DEFAULT_MS, gcTime: QUERY_GC_DEFAULT_MS, enabled };
}

function toResult<T>(query: {
  data: T | undefined;
  isLoading: boolean;
  isFetching: boolean;
  error: unknown;
  refetch: () => unknown;
}) {
  return {
    data: query.data ?? null,
    loading: query.isLoading,
    fetching: query.isFetching,
    error: query.error,
    refetch: query.refetch,
  };
}

// ─── Page « Usage des tables UC » ───────────────────────────────────────────

export function useUcUsageOverview(filters: UcUsageFilters, period: UcUsageAppliedPeriod | null) {
  const params = usePeriodParams(filters, period);
  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.overview(params),
      queryFn: () => getUcUsageOverview(params),
      ...datedQueryOptions(period),
    })
  );
}

// A chart query never receives a table page, search or sort, and never retains
// data from a previous scope while the newly applied selection is loading.
export function useUcUsageTableCharts(
  filters: UcUsageFilters,
  period: UcUsageAppliedPeriod | null,
  enabled = true
) {
  const params = usePeriodParams(filters, period);
  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.charts('tables', params),
      queryFn: () => getUcUsageTableCharts(params),
      ...datedQueryOptions(period, enabled),
    })
  );
}

export function useUcUsageConsumerCharts(
  filters: UcUsageFilters,
  period: UcUsageAppliedPeriod | null,
  enabled = true
) {
  const params = useConsumerPeriodParams(filters, period);
  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.charts('consumers', params),
      queryFn: () => getUcUsageConsumerCharts(params),
      ...datedQueryOptions(period, enabled),
    })
  );
}

export function useUcUsageFinopsCharts(
  filters: UcUsageFilters,
  period: UcUsageAppliedPeriod | null,
  enabled = true
) {
  const params = usePeriodParams(filters, period);
  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.charts('finops', params),
      queryFn: () => getUcUsageFinopsCharts(params),
      ...datedQueryOptions(period, enabled),
    })
  );
}

export function useUcUsageTables(
  filters: UcUsageFilters,
  period: UcUsageAppliedPeriod | null,
  options: {
    search?: string;
    direction?: 'asc' | 'desc';
    columnFilters?: Record<string, string>;
    sort?: UcUsageTablesParams['sort'];
    page?: number;
    enabled?: boolean;
  } = {}
) {
  const scoped = usePeriodParams(filters, period);
  const params = useMemo(
    () =>
      ({
        ...scoped,
        search: options.search?.trim() || undefined,
        sort: options.sort ?? 'popularity',
        direction: options.direction ?? 'desc',
        column_filter: toColumnFilterParam(options.columnFilters ?? {}),
        page: options.page ?? 1,
        page_size: PAGE_SIZE,
      }) satisfies UcUsageTablesParams,
    [scoped, options.search, options.sort, options.page, options.direction, options.columnFilters]
  );

  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.tables(params),
      queryFn: () => listUcUsageTables(params),
      ...datedQueryOptions(period, options.enabled ?? true),
    })
  );
}

/** Drill-down top 5 : `LIMIT 5` serveur, donc ni page ni tri côté client (FR-004). */
export function useUcUsageTopConsumers(
  tableFullName: string | null,
  period: UcUsageAppliedPeriod | null,
  includeDeleted = false
) {
  const params = useMemo(
    () => ({
      period_start: period?.start ?? '',
      period_end: period?.end ?? '',
      // Sans le drapeau, le drill-down d'une table supprimée — visible seulement
      // quand la case est cochée — reviendrait vide.
      include_deleted: includeDeleted || undefined,
    }),
    [period?.start, period?.end, includeDeleted]
  );

  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.topConsumers(tableFullName ?? 'none', params),
      queryFn: () => getUcUsageTableTopConsumers(tableFullName as string, params),
      ...datedQueryOptions(period, Boolean(tableFullName)),
    })
  );
}

export function useUcUsageConsumers(
  filters: UcUsageFilters,
  period: UcUsageAppliedPeriod | null,
  options: {
    search?: string;
    direction?: 'asc' | 'desc';
    columnFilters?: Record<string, string>;
    consumerType?: string;
    sort?: UcUsageConsumersParams['sort'];
    page?: number;
    enabled?: boolean;
  } = {}
) {
  const scoped = useConsumerPeriodParams(filters, period);
  const params = useMemo(
    () =>
      ({
        ...scoped,
        search: options.search?.trim() || undefined,
        consumer_type: options.consumerType?.trim() || undefined,
        sort: options.sort ?? 'cost',
        direction: options.direction ?? 'desc',
        column_filter: toColumnFilterParam(options.columnFilters ?? {}),
        page: options.page ?? 1,
        page_size: PAGE_SIZE,
      }) satisfies UcUsageConsumersParams,
    [
      scoped,
      options.search,
      options.consumerType,
      options.sort,
      options.page,
      options.direction,
      options.columnFilters,
    ]
  );

  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.consumers(params),
      queryFn: () => listUcUsageConsumers(params),
      ...datedQueryOptions(period, options.enabled ?? true),
    })
  );
}

export function useUcUsageFinopsKpis(
  filters: UcUsageFilters,
  period: UcUsageAppliedPeriod | null,
  options: { enabled?: boolean } = {}
) {
  const params = usePeriodParams(filters, period);
  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.finopsKpis(params),
      queryFn: () => getUcUsageFinopsKpis(params),
      ...datedQueryOptions(period, options.enabled ?? true),
    })
  );
}

export function useUcUsageCostByTable(
  filters: UcUsageFilters,
  period: UcUsageAppliedPeriod | null,
  options: {
    search?: string;
    sort?: UcUsageCostByTableParams['sort'];
    direction?: 'asc' | 'desc';
    columnFilters?: Record<string, string>;
    page?: number;
    enabled?: boolean;
  } = {}
) {
  const scoped = usePeriodParams(filters, period);
  const params = useMemo(
    () =>
      ({
        ...scoped,
        search: options.search?.trim() || undefined,
        sort: options.sort ?? 'cost',
        direction: options.direction ?? 'desc',
        column_filter: toColumnFilterParam(options.columnFilters ?? {}),
        page: options.page ?? 1,
        page_size: PAGE_SIZE,
      }) satisfies UcUsageCostByTableParams,
    [scoped, options.search, options.sort, options.direction, options.columnFilters, options.page]
  );

  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.costByTable(params),
      queryFn: () => listUcUsageCostByTable(params),
      ...datedQueryOptions(period, options.enabled ?? true),
      placeholderData: (previous) => previous,
    })
  );
}

/**
 * Réalisé **puis** prévision. Les bornes ne partent qu'une fois la période
 * appliquée : avant cela, la carte n'affiche que la projection (FR-017).
 */
export function useUcUsageTrends(
  filters: UcUsageFilters,
  period: UcUsageAppliedPeriod | null,
  options: { metrics?: UcUsageForecastMetric[]; enabled?: boolean } = {}
) {
  const scope = useScopeParams(filters);
  const metricsKey = options.metrics?.join(',');
  const params = useMemo(
    () => ({
      ...scope,
      metrics: metricsKey ? (metricsKey.split(',') as UcUsageForecastMetric[]) : undefined,
      period_start: period?.start,
      period_end: period?.end,
    }),
    [scope, metricsKey, period?.start, period?.end]
  );

  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.trends(params),
      queryFn: () => getUcUsageFinopsTrends(params),
      ...snapshotQueryOptions(options.enabled ?? true),
    })
  );
}

/**
 * Bloc « Points d'attention » (FR-001). **Snapshot** : `recommendations` ne porte
 * pas de période, une anomalie ouverte depuis six mois est précisément celle à
 * traiter — la borner par la période du bandeau la masquerait.
 */
export function useUcUsageAttention(filters: UcUsageFilters, limit = 3, enabled = true) {
  const scope = useScopeParams(filters);
  const params = useMemo(() => ({ ...scope, limit }), [scope, limit]);

  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.attention(params),
      queryFn: () => getUcUsageAttention(params),
      ...snapshotQueryOptions(enabled),
    })
  );
}

/**
 * Valeurs proposables par les filtres — **snapshot** du registre, donc chargées
 * dès l'ouverture de la page : sans elles les sélecteurs seraient vides, ce qui
 * obligerait à taper un nom de catalogue de mémoire.
 */
export function useUcUsageFilterOptions(
  params: { catalog?: string; schema?: string; search?: string; includeDeleted?: boolean } = {}
) {
  const query = useMemo(
    () => ({
      catalog: params.catalog?.trim() || undefined,
      schema: params.schema?.trim() || undefined,
      search: params.search?.trim() || undefined,
      // Lu dans le brouillon, pas dans le périmètre appliqué : cocher la case doit
      // rendre les tables supprimées choisissables avant de cliquer sur Appliquer.
      include_deleted: params.includeDeleted || undefined,
    }),
    [params.catalog, params.schema, params.search, params.includeDeleted]
  );

  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.filterOptions(query),
      queryFn: () => getUcUsageFilterOptions(query),
      ...snapshotQueryOptions(),
      placeholderData: (previous) => previous,
    })
  );
}

// ─── Page « Gouvernance & Recommandations » ─────────────────────────────────

export function useUcUsageGovernanceCharts(filters: UcUsageFilters, enabled = true) {
  const scope = useScopeParams(filters);
  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.governanceCharts(scope),
      queryFn: () => getUcUsageGovernanceCharts(scope),
      ...snapshotQueryOptions(enabled),
    })
  );
}

export function useUcUsageRecommendationCharts(filters: UcUsageFilters, enabled = true) {
  const scope = useScopeParams(filters);
  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.recommendationCharts(scope),
      queryFn: () => getUcUsageRecommendationCharts(scope),
      ...snapshotQueryOptions(enabled),
    })
  );
}

export function useUcUsageGovernanceKpis(filters: UcUsageFilters, enabled = true) {
  const scope = useScopeParams(filters);
  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.governanceKpis(scope),
      queryFn: () => getUcUsageGovernanceKpis(scope),
      ...snapshotQueryOptions(enabled),
    })
  );
}

export function useUcUsageRegistry(
  filters: UcUsageFilters,
  options: {
    search?: string;
    signal?: UcUsageRegistryParams['signal'];
    inactivity?: UcUsageRegistryParams['inactivity'];
    missingTag?: UcUsageRegistryParams['missing_tag'];
    sort?: UcUsageRegistryParams['sort'];
    page?: number;
    enabled?: boolean;
  } = {}
) {
  const scope = useScopeParams(filters);
  const params = useMemo(
    () =>
      ({
        ...scope,
        search: options.search?.trim() || undefined,
        signal: options.signal,
        inactivity: options.inactivity,
        missing_tag: options.missingTag,
        sort: options.sort ?? 'severity',
        page: options.page ?? 1,
        page_size: PAGE_SIZE,
      }) satisfies UcUsageRegistryParams,
    [
      scope,
      options.search,
      options.sort,
      options.page,
      options.signal,
      options.inactivity,
      options.missingTag,
    ]
  );

  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.registry(params),
      queryFn: () => listUcUsageGovernanceRegistry(params),
      ...snapshotQueryOptions(options.enabled ?? true),
    })
  );
}

export function useUcUsageRecommendations(
  filters: UcUsageFilters,
  options: Pick<
    UcUsageRecommendationsParams,
    'category' | 'severity' | 'object_type' | 'age_bucket' | 'sort'
  > & {
    page?: number;
    enabled?: boolean;
  } = {}
) {
  const scope = useScopeParams(filters);
  const params = useMemo(
    () => ({
      ...scope,
      category: options.category || undefined,
      severity: options.severity || undefined,
      object_type: options.object_type,
      age_bucket: options.age_bucket,
      sort: options.sort,
      page: options.page ?? 1,
      page_size: PAGE_SIZE,
    }),
    [
      scope,
      options.category,
      options.page,
      options.severity,
      options.object_type,
      options.age_bucket,
      options.sort,
    ]
  );

  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.recommendations(params),
      queryFn: () => listUcUsageRecommendations(params),
      ...snapshotQueryOptions(options.enabled ?? true),
    })
  );
}

export { PAGE_SIZE as UC_USAGE_PAGE_SIZE };

export function useUcUsageWriteCharts(
  filters: UcUsageFilters,
  period: UcUsageAppliedPeriod | null,
  enabled = true
) {
  const params = usePeriodParams(filters, period);
  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.charts('writes', params),
      queryFn: () => getUcUsageWriteCharts(params),
      ...datedQueryOptions(period, enabled),
    })
  );
}
export function useUcUsageCostChanges(
  filters: UcUsageFilters,
  period: UcUsageAppliedPeriod | null,
  enabled = true
) {
  const params = usePeriodParams(filters, period);
  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.charts('cost-changes', params),
      queryFn: () => getUcUsageCostChanges(params),
      ...datedQueryOptions(period, enabled),
    })
  );
}
export function useUcUsageEntityDetail(
  filters: UcUsageFilters,
  period: UcUsageAppliedPeriod | null,
  selection: UcUsageEntitySelection | null
) {
  const params = usePeriodParams(filters, period);
  return toResult(
    useQuery({
      queryKey: ucUsageQueryKeys.detail(selection?.kind ?? 'table', selection?.id ?? '', params),
      queryFn: () =>
        getUcUsageEntityDetail({
          ...params,
          entity_kind: selection!.kind,
          entity_id: selection!.id,
        }),
      ...datedQueryOptions(period, Boolean(selection)),
    })
  );
}
