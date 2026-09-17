import { useQuery } from '@tanstack/react-query';
import { getComputeRecommendationsSummary } from '../api/dcmApiClient';
import { computeRecommendationsQueryKeys } from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';
import { useComputeScopeParams } from './useComputeRecommendations';

/** Nav badge — open recommendations count for current scope. */
export function useComputeRecommendationsOpenCount() {
  const scopeParams = useComputeScopeParams();
  const query = useQuery({
    queryKey: computeRecommendationsQueryKeys.openCount(scopeParams),
    queryFn: () => getComputeRecommendationsSummary(scopeParams),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled: Boolean(scopeParams.period_start && scopeParams.period_end),
    select: (data) => data.open_count,
  });

  return {
    openCount: query.data ?? 0,
    loading: query.isLoading,
  };
}
