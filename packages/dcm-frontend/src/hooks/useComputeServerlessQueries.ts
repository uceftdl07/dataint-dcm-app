import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getComputeServerlessCostTrend,
  getComputeServerlessLevers,
  getComputeServerlessObjectCostTrend,
  getComputeServerlessObjectDetail,
  getComputeServerlessOverview,
  listComputeServerlessGovernance,
  listComputeServerlessObjects,
  listComputeServerlessSurfaces,
  type ComputeServerlessCostTrendParams,
  type ComputeServerlessGovernanceParams,
  type ComputeServerlessObjectCostTrendParams,
  type ComputeServerlessObjectDetailParams,
  type ComputeServerlessObjectsParams,
  type ComputeServerlessObjectsSort,
  type ComputeServerlessSurfacesParams,
  type ComputeServerlessSurfacesSort,
  type ComputeServerlessWindowParams,
} from '../api/dcmApiClient';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { toColumnFilterParam } from '../lib/compute/column-filters';
import { lastNDaysPeriodIso } from '../lib/compute/format';
import type {
  ComputeColumnFilterValues,
  ComputeJobWindowDays,
  ComputeMetricTrendGranularity,
} from '../types/api';
import { computeServerlessQueryKeys, type ComputeMetricsScopeQueryParams } from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';

/**
 * Reference span forwarded on every request, exactly as the other compute pages do.
 * The rolling views only echo these bounds back — a year keeps the last snapshot
 * visible even when the pipeline lags — while the two trend endpoints read the daily
 * table and get their own, narrower period from the caller.
 */
const REFERENCE_SPAN_DAYS = 365;

