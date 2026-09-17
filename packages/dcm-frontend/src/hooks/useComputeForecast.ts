import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getComputeForecast, type ComputeForecastParams } from '../api/dcmApiClient';
import type { ComputeForecastMetricName } from '../types/api';
import { computeRecommendationsQueryKeys } from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';
import { useComputeScopeParams } from './useComputeRecommendations';

export function useComputeForecastData(options?: {
  metric_name?: ComputeForecastMetricName;
  object_type?: string;
  object_id?: string;
  enabled?: boolean;
}) {
  const scopeParams = useComputeScopeParams();
  const params = useMemo(
    () =>
      ({
        ...scopeParams,
        metric_name: options?.metric_name,
        object_type: options?.object_type || undefined,
        object_id: options?.object_id || undefined,
      }) satisfies ComputeForecastParams,
    [scopeParams, options?.metric_name, options?.object_type, options?.object_id]
  );

  const query = useQuery({
    queryKey: computeRecommendationsQueryKeys.forecast(params),
    queryFn: () => getComputeForecast(params),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled:
      (options?.enabled ?? true) && Boolean(scopeParams.period_start && scopeParams.period_end),
    placeholderData: (previous) => previous,
  });

  return {
    params,
    data: query.data ?? null,
    loading: query.isLoading,
    fetching: query.isFetching,
    error: query.error,
    refetch: query.refetch,
  };
}
