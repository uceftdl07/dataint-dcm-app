import { useQuery } from '@tanstack/react-query';
import { getCurrentDcmUser, getDcmApiErrorMessage } from '../api/dcmApiClient';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';
import { currentUserQueryKeys } from './query-keys';

export function useCurrentDcmUser() {
  const query = useQuery({
    queryKey: currentUserQueryKeys.me(),
    queryFn: getCurrentDcmUser,
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    retry: 1,
  });

  return {
    user: query.data ?? null,
    loading: query.isLoading,
    error: query.error ? getDcmApiErrorMessage(query.error, 'Unable to load current DCM user.') : null,
    reload: () => {
      void query.refetch();
    },
  };
}
