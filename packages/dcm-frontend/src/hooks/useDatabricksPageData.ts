import { useCallback, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getDatabricksFull,
  getDcmApiErrorMessage,
  isDcmDatabaseUnavailableError,
} from '../api/dcmApiClient';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { matchesWorkspaceScope } from '../lib/databricks-workspace-filter';
import { formatWorkspaceLabel } from '../lib/databricks/workspace-label';
import { useGlobalTimeRange } from '../contexts/time-range';
import type { ComputeState } from '../types/api';
import type { WorkloadAccordionRow } from '../components/domain/workload-accordion';
import {
  containsDatabricksSignal,
  DATABASE_UNAVAILABLE_MESSAGE,
  formatPipelineType,
  isDatabricksCompute,
  isDatabricksCost,
} from '../lib/databricks/databricks-utils';
import { isDatabricksPipeline } from '../lib/pipelines/pipeline-type';
import type { DatabricksComputeMetric, DatabricksFocusViewData } from '../lib/databricks/view-data';
import {
  getClusterCreator,
  getClusterHourlyCost,
  normalizeTags,
} from '../lib/databricks/view-data';
import { databricksQueryKeys } from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';

export interface UseDatabricksPageDataOptions {
  initialStateFilter?: ComputeState | '';
  initialJobStatusFilter?: string;
}

