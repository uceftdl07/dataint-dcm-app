import { useQuery } from '@tanstack/react-query';
import { listLandingZones } from '../api/dcmApiClient';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';
import { landingZonesQueryKeys } from './query-keys';

export function useLandingZonesList(enabled = true) {
  return useQuery({
    queryKey: landingZonesQueryKeys.list(),
    queryFn: async () => {
      const response = await listLandingZones();
      const byId = new Map<string, (typeof response.items)[number]>();
      for (const landingZone of response.items) {
        if (!byId.has(landingZone.lz_id)) {
          byId.set(landingZone.lz_id, landingZone);
        }
      }
      const items = [...byId.values()].sort((a, b) => {
        const nameA = (a.lz_name || a.lz_id).toLowerCase();
        const nameB = (b.lz_name || b.lz_id).toLowerCase();
        return nameA.localeCompare(nameB);
      });
      return { ...response, items, total: items.length };
    },
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled,
  });
}
