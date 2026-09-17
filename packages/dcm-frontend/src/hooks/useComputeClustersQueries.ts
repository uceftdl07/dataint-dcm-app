import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getComputeClusterCostTrend,
  getComputeClusterDetail,
  getComputeClusterLifetimeTrend,
  getComputeClustersOverview,
  listComputeClustersCost,
  listComputeClustersEfficiency,
  listComputeClustersGovernance,
  type ComputeClustersCostParams,
  type ComputeClustersEfficiencyParams,
  type ComputeClustersGovernanceParams,
  type ComputeClustersOverviewParams,
  type ComputeClusterTrendParams,
  type ComputeClustersWindowParams,
} from '../api/dcmApiClient';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { toColumnFilterParam } from '../lib/compute/column-filters';
import { lastNDaysPeriodIso } from '../lib/compute/format';
import type {
  ComputeClusterWindowDays,
  ComputeColumnFilterValues,
  ComputeMetricTrendGranularity,
} from '../types/api';
import {
  computeClustersQueryKeys,
  type ComputeClustersTrendQueryParams,
  type ComputeMetricsScopeQueryParams,
} from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';

/**
 * Bornes envoyées par défaut, **calculées ici et non lues dans l'en-tête**.
 *
 * La page clusters n'expose plus de dates : ses quatre tableaux lisent un
 * instantané pré-agrégé par fenêtre, où le serveur ne fait que renvoyer ces bornes.
 * Seules les deux courbes du tiroir filtrent vraiment dessus, et elles passent leur
 * propre plage. Un an couvre le détail même quand la dernière capture a plusieurs
 * semaines de retard.
 */
const REFERENCE_SPAN_DAYS = 365;

function useComputeScopeParams(): ComputeMetricsScopeQueryParams {
  const { getScopedParams } = useMonitoringScope();
  // Figée au montage : une plage recalculée à chaque rendu changerait la clé de
  // cache sans rien changer aux données.
  const { period_start, period_end } = useMemo(() => lastNDaysPeriodIso(REFERENCE_SPAN_DAYS), []);
  // The cluster metrics tables are keyed on `workspace_id`; the backend resolves
  // the selected landing zone to its Databricks workspaces and narrows on them,
  // so declare the `sourceLzId` support to forward the header LZ filter.
  const scoped = getScopedParams({ workspaceId: true, cloudProvider: true, sourceLzId: true });

  return useMemo(
    () => ({
      period_start,
      period_end,
      cloud_provider: scoped.cloud_provider,
      workspace_id: scoped.workspace_id,
      workspace_ids: scoped.workspace_ids,
      source_lz_id: scoped.source_lz_id,
      source_lz_ids: scoped.source_lz_ids,
    }),
    [
      period_start,
      period_end,
      scoped.cloud_provider,
      scoped.workspace_id,
      scoped.workspace_ids,
      scoped.source_lz_id,
      scoped.source_lz_ids,
    ]
  );
}

export function useComputeClustersOverviewData(options?: {
  window_days?: ComputeClusterWindowDays;
  search?: string;
  utilization_status?: string;
  /**
   * Per-column filters held by the page. Serialized here so a page passes the one
   * state object it already owns — and so the value of an aliased column
   * (`utilization_status` here) comes from that same object: two different values
   * for one predicate is a 422, by design.
   */
  filters?: ComputeColumnFilterValues;
  sort?: ComputeClustersOverviewParams['sort'];
  sort_direction?: ComputeClustersOverviewParams['sort_direction'];
  page?: number;
  pageSize?: number;
}) {
  const scopeParams = useComputeScopeParams();
  const params = useMemo(
    () =>
      ({
        ...scopeParams,
        window_days: options?.window_days ?? 1,
        search: options?.search?.trim() || undefined,
        utilization_status: options?.utilization_status || undefined,
        column_filter: toColumnFilterParam(options?.filters),
        sort: options?.sort ?? 'cost',
        sort_direction: options?.sort_direction ?? 'desc',
        page: options?.page ?? 1,
        page_size: options?.pageSize ?? 25,
      }) satisfies ComputeClustersOverviewParams,
    [
      scopeParams,
      options?.window_days,
      options?.search,
      options?.utilization_status,
      options?.filters,
      options?.sort,
      options?.sort_direction,
      options?.page,
      options?.pageSize,
    ]
  );
  const query = useQuery({
    queryKey: computeClustersQueryKeys.overview(params),
    queryFn: () => getComputeClustersOverview(params),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled: Boolean(scopeParams.period_start && scopeParams.period_end),
    placeholderData: (previous) => previous,
  });

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    fetching: query.isFetching,
    error: query.error,
    refetch: query.refetch,
  };
}

