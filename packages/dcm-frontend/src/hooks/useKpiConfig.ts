import { useQuery } from '@tanstack/react-query';
import { useCallback, useMemo } from 'react';
import { getDcmApiErrorMessage, getKpiConfig } from '../api/dcmApiClient';
import type { MetricTone } from '../components/domain/metric-card';
import type { KpiConfigItem } from '../types/api';
import { QUERY_STALE_DEFAULT_MS } from './query-config';
import { kpiQueryKeys } from './query-keys';

interface ThresholdToneOptions {
  inverted?: boolean;
  defaultTone?: MetricTone;
}

export interface KpiConfigState {
  items: KpiConfigItem[];
  values: Record<string, number>;
  loading: boolean;
  error: string | null;
  reload: () => void;
  getThresholdTone: (
    value: number | null | undefined,
    warningKey: string,
    criticalKey: string,
    options?: ThresholdToneOptions,
  ) => MetricTone;
}

export function getKpiThresholdTone(
  values: Record<string, number>,
  value: number | null | undefined,
  warningKey: string,
  criticalKey: string,
  options: ThresholdToneOptions = {},
): MetricTone {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return options.defaultTone ?? 'default';
  }

  const warning = values[warningKey];
  const critical = values[criticalKey];
  if (warning === undefined || critical === undefined) {
    return options.defaultTone ?? 'default';
  }

  if (options.inverted) {
    if (value <= critical) return 'danger';
    if (value <= warning) return 'warning';
    return 'success';
  }

  if (value >= critical) return 'danger';
  if (value >= warning) return 'warning';
  return 'success';
}

export function useKpiConfig(): KpiConfigState {
  const query = useQuery({
    queryKey: kpiQueryKeys.config(),
    queryFn: getKpiConfig,
    staleTime: QUERY_STALE_DEFAULT_MS,
  });

  const values = query.data?.values ?? {};
  const items = query.data?.items ?? [];

  const getThresholdTone = useCallback<KpiConfigState['getThresholdTone']>(
    (value, warningKey, criticalKey, options) =>
      getKpiThresholdTone(values, value, warningKey, criticalKey, options),
    [values],
  );

  return useMemo(() => ({
    items,
    values,
    loading: query.isLoading,
    error: query.error ? getDcmApiErrorMessage(query.error, 'Unable to load KPI configuration.') : null,
    reload: () => {
      void query.refetch();
    },
    getThresholdTone,
  }), [getThresholdTone, items, query.error, query.isLoading, query.refetch, values]);
}
