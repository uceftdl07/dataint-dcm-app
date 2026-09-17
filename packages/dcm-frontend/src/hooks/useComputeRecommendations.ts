import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getComputeRecommendations,
  getComputeRecommendationsSummary,
  type ComputeRecommendationsParams,
} from '../api/dcmApiClient';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { useGlobalTimeRange } from '../contexts/time-range';
import { toColumnFilterParam } from '../lib/compute/column-filters';
import type { ComputeColumnFilterValues } from '../types/api';
import { computeRecommendationsQueryKeys, type ComputeMetricsScopeQueryParams } from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';

export function useComputeScopeParams(): ComputeMetricsScopeQueryParams {
  const { getScopedParams } = useMonitoringScope();
  const { getApiParams } = useGlobalTimeRange();
  const { start_date, end_date } = getApiParams();
  // `gold_dbx_compute_recommendations` and `gold_dbx_compute_forecast_daily` are
  // keyed on `workspace_id` and carry no `source_lz_id`; the backend resolves the
  // selected landing zone to its Databricks workspaces and narrows on them, so
  // declare the `sourceLzId` support to forward the header LZ (and project) filter.
  const scoped = getScopedParams({ workspaceId: true, cloudProvider: true, sourceLzId: true });

  return useMemo(
    () => ({
      period_start: start_date,
      period_end: end_date,
      cloud_provider: scoped.cloud_provider,
      workspace_id: scoped.workspace_id,
      workspace_ids: scoped.workspace_ids,
      source_lz_id: scoped.source_lz_id,
      source_lz_ids: scoped.source_lz_ids,
    }),
    [
      start_date,
      end_date,
      scoped.cloud_provider,
      scoped.workspace_id,
      scoped.workspace_ids,
      scoped.source_lz_id,
      scoped.source_lz_ids,
    ]
  );
}

export function useComputeRecommendationsSummaryData() {
  const scopeParams = useComputeScopeParams();
  const query = useQuery({
    queryKey: computeRecommendationsQueryKeys.summary(scopeParams),
    queryFn: () => getComputeRecommendationsSummary(scopeParams),
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

export function useComputeRecommendationsData(options?: {
  object_type?: string;
  category?: string;
  severity?: string;
  status?: string;
  search?: string;
  /**
   * Per-column filters held by the page. Serialized here so a page passes the one
   * state object it already owns — and so the value of an aliased column
   * (`category`, `severity`, `status` here) comes from that same object: two
   * different values for one predicate is a 422, by design.
   */
  filters?: ComputeColumnFilterValues;
  sort?: ComputeRecommendationsParams['sort'];
  order?: ComputeRecommendationsParams['order'];
  page?: number;
  pageSize?: number;
  enabled?: boolean;
}) {
  const scopeParams = useComputeScopeParams();
  const params = useMemo(
    () =>
      ({
        ...scopeParams,
        object_type: options?.object_type || undefined,
        category: options?.category || undefined,
        severity: options?.severity || undefined,
        status: options?.status || undefined,
        search: options?.search?.trim() || undefined,
        column_filter: toColumnFilterParam(options?.filters),
        sort: options?.sort ?? 'severity',
        order: options?.order ?? 'desc',
        page: options?.page ?? 1,
        page_size: options?.pageSize ?? 25,
      }) satisfies ComputeRecommendationsParams,
    [
      scopeParams,
      options?.object_type,
      options?.category,
      options?.severity,
      options?.status,
      options?.search,
      options?.filters,
      options?.sort,
      options?.order,
      options?.page,
      options?.pageSize,
    ]
  );

  const query = useQuery({
    queryKey: computeRecommendationsQueryKeys.list(params),
    queryFn: () => getComputeRecommendations(params),
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