export function useComputeClustersCostData(options?: {
  window_days?: ComputeClusterWindowDays;
  search?: string;
  sku_group?: string;
  /** See `useComputeClustersOverviewData`. Aliases here: `search`, `sku_group`. */
  filters?: ComputeColumnFilterValues;
  sort?: ComputeClustersCostParams['sort'];
  page?: number;
  pageSize?: number;
  enabled?: boolean;
}) {
  const scopeParams = useComputeScopeParams();
  const params = useMemo(
    () =>
      ({
        ...scopeParams,
        window_days: options?.window_days ?? 1,
        search: options?.search?.trim() || undefined,
        sku_group: options?.sku_group || undefined,
        column_filter: toColumnFilterParam(options?.filters),
        sort: options?.sort ?? 'cost_desc',
        page: options?.page ?? 1,
        page_size: options?.pageSize ?? 25,
      }) satisfies ComputeClustersCostParams,
    [
      scopeParams,
      options?.window_days,
      options?.search,
      options?.sku_group,
      options?.filters,
      options?.sort,
      options?.page,
      options?.pageSize,
    ]
  );

  const query = useQuery({
    queryKey: computeClustersQueryKeys.cost(params),
    queryFn: () => listComputeClustersCost(params),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled:
      (options?.enabled ?? true) && Boolean(scopeParams.period_start && scopeParams.period_end),
    placeholderData: (previous) => previous,
  });

  return {
    params,
    data: query.data ?? null,
    loading: query.isLoading,
    fetching: query.isFetching,
    error: query.error,
    refetch: query.refetch,
  };
}

export function useComputeClustersEfficiencyData(options?: {
  window_days?: ComputeClusterWindowDays;
  utilization_status?: string;
  is_zombie?: boolean;
  /** See `useComputeClustersOverviewData`. Alias here: `utilization_status`. */
  filters?: ComputeColumnFilterValues;
  page?: number;
  pageSize?: number;
  enabled?: boolean;
}) {
  const scopeParams = useComputeScopeParams();
  const params = useMemo(
    () =>
      ({
        ...scopeParams,
        window_days: options?.window_days ?? 1,
        utilization_status: options?.utilization_status || undefined,
        is_zombie: options?.is_zombie,
        column_filter: toColumnFilterParam(options?.filters),
        page: options?.page ?? 1,
        page_size: options?.pageSize ?? 25,
      }) satisfies ComputeClustersEfficiencyParams,
    [
      scopeParams,
      options?.window_days,
      options?.utilization_status,
      options?.is_zombie,
      options?.filters,
      options?.page,
      options?.pageSize,
    ]
  );

  const query = useQuery({
    queryKey: computeClustersQueryKeys.efficiency({
      ...scopeParams,
      window_days: params.window_days,
      utilization_status: params.utilization_status,
      is_zombie: params.is_zombie,
      // Rebuilt field by field here, so the filters have to be repeated: a key
      // blind to them would serve the unfiltered page from cache.
      column_filter: params.column_filter,
      page: params.page,
      page_size: params.page_size,
    }),
    queryFn: () => listComputeClustersEfficiency(params),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled:
      (options?.enabled ?? true) && Boolean(scopeParams.period_start && scopeParams.period_end),
    placeholderData: (previous) => previous,
  });

  return {
    params,
    data: query.data ?? null,
    loading: query.isLoading,
    fetching: query.isFetching,
    error: query.error,
    refetch: query.refetch,
  };
}

