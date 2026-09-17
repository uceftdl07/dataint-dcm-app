import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import {
  getLakeflowJob,
  getLakeflowJobRuns,
  getLakeflowJobs,
  getLakeflowRunTasks,
} from '../api/dcmApiClient';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { useGlobalTimeRange } from '../contexts/time-range';
import { toColumnFilterParam } from '../lib/compute/column-filters';
import type { ComputeColumnFilterValues } from '../types/api';
import { lakeflowQueryKeys } from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';

/** Exported for `useColumnFilterOptions`: the combos must ask in the table's own scope. */
export function useJobsScopeParams() {
  const { getScopedParams } = useMonitoringScope();
  const { getApiParams } = useGlobalTimeRange();
  const { start_date, end_date } = getApiParams();
  // `gold_dbx_workflow_*` is keyed on `workspace_id` and carries no
  // `source_lz_id`; the backend resolves the selected landing zone to its
  // Databricks workspaces and narrows on them, so declare the `sourceLzId`
  // support to forward the header LZ filter.
  const scoped = getScopedParams({ workspaceId: true, sourceLzId: true });
  return useMemo(
    () => ({
      start_date,
      end_date,
      // Header sends workspace_id for a single selection; Lakeflow APIs expect workspace_ids.
      workspace_ids:
        scoped.workspace_ids ?? (scoped.workspace_id ? [scoped.workspace_id] : undefined),
      source_lz_id: scoped.source_lz_id,
      source_lz_ids: scoped.source_lz_ids,
    }),
    [
      start_date,
      end_date,
      scoped.workspace_id,
      scoped.workspace_ids,
      scoped.source_lz_id,
      scoped.source_lz_ids,
    ]
  );
}

export function useLakeflowJobsList(options?: {
  search?: string;
  /**
   * Per-column filters held by the page. Serialized here so a page passes the one
   * state object it already owns — and so the value of an aliased column (`search`,
   * `status`, `trigger_type` here) comes from that same object: a `status=[SUCCESS]`
   * against `column_filter=status:FAILED` is a 422, by design.
   */
  filters?: ComputeColumnFilterValues;
  page?: number;
  pageSize?: number;
  sort?: string;
  order?: 'asc' | 'desc';
  driftOnly?: boolean;
  noRuns?: boolean;
  withRetries?: boolean;
}) {
  const scopeParams = useJobsScopeParams();
  const [searchParams] = useSearchParams();
  const statusFromUrl = searchParams.get('status');

  const search = options?.search;
  const page = options?.page ?? 1;
  const pageSize = options?.pageSize ?? 25;
  const sort = options?.sort ?? 'problems';
  const order = options?.order ?? 'desc';
  const driftOnly = options?.driftOnly;
  const noRuns = options?.noRuns;
  const withRetries = options?.withRetries;

  const queryParams = useMemo(() => {
    const status = statusFromUrl
      ? statusFromUrl
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
      : undefined;
    return {
      ...scopeParams,
      search: search || undefined,
      status,
      column_filter: toColumnFilterParam(options?.filters),
      drift_only: driftOnly || undefined,
      no_runs: noRuns || undefined,
      with_retries: withRetries || undefined,
      sort,
      order,
      page,
      page_size: pageSize,
    };
  }, [
    scopeParams,
    statusFromUrl,
    search,
    options?.filters,
    page,
    pageSize,
    sort,
    order,
    driftOnly,
    noRuns,
    withRetries,
  ]);

  const query = useQuery({
    queryKey: lakeflowQueryKeys.jobs(queryParams),
    queryFn: () => getLakeflowJobs(queryParams),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled: Boolean(scopeParams.start_date && scopeParams.end_date),
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

export function useLakeflowJobDetail(workflowId: string | undefined) {
  const scopeParams = useJobsScopeParams();
  const query = useQuery({
    queryKey: lakeflowQueryKeys.job(workflowId ?? '', scopeParams),
    queryFn: () => getLakeflowJob(workflowId!, scopeParams),
    enabled: Boolean(workflowId && scopeParams.start_date && scopeParams.end_date),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
  });
  return {
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error,
    refetch: query.refetch,
  };
}

export function useLakeflowJobRuns(
  workflowId: string | undefined,
  options?: {
    page?: number;
    pageSize?: number;
    search?: string;
    status?: string[];
    trigger_type?: string[];
    /** See `useLakeflowJobsList`. Aliases here: `status`, `trigger_type`. */
    filters?: ComputeColumnFilterValues;
    withRetries?: boolean;
    sort?: string;
    order?: 'asc' | 'desc';
  }
) {
  const scopeParams = useJobsScopeParams();
  const params = useMemo(
    () => ({
      ...scopeParams,
      search: options?.search?.trim() || undefined,
      status: options?.status?.length ? options.status : undefined,
      trigger_type: options?.trigger_type?.length ? options.trigger_type : undefined,
      column_filter: toColumnFilterParam(options?.filters),
      with_retries: options?.withRetries || undefined,
      sort: options?.sort ?? 'start_time',
      order: options?.order ?? 'desc',
      page: options?.page ?? 1,
      page_size: options?.pageSize ?? 25,
    }),
    [
      scopeParams,
      options?.search,
      options?.status,
      options?.trigger_type,
      options?.filters,
      options?.withRetries,
      options?.sort,
      options?.order,
      options?.page,
      options?.pageSize,
    ]
  );
  const query = useQuery({
    queryKey: lakeflowQueryKeys.jobRuns(workflowId ?? '', params),
    queryFn: () => getLakeflowJobRuns(workflowId!, params),
    enabled: Boolean(workflowId && scopeParams.start_date && scopeParams.end_date),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
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

export function useLakeflowRunTasks(
  workflowId: string | undefined,
  runId: string | undefined,
  failedOnly = false
) {
  const scopeParams = useJobsScopeParams();
  const params = useMemo(
    () => ({
      workspace_ids: scopeParams.workspace_ids,
      failed_only: failedOnly || undefined,
    }),
    [scopeParams, failedOnly]
  );
  const query = useQuery({
    queryKey: lakeflowQueryKeys.runTasks(workflowId ?? '', runId ?? '', params),
    queryFn: () => getLakeflowRunTasks(workflowId!, runId!, params),
    enabled: Boolean(workflowId && runId),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
  });
  return {
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error,
    refetch: query.refetch,
  };
}
