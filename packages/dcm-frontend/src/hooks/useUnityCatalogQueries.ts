import { useQuery } from '@tanstack/react-query';
import {
  getUnityCatalogExplorerFull,
  getUnityCatalogTableMetadata,
  getUnityCatalogTablePreview,
} from '../api/dcmApiClient';
import type { UnityCatalogPagination, UnityCatalogTableMetadata } from '../types/api';
import type { UnityCatalogNavigationParams, UnityCatalogTableDetailsParams } from './query-keys';
import { unityCatalogQueryKeys } from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';

export function useUnityCatalogNavigation(params: UnityCatalogNavigationParams) {
  return useQuery({
    queryKey: unityCatalogQueryKeys.navigation(params),
    queryFn: () => getUnityCatalogExplorerFull(params),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled: Boolean(params.catalogName),
  });
}

export function useUnityCatalogTableDetails(
  params: UnityCatalogTableDetailsParams,
  enabled = true,
) {
  const metadataQuery = useQuery({
    queryKey: unityCatalogQueryKeys.tableMetadata(params),
    queryFn: () =>
      getUnityCatalogTableMetadata(params.catalogName, params.schemaName, params.tableName),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled: enabled && Boolean(params.catalogName && params.schemaName && params.tableName),
  });

  const previewQuery = useQuery({
    queryKey: unityCatalogQueryKeys.tablePreview(params),
    queryFn: () =>
      getUnityCatalogTablePreview(
        params.catalogName,
        params.schemaName,
        params.tableName,
        params.limit ?? 100,
        params.offset ?? 0,
        params.orderBy,
        false,
      ),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled: enabled && Boolean(params.catalogName && params.schemaName && params.tableName),
  });

  const metadata: UnityCatalogTableMetadata | null =
    metadataQuery.data?.Table ?? metadataQuery.data?.table ?? null;
  const preview = previewQuery.data?.Table ?? previewQuery.data?.table ?? null;
  const pagination: UnityCatalogPagination | null =
    previewQuery.data?.Pagination ?? previewQuery.data?.pagination ?? null;

  return {
    metadata,
    preview,
    pagination,
    isLoadingDetails: metadataQuery.isLoading || previewQuery.isLoading,
    isFetchingDetails: metadataQuery.isFetching || previewQuery.isFetching,
    error: metadataQuery.error ?? previewQuery.error,
    refetchDetails: async () => {
      await Promise.all([metadataQuery.refetch(), previewQuery.refetch()]);
    },
  };
}
