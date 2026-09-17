import { useQuery } from '@tanstack/react-query';
import { getDashboardFull } from '../api/dcmApiClient';
import type {
  ComputeMetric,
  CostSummary,
  DashboardOverview,
  DatabaseMetric,
  GovernanceScore,
  PipelineRun,
  SecurityAlert,
} from '../types/api';
import { filterBySelectedWorkspaceIds } from '../lib/databricks-workspace-filter';
import { dashboardQueryKeys, type DashboardQueryParams } from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';

export interface DashboardData {
  overview: DashboardOverview;
  governance: GovernanceScore;
  costs: CostSummary;
  pipelines: PipelineRun[];
  computes: ComputeMetric[];
  databases: DatabaseMetric[];
  alerts: SecurityAlert[];
}

function buildLzParams(params: DashboardQueryParams) {
  const { source_lz_id, source_lz_ids } = params;
  if (source_lz_ids?.length) {
    return { source_lz_ids };
  }
  if (source_lz_id) {
    return { source_lz_id };
  }
  return {};
}

function buildWorkspaceParams(params: DashboardQueryParams) {
  const { workspace_id, workspace_ids } = params;
  if (workspace_ids !== undefined) {
    return { workspace_ids };
  }
  if (workspace_id) {
    return { workspace_id };
  }
  return {};
}

function getSelectedWorkspaceIds(params: DashboardQueryParams): string[] | null {
  if (params.workspace_ids !== undefined) {
    return params.workspace_ids;
  }
  if (params.workspace_id) {
    return [params.workspace_id];
  }
  return null;
}

function filterCosts(
  costs: CostSummary,
  overview: DashboardOverview,
  selectedLzIds: string[] | null | undefined,
): CostSummary {
  if (selectedLzIds === null || selectedLzIds === undefined) {
    return costs;
  }

  return {
    ...costs,
    total_usd: overview.total_cost_usd,
  };
}

function mergeDashboardData(
  bundle: {
    overview: DashboardOverview;
    governance: GovernanceScore;
    costs: CostSummary;
    pipelines: PipelineRun[];
    computes: ComputeMetric[];
    databases: DatabaseMetric[];
    alerts: SecurityAlert[];
  },
  selectedLzIds: string[] | null | undefined,
  selectedWorkspaceIds: string[] | null,
): DashboardData {
  const computes = filterBySelectedWorkspaceIds(bundle.computes, selectedWorkspaceIds);
  const activeClusters = selectedWorkspaceIds === null
    ? bundle.overview.active_clusters
    : computes.filter((compute) => compute.state === 'running').length;

  return {
    overview: {
      ...bundle.overview,
      active_clusters: activeClusters,
    },
    governance: bundle.governance,
    costs: filterCosts(bundle.costs, bundle.overview, selectedLzIds),
    pipelines: bundle.pipelines,
    computes,
    databases: bundle.databases,
    alerts: bundle.alerts,
  };
}

async function fetchDashboardData(params: DashboardQueryParams): Promise<DashboardData> {
  const { start_date, end_date, cloud_provider } = params;
  const lzParams = buildLzParams(params);
  const workspaceParams = buildWorkspaceParams(params);
  const selectedLzIds = params.source_lz_ids ?? (params.source_lz_id ? [params.source_lz_id] : null);
  const selectedWorkspaceIds = getSelectedWorkspaceIds(params);

  const bundle = await getDashboardFull({
    start_date,
    end_date,
    cloud_provider,
    ...lzParams,
    ...workspaceParams,
  });

  return mergeDashboardData(bundle, selectedLzIds, selectedWorkspaceIds);
}

export function useDashboardQueries(params: DashboardQueryParams) {
  const query = useQuery({
    queryKey: dashboardQueryKeys.data(params),
    queryFn: () => fetchDashboardData(params),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
  });

  return {
    data: query.data ?? null,
    isLoading: query.isLoading,
    isLoadingDetails: false,
    error: query.error,
    isFetching: query.isFetching,
    refetch: query.refetch,
  };
}
