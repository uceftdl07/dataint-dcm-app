import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getLakeflowOverview } from '../api/dcmApiClient';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { useGlobalTimeRange } from '../contexts/time-range';
import { lakeflowQueryKeys } from './query-keys';
import { QUERY_STALE_DEFAULT_MS, QUERY_GC_DEFAULT_MS } from './query-config';

export type LakeflowWindow = 'today' | '7d' | '30d';

export function useLakeflowOverviewData(window: LakeflowWindow = 'today') {
  const { scope, getScopedParams } = useMonitoringScope();
  const { getApiParams } = useGlobalTimeRange();
  const { start_date, end_date } = getApiParams();

  // `gold_dbx_workflow_*` is keyed on `workspace_id` and carries no
  // `source_lz_id`; the backend resolves the selected landing zone to its
  // Databricks workspaces and narrows on them, so declare the `sourceLzId`
  // support to forward the header LZ filter.
  const scopedParams = getScopedParams({
    workspaceId: true,
    sourceLzId: true,
  });

  const queryParams = useMemo(
    () => ({
      window,
      start_date,
      end_date,
      // Header sends workspace_id for a single selection; Lakeflow APIs expect workspace_ids.
      workspace_ids:
        scopedParams.workspace_ids ??
        (scopedParams.workspace_id ? [scopedParams.workspace_id] : undefined),
      source_lz_id: scopedParams.source_lz_id,
      source_lz_ids: scopedParams.source_lz_ids,
    }),
    [
      window,
      start_date,
      end_date,
      scopedParams.workspace_id,
      scopedParams.workspace_ids,
      scopedParams.source_lz_id,
      scopedParams.source_lz_ids,
    ]
  );

  const query = useQuery({
    queryKey: lakeflowQueryKeys.overview(queryParams),
    queryFn: () => getLakeflowOverview(queryParams),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled: Boolean(start_date && end_date),
    placeholderData: (previous) => previous,
  });

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    fetching: query.isFetching,
    error: query.error,
    isStale: query.isStale,
    refetch: query.refetch,
    scope,
    start_date,
    end_date,
  };
}
