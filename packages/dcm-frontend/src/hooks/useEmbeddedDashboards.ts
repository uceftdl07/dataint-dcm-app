import { useQuery } from '@tanstack/react-query';
import { getEmbeddedDashboard, listEmbeddedDashboards } from '../api/dcmApiClient';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';
import { embeddedDashboardsQueryKeys } from './query-keys';

export function useEmbeddedDashboards(menuGroup = 'insights') {
  return useQuery({
    queryKey: embeddedDashboardsQueryKeys.list(menuGroup),
    queryFn: () => listEmbeddedDashboards(menuGroup),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
  });
}

export function useEmbeddedDashboard(slug: string | undefined) {
  return useQuery({
    queryKey: embeddedDashboardsQueryKeys.detail(slug ?? ''),
    queryFn: () => getEmbeddedDashboard(slug!),
    enabled: Boolean(slug),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
  });
}
