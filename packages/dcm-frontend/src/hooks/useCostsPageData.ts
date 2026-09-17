import { useMemo } from 'react';
import { getCostSummary, getCostsByService } from '../api/dcmApiClient';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { useGlobalTimeRange } from '../contexts/time-range';
import type { CostSummary, ServiceCostDetail } from '../types/api';
import { useStagedQueries } from './useStagedQueries';

export function useCostsPageData() {
  const { getApiParams, getDisplayRange } = useGlobalTimeRange();
  const { scope, getScopedParams } = useMonitoringScope();
  const { start_date, end_date } = getApiParams();
  const scopedParams = getScopedParams({ cloudProvider: true, sourceLzId: true });
  const params = useMemo(() => ({
    start_date,
    end_date,
    cloud_provider: scopedParams.cloud_provider,
    source_lz_id: scopedParams.source_lz_id,
  }), [end_date, scopedParams.cloud_provider, scopedParams.source_lz_id, start_date]);

  const staged = useStagedQueries({
    queryKey: ['costs-page', params],
    fetchPrimary: () => getCostSummary(params),
    fetchDetails: async () => {
      const response = await getCostsByService(params);
      return response.items ?? [];
    },
    emptyDetails: () => [],
    merge: (summary, byService) => ({ summary, byService }),
  });

  const summary = staged.data?.summary ?? null;
  const byService = staged.data?.byService ?? [];
  const display = getDisplayRange();
  const cloudCount = summary ? Object.keys(summary.by_cloud).length : 0;
  const error = staged.error instanceof Error ? staged.error.message : staged.error ? 'Error' : null;

  return {
    byService,
    cloudCount,
    display,
    error,
    load: staged.refetch,
    loading: staged.isLoading,
    loadingDetails: staged.isLoadingDetails,
    scope,
    summary,
  };
}
