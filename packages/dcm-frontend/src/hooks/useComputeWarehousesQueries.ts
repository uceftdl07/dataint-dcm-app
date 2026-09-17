import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getComputeWarehouseCostTrend,
  getComputeWarehouseDetail,
  getComputeWarehousesOverview,
  listComputeWarehousesCost,
  listComputeWarehousesQueryPerformance,
  listComputeWarehousesSlowQueries,
  type ComputeWarehousesCostParams,
  type ComputeWarehousesOverviewParams,
  type ComputeWarehousesQueryPerformanceParams,
  type ComputeWarehousesSlowQueriesParams,
} from '../api/dcmApiClient';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { toColumnFilterParam } from '../lib/compute/column-filters';
import { lastNDaysPeriodIso } from '../lib/compute/format';
import type {
  ComputeColumnFilterValues,
  ComputeMetricTrendGranularity,
  ComputeWarehouseWindowDays,
} from '../types/api';
import { computeWarehousesQueryKeys, type ComputeMetricsScopeQueryParams } from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';

/**
 * Bornes envoyées par défaut, **calculées ici et non lues dans l'en-tête**.
 *
 * La page warehouses n'expose plus de dates : ses trois onglets à fenêtre lisent un
 * instantané pré-agrégé, où le serveur ne fait que renvoyer ces bornes. Deux
 * endpoints s'en servent pour de vrai — le détail du tiroir (dernière ligne dans la
 * plage) et la liste des requêtes lentes, qui passe désormais la sienne. Un an
 * couvre le détail même quand la dernière capture a plusieurs semaines de retard,
 * ce qu'un défaut de 30 jours ne garantit pas.
 */
const REFERENCE_SPAN_DAYS = 365;

/** Plage par défaut de l'onglet Slow queries — celle de l'ancien en-tête. */
export const SLOW_QUERIES_DEFAULT_DAYS = 30;