export function useDatabricksPageData(options: UseDatabricksPageDataOptions = {}) {
  const { scope, getScopedParams, databricksWorkspaceIds } = useMonitoringScope();
  const { getApiParams } = useGlobalTimeRange();
  const [stateFilter, setStateFilter] = useState<ComputeState | ''>(
    options.initialStateFilter ?? ''
  );
  const [jobStatusFilter, setJobStatusFilter] = useState(options.initialJobStatusFilter ?? '');
  const [search, setSearch] = useState('');
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(null);

  // The dashboard bundle mixes LZ-keyed curated tables (which filter on
  // `source_lz_id` directly) with workspace-keyed gold tables (which the backend
  // scopes by resolving the selected LZ to its workspaces). Declaring both the
  // workspace and the source-LZ support lets the header landing-zone filter
  // reach the backend. `useDatabricksBundleCache` must declare the very same
  // support to land on this query key.
  const scopedParams = getScopedParams({
    cloudProvider: true,
    subscriptionOrAccountId: true,
    workspaceId: true,
    sourceLzId: true,
  });
  const { start_date, end_date } = getApiParams();

  const queryParams = useMemo(
    () => ({
      start_date,
      end_date,
      cloud_provider: scopedParams.cloud_provider,
      subscription_or_account_id: scopedParams.subscription_or_account_id,
      workspace_id: scopedParams.workspace_id,
      workspace_ids: scopedParams.workspace_ids,
      source_lz_id: scopedParams.source_lz_id,
      source_lz_ids: scopedParams.source_lz_ids,
    }),
    [
      end_date,
      scopedParams.cloud_provider,
      scopedParams.subscription_or_account_id,
      scopedParams.workspace_id,
      scopedParams.workspace_ids,
      scopedParams.source_lz_id,
      scopedParams.source_lz_ids,
      start_date,
    ]
  );

  const bundleQuery = useQuery({
    queryKey: databricksQueryKeys.full(queryParams),
    queryFn: () => getDatabricksFull(queryParams),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
  });

  const clusters = useMemo(
    () => (bundleQuery.data?.computes.items ?? []) as DatabricksComputeMetric[],
    [bundleQuery.data?.computes.items]
  );
  const jobs = bundleQuery.data?.pipelines.items ?? [];
  const activities = bundleQuery.data?.activities.items ?? [];
  const costItems = (bundleQuery.data?.costs.items ?? []).filter(isDatabricksCost);
  const securityAlerts = bundleQuery.data?.alerts.items ?? [];
  const standardChecks = bundleQuery.data?.checks.items ?? [];
  const governanceScore = bundleQuery.data?.governance ?? null;

  const loading = bundleQuery.isLoading;
  const loadingDetails = bundleQuery.isFetching && !bundleQuery.isLoading;
  const notice = isDcmDatabaseUnavailableError(bundleQuery.error)
    ? DATABASE_UNAVAILABLE_MESSAGE
    : null;
  const error =
    bundleQuery.error && !notice
      ? getDcmApiErrorMessage(bundleQuery.error, 'Error while loading Databricks')
      : null;
  const load = useCallback(async () => {
    await bundleQuery.refetch();
  }, [bundleQuery]);

  const filteredClusters = useMemo(() => {
    const scopedParams = getScopedParams({ subscriptionOrAccountId: true });
    const effectiveSubscription = scopedParams.subscription_or_account_id || '';
    const term = search.trim().toLowerCase();
    return clusters.filter(isDatabricksCompute).filter((cluster) => {
      const matchesState = !stateFilter || cluster.state === stateFilter;
      const matchesWorkspace = matchesWorkspaceScope(cluster.workspace_id, databricksWorkspaceIds);
      const matchesSubscription =
        !effectiveSubscription || cluster.subscription_or_account_id === effectiveSubscription;
      const tags = normalizeTags(cluster.tags);
      const matchesSearch =
        !term ||
        [
          cluster.resource_name,
          cluster.compute_resource_id,
          cluster.source_lz_id,
          cluster.subscription_or_account_id,
          cluster.workspace_id,
          cluster.node_type,
          cluster.spark_version,
          cluster.compute_type,
          cluster.cloud_provider,
          cluster.state,
          getClusterCreator(cluster),
          ...Object.keys(tags),
          ...Object.values(tags).map(String),
        ]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(term));

      return matchesState && matchesWorkspace && matchesSubscription && matchesSearch;
    });
  }, [clusters, databricksWorkspaceIds, getScopedParams, search, stateFilter]);

  const selectedCluster = useMemo(
    () =>
      filteredClusters.find((cluster) => cluster.compute_resource_id === selectedClusterId) ??
      filteredClusters[0] ??
      null,
    [filteredClusters, selectedClusterId]
  );

  const selectedClusterTags = useMemo(
    () => (selectedCluster ? normalizeTags(selectedCluster.tags) : {}),
    [selectedCluster]
  );

  const databricksClusterIds = useMemo(
    () => new Set(filteredClusters.map((cluster) => cluster.compute_resource_id)),
    [filteredClusters]
  );

  const runningClusters = filteredClusters.filter((cluster) => cluster.state === 'running');
  const errorClusters = filteredClusters.filter((cluster) => cluster.state === 'error');

  const databricksActivities = activities.filter(
    (activity) =>
      activity.activity_type === 'databricks_notebook' ||
      containsDatabricksSignal(
        [
          activity.activity_name,
          activity.pipeline_name,
          activity.error_message,
          activity.source_lz_id,
          activity.subscription_or_account_id,
        ],
        databricksClusterIds
      )
  );

  const databricksPipelines = jobs.filter((job) => isDatabricksPipeline(job));

  const workloadRows: WorkloadAccordionRow[] = [
    ...databricksActivities.map((activity) => ({
      dataReadBytes: activity.data_read_bytes,
      dataWrittenBytes: activity.data_written_bytes,
      durationSeconds: activity.duration_seconds,
      endTime: activity.end_time,
      errorMessage: activity.error_message,
      id: `${activity.pipeline_run_id}:${activity.activity_name}`,
      name: activity.activity_name,
      parentName: activity.pipeline_name,
      rowsRead: activity.rows_read,
      rowsWritten: activity.rows_written,
      source: 'Activity' as const,
      sourceLzId: activity.source_lz_id,
      startTime: activity.start_time,
      status: activity.status,
      subscriptionOrAccountId: activity.subscription_or_account_id,
      type: activity.activity_type,
    })),
    ...databricksPipelines.map((job) => ({
      durationSeconds: job.duration_seconds,
      endTime: job.end_time,
      errorMessage: job.error_message,
      id: job.run_id,
      name: job.pipeline_name,
      parentName: job.pipeline_id,
      source: 'Pipeline' as const,
      sourceLzId: job.source_lz_id,
      startTime: job.start_time,
      status: job.status,
      subscriptionOrAccountId: null,
      type: formatPipelineType(job.pipeline_type),
    })),
  ].sort((a, b) => new Date(b.startTime ?? 0).getTime() - new Date(a.startTime ?? 0).getTime());

  const filteredWorkloadRows = workloadRows.filter((workload) => {
    const matchesStatus = !jobStatusFilter || workload.status === jobStatusFilter;
    const term = search.trim().toLowerCase();
    const matchesSearch =
      !term ||
      [
        workload.name,
        workload.id,
        workload.type,
        workload.status,
        workload.parentName,
        workload.errorMessage,
        workload.sourceLzId,
        workload.subscriptionOrAccountId,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(term));
    return matchesStatus && matchesSearch;
  });

  const failedJobs = workloadRows.filter((job) => job.status === 'failed');
  const runningJobs = workloadRows.filter((job) => job.status === 'running');

  const avgCpu =
    runningClusters.length === 0
      ? null
      : runningClusters.reduce((sum, cluster) => sum + (cluster.avg_cpu_utilization_pct ?? 0), 0) /
        runningClusters.length;

  const avgMem =
    runningClusters.length === 0
      ? null
      : runningClusters.reduce((sum, cluster) => sum + (cluster.avg_mem_utilization_pct ?? 0), 0) /
        runningClusters.length;

  const landingZones = new Set(
    filteredClusters.map((cluster) => cluster.source_lz_id).filter(Boolean)
  );
  const workspaces = new Set(
    filteredClusters.map((cluster) => cluster.workspace_id).filter(Boolean)
  );
  const databricksCostUsd = costItems.reduce((sum, item) => sum + item.total_cost_usd, 0);
  const estimatedHourlyCostUsd = filteredClusters.reduce(
    (sum, cluster) => sum + (getClusterHourlyCost(cluster) ?? 0),
    0
  );

  const databricksAlerts = securityAlerts.filter((alert) =>
    containsDatabricksSignal(
      [alert.title, alert.description, alert.resource_id, alert.resource_type, alert.source_lz_id],
      databricksClusterIds
    )
  );

  const databricksChecks = standardChecks.filter((check) =>
    containsDatabricksSignal(
      [
        check.check_name,
        check.resource_id,
        check.resource_name,
        check.resource_type,
        check.source_lz_id,
        check.check_effect,
      ],
      databricksClusterIds
    )
  );

  const nonCompliantChecks = databricksChecks.filter(
    (check) => check.check_state === 'no_compliant' || check.check_state === 'non_compliant'
  );

  const avgWorkloadDuration =
    workloadRows.length === 0
      ? null
      : workloadRows.reduce((sum, workload) => sum + (workload.durationSeconds ?? 0), 0) /
        workloadRows.length;

  const workspaceSummaries = Array.from(workspaces).map((workspaceId) => {
    const workspaceClusters = filteredClusters.filter(
      (cluster) => cluster.workspace_id === workspaceId
    );
    const workspaceSubscriptions = new Set(
      workspaceClusters.map((cluster) => cluster.subscription_or_account_id).filter(Boolean)
    );
    const workspaceCosts = costItems.filter(
      (item) =>
        item.subscription_or_account_id &&
        workspaceSubscriptions.has(item.subscription_or_account_id)
    );
    return {
      costUsd: workspaceCosts.reduce((sum, item) => sum + item.total_cost_usd, 0),
      id: workspaceId,
      name: formatWorkspaceLabel(workspaceId),
      running: workspaceClusters.filter((cluster) => cluster.state === 'running').length,
      total: workspaceClusters.length,
    };
  });

  const focusViewData = useMemo<DatabricksFocusViewData>(
    () => ({
      avgWorkloadDuration,
      costItems,
      databricksAlerts,
      databricksChecks,
      filteredClusters,
      filteredWorkloadRows,
      loading,
      onSelectCluster: setSelectedClusterId,
      selectedCluster,
      selectedClusterTags,
      workspaceSummaries,
    }),
    [
      avgWorkloadDuration,
      costItems,
      databricksAlerts,
      databricksChecks,
      filteredClusters,
      filteredWorkloadRows,
      loading,
      selectedCluster,
      selectedClusterTags,
      workspaceSummaries,
    ]
  );

  const resetFilters = useCallback(() => {
    setStateFilter('');
    setJobStatusFilter('');
    setSearch('');
  }, []);

  return {
    avgCpu,
    avgMem,
    clusters,
    databricksPipelines,
    databricksAlerts,
    databricksCostUsd,
    error,
    errorClusters,
    estimatedHourlyCostUsd,
    failedJobs,
    filteredClusters,
    filteredWorkloadRows,
    focusViewData,
    governanceScore,
    jobStatusFilter,
    landingZones,
    load,
    loading,
    loadingDetails,
    nonCompliantChecks,
    notice,
    resetFilters,
    runningClusters,
    runningJobs,
    scope,
    search,
    databricksWorkspaceIds,
    setJobStatusFilter,
    setSearch,
    setStateFilter,
    stateFilter,
    workloadRows,
    workspaces,
  };
}
