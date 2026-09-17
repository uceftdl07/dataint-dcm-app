import { useCallback, useMemo, useState } from 'react';
import {
  getDataProductUsageOverview,
  getDataProductUsageTrends,
  getTopDataProductConsumers,
  listDataProductUsage,
} from '../api/dcmApiClient';
import type { DataProductTopMetric } from '../lib/data-product-usage/focus-view';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { getApiLzParams } from '../lib/monitoring-scope-filter';
import { useGlobalTimeRange } from '../contexts/time-range';
import type {
  DataProductConsumerUsage,
  DataProductUsage as DataProductUsageRow,
  DataProductUsageOverview,
  DataProductUsageTrend,
} from '../types/api';
import { useStagedQueries } from './useStagedQueries';

const LIMIT = 50;
type Grain = 'day' | 'week' | 'month';

export interface UseDataProductUsagePageDataOptions {
  initialProductFilter?: string;
  initialConsumerFilter?: string;
  initialTopMetric?: DataProductTopMetric;
}

export function useDataProductUsagePageData(options: UseDataProductUsagePageDataOptions = {}) {
  const { getApiParams } = useGlobalTimeRange();
  const { scope, getScopedParams } = useMonitoringScope();
  const [offset, setOffset] = useState(0);
  const [dataProductFilter, setDataProductFilter] = useState(options.initialProductFilter ?? '');
  const [consumerFilter, setConsumerFilter] = useState(options.initialConsumerFilter ?? '');
  const [grain, setGrain] = useState<Grain>('day');
  const [topMetric, setTopMetric] = useState<DataProductTopMetric>(options.initialTopMetric ?? 'data_read_bytes');

  const { start_date, end_date } = getApiParams();
  const scopedParams = getScopedParams({ cloudProvider: true, subscriptionOrAccountId: true, sourceLzId: true });
  const baseParams = useMemo(() => ({
    start_date,
    end_date,
    cloud_provider: scopedParams.cloud_provider,
    subscription_or_account_id: scopedParams.subscription_or_account_id,
    ...getApiLzParams(scope),
    data_product_id: dataProductFilter || undefined,
    consumer_id: consumerFilter || undefined,
  }), [
    consumerFilter,
    dataProductFilter,
    end_date,
    scopedParams.cloud_provider,
    scopedParams.subscription_or_account_id,
    scope,
    start_date,
  ]);

  const staged = useStagedQueries({
    queryKey: ['data-product-usage-page', baseParams, grain, topMetric, offset],
    fetchPrimary: async () => {
      const [overview, trends, topConsumers] = await Promise.all([
        getDataProductUsageOverview(baseParams),
        getDataProductUsageTrends({ ...baseParams, grain }),
        getTopDataProductConsumers({ ...baseParams, metric: topMetric, limit: 50 }),
      ]);
      return { overview, trends: trends.items, topConsumers: topConsumers.items };
    },
    fetchDetails: async () => {
      const listResponse = await listDataProductUsage({ ...baseParams, limit: LIMIT, offset });
      return { rows: listResponse.items, total: listResponse.total };
    },
    emptyDetails: () => ({ rows: [], total: 0 }),
    merge: (primary, details) => ({
      overview: primary.overview,
      trends: primary.trends,
      topConsumers: primary.topConsumers,
      rows: details.rows,
      total: details.total,
    }),
  });

  const load = useCallback((newOffset = 0) => {
    setOffset(newOffset);
    void staged.refetch();
  }, [staged]);

  const resetFilters = useCallback(() => {
    setDataProductFilter('');
    setConsumerFilter('');
  }, []);

  const overview = staged.data?.overview ?? null;
  const trends = staged.data?.trends ?? [];
  const topConsumers = staged.data?.topConsumers ?? [];
  const rows = staged.data?.rows ?? [];
  const total = staged.data?.total ?? 0;
  const error = staged.error instanceof Error ? staged.error.message : staged.error ? 'Error' : null;
  const canPrev = offset > 0;
  const canNext = offset + LIMIT < total;

  return {
    canNext,
    canPrev,
    consumerFilter,
    dataProductFilter,
    error,
    grain,
    load,
    loading: staged.isLoading,
    loadingDetails: staged.isLoadingDetails,
    offset,
    overview,
    resetFilters,
    rows,
    scope,
    setConsumerFilter,
    setDataProductFilter,
    setGrain,
    setTopMetric,
    topConsumers,
    topMetric,
    total,
    trends,
  };
}
