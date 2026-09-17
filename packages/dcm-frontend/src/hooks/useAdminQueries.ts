import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { getAdminFull, type AdminFullResponse } from '../api/dcmApiClient';
import { QUERY_GC_ADMIN_MS, QUERY_STALE_ADMIN_MS } from './query-config';
import { adminQueryKeys, type AdminQueryParams } from './query-keys';

const emptyAdminBundle: AdminFullResponse = {
  users: { items: [], total: 0, limit: 0, offset: 0 },
  landingZones: { items: [], total: 0 },
  alertRules: { items: [], total: 0 },
  collectors: { items: [], total: 0 },
  channels: { items: [], total: 0 },
  accessRequests: { items: [], total: 0, pending_total: 0, limit: 0, offset: 0 },
  kpiConfig: { items: [], values: {} },
  retentionPolicies: { items: [], values: {} },
  retentionStats: { items: [], total: 0 },
  maintenanceWindows: { items: [], total: 0 },
  auditLog: { items: [], total: 0, limit: 0, offset: 0 },
};

function mergeAdminBundles(
  core: Partial<AdminFullResponse> | undefined,
  extended: Partial<AdminFullResponse> | undefined,
): AdminFullResponse {
  return {
    ...emptyAdminBundle,
    ...core,
    ...extended,
  };
}

function adminFetchParams(params: AdminQueryParams) {
  return {
    accessRequestStatus: params.accessRequestStatus,
    accessRequestLimit: params.accessRequestPageSize,
    accessRequestOffset: (params.accessRequestPage - 1) * params.accessRequestPageSize,
    auditLimit: params.auditLimit,
    auditOffset: params.auditOffset,
  };
}

export function useAdminQueries(params: AdminQueryParams) {
  const fetchParams = adminFetchParams(params);

  const coreQuery = useQuery({
    queryKey: [...adminQueryKeys.full(params), 'core'] as const,
    queryFn: () => getAdminFull({ ...fetchParams, sections: 'core' }),
    staleTime: QUERY_STALE_ADMIN_MS,
    gcTime: QUERY_GC_ADMIN_MS,
  });

  const extendedQuery = useQuery({
    queryKey: [...adminQueryKeys.full(params), 'extended'] as const,
    queryFn: () => getAdminFull({ ...fetchParams, sections: 'extended' }),
    staleTime: QUERY_STALE_ADMIN_MS,
    gcTime: QUERY_GC_ADMIN_MS,
    enabled: coreQuery.isSuccess,
  });

  const data = useMemo(
    () => mergeAdminBundles(coreQuery.data, extendedQuery.data),
    [coreQuery.data, extendedQuery.data],
  );

  return {
    data,
    isLoading: coreQuery.isLoading,
    isFetching: coreQuery.isFetching || extendedQuery.isFetching,
    error: coreQuery.error ?? extendedQuery.error ?? null,
    refetch: async () => {
      await Promise.all([coreQuery.refetch(), extendedQuery.refetch()]);
    },
  };
}
