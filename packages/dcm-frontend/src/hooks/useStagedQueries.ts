import { useQuery, type QueryKey } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';

export interface StagedQueriesResult<TMerged> {
  data: TMerged | null;
  isLoading: boolean;
  isLoadingDetails: boolean;
  error: unknown;
  isFetching: boolean;
  refetch: () => Promise<void>;
}

export function useStagedQueries<TPrimary, TDetails, TMerged>({
  queryKey,
  fetchPrimary,
  fetchDetails,
  merge,
  emptyDetails,
  enabled = true,
}: {
  queryKey: QueryKey;
  fetchPrimary: () => Promise<TPrimary>;
  fetchDetails: () => Promise<TDetails>;
  merge: (primary: TPrimary, details: TDetails) => TMerged;
  emptyDetails: (primary: TPrimary) => TDetails;
  enabled?: boolean;
}): StagedQueriesResult<TMerged> {
  const primaryQuery = useQuery({
    queryKey: [...queryKey, 'primary'],
    queryFn: fetchPrimary,
    enabled,
  });

  const detailsQuery = useQuery({
    queryKey: [...queryKey, 'details'],
    queryFn: fetchDetails,
    enabled: enabled && primaryQuery.isSuccess,
  });

  const data = primaryQuery.data
    ? merge(primaryQuery.data, detailsQuery.data ?? emptyDetails(primaryQuery.data))
    : null;

  return {
    data,
    isLoading: primaryQuery.isLoading,
    isLoadingDetails: primaryQuery.isSuccess && detailsQuery.isLoading,
    error: primaryQuery.error ?? detailsQuery.error,
    isFetching: primaryQuery.isFetching || detailsQuery.isFetching,
    refetch: async () => {
      await Promise.all([primaryQuery.refetch(), detailsQuery.refetch()]);
    },
  };
}

export interface StagedListFetchState<TItem> {
  items: TItem[];
  total: number;
  loading: boolean;
  loadingDetails: boolean;
  error: string | null;
  reload: () => void;
}

const PRIMARY_LIST_LIMIT = 32;
const DETAILS_LIST_LIMIT = 200;

export function useStagedListFetch<TItem, TResponse extends { items: TItem[]; total: number }>(
  fetchPage: (limit: number) => Promise<TResponse>,
  deps: unknown[],
  options: { enabled?: boolean } = {},
): StagedListFetchState<TItem> {
  const enabled = options.enabled ?? true;
  const [items, setItems] = useState<TItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const reload = useCallback(() => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    setLoadingDetails(false);
    setError(null);

    fetchPage(PRIMARY_LIST_LIMIT)
      .then((response) => {
        if (requestIdRef.current !== requestId) return;
        setItems(response.items ?? []);
        setTotal(response.total);
        setLoading(false);
        setLoadingDetails(true);
        return fetchPage(DETAILS_LIST_LIMIT);
      })
      .then((response) => {
        if (!response || requestIdRef.current !== requestId) return;
        setItems(response.items ?? []);
        setTotal(response.total);
      })
      .catch((err: unknown) => {
        if (requestIdRef.current !== requestId) return;
        setError(err instanceof Error ? err.message : 'Error');
        setItems([]);
        setTotal(0);
      })
      .finally(() => {
        if (requestIdRef.current !== requestId) return;
        setLoading(false);
        setLoadingDetails(false);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps -- caller controls invalidation via deps
  }, deps);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      setLoadingDetails(false);
      return;
    }
    reload();
  }, [enabled, reload]);

  return { items, total, loading, loadingDetails, error, reload };
}
