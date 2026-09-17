import { useCallback, useMemo, useState } from 'react';
import { listComputes } from '../api/dcmApiClient';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import type { ComputeMetric, ComputeState } from '../types/api';
import { useStagedListFetch } from './useStagedQueries';

export function useClustersPageData(options: { initialStateFilter?: ComputeState | '' } = {}) {
  const { scope, getScopedParams } = useMonitoringScope();
  const [stateFilter, setStateFilter] = useState<ComputeState | ''>(options.initialStateFilter ?? '');
  const [workspaceFilter, setWorkspaceFilter] = useState('');
  const [search, setSearch] = useState('');
  const scopedParams = getScopedParams({ cloudProvider: true });

  const {
    items: computes,
    loading,
    loadingDetails,
    error,
    reload: load,
  } = useStagedListFetch<ComputeMetric, { items: ComputeMetric[]; total: number }>(
    () => listComputes({
      cloud_provider: scopedParams.cloud_provider,
      workspace_id: workspaceFilter || undefined,
    }).then((response) => ({
      items: response.items ?? [],
      total: response.items?.length ?? 0,
    })),
    [scopedParams.cloud_provider, workspaceFilter],
  );

  const filteredComputes = useMemo(() => {
    const term = search.trim().toLowerCase();
    return computes.filter((c) => {
      const matchesState = !stateFilter || c.state === stateFilter;
      const matchesSearch =
        !term
        || [c.resource_name, c.compute_resource_id, c.workspace_id, c.node_type]
          .filter(Boolean)
          .some((v) => String(v).toLowerCase().includes(term));
      return matchesState && matchesSearch;
    });
  }, [computes, search, stateFilter]);

  const runningCount = computes.filter((c) => c.state === 'running').length;
  const errorCount = computes.filter((c) => c.state === 'error').length;
  const terminatedCount = computes.filter((c) => c.state === 'terminated').length;

  const resetFilters = useCallback(() => {
    setStateFilter('');
    setWorkspaceFilter('');
    setSearch('');
  }, []);

  return {
    computes,
    error,
    errorCount,
    filteredComputes,
    load,
    loading,
    loadingDetails,
    resetFilters,
    runningCount,
    scope,
    search,
    setSearch,
    setStateFilter,
    setWorkspaceFilter,
    stateFilter,
    terminatedCount,
    workspaceFilter,
  };
}
