import { useQuery } from '@tanstack/react-query';
import { getMonitoringReportsFull } from '../api/dcmApiClient';
import {
  normalizeMonitoringReportItems,
  type MonitoringReportItem,
} from '../lib/domain/monitoring-report';
import type {
  ComputeMetric,
  DataProductUsageTrend,
  PipelineRun,
} from '../types/api';
import { monitoringReportsQueryKeys, type MonitoringReportsQueryParams } from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';

export interface MonitoringReportsData {
  items: MonitoringReportItem[];
  usageTrends: DataProductUsageTrend[];
  computes: ComputeMetric[];
  pipelines: PipelineRun[];
  apiCostTotalUsd: number | null;
}

const LIST_LIMIT = 200;

function buildLzParams(params: MonitoringReportsQueryParams) {
  const { source_lz_id, source_lz_ids } = params;
  if (source_lz_ids?.length) {
    return { source_lz_ids };
  }
  if (source_lz_id) {
    return { source_lz_id };
  }
  return {};
}

async function fetchMonitoringReportsData(
  params: MonitoringReportsQueryParams,
): Promise<MonitoringReportsData> {
  const bundle = await getMonitoringReportsFull({
    start_date: params.start_date,
    end_date: params.end_date,
    cloud_provider: params.cloud_provider,
    subscription_or_account_id: params.subscription_or_account_id,
    usage_limit: LIST_LIMIT,
    list_limit: LIST_LIMIT,
    trend_grain: 'day',
    ...buildLzParams(params),
  });

  return {
    usageTrends: bundle.usage_trends.items,
    computes: bundle.computes.items,
    pipelines: bundle.pipelines.items,
    apiCostTotalUsd: bundle.cost_summary.total_usd,
    items: normalizeMonitoringReportItems({
      usageRows: bundle.data_product_usage.items,
      landingZones: bundle.landing_zones.items,
      standardChecks: bundle.standard_checks.items,
      securityAlerts: bundle.security_alerts.items,
      computes: bundle.computes.items,
      costsByService: bundle.costs_by_service.items,
      governanceScore: bundle.governance,
    }),
  };
}

export function useMonitoringReportsQueries(params: MonitoringReportsQueryParams) {
  const query = useQuery({
    queryKey: monitoringReportsQueryKeys.data(params),
    queryFn: () => fetchMonitoringReportsData(params),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
  });

  return {
    data: query.data ?? null,
    isLoading: query.isLoading,
    error: query.error,
    isFetching: query.isFetching,
    refetch: query.refetch,
  };
}
