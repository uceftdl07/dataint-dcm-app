import { useCallback, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getDataFactoryFull, getDcmApiErrorMessage } from '../api/dcmApiClient';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { useGlobalTimeRange } from '../contexts/time-range';
import type { PipelineRun, PipelineStatus } from '../types/api';
import { isAdfPipeline } from '../lib/pipelines/pipeline-type';
import { datafactoryQueryKeys } from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';

function computePipelineStats(runs: PipelineRun[]) {
  const succeeded = runs.filter((run) => run.status === 'succeeded').length;
  const failed = runs.filter((run) => run.status === 'failed').length;
  const running = runs.filter((run) => run.status === 'running').length;
  const successRate = runs.length === 0 ? 0 : Math.round((succeeded / runs.length) * 100);
  return { succeeded, failed, running, successRate };
}

export function useDataFactoryPageData(options: { initialStatusFilter?: PipelineStatus | '' } = {}) {
  const { getScopedParams } = useMonitoringScope();
  const { getApiParams } = useGlobalTimeRange();
  const [statusFilter, setStatusFilter] = useState<PipelineStatus | ''>(options.initialStatusFilter ?? '');
  const [search, setSearch] = useState('');
  const { start_date, end_date } = getApiParams();

  const scopedParams = getScopedParams({
    cloudProvider: true,
    sourceLzId: true,
  });

  const queryParams = useMemo(
    () => ({
      start_date,
      end_date,
      source_lz_id: scopedParams.source_lz_id,
      source_lz_ids: scopedParams.source_lz_ids,
    }),
    [end_date, scopedParams.source_lz_id, scopedParams.source_lz_ids, start_date],
  );

  const bundleQuery = useQuery({
    queryKey: datafactoryQueryKeys.full(queryParams),
    queryFn: () => getDataFactoryFull(queryParams),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
  });

  const runs = useMemo(
    () => (bundleQuery.data?.pipelines.items ?? []).filter(isAdfPipeline),
    [bundleQuery.data?.pipelines.items],
  );
  const total = bundleQuery.data?.pipelines.total ?? 0;
  const error = bundleQuery.error
    ? getDcmApiErrorMessage(bundleQuery.error, 'Error while loading Data Factory')
    : null;

  const filteredRuns = useMemo(() => {
    const term = search.trim().toLowerCase();
    return runs.filter((run) => {
      const matchesStatus = !statusFilter || run.status === statusFilter;
      const matchesSearch =
        !term
        || [run.pipeline_name, run.pipeline_id, run.run_id, run.error_message, run.source_lz_id]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(term));
      return matchesStatus && matchesSearch;
    });
  }, [runs, search, statusFilter]);

  const stats = useMemo(() => computePipelineStats(runs), [runs]);

  const resetFilters = useCallback(() => {
    setStatusFilter('');
    setSearch('');
  }, []);

  const load = useCallback(async () => {
    await bundleQuery.refetch();
  }, [bundleQuery]);

  return {
    error,
    filteredRuns,
    load,
    loading: bundleQuery.isLoading,
    loadingDetails: bundleQuery.isFetching && !bundleQuery.isLoading,
    resetFilters,
    runs,
    search,
    setSearch,
    setStatusFilter,
    stats,
    statusFilter,
    total,
  };
}