function useComputeScopeParams(): ComputeMetricsScopeQueryParams {
  const { getScopedParams } = useMonitoringScope();
  // Frozen at mount: a range recomputed each render would churn the cache key without
  // changing the data.
  const { period_start, period_end } = useMemo(() => lastNDaysPeriodIso(REFERENCE_SPAN_DAYS), []);
  // Gold is keyed on `workspace_id`; the backend resolves the selected landing zone to
  // its Databricks workspaces, so forward the header LZ filter too.
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

/** The KPIs of the framing banner, plus the serverless share of compute spend. */
export function useComputeServerlessOverview(windowDays: ComputeJobWindowDays = 30) {
  const scopeParams = useComputeScopeParams();
  const params = useMemo(
    () => ({ ...scopeParams, window_days: windowDays }) satisfies ComputeServerlessWindowParams,
    [scopeParams, windowDays]
  );

  const query = useQuery({
    queryKey: computeServerlessQueryKeys.overview(params),
    queryFn: () => getComputeServerlessOverview(params),
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

/**
 * Spend per surface. Paged like every other compute list, but the ranking chart wants
 * all twelve rows at once, so the caller raises `pageSize` rather than paging.
 */
export function useComputeServerlessSurfaces(options?: {
  window_days?: ComputeJobWindowDays;
  sort?: ComputeServerlessSurfacesSort;
  sortDirection?: 'asc' | 'desc';
  page?: number;
  pageSize?: number;
  enabled?: boolean;
}) {
  const scopeParams = useComputeScopeParams();
  const params = useMemo(
    () =>
      ({
        ...scopeParams,
        window_days: options?.window_days ?? 30,
        sort: options?.sort ?? 'cost',
        sort_direction: options?.sortDirection ?? 'desc',
        page: options?.page ?? 1,
        page_size: options?.pageSize ?? 25,
      }) satisfies ComputeServerlessSurfacesParams,
    [
      scopeParams,
      options?.window_days,
      options?.sort,
      options?.sortDirection,
      options?.page,
      options?.pageSize,
    ]
  );

  const query = useQuery({
    queryKey: computeServerlessQueryKeys.surfaces(params),
    queryFn: () => listComputeServerlessSurfaces(params),
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

/**
 * Daily serverless cost, split by surface. Reads the daily table, so it takes a period
 * and **not** the page's window: the caller passes the span it wants to draw.
 */
export function useComputeServerlessCostTrend(options: {
  period_start: string;
  period_end: string;
  granularity?: ComputeMetricTrendGranularity;
  surface?: string;
  enabled?: boolean;
}) {
  const scopeParams = useComputeScopeParams();
  const params = useMemo(
    () =>
      ({
        ...scopeParams,
        period_start: options.period_start,
        period_end: options.period_end,
        granularity: options.granularity ?? 'day',
        surface: options.surface,
      }) satisfies ComputeServerlessCostTrendParams,
    [scopeParams, options.period_start, options.period_end, options.granularity, options.surface]
  );

  const query = useQuery({
    queryKey: computeServerlessQueryKeys.costTrend({
      ...params,
      granularity: params.granularity ?? 'day',
    }),
    queryFn: () => getComputeServerlessCostTrend(params),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled: (options.enabled ?? true) && Boolean(params.period_start && params.period_end),
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

/**
 * Tag, budget-policy and identity coverage per (workspace, surface).
 *
 * No `window_days` anywhere in this hook: the governance table is a 90-day snapshot
 * with its own cadence, and it legends its own span in `governance_period`.
 */
export function useComputeServerlessGovernance(options?: {
  sort?: ComputeServerlessGovernanceParams['sort'];
  sortDirection?: 'asc' | 'desc';
  page?: number;
  pageSize?: number;
  /**
   * Column filters as the page holds them, serialized here — same contract as the
   * clusters and warehouses hooks: the page owns one state object per table, and the
   * repeatable `column_filter` parameter is derived from it and never stored twice.
   */
  filters?: ComputeColumnFilterValues;
  enabled?: boolean;
}) {
  const scopeParams = useComputeScopeParams();
  const params = useMemo(
    () =>
      ({
        ...scopeParams,
        column_filter: toColumnFilterParam(options?.filters),
        sort: options?.sort ?? 'cost',
        sort_direction: options?.sortDirection ?? 'desc',
        page: options?.page ?? 1,
        page_size: options?.pageSize ?? 25,
      }) satisfies ComputeServerlessGovernanceParams,
    [
      scopeParams,
      options?.filters,
      options?.sort,
      options?.sortDirection,
      options?.page,
      options?.pageSize,
    ]
  );

  const query = useQuery({
    queryKey: computeServerlessQueryKeys.governance(params),
    queryFn: () => listComputeServerlessGovernance(params),
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

/** `performance_target`, cost per run and the DLT serverless-vs-classic comparison. */
export function useComputeServerlessLevers(
  windowDays: ComputeJobWindowDays = 30,
  options?: { enabled?: boolean }
) {
  const scopeParams = useComputeScopeParams();
  const params = useMemo(
    () => ({ ...scopeParams, window_days: windowDays }) satisfies ComputeServerlessWindowParams,
    [scopeParams, windowDays]
  );

  const query = useQuery({
    queryKey: computeServerlessQueryKeys.levers(params),
    queryFn: () => getComputeServerlessLevers(params),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled:
      (options?.enabled ?? true) && Boolean(scopeParams.period_start && scopeParams.period_end),
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

/** The drill-down list, one tab per surface. */
export function useComputeServerlessObjects(options?: {
  window_days?: ComputeJobWindowDays;
  surface?: string;
  search?: string;
  sort?: ComputeServerlessObjectsSort;
  sortDirection?: 'asc' | 'desc';
  page?: number;
  pageSize?: number;
  /**
   * Same contract as the governance hook above. `surface` is **not** among these
   * filters even though the server allowlists it: it doubles the route's own `surface`
   * parameter, which the tab strip owns, and two values for one predicate is a 422.
   */
  filters?: ComputeColumnFilterValues;
  enabled?: boolean;
}) {
  const scopeParams = useComputeScopeParams();
  const params = useMemo(
    () =>
      ({
        ...scopeParams,
        window_days: options?.window_days ?? 30,
        surface: options?.surface,
        search: options?.search?.trim() || undefined,
        column_filter: toColumnFilterParam(options?.filters),
        sort: options?.sort ?? 'cost',
        sort_direction: options?.sortDirection ?? 'desc',
        page: options?.page ?? 1,
        page_size: options?.pageSize ?? 25,
      }) satisfies ComputeServerlessObjectsParams,
    [
      scopeParams,
      options?.window_days,
      options?.surface,
      options?.search,
      options?.filters,
      options?.sort,
      options?.sortDirection,
      options?.page,
      options?.pageSize,
    ]
  );

  const query = useQuery({
    queryKey: computeServerlessQueryKeys.objects(params),
    queryFn: () => listComputeServerlessObjects(params),
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

/**
 * Drawer payload of one object. Both `objectId` and `surface` are required by the
 * endpoint — the pair is the identity, since the same id is billed under two surfaces
 * for a handful of objects — so the query stays disabled until both are known.
 */
export function useComputeServerlessObjectDetail(
  objectId: string | null,
  surface: string | null,
  windowDays: ComputeJobWindowDays = 30
) {
  const scopeParams = useComputeScopeParams();
  const params = useMemo(
    () =>
      ({
        ...scopeParams,
        surface: surface ?? '',
        window_days: windowDays,
      }) satisfies ComputeServerlessObjectDetailParams,
    [scopeParams, surface, windowDays]
  );

  const query = useQuery({
    queryKey: computeServerlessQueryKeys.objectDetail(objectId ?? 'none', params),
    queryFn: () => getComputeServerlessObjectDetail(objectId!, params),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled: Boolean(objectId && surface && scopeParams.period_start && scopeParams.period_end),
  });

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    fetching: query.isFetching,
    error: query.error,
    refetch: query.refetch,
  };
}

/** Daily cost of one object, for the drawer's trend. Same identity rule as above. */
export function useComputeServerlessObjectCostTrend(options: {
  objectId: string | null;
  surface: string | null;
  period_start: string;
  period_end: string;
  granularity?: ComputeMetricTrendGranularity;
}) {
  const scopeParams = useComputeScopeParams();
  const params = useMemo(
    () =>
      ({
        ...scopeParams,
        period_start: options.period_start,
        period_end: options.period_end,
        surface: options.surface ?? '',
        granularity: options.granularity ?? 'day',
      }) satisfies ComputeServerlessObjectCostTrendParams,
    [scopeParams, options.period_start, options.period_end, options.surface, options.granularity]
  );

  const query = useQuery({
    queryKey: computeServerlessQueryKeys.objectCostTrend(options.objectId ?? 'none', {
      ...params,
      granularity: params.granularity ?? 'day',
    }),
    queryFn: () => getComputeServerlessObjectCostTrend(options.objectId!, params),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled: Boolean(
      options.objectId && options.surface && params.period_start && params.period_end
    ),
  });

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    fetching: query.isFetching,
    error: query.error,
    refetch: query.refetch,
  };
}