function useComputeScopeParams(): ComputeMetricsScopeQueryParams {
  const { getScopedParams } = useMonitoringScope();
  // Figée au montage : une plage recalculée à chaque rendu changerait la clé de
  // cache sans rien changer aux données.
  const { period_start, period_end } = useMemo(() => lastNDaysPeriodIso(REFERENCE_SPAN_DAYS), []);
  // The warehouse metrics tables are keyed on `workspace_id`; the backend
  // resolves the selected landing zone to its Databricks workspaces and narrows
  // on them, so declare the `sourceLzId` support to forward the header LZ filter.
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

export function useComputeWarehousesOverviewData(options?: {
  window_days?: ComputeWarehouseWindowDays;
  search?: string;
  warehouse_size?: string;
  min_failure_rate_pct?: number;
  /**
   * Per-column filters held by the page. Serialized here so a page passes the one
   * state object it already owns — and so the value of an aliased column
   * (`warehouse_size`, `min_failure_rate_pct` here) comes from that same object:
   * two different values for one predicate is a 422, by design.
   */
  filters?: ComputeColumnFilterValues;
  sort?: ComputeWarehousesOverviewParams['sort'];
  sort_direction?: ComputeWarehousesOverviewParams['sort_direction'];
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
        warehouse_size: options?.warehouse_size || undefined,
        min_failure_rate_pct: options?.min_failure_rate_pct,
        column_filter: toColumnFilterParam(options?.filters),
        sort: options?.sort ?? 'cost',
        sort_direction: options?.sort_direction ?? 'desc',
        page: options?.page ?? 1,
        page_size: options?.pageSize ?? 25,
      }) satisfies ComputeWarehousesOverviewParams,
    [
      scopeParams,
      options?.window_days,
      options?.search,
      options?.warehouse_size,
      options?.min_failure_rate_pct,
      options?.filters,
      options?.sort,
      options?.sort_direction,
      options?.page,
      options?.pageSize,
    ]
  );
  const query = useQuery({
    queryKey: computeWarehousesQueryKeys.overview(params),
    queryFn: () => getComputeWarehousesOverview(params),
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

export function useComputeWarehousesCostData(options?: {
  window_days?: ComputeWarehouseWindowDays;
  search?: string;
  warehouse_size?: string;
  /** See `useComputeWarehousesOverviewData`. Aliases here: `search`, `warehouse_size`. */
  filters?: ComputeColumnFilterValues;
  sort?: ComputeWarehousesCostParams['sort'];
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
        warehouse_size: options?.warehouse_size || undefined,
        column_filter: toColumnFilterParam(options?.filters),
        sort: options?.sort ?? 'cost_desc',
        page: options?.page ?? 1,
        page_size: options?.pageSize ?? 25,
      }) satisfies ComputeWarehousesCostParams,
    [
      scopeParams,
      options?.window_days,
      options?.search,
      options?.warehouse_size,
      options?.filters,
      options?.sort,
      options?.page,
      options?.pageSize,
    ]
  );

  const query = useQuery({
    queryKey: computeWarehousesQueryKeys.cost(params),
    queryFn: () => listComputeWarehousesCost(params),
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

export function useComputeWarehousesQueryPerformanceData(options?: {
  window_days?: ComputeWarehouseWindowDays;
  min_failure_rate_pct?: number;
  has_spill?: boolean;
  min_latency_p95_ms?: number;
  /**
   * See `useComputeWarehousesOverviewData`. Aliases here: `min_failure_rate_pct`,
   * `has_spill`, `min_latency_p95_ms`.
   */
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
        min_failure_rate_pct: options?.min_failure_rate_pct,
        has_spill: options?.has_spill,
        min_latency_p95_ms: options?.min_latency_p95_ms,
        column_filter: toColumnFilterParam(options?.filters),
        page: options?.page ?? 1,
        page_size: options?.pageSize ?? 25,
      }) satisfies ComputeWarehousesQueryPerformanceParams,
    [
      scopeParams,
      options?.window_days,
      options?.min_failure_rate_pct,
      options?.has_spill,
      options?.min_latency_p95_ms,
      options?.filters,
      options?.page,
      options?.pageSize,
    ]
  );

  const query = useQuery({
    queryKey: computeWarehousesQueryKeys.queryPerformance(params),
    queryFn: () => listComputeWarehousesQueryPerformance(params),
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

export function useComputeWarehousesSlowQueriesData(options?: {
  warehouse_id?: string;
  reason?: string;
  /**
   * Plage à lire, en jours révolus jusqu'à aujourd'hui. Cet onglet est le seul de
   * la page dont l'endpoint filtre vraiment sur des bornes
   * (`CAST(start_time AS DATE) BETWEEN …`) : il porte donc son propre choix de
   * plage, à la place du sélecteur de dates retiré de l'en-tête.
   */
  windowDays?: number;
  /** See `useComputeWarehousesOverviewData`. Alias here: `reason`. */
  filters?: ComputeColumnFilterValues;
  page?: number;
  pageSize?: number;
  enabled?: boolean;
}) {
  const scopeParams = useComputeScopeParams();
  const windowDays = options?.windowDays ?? SLOW_QUERIES_DEFAULT_DAYS;
  const period = useMemo(() => lastNDaysPeriodIso(windowDays), [windowDays]);
  const params = useMemo(
    () =>
      ({
        ...scopeParams,
        ...period,
        warehouse_id: options?.warehouse_id || undefined,
        reason: options?.reason || undefined,
        column_filter: toColumnFilterParam(options?.filters),
        page: options?.page ?? 1,
        page_size: options?.pageSize ?? 25,
      }) satisfies ComputeWarehousesSlowQueriesParams,
    [
      scopeParams,
      period,
      options?.warehouse_id,
      options?.reason,
      options?.filters,
      options?.page,
      options?.pageSize,
    ]
  );

  const query = useQuery({
    queryKey: computeWarehousesQueryKeys.slowQueries(params),
    queryFn: () => listComputeWarehousesSlowQueries(params),
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

export function useComputeWarehousesSlowQueriesEnabled() {
  const probe = useComputeWarehousesSlowQueriesData({ pageSize: 1, enabled: true });
  return probe.data?.enabled ?? null;
}

export function useComputeWarehouseDetail(warehouseId: string | null) {
  const scopeParams = useComputeScopeParams();
  const query = useQuery({
    queryKey: computeWarehousesQueryKeys.detail(warehouseId ?? 'none', scopeParams),
    queryFn: () => getComputeWarehouseDetail(warehouseId!, scopeParams),
    enabled: Boolean(warehouseId && scopeParams.period_start && scopeParams.period_end),
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

export function useComputeWarehouseCostTrend(params: {
  warehouseId: string | null;
  granularity: ComputeMetricTrendGranularity;
  period_start: string;
  period_end: string;
}) {
  const scope = useComputeScopeParams();
  const apiParams = useMemo(
    () => ({
      ...scope,
      period_start: params.period_start,
      period_end: params.period_end,
      granularity: params.granularity,
    }),
    [scope, params.period_start, params.period_end, params.granularity]
  );

  const query = useQuery({
    queryKey: computeWarehousesQueryKeys.costTrend(params.warehouseId ?? 'none', {
      ...apiParams,
      granularity: params.granularity,
    }),
    queryFn: () => getComputeWarehouseCostTrend(params.warehouseId!, apiParams),
    enabled: Boolean(params.warehouseId && apiParams.period_start && apiParams.period_end),
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
