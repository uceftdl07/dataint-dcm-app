import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getComputePipelineCostTrend,
  getComputePipelineDetail,
  getComputePipelineUptimeTrend,
  getComputePipelinesOverview,
  listComputePipelinesCost,
  listComputePipelinesEfficiency,
  type ComputePipelinesCostParams,
  type ComputePipelinesEfficiencyParams,
  type ComputePipelinesOverviewParams,
  type ComputeStableGrainTrendParams,
  type ComputeStableGrainWindowParams,
} from '../api/dcmApiClient';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { lastNDaysPeriodIso } from '../lib/compute/format';
import type { ComputeJobWindowDays, ComputeMetricTrendGranularity } from '../types/api';
import {
  computePipelinesQueryKeys,
  type ComputeMetricsScopeQueryParams,
  type ComputeStableGrainTrendQueryParams,
} from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';

/**
 * Reference span forwarded on every request. The pipeline list reads a
 * pre-aggregated rolling window, so the server only echoes these bounds — a year
 * is wide enough to keep the last snapshot visible even when it lags.
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

export function useComputePipelinesOverviewData(options?: {
  window_days?: ComputeJobWindowDays;
  search?: string;
  sort?: ComputePipelinesOverviewParams['sort'];
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
      }) satisfies ComputePipelinesOverviewParams,
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
    queryKey: computePipelinesQueryKeys.overview(params),
    queryFn: () => getComputePipelinesOverview(params),
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

export function useComputePipelinesCostData(options?: {
  window_days?: ComputeJobWindowDays;
  search?: string;
  sort?: ComputePipelinesCostParams['sort'];
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
      }) satisfies ComputePipelinesCostParams,
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
    queryKey: computePipelinesQueryKeys.cost(params),
    queryFn: () => listComputePipelinesCost(params),
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
 * Utilization of each DLT pipeline over the window. Serverless pipelines have no
 * `node_timeline` row, so they are billed without being measured and simply do not
 * appear here (024 SC-005) — the Cost tab stays the exhaustive view.
 */
export function useComputePipelinesEfficiencyData(options?: {
  window_days?: ComputeJobWindowDays;
  search?: string;
  sort?: ComputePipelinesEfficiencyParams['sort'];
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
      }) satisfies ComputePipelinesEfficiencyParams,
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
    queryKey: computePipelinesQueryKeys.efficiency(params),
    queryFn: () => listComputePipelinesEfficiency(params),
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

/** Drawer payload of one pipeline: cost + efficiency over the list's window. */
export function useComputePipelineDetail(
  pipelineId: string | null,
  windowDays: ComputeJobWindowDays = 1
) {
  const scopeParams = useComputeScopeParams();
  const params = useMemo(
    () => ({ ...scopeParams, window_days: windowDays }) satisfies ComputeStableGrainWindowParams,
    [scopeParams, windowDays]
  );
  const query = useQuery({
    queryKey: computePipelinesQueryKeys.detail(pipelineId ?? 'none', params),
    queryFn: () => getComputePipelineDetail(pipelineId!, params),
    enabled: Boolean(pipelineId && scopeParams.period_start && scopeParams.period_end),
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

export interface ComputePipelineTrendOptions {
  pipelineId: string | null;
  granularity: ComputeMetricTrendGranularity;
  period_start: string;
  period_end: string;
}

/**
 * Both per-pipeline trends share their shape: a ≈90-day period on a `*_daily`
 * table, aggregated by day, week or month. Only the endpoint and the key differ.
 */
function useComputePipelineTrend<TResponse>(
  options: ComputePipelineTrendOptions,
  keyFor: (pipelineId: string, params: ComputeStableGrainTrendQueryParams) => readonly unknown[],
  fetcher: (pipelineId: string, params: ComputeStableGrainTrendParams) => Promise<TResponse>
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
    queryKey: keyFor(options.pipelineId ?? 'none', apiParams),
    queryFn: () => fetcher(options.pipelineId!, apiParams),
    enabled: Boolean(options.pipelineId && apiParams.period_start && apiParams.period_end),
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

export function useComputePipelineCostTrend(options: ComputePipelineTrendOptions) {
  return useComputePipelineTrend(
    options,
    computePipelinesQueryKeys.costTrend,
    getComputePipelineCostTrend
  );
}

export function useComputePipelineUptimeTrend(options: ComputePipelineTrendOptions) {
  return useComputePipelineTrend(
    options,
    computePipelinesQueryKeys.uptimeTrend,
    getComputePipelineUptimeTrend
  );
}
