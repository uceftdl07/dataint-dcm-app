import { useQuery } from '@tanstack/react-query';
import { listUsers } from '../api/dcmApiClient';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';
import { usersQueryKeys, type UsersQueryParams } from './query-keys';

export function useUsersPageData(params: UsersQueryParams) {
  return useQuery({
    queryKey: usersQueryKeys.list(params),
    queryFn: () => listUsers(params),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
  });
}
