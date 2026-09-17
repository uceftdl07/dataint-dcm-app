import { useQuery } from '@tanstack/react-query';
import { listDatabricksWorkspaces } from '../api/dcmApiClient';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';
import { databricksWorkspacesQueryKeys } from './query-keys';

export function useDatabricksWorkspacesList(enabled = true) {
  return useQuery({
    queryKey: databricksWorkspacesQueryKeys.list(),
    queryFn: () => listDatabricksWorkspaces(),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled,
  });
}
