import { useQuery } from '@tanstack/react-query';
import { getAlertsPageBundle } from '../api/dcmApiClient';
import type { SecurityAlert } from '../types/api';
import { alertsQueryKeys, type AlertsPageQueryParams } from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';
import { useDatabricksBundleCache } from './useDatabricksBundleCache';

export function useAlertsPageQueries(params: AlertsPageQueryParams) {
  const bundleCache = useDatabricksBundleCache();
  const placeholderData = bundleCache
    ? { items: bundleCache.alerts.items as SecurityAlert[], total: bundleCache.alerts.items.length }
    : undefined;

  const query = useQuery({
    queryKey: alertsQueryKeys.pageBundle(params),
    queryFn: () => getAlertsPageBundle(params),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    placeholderData,
  });

  return {
    items: query.data?.items ?? [],
    total: query.data?.total ?? 0,
    loading: query.isLoading,
    loadingDetails: query.isFetching && !query.isLoading,
    error: query.error,
    reload: query.refetch,
  };
}
