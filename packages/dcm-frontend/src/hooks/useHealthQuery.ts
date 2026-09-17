import { useQuery } from '@tanstack/react-query';
import { getDcmApiErrorMessage, getHealth } from '../api/dcmApiClient';
import type { HealthResponse } from '../types/api';
import { HEALTH_POLL_MS, QUERY_GC_DEFAULT_MS, QUERY_STALE_HEALTH_MS } from './query-config';
import { healthQueryKeys } from './query-keys';

export interface UseHealthQueryOptions {
  /** Poll interval; defaults to no polling. Collection Status uses `HEALTH_POLL_MS`. */
  pollIntervalMs?: number | false;
  /** When true, failed requests expose a degraded health payload (Collection Status UX). */
  fallbackOnError?: boolean;
}

const FALLBACK_HEALTH: HealthResponse = {
  status: 'degraded',
  database: 'unreachable',
  timestamp: new Date().toISOString(),
  service: 'dcm-backend',
};

export function useHealthQuery(options: UseHealthQueryOptions = {}) {
  const { pollIntervalMs = false, fallbackOnError = false } = options;

  const query = useQuery({
    queryKey: healthQueryKeys.status(),
    queryFn: getHealth,
    staleTime: QUERY_STALE_HEALTH_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    refetchInterval: pollIntervalMs === false ? undefined : pollIntervalMs,
    retry: fallbackOnError ? 0 : 1,
  });

  const lastChecked = query.dataUpdatedAt > 0 ? new Date(query.dataUpdatedAt) : null;

  const health =
    query.data ??
    (fallbackOnError && query.isError
      ? {
          ...FALLBACK_HEALTH,
          timestamp: lastChecked?.toISOString() ?? new Date().toISOString(),
        }
      : null);

  const error = query.error
    ? getDcmApiErrorMessage(
        query.error,
        fallbackOnError ? 'Healthcheck indisponible' : 'Healthcheck error',
      )
    : null;

  return {
    health,
    loading: query.isLoading,
    isFetching: query.isFetching,
    error,
    lastChecked,
    refetch: query.refetch,
  };
}

export { HEALTH_POLL_MS };
