import { useQuery } from '@tanstack/react-query';
import { getFinOpsPageBundle } from '../api/dcmApiClient';
import type { CostSummary, CostsByServiceResponse } from '../types/api';
import { finopsQueryKeys, type FinOpsPageQueryParams } from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';
import { useDatabricksBundleCache } from './useDatabricksBundleCache';

function buildFinOpsPlaceholder(bundleCache: NonNullable<ReturnType<typeof useDatabricksBundleCache>>) {
  const items = bundleCache.costs.items;
  const totalUsd = items.reduce((sum, item) => sum + item.total_cost_usd, 0);
  const byCloud = items.reduce<Record<string, number>>((acc, item) => {
    acc[item.cloud_provider] = (acc[item.cloud_provider] ?? 0) + item.total_cost_usd;
    return acc;
  }, {});

  const summary: CostSummary = {
    total_usd: Math.round(totalUsd * 100) / 100,
    by_cloud: Object.fromEntries(
      Object.entries(byCloud).map(([provider, total]) => [provider, Math.round(total * 100) / 100]),
    ),
    by_service: items.slice(0, 10).map((item) => ({
      service_name: item.service_name,
      cloud_provider: item.cloud_provider,
      cost_usd: item.total_cost_usd,
    })),
    period: bundleCache.period,
  };

  const byService: CostsByServiceResponse = { items };
  return { summary, byService };
}

export function useFinOpsPageQueries(params: FinOpsPageQueryParams) {
  const bundleCache = useDatabricksBundleCache();
  const placeholderData = bundleCache ? buildFinOpsPlaceholder(bundleCache) : undefined;

  const query = useQuery({
    queryKey: finopsQueryKeys.pageBundle(params),
    queryFn: () => getFinOpsPageBundle(params),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    placeholderData,
  });

  return {
    summary: query.data?.summary ?? null,
    byService: query.data?.byService ?? { items: [] },
    loading: query.isLoading,
    loadingDetails: query.isFetching && !query.isLoading,
    error: query.error,
    reload: query.refetch,
  };
}