export function useComputeClustersGovernanceData(options?: {
  severity?: string;
  missing_tags?: boolean;
  dbr_obsolete?: boolean;
  /** See `useComputeClustersOverviewData`. Alias here: `severity`. */
  filters?: ComputeColumnFilterValues;
  page?: number;
  pageSize?: number;
  enabled?: boolean;
}) {
  const scopeParams = useComputeScopeParams();
  const params = useMemo(
    () =>
      ({
        ...scopeParams,
        severity: options?.severity || undefined,
        missing_tags: options?.missing_tags,
        dbr_obsolete: options?.dbr_obsolete,
        column_filter: toColumnFilterParam(options?.filters),
        page: options?.page ?? 1,
        page_size: options?.pageSize ?? 25,
      }) satisfies ComputeClustersGovernanceParams,
    [
      scopeParams,
      options?.severity,
      options?.missing_tags,
      options?.dbr_obsolete,
      options?.filters,
      options?.page,
      options?.pageSize,
    ]
  );

  const query = useQuery({
    queryKey: computeClustersQueryKeys.governance({
      ...scopeParams,
      severity: params.severity,
      missing_tags: params.missing_tags,
      dbr_obsolete: params.dbr_obsolete,
      column_filter: params.column_filter,
      page: params.page,
      page_size: params.page_size,
    }),
    queryFn: () => listComputeClustersGovernance(params),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled:
      (options?.enabled ?? true) && Boolean(scopeParams.period_start && scopeParams.period_end),
    placeholderData: (previous) => previous,
  });

  return {
    params,
    data: query.data ?? null,
    loading: query.isLoading,
    fetching: query.isFetching,
    error: query.error,
    refetch: query.refetch,
  };
}

export function useComputeClusterDetail(
  clusterId: string | null,
  windowDays: ComputeClusterWindowDays = 1
) {
  const scopeParams = useComputeScopeParams();
  const params = useMemo(
    () => ({ ...scopeParams, window_days: windowDays }) satisfies ComputeClustersWindowParams,
    [scopeParams, windowDays]
  );
  const query = useQuery({
    queryKey: computeClustersQueryKeys.detail(clusterId ?? 'none', params),
    queryFn: () => getComputeClusterDetail(clusterId!, params),
    enabled: Boolean(clusterId && scopeParams.period_start && scopeParams.period_end),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
  });

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    fetching: query.isFetching,
    error: query.error,
    refetch: query.refetch,
  };
}

export interface ComputeClusterTrendOptions {
  clusterId: string | null;
  granularity: ComputeMetricTrendGranularity;
  period_start: string;
  period_end: string;
}

/**
 * Both per-cluster trends share their shape: a ≈90-day period on a `*_daily`
 * table, aggregated by day, week or month. Only the endpoint and the key differ.
 */
function useComputeClusterTrend<TResponse>(
  options: ComputeClusterTrendOptions,
  keyFor: (clusterId: string, params: ComputeClustersTrendQueryParams) => readonly unknown[],
  fetcher: (clusterId: string, params: ComputeClusterTrendParams) => Promise<TResponse>
) {
  const scope = useComputeScopeParams();
  const apiParams = useMemo(
    () => ({
      ...scope,
      period_start: options.period_start,
      period_end: options.period_end,
      granularity: options.granularity,
    }),
    [scope, options.period_start, options.period_end, options.granularity]
  );

  const query = useQuery({
    queryKey: keyFor(options.clusterId ?? 'none', apiParams),
    queryFn: () => fetcher(options.clusterId!, apiParams),
    enabled: Boolean(options.clusterId && apiParams.period_start && apiParams.period_end),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
  });

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    fetching: query.isFetching,
    error: query.error,
    refetch: query.refetch,
  };
}

export function useComputeClusterCostTrend(options: ComputeClusterTrendOptions) {
  return useComputeClusterTrend(
    options,
    computeClustersQueryKeys.costTrend,
    getComputeClusterCostTrend
  );
}

export function useComputeClusterLifetimeTrend(options: ComputeClusterTrendOptions) {
  return useComputeClusterTrend(
    options,
    computeClustersQueryKeys.lifetimeTrend,
    getComputeClusterLifetimeTrend
  );
}
