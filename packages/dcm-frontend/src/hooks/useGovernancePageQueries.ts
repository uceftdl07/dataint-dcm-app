import { useQuery } from '@tanstack/react-query';
import { getGovernancePageBundle } from '../api/dcmApiClient';
import type { GovernanceScore, StandardCheck } from '../types/api';
import { governanceQueryKeys, type GovernancePageQueryParams } from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';
import { useDatabricksBundleCache } from './useDatabricksBundleCache';

export interface GovernancePageData {
  score: GovernanceScore | null;
  checks: StandardCheck[];
  totalChecks: number;
}

export function useGovernancePageQueries(params: GovernancePageQueryParams) {
  const bundleCache = useDatabricksBundleCache();
  const placeholderData = bundleCache
    ? {
        score: bundleCache.governance,
        checks: bundleCache.checks.items as StandardCheck[],
        totalChecks: bundleCache.checks.items.length,
      }
    : undefined;

  const query = useQuery({
    queryKey: governanceQueryKeys.pageBundle(params),
    queryFn: () => getGovernancePageBundle(params),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    placeholderData,
  });

  return {
    score: query.data?.score ?? null,
    checks: query.data?.checks ?? [],
    totalChecks: query.data?.totalChecks ?? 0,
    loading: query.isLoading,
    loadingDetails: query.isFetching && !query.isLoading,
    error: query.error,
    reload: query.refetch,
  };
}
