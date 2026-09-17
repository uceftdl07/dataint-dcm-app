import { useCallback, useMemo, useState } from 'react';
import { getDashboardOverview, listPipelines } from '../api/dcmApiClient';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { useGlobalTimeRange } from '../contexts/time-range';
import type { PipelineRun, PipelineStatus } from '../types/api';
import { useStagedListFetch, useStagedQueries } from './useStagedQueries';

function computePipelineStats(runs: PipelineRun[]) {
  const succeeded = runs.filter((r) => r.status === 'succeeded').length;
  const failed = runs.filter((r) => r.status === 'failed').length;
  const running = runs.filter((r) => r.status === 'running').length;
  const now = new Date();
  const failed24h = runs.filter(
    (r) => r.status === 'failed' && r.start_time && now.getTime() - new Date(r.start_time).getTime() < 86400000,
  ).length;
  const successRate = runs.length === 0 ? 0 : Math.round((succeeded / runs.length) * 100);
  return { succeeded, failed, running, failed24h, successRate };
}

export function usePipelinesPageData(options: { initialStatusFilter?: PipelineStatus | ''; initialTypeFilter?: string } = {}) {
  const { getApiParams } = useGlobalTimeRange();
  const { scope, getScopedParams } = useMonitoringScope();
  const [pipelineTypeFilter, setPipelineTypeFilter] = useState(options.initialTypeFilter ?? '');
  const [statusFilter, setStatusFilter] = useState<PipelineStatus | ''>(options.initialStatusFilter ?? '');
  const [search, setSearch] = useState('');

  const { start_date, end_date } = getApiParams();
  const scopedParams = getScopedParams({ cloudProvider: true });
  const hasTypeFilter = Boolean(pipelineTypeFilter);

  const overviewParams = useMemo(() => ({
    start_date,
    end_date,
    cloud_provider: scopedParams.cloud_provider,
  }), [end_date, scopedParams.cloud_provider, start_date]);

  const overviewStaged = useStagedQueries({
    queryKey: ['pipelines-page', overviewParams],
    enabled: !hasTypeFilter,
    fetchPrimary: () => getDashboardOverview(overviewParams),
    fetchDetails: () => listPipelines({
      start_date,
      end_date,
      cloud_provider: scopedParams.cloud_provider,
      limit: 200,
    }),
    emptyDetails: () => ({ items: [], total: 0 }),
    merge: (overview, pipelines) => ({ overview, pipelines }),
  });

  const filteredList = useStagedListFetch<PipelineRun, { items: PipelineRun[]; total: number }>(
    (limit) => listPipelines({
      start_date,
      end_date,
      cloud_provider: scopedParams.cloud_provider,
      pipeline_type: pipelineTypeFilter || undefined,
      limit,
    }),
    [end_date, pipelineTypeFilter, scopedParams.cloud_provider, start_date],
    { enabled: hasTypeFilter },
  );

  const runs = hasTypeFilter ? filteredList.items : (overviewStaged.data?.pipelines.items ?? []);
  const total = hasTypeFilter
    ? filteredList.total
    : (overviewStaged.data?.pipelines.total ?? overviewStaged.data?.overview.total_pipelines ?? 0);
  const loading = hasTypeFilter ? filteredList.loading : overviewStaged.isLoading;
  const loadingDetails = hasTypeFilter ? filteredList.loadingDetails : overviewStaged.isLoadingDetails;
  const error = hasTypeFilter
    ? filteredList.error
    : (overviewStaged.error instanceof Error ? overviewStaged.error.message : overviewStaged.error ? 'Error' : null);
  const load = hasTypeFilter ? filteredList.reload : overviewStaged.refetch;

  const filteredRuns = useMemo(() => {
    const term = search.trim().toLowerCase();
    return runs.filter((run) => {
      const matchesStatus = !statusFilter || run.status === statusFilter;
      const matchesSearch =
        !term
        || [run.pipeline_name, run.run_id, run.error_message, run.pipeline_type]
          .filter(Boolean)
          .some((v) => String(v).toLowerCase().includes(term));
      return matchesStatus && matchesSearch;
    });
  }, [runs, search, statusFilter]);

  const stats = useMemo(() => {
    const computed = computePipelineStats(runs);
    if (!hasTypeFilter && overviewStaged.data?.overview) {
      return {
        ...computed,
        failed24h: overviewStaged.data.overview.failed_pipelines_24h,
      };
    }
    return computed;
  }, [hasTypeFilter, overviewStaged.data?.overview, runs]);

  const resetFilters = useCallback(() => {
    setPipelineTypeFilter('');
    setStatusFilter('');
    setSearch('');
  }, []);

  return {
    error,
    filteredRuns,
    load,
    loading,
    loadingDetails,
    pipelineTypeFilter,
    resetFilters,
    runs,
    scope,
    search,
    setPipelineTypeFilter,
    setSearch,
    setStatusFilter,
    stats,
    statusFilter,
    total,
  };
}
