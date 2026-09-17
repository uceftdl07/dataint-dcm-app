import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getComputeJobCostTrend,
  getComputeJobDetail,
  getComputeJobUptimeTrend,
  getComputeJobsOverview,
  listComputeJobsCost,
  listComputeJobsEfficiency,
  type ComputeJobsCostParams,
  type ComputeJobsEfficiencyParams,
  type ComputeJobsOverviewParams,
  type ComputeStableGrainTrendParams,
  type ComputeStableGrainWindowParams,
} from '../api/dcmApiClient';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { lastNDaysPeriodIso } from '../lib/compute/format';
import type { ComputeJobWindowDays, ComputeMetricTrendGranularity } from '../types/api';
import {
  computeJobsQueryKeys,
  type ComputeMetricsScopeQueryParams,
  type ComputeStableGrainTrendQueryParams,
} from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';

/**
 * Reference span forwarded on every request. The job list reads a pre-aggregated
 * rolling window, so the server only echoes these bounds — a year is wide enough
 * to keep the last snapshot visible even when it lags by several weeks.
 */
const REFERENCE_SPAN_DAYS = 365;

function useComputeScopeParams(): ComputeMetricsScopeQueryParams {
  const { getScopedParams } = useMonitoringScope();
  // Frozen at mount: a range recomputed each render would churn the cache key
  // without changing the data.
  const { period_start, period_end } = useMemo(() => lastNDaysPeriodIso(REFERENCE_SPAN_DAYS), []);
  // Gold is keyed on `workspace_id`; the backend resolves the selected landing
  // zone to its Databricks workspaces, so forward the header LZ filter too.
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

export function useComputeJobsOverviewData(options?: {
  window_days?: ComputeJobWindowDays;
  search?: string;
  sort?: ComputeJobsOverviewParams['sort'];
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
        sort: options?.sort ?? 'cost_desc',
        page: options?.page ?? 1,
        page_size: options?.pageSize ?? 25,
      }) satisfies ComputeJobsOverviewParams,
    [
      scopeParams,
      options?.window_days,
      options?.search,
      options?.sort,
      options?.page,
      options?.pageSize,
    ]
  );

  const query = useQuery({
    queryKey: computeJobsQueryKeys.overview(params),
    queryFn: () => getComputeJobsOverview(params),
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

export function useComputeJobsCostData(options?: {
  window_days?: ComputeJobWindowDays;
  search?: string;
  sort?: ComputeJobsCostParams['sort'];
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
        sort: options?.sort ?? 'cost_desc',
        page: options?.page ?? 1,
        page_size: options?.pageSize ?? 25,
      }) satisfies ComputeJobsCostParams,
    [
      scopeParams,
      options?.window_days,
      options?.search,
      options?.sort,
      options?.page,
      options?.pageSize,
    ]
  );

  const query = useQuery({
    queryKey: computeJobsQueryKeys.cost(params),
    queryFn: () => listComputeJobsCost(params),
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
 * Utilization of each job over the window. A smaller population than the cost
 * views — efficiency comes from `node_timeline`, cost from billing — so a job
 * listed under Cost may legitimately be absent here (024 SC-005).
 */
export function useComputeJobsEfficiencyData(options?: {
  window_days?: ComputeJobWindowDays;
  search?: string;
  sort?: ComputeJobsEfficiencyParams['sort'];
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
        sort: options?.sort ?? 'savings_desc',
        page: options?.page ?? 1,
        page_size: options?.pageSize ?? 25,
      }) satisfies ComputeJobsEfficiencyParams,
    [
      scopeParams,
      options?.window_days,
      options?.search,
      options?.sort,
      options?.page,
      options?.pageSize,
    ]
  );

  const query = useQuery({
    queryKey: computeJobsQueryKeys.efficiency(params),
    queryFn: () => listComputeJobsEfficiency(params),
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

/** Drawer payload of one job: cost + efficiency over the same window as the list. */
export function useComputeJobDetail(jobId: string | null, windowDays: ComputeJobWindowDays = 1) {
  const scopeParams = useComputeScopeParams();
  const params = useMemo(
    () => ({ ...scopeParams, window_days: windowDays }) satisfies ComputeStableGrainWindowParams,
    [scopeParams, windowDays]
  );
  const query = useQuery({
    queryKey: computeJobsQueryKeys.detail(jobId ?? 'none', params),
    queryFn: () => getComputeJobDetail(jobId!, params),
    enabled: Boolean(jobId && scopeParams.period_start && scopeParams.period_end),
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

export interface ComputeJobTrendOptions {
  jobId: string | null;
  granularity: ComputeMetricTrendGranularity;
  period_start: string;
  period_end: string;
}

/**
 * Both per-job trends share their shape: a ≈90-day period on a `*_daily` table,
 * aggregated by day, week or month. Only the endpoint and the key differ.
 */
function useComputeJobTrend<TResponse>(
  options: ComputeJobTrendOptions,
  keyFor: (jobId: string, params: ComputeStableGrainTrendQueryParams) => readonly unknown[],
  fetcher: (jobId: string, params: ComputeStableGrainTrendParams) => Promise<TResponse>
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
    queryKey: keyFor(options.jobId ?? 'none', apiParams),
    queryFn: () => fetcher(options.jobId!, apiParams),
    enabled: Boolean(options.jobId && apiParams.period_start && apiParams.period_end),
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

export function useComputeJobCostTrend(options: ComputeJobTrendOptions) {
  return useComputeJobTrend(options, computeJobsQueryKeys.costTrend, getComputeJobCostTrend);
}

export function useComputeJobUptimeTrend(options: ComputeJobTrendOptions) {
  return useComputeJobTrend(options, computeJobsQueryKeys.uptimeTrend, getComputeJobUptimeTrend);
}
