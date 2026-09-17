import { useQuery } from '@tanstack/react-query';
import { listLandingZonesAccessOverview } from '../api/dcmApiClient';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';
import { landingZonesQueryKeys } from './query-keys';

export function useLandingZonesAccessOverview() {
  return useQuery({
    queryKey: landingZonesQueryKeys.accessOverview(),
    // Wrap: TanStack Query passes QueryFunctionContext as 1st arg; do not forward to apiFetch params.
    queryFn: () => listLandingZonesAccessOverview(),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
  });
}
