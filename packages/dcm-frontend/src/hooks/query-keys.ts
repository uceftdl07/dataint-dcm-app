import type { CloudProvider, ComputeMetricTrendGranularity } from '../types/api';

export interface DashboardQueryParams {
  start_date: string;
  end_date: string;
  cloud_provider?: CloudProvider;
  source_lz_id?: string;
  source_lz_ids?: string[] | null;
  workspace_id?: string;
  workspace_ids?: string[];
}

function normalizeDashboardParams(params: DashboardQueryParams) {
  return {
    start_date: params.start_date,
    end_date: params.end_date,
    cloud_provider: params.cloud_provider ?? 'all',
    source_lz_id: params.source_lz_id ?? 'all',
    source_lz_ids: params.source_lz_ids?.slice().sort().join(',') ?? 'all',
    workspace_id: params.workspace_id ?? 'all',
    workspace_ids: params.workspace_ids?.slice().sort().join(',') ?? 'all',
  };
}

export const dashboardQueryKeys = {
  all: ['dashboard'] as const,
  data: (params: DashboardQueryParams) =>
    [...dashboardQueryKeys.all, 'full', normalizeDashboardParams(params)] as const,
};

export interface MonitoringReportsQueryParams {
  start_date: string;
  end_date: string;
  cloud_provider?: string;
  source_lz_id?: string;
  source_lz_ids?: string[];
  subscription_or_account_id?: string;
}

function normalizeMonitoringReportsParams(params: MonitoringReportsQueryParams) {
  return {
    start_date: params.start_date,
    end_date: params.end_date,
    cloud_provider: params.cloud_provider ?? 'all',
    source_lz_id: params.source_lz_id ?? 'all',
    source_lz_ids: params.source_lz_ids?.slice().sort().join(',') ?? 'all',
    subscription_or_account_id: params.subscription_or_account_id ?? 'all',
  };
}

export const monitoringReportsQueryKeys = {
  all: ['monitoring-reports'] as const,
  data: (params: MonitoringReportsQueryParams) =>
    [...monitoringReportsQueryKeys.all, 'full', normalizeMonitoringReportsParams(params)] as const,
};

export interface UnityCatalogNavigationParams {
  catalogName: string;
  schemaName?: string;
}

export interface UnityCatalogTableDetailsParams {
  catalogName: string;
  schemaName: string;
  tableName: string;
  offset?: number;
  limit?: number;
  orderBy?: string;
}

export const unityCatalogQueryKeys = {
  all: ['unity-catalog'] as const,
  navigation: (params: UnityCatalogNavigationParams) =>
    [
      ...unityCatalogQueryKeys.all,
      'full',
      params.catalogName || 'none',
      params.schemaName || 'none',
    ] as const,
  tableMetadata: (params: UnityCatalogTableDetailsParams) =>
    [
      ...unityCatalogQueryKeys.all,
      'metadata',
      params.catalogName,
      params.schemaName,
      params.tableName,
    ] as const,
  tablePreview: (params: UnityCatalogTableDetailsParams) =>
    [
      ...unityCatalogQueryKeys.all,
      'preview',
      params.catalogName,
      params.schemaName,
      params.tableName,
      params.offset ?? 0,
      params.limit ?? 100,
      params.orderBy ?? 'default',
    ] as const,
};

export interface DatabricksQueryParams {
  start_date: string;
  end_date: string;
  cloud_provider?: string;
  source_lz_id?: string;
  source_lz_ids?: string[];
  subscription_or_account_id?: string;
  workspace_id?: string;
  workspace_ids?: string[];
}

function normalizeDatabricksParams(params: DatabricksQueryParams) {
  return {
    start_date: params.start_date,
    end_date: params.end_date,
    cloud_provider: params.cloud_provider ?? 'all',
    source_lz_id: params.source_lz_id ?? 'all',
    source_lz_ids: params.source_lz_ids?.slice().sort().join(',') ?? 'all',
    subscription_or_account_id: params.subscription_or_account_id ?? 'all',
    workspace_id: params.workspace_id ?? 'all',
    workspace_ids: params.workspace_ids?.slice().sort().join(',') ?? 'all',
  };
}

export const databricksQueryKeys = {
  all: ['databricks'] as const,
  full: (params: DatabricksQueryParams) =>
    [...databricksQueryKeys.all, 'full', normalizeDatabricksParams(params)] as const,
};

export interface DataFactoryQueryParams {
  start_date: string;
  end_date: string;
  source_lz_id?: string;
  source_lz_ids?: string[];
}

function normalizeDataFactoryParams(params: DataFactoryQueryParams) {
  return {
    start_date: params.start_date,
    end_date: params.end_date,
    source_lz_id: params.source_lz_id ?? 'all',
    source_lz_ids: params.source_lz_ids?.slice().sort().join(',') ?? 'all',
  };
}

export const datafactoryQueryKeys = {
  all: ['datafactory'] as const,
  full: (params: DataFactoryQueryParams) =>
    [...datafactoryQueryKeys.all, 'full', normalizeDataFactoryParams(params)] as const,
};

export interface AdminQueryParams {
  accessRequestStatus?: string;
  accessRequestPage: number;
  accessRequestPageSize: number;
  auditLimit: number;
  auditOffset: number;
}

export const adminQueryKeys = {
  all: ['admin'] as const,
  full: (params: AdminQueryParams) =>
    [
      ...adminQueryKeys.all,
      'full',
      params.accessRequestStatus ?? 'all',
      params.accessRequestPage,
      params.accessRequestPageSize,
      params.auditLimit,
      params.auditOffset,
    ] as const,
};

export const landingZonesQueryKeys = {
  all: ['landing-zones'] as const,
  accessOverview: () => [...landingZonesQueryKeys.all, 'access-overview'] as const,
  list: () => [...landingZonesQueryKeys.all, 'list'] as const,
};

export const databricksWorkspacesQueryKeys = {
  all: ['databricks-workspaces'] as const,
  list: () => [...databricksWorkspacesQueryKeys.all, 'list'] as const,
};

export const embeddedDashboardsQueryKeys = {
  all: ['embedded-dashboards'] as const,
  list: (menuGroup = 'insights') =>
    [...embeddedDashboardsQueryKeys.all, 'list', menuGroup] as const,
  detail: (slug: string) => [...embeddedDashboardsQueryKeys.all, 'detail', slug] as const,
};

export const notificationQueryKeys = {
  all: ['notification-preferences'] as const,
  preferences: () => [...notificationQueryKeys.all, 'me'] as const,
};

export interface HeaderNotificationsQueryParams {
  start_date: string;
  end_date: string;
}

export const headerNotificationsQueryKeys = {
  all: ['header-notifications'] as const,
  alerts: (params: HeaderNotificationsQueryParams) =>
    [...headerNotificationsQueryKeys.all, 'alerts', params.start_date, params.end_date] as const,
};

export interface UsersQueryParams {
  start_date?: string;
  end_date?: string;
  cloud_provider?: string;
  source_lz_id?: string;
  subscription_or_account_id?: string;
  user_type?: string;
  is_active?: boolean;
  search?: string;
  limit?: number;
  offset?: number;
}

export const usersQueryKeys = {
  all: ['users'] as const,
  list: (params: UsersQueryParams) => [...usersQueryKeys.all, 'list', params] as const,
};

export const healthQueryKeys = {
  all: ['health'] as const,
  status: () => [...healthQueryKeys.all, 'status'] as const,
};

export const kpiQueryKeys = {
  all: ['kpi-config'] as const,
  config: () => [...kpiQueryKeys.all] as const,
};

export interface GovernancePageQueryParams {
  start_date: string;
  end_date: string;
  cloud_provider?: string;
  limit?: number;
}

export const governanceQueryKeys = {
  all: ['governance'] as const,
  pageBundle: (params: GovernancePageQueryParams) =>
    [
      ...governanceQueryKeys.all,
      'page-bundle',
      params.start_date,
      params.end_date,
      params.cloud_provider ?? 'azure',
      params.limit ?? 100,
    ] as const,
};

export interface FinOpsPageQueryParams {
  start_date: string;
  end_date: string;
  cloud_provider?: string;
}

export const finopsQueryKeys = {
  all: ['finops'] as const,
  pageBundle: (params: FinOpsPageQueryParams) =>
    [
      ...finopsQueryKeys.all,
      'page-bundle',
      params.start_date,
      params.end_date,
      params.cloud_provider ?? 'azure',
    ] as const,
};

export interface AlertsPageQueryParams {
  start_date: string;
  end_date: string;
  cloud_provider?: string;
  limit?: number;
}

export const alertsQueryKeys = {
  all: ['alerts'] as const,
  pageBundle: (params: AlertsPageQueryParams) =>
    [
      ...alertsQueryKeys.all,
      'page-bundle',
      params.start_date,
      params.end_date,
      params.cloud_provider ?? 'all',
      params.limit ?? 200,
    ] as const,
};

export const currentUserQueryKeys = {
  all: ['current-user'] as const,
  me: () => [...currentUserQueryKeys.all, 'me'] as const,
  permissions: () => [...currentUserQueryKeys.all, 'permissions'] as const,
};

export const projectsQueryKeys = {
  all: ['projects'] as const,
  list: () => [...projectsQueryKeys.all, 'list'] as const,
  detail: (projectId: string) => [...projectsQueryKeys.all, 'detail', projectId] as const,
  members: (projectId: string) => [...projectsQueryKeys.all, 'members', projectId] as const,
  joinRequests: (projectId: string) =>
    [...projectsQueryKeys.all, 'join-requests', projectId] as const,
  /** Platform-admin queue: pending join requests across every project. */
  allJoinRequests: () => [...projectsQueryKeys.all, 'join-requests', 'all'] as const,
  scopeRequests: () => [...projectsQueryKeys.all, 'scope-requests'] as const,
  /** Public reference data (Business Applications / landing zones) for the login forms. */
  referenceLandingZones: () => [...projectsQueryKeys.all, 'reference', 'landing-zones'] as const,
  /** Public Business-Application catalog (BA + LZ + workspace suggestions) for the login forms. */
  referenceBusinessApplications: () =>
    [...projectsQueryKeys.all, 'reference', 'business-applications'] as const,
  /** Public joinable DCM projects catalog for the login "Join a project" form. */
  referenceProjects: () => [...projectsQueryKeys.all, 'reference', 'projects'] as const,
};

// ─── Lakeflow ──────────────────────────────────────────────────────────────

export interface LakeflowOverviewQueryParams {
  window: string;
  start_date?: string;
  end_date?: string;
  source_lz_id?: string;
  source_lz_ids?: string[];
  workspace_ids?: string[];
}

function normalizeLakeflowParams(params: LakeflowOverviewQueryParams) {
  return {
    window: params.window,
    start_date: params.start_date ?? '',
    end_date: params.end_date ?? '',
    source_lz_id: params.source_lz_id ?? 'all',
    source_lz_ids: params.source_lz_ids?.slice().sort().join(',') ?? 'all',
    workspace_ids: params.workspace_ids?.slice().sort().join(',') ?? 'all',
  };
}

export const lakeflowQueryKeys = {
  all: ['lakeflow'] as const,
  overview: (params: LakeflowOverviewQueryParams) =>
    [...lakeflowQueryKeys.all, 'overview', normalizeLakeflowParams(params)] as const,
  jobs: (params: Record<string, unknown>) => [...lakeflowQueryKeys.all, 'jobs', params] as const,
  job: (workflowId: string, params: Record<string, unknown>) =>
    [...lakeflowQueryKeys.all, 'job', workflowId, params] as const,
  jobRuns: (workflowId: string, params: Record<string, unknown>) =>
    [...lakeflowQueryKeys.all, 'job-runs', workflowId, params] as const,
  runTasks: (workflowId: string, runId: string, params: Record<string, unknown>) =>
    [...lakeflowQueryKeys.all, 'run-tasks', workflowId, runId, params] as const,
};

// ─── Databricks Compute Metrics (T001/T002) ──────────────────────────────────

export interface ComputeMetricsQueryParams {
  period_start: string;
  period_end: string;
  cloud_provider?: string;
  source_lz_id?: string;
  source_lz_ids?: string[];
  workspace_id?: string;
  workspace_ids?: string[];
  page?: number;
  page_size?: number;
  // filters (tab-specific)
  search?: string;
  sku_group?: string;
  sort?: string;
  utilization_status?: string;
  is_zombie?: boolean;
  severity?: string;
  missing_tags?: boolean;
  dbr_obsolete?: boolean;
  granularity?: string;
}

// ─── Databricks Compute Metrics — Clusters ───────────────────────────────────

export interface ComputeMetricsScopeQueryParams {
  period_start: string;
  period_end: string;
  cloud_provider?: string;
  source_lz_id?: string;
  source_lz_ids?: string[];
  workspace_id?: string;
  workspace_ids?: string[];
  /** Repeatable `<column>:<value>` — see `toColumnFilterParam`. */
  column_filter?: string[];
}

/**
 * `column_filter` is normalized **here**, on the shared scope, rather than in each
 * of the nine list normalizers: the filters narrow the response, so a key that
 * ignored them would serve the unfiltered page from cache. Declaring it once is
 * also the only way not to forget one of the nine.
 *
 * Sorted, so the same selection made in a different click order is one key.
 */
function normalizeComputeMetricsScopeParams(params: ComputeMetricsScopeQueryParams) {
  return {
    period_start: params.period_start,
    period_end: params.period_end,
    cloud_provider: params.cloud_provider ?? 'all',
    source_lz_id: params.source_lz_id ?? 'all',
    source_lz_ids: params.source_lz_ids?.slice().sort().join(',') ?? 'all',
    workspace_id: params.workspace_id ?? 'all',
    workspace_ids: params.workspace_ids?.slice().sort().join(',') ?? 'all',
    column_filter: params.column_filter?.slice().sort().join('|') || 'none',
  };
}

/**
 * `window_days` belongs to the key of every view served by a `*_rolling` table:
 * without it, switching range would serve the previous window from cache.
 */
export interface ComputeClustersWindowQueryParams extends ComputeMetricsScopeQueryParams {
  window_days?: number;
}

function normalizeComputeClustersWindowParams(params: ComputeClustersWindowQueryParams) {
  return {
    ...normalizeComputeMetricsScopeParams(params),
    window_days: params.window_days ?? 1,
  };
}

/** The overview pages, sorts and searches server-side: all of it keys the cache. */
export interface ComputeClustersOverviewQueryParams extends ComputeClustersWindowQueryParams {
  search?: string;
  utilization_status?: string;
  sort?: string;
  sort_direction?: string;
  page?: number;
  page_size?: number;
}

function normalizeComputeClustersOverviewParams(params: ComputeClustersOverviewQueryParams) {
  return {
    ...normalizeComputeClustersWindowParams(params),
    search: params.search?.trim() || 'none',
    utilization_status: params.utilization_status ?? 'all',
    sort: params.sort ?? 'cost',
    sort_direction: params.sort_direction ?? 'desc',
    page: params.page ?? 1,
    page_size: params.page_size ?? 25,
  };
}

export interface ComputeClustersCostQueryParams extends ComputeClustersWindowQueryParams {
  search?: string;
  sku_group?: string;
  sort?: 'cost_desc' | 'name' | 'rank';
  page?: number;
  page_size?: number;
}

function normalizeComputeClustersCostParams(params: ComputeClustersCostQueryParams) {
  return {
    ...normalizeComputeClustersWindowParams(params),
    search: params.search?.trim() || 'none',
    sku_group: params.sku_group ?? 'all',
    sort: params.sort ?? 'cost_desc',
    page: params.page ?? 1,
    page_size: params.page_size ?? 25,
  };
}

export interface ComputeClustersEfficiencyQueryParams extends ComputeClustersWindowQueryParams {
  utilization_status?: string;
  is_zombie?: boolean;
  page?: number;
  page_size?: number;
}

function normalizeComputeClustersEfficiencyParams(params: ComputeClustersEfficiencyQueryParams) {
  return {
    ...normalizeComputeClustersWindowParams(params),
    utilization_status: params.utilization_status ?? 'all',
    is_zombie: params.is_zombie ?? null,
    page: params.page ?? 1,
    page_size: params.page_size ?? 25,
  };
}

export interface ComputeClustersGovernanceQueryParams extends ComputeMetricsScopeQueryParams {
  severity?: string;
  missing_tags?: boolean;
  dbr_obsolete?: boolean;
  page?: number;
  page_size?: number;
}

function normalizeComputeClustersGovernanceParams(params: ComputeClustersGovernanceQueryParams) {
  return {
    ...normalizeComputeMetricsScopeParams(params),
    severity: params.severity ?? 'all',
    missing_tags: params.missing_tags ?? null,
    dbr_obsolete: params.dbr_obsolete ?? null,
    page: params.page ?? 1,
    page_size: params.page_size ?? 25,
  };
}

export interface ComputeClustersDetailQueryParams extends ComputeClustersWindowQueryParams {}

/** The two per-cluster trends read the `*_daily` tables: no window, a period. */
export interface ComputeClustersTrendQueryParams extends ComputeMetricsScopeQueryParams {
  granularity: ComputeMetricTrendGranularity;
}

export const computeClustersQueryKeys = {
  all: ['compute-clusters'] as const,
  overview: (params: ComputeClustersOverviewQueryParams) =>
    [
      ...computeClustersQueryKeys.all,
      'overview',
      normalizeComputeClustersOverviewParams(params),
    ] as const,
  cost: (params: ComputeClustersCostQueryParams) =>
    [...computeClustersQueryKeys.all, 'cost', normalizeComputeClustersCostParams(params)] as const,
  efficiency: (params: ComputeClustersEfficiencyQueryParams) =>
    [
      ...computeClustersQueryKeys.all,
      'efficiency',
      normalizeComputeClustersEfficiencyParams(params),
    ] as const,
  governance: (params: ComputeClustersGovernanceQueryParams) =>
    [
      ...computeClustersQueryKeys.all,
      'governance',
      normalizeComputeClustersGovernanceParams(params),
    ] as const,
  detail: (clusterId: string, params: ComputeClustersDetailQueryParams) =>
    [
      ...computeClustersQueryKeys.all,
      'detail',
      clusterId,
      normalizeComputeClustersWindowParams(params),
    ] as const,
  costTrend: (clusterId: string, params: ComputeClustersTrendQueryParams) =>
    [
      ...computeClustersQueryKeys.all,
      'cost-trend',
      clusterId,
      normalizeComputeMetricsScopeParams(params),
      params.granularity,
    ] as const,
  lifetimeTrend: (clusterId: string, params: ComputeClustersTrendQueryParams) =>
    [
      ...computeClustersQueryKeys.all,
      'lifetime-trend',
      clusterId,
      normalizeComputeMetricsScopeParams(params),
      params.granularity,
    ] as const,
};

// ─── Databricks Compute Metrics — SQL Warehouses ─────────────────────────────

/**
 * Same rule as the clusters: `window_days` belongs to the key of every warehouse
 * view served by a `*_rolling` table, or switching range would serve the previous
 * window from cache.
 */
export interface ComputeWarehousesWindowQueryParams extends ComputeMetricsScopeQueryParams {
  window_days?: number;
}

function normalizeComputeWarehousesWindowParams(params: ComputeWarehousesWindowQueryParams) {
  return {
    ...normalizeComputeMetricsScopeParams(params),
    window_days: params.window_days ?? 1,
  };
}

/** The overview pages, sorts and searches server-side: all of it keys the cache. */
export interface ComputeWarehousesOverviewQueryParams extends ComputeWarehousesWindowQueryParams {
  search?: string;
  warehouse_size?: string;
  min_failure_rate_pct?: number;
  sort?: string;
  sort_direction?: string;
  page?: number;
  page_size?: number;
}

function normalizeComputeWarehousesOverviewParams(params: ComputeWarehousesOverviewQueryParams) {
  return {
    ...normalizeComputeWarehousesWindowParams(params),
    search: params.search?.trim() || 'none',
    warehouse_size: params.warehouse_size ?? 'all',
    min_failure_rate_pct: params.min_failure_rate_pct ?? null,
    sort: params.sort ?? 'cost',
    sort_direction: params.sort_direction ?? 'desc',
    page: params.page ?? 1,
    page_size: params.page_size ?? 25,
  };
}

export interface ComputeWarehousesCostQueryParams extends ComputeWarehousesWindowQueryParams {
  search?: string;
  warehouse_size?: string;
  sort?: 'cost_desc' | 'name';
  page?: number;
  page_size?: number;
}

function normalizeComputeWarehousesCostParams(params: ComputeWarehousesCostQueryParams) {
  return {
    ...normalizeComputeWarehousesWindowParams(params),
    search: params.search?.trim() || 'none',
    warehouse_size: params.warehouse_size ?? 'all',
    sort: params.sort ?? 'cost_desc',
    page: params.page ?? 1,
    page_size: params.page_size ?? 25,
  };
}

export interface ComputeWarehousesQueryPerformanceQueryParams extends ComputeWarehousesWindowQueryParams {
  min_failure_rate_pct?: number;
  has_spill?: boolean;
  min_latency_p95_ms?: number;
  page?: number;
  page_size?: number;
}

function normalizeComputeWarehousesQueryPerformanceParams(
  params: ComputeWarehousesQueryPerformanceQueryParams
) {
  return {
    ...normalizeComputeWarehousesWindowParams(params),
    min_failure_rate_pct: params.min_failure_rate_pct ?? null,
    has_spill: params.has_spill ?? null,
    min_latency_p95_ms: params.min_latency_p95_ms ?? null,
    page: params.page ?? 1,
    page_size: params.page_size ?? 25,
  };
}

export interface ComputeWarehousesSlowQueriesQueryParams extends ComputeMetricsScopeQueryParams {
  warehouse_id?: string;
  reason?: string;
  page?: number;
  page_size?: number;
}

function normalizeComputeWarehousesSlowQueriesParams(
  params: ComputeWarehousesSlowQueriesQueryParams
) {
  return {
    ...normalizeComputeMetricsScopeParams(params),
    warehouse_id: params.warehouse_id ?? 'all',
    reason: params.reason ?? 'all',
    page: params.page ?? 1,
    page_size: params.page_size ?? 25,
  };
}

export const computeWarehousesQueryKeys = {
  all: ['compute-warehouses'] as const,
  overview: (params: ComputeWarehousesOverviewQueryParams) =>
    [
      ...computeWarehousesQueryKeys.all,
      'overview',
      normalizeComputeWarehousesOverviewParams(params),
    ] as const,
  cost: (params: ComputeWarehousesCostQueryParams) =>
    [
      ...computeWarehousesQueryKeys.all,
      'cost',
      normalizeComputeWarehousesCostParams(params),
    ] as const,
  queryPerformance: (params: ComputeWarehousesQueryPerformanceQueryParams) =>
    [
      ...computeWarehousesQueryKeys.all,
      'query-performance',
      normalizeComputeWarehousesQueryPerformanceParams(params),
    ] as const,
  slowQueries: (params: ComputeWarehousesSlowQueriesQueryParams) =>
    [
      ...computeWarehousesQueryKeys.all,
      'slow-queries',
      normalizeComputeWarehousesSlowQueriesParams(params),
    ] as const,
  detail: (warehouseId: string, params: ComputeMetricsScopeQueryParams) =>
    [
      ...computeWarehousesQueryKeys.all,
      'detail',
      warehouseId,
      normalizeComputeMetricsScopeParams(params),
    ] as const,
  costTrend: (
    warehouseId: string,
    params: ComputeMetricsScopeQueryParams & { granularity: ComputeMetricTrendGranularity }
  ) =>
    [
      ...computeWarehousesQueryKeys.all,
      'cost-trend',
      warehouseId,
      normalizeComputeMetricsScopeParams(params),
      params.granularity,
    ] as const,
};

// ─── Databricks Compute Metrics — Job & Pipeline (DLT) compute ───────────────

/** Window + server-side search/sort/paging: every dimension keys the cache. */
export interface ComputeJobsCostQueryParams extends ComputeWarehousesWindowQueryParams {
  search?: string;
  sort?: 'cost_desc' | 'name';
  page?: number;
  page_size?: number;
}

function normalizeComputeJobsCostParams(params: ComputeJobsCostQueryParams) {
  return {
    ...normalizeComputeWarehousesWindowParams(params),
    search: params.search?.trim() || 'none',
    sort: params.sort ?? 'cost_desc',
    page: params.page ?? 1,
    page_size: params.page_size ?? 25,
  };
}

/** Same paging dimensions, its own `sort` union — the efficiency views rank on savings. */
export interface ComputeStableGrainEfficiencyQueryParams extends ComputeWarehousesWindowQueryParams {
  search?: string;
  sort?: 'savings_desc' | 'uptime' | 'name';
  page?: number;
  page_size?: number;
}

function normalizeComputeStableGrainEfficiencyParams(
  params: ComputeStableGrainEfficiencyQueryParams
) {
  return {
    ...normalizeComputeWarehousesWindowParams(params),
    search: params.search?.trim() || 'none',
    sort: params.sort ?? 'savings_desc',
    page: params.page ?? 1,
    page_size: params.page_size ?? 25,
  };
}

/**
 * The detail reads a `*_rolling` snapshot, so the window keys it: the same job seen
 * over 1 day and over 90 days is two different payloads, not one cache entry.
 */
export interface ComputeStableGrainDetailQueryParams extends ComputeWarehousesWindowQueryParams {}

/** The two per-grain trends read the `*_daily` tables: no window, a period. */
export interface ComputeStableGrainTrendQueryParams extends ComputeMetricsScopeQueryParams {
  granularity: ComputeMetricTrendGranularity;
}

export const computeJobsQueryKeys = {
  all: ['compute-jobs'] as const,
  overview: (params: ComputeJobsCostQueryParams) =>
    [...computeJobsQueryKeys.all, 'overview', normalizeComputeJobsCostParams(params)] as const,
  cost: (params: ComputeJobsCostQueryParams) =>
    [...computeJobsQueryKeys.all, 'cost', normalizeComputeJobsCostParams(params)] as const,
  efficiency: (params: ComputeStableGrainEfficiencyQueryParams) =>
    [
      ...computeJobsQueryKeys.all,
      'efficiency',
      normalizeComputeStableGrainEfficiencyParams(params),
    ] as const,
  detail: (jobId: string, params: ComputeStableGrainDetailQueryParams) =>
    [
      ...computeJobsQueryKeys.all,
      'detail',
      jobId,
      normalizeComputeWarehousesWindowParams(params),
    ] as const,
  costTrend: (jobId: string, params: ComputeStableGrainTrendQueryParams) =>
    [
      ...computeJobsQueryKeys.all,
      'cost-trend',
      jobId,
      normalizeComputeMetricsScopeParams(params),
      params.granularity,
    ] as const,
  uptimeTrend: (jobId: string, params: ComputeStableGrainTrendQueryParams) =>
    [
      ...computeJobsQueryKeys.all,
      'uptime-trend',
      jobId,
      normalizeComputeMetricsScopeParams(params),
      params.granularity,
    ] as const,
};

export const computePipelinesQueryKeys = {
  all: ['compute-pipelines'] as const,
  overview: (params: ComputeJobsCostQueryParams) =>
    [...computePipelinesQueryKeys.all, 'overview', normalizeComputeJobsCostParams(params)] as const,
  cost: (params: ComputeJobsCostQueryParams) =>
    [...computePipelinesQueryKeys.all, 'cost', normalizeComputeJobsCostParams(params)] as const,
  efficiency: (params: ComputeStableGrainEfficiencyQueryParams) =>
    [
      ...computePipelinesQueryKeys.all,
      'efficiency',
      normalizeComputeStableGrainEfficiencyParams(params),
    ] as const,
  detail: (pipelineId: string, params: ComputeStableGrainDetailQueryParams) =>
    [
      ...computePipelinesQueryKeys.all,
      'detail',
      pipelineId,
      normalizeComputeWarehousesWindowParams(params),
    ] as const,
  costTrend: (pipelineId: string, params: ComputeStableGrainTrendQueryParams) =>
    [
      ...computePipelinesQueryKeys.all,
      'cost-trend',
      pipelineId,
      normalizeComputeMetricsScopeParams(params),
      params.granularity,
    ] as const,
  uptimeTrend: (pipelineId: string, params: ComputeStableGrainTrendQueryParams) =>
    [
      ...computePipelinesQueryKeys.all,
      'uptime-trend',
      pipelineId,
      normalizeComputeMetricsScopeParams(params),
      params.granularity,
    ] as const,
};

// ─── Databricks Compute Metrics — Serverless (025) ───────────────────────────

/** The window keys every serverless view served by a `*_rolling` snapshot. */
export interface ComputeServerlessWindowQueryParams extends ComputeMetricsScopeQueryParams {
  window_days?: number;
}

function normalizeComputeServerlessWindowParams(params: ComputeServerlessWindowQueryParams) {
  return {
    ...normalizeComputeMetricsScopeParams(params),
    window_days: params.window_days ?? 1,
  };
}

export interface ComputeServerlessSurfacesQueryParams extends ComputeServerlessWindowQueryParams {
  sort?: string;
  sort_direction?: string;
  page?: number;
  page_size?: number;
}

function normalizeComputeServerlessSurfacesParams(params: ComputeServerlessSurfacesQueryParams) {
  return {
    ...normalizeComputeServerlessWindowParams(params),
    sort: params.sort ?? 'cost',
    sort_direction: params.sort_direction ?? 'desc',
    page: params.page ?? 1,
    page_size: params.page_size ?? 25,
  };
}

/**
 * The cost trend reads the daily table: a period and a granularity, no window.
 * `surface` keys it too — the unfiltered response is a different series, not the same
 * one with rows hidden.
 */
export interface ComputeServerlessCostTrendQueryParams extends ComputeMetricsScopeQueryParams {
  granularity: ComputeMetricTrendGranularity;
  surface?: string;
}

/**
 * Governance takes **no** `window_days`, so none appears in its key: adding one would
 * cache four copies of the same 90-day snapshot and suggest the range narrowed it.
 */
export interface ComputeServerlessGovernanceQueryParams extends ComputeMetricsScopeQueryParams {
  sort?: string;
  sort_direction?: string;
  page?: number;
  page_size?: number;
}

function normalizeComputeServerlessGovernanceParams(
  params: ComputeServerlessGovernanceQueryParams
) {
  return {
    ...normalizeComputeMetricsScopeParams(params),
    sort: params.sort ?? 'cost',
    sort_direction: params.sort_direction ?? 'desc',
    page: params.page ?? 1,
    page_size: params.page_size ?? 25,
  };
}

export interface ComputeServerlessObjectsQueryParams extends ComputeServerlessWindowQueryParams {
  surface?: string;
  search?: string;
  sort?: string;
  sort_direction?: string;
  page?: number;
  page_size?: number;
}

function normalizeComputeServerlessObjectsParams(params: ComputeServerlessObjectsQueryParams) {
  return {
    ...normalizeComputeServerlessWindowParams(params),
    surface: params.surface ?? 'all',
    search: params.search?.trim() || 'none',
    sort: params.sort ?? 'cost',
    sort_direction: params.sort_direction ?? 'desc',
    page: params.page ?? 1,
    page_size: params.page_size ?? 25,
  };
}

/** `surface` completes the object's identity, so it belongs in the key, not beside it. */
export interface ComputeServerlessObjectDetailQueryParams extends ComputeServerlessWindowQueryParams {
  surface: string;
}

export interface ComputeServerlessObjectTrendQueryParams extends ComputeMetricsScopeQueryParams {
  surface: string;
  granularity: ComputeMetricTrendGranularity;
}

export const computeServerlessQueryKeys = {
  all: ['compute-serverless'] as const,
  overview: (params: ComputeServerlessWindowQueryParams) =>
    [
      ...computeServerlessQueryKeys.all,
      'overview',
      normalizeComputeServerlessWindowParams(params),
    ] as const,
  surfaces: (params: ComputeServerlessSurfacesQueryParams) =>
    [
      ...computeServerlessQueryKeys.all,
      'surfaces',
      normalizeComputeServerlessSurfacesParams(params),
    ] as const,
  costTrend: (params: ComputeServerlessCostTrendQueryParams) =>
    [
      ...computeServerlessQueryKeys.all,
      'cost-trend',
      normalizeComputeMetricsScopeParams(params),
      params.granularity,
      params.surface ?? 'all',
    ] as const,
  governance: (params: ComputeServerlessGovernanceQueryParams) =>
    [
      ...computeServerlessQueryKeys.all,
      'governance',
      normalizeComputeServerlessGovernanceParams(params),
    ] as const,
  levers: (params: ComputeServerlessWindowQueryParams) =>
    [
      ...computeServerlessQueryKeys.all,
      'levers',
      normalizeComputeServerlessWindowParams(params),
    ] as const,
  objects: (params: ComputeServerlessObjectsQueryParams) =>
    [
      ...computeServerlessQueryKeys.all,
      'objects',
      normalizeComputeServerlessObjectsParams(params),
    ] as const,
  objectDetail: (objectId: string, params: ComputeServerlessObjectDetailQueryParams) =>
    [
      ...computeServerlessQueryKeys.all,
      'object-detail',
      objectId,
      params.surface,
      normalizeComputeServerlessWindowParams(params),
    ] as const,
  objectCostTrend: (objectId: string, params: ComputeServerlessObjectTrendQueryParams) =>
    [
      ...computeServerlessQueryKeys.all,
      'object-cost-trend',
      objectId,
      params.surface,
      normalizeComputeMetricsScopeParams(params),
      params.granularity,
    ] as const,
};

// ─── Databricks Compute Metrics — Recommendations & Forecast ─────────────────

export interface ComputeRecommendationsQueryParams extends ComputeMetricsScopeQueryParams {
  object_type?: string;
  category?: string;
  severity?: string;
  status?: string;
  search?: string;
  sort?: string;
  order?: string;
  page?: number;
  page_size?: number;
}

function normalizeComputeRecommendationsParams(params: ComputeRecommendationsQueryParams) {
  return {
    ...normalizeComputeMetricsScopeParams(params),
    object_type: params.object_type ?? 'all',
    category: params.category ?? 'all',
    severity: params.severity ?? 'all',
    status: params.status ?? 'all',
    search: params.search?.trim() || 'none',
    sort: params.sort ?? 'severity',
    order: params.order ?? 'desc',
    page: params.page ?? 1,
    page_size: params.page_size ?? 25,
  };
}

export interface ComputeForecastQueryParams extends ComputeMetricsScopeQueryParams {
  metric_name?: string;
  object_type?: string;
  object_id?: string;
}

function normalizeComputeForecastParams(params: ComputeForecastQueryParams) {
  return {
    ...normalizeComputeMetricsScopeParams(params),
    metric_name: params.metric_name ?? 'all',
    object_type: params.object_type ?? 'all',
    object_id: params.object_id ?? 'none',
  };
}

export const computeRecommendationsQueryKeys = {
  all: ['compute-recommendations'] as const,
  list: (params: ComputeRecommendationsQueryParams) =>
    [
      ...computeRecommendationsQueryKeys.all,
      'list',
      normalizeComputeRecommendationsParams(params),
    ] as const,
  summary: (params: ComputeMetricsScopeQueryParams) =>
    [
      ...computeRecommendationsQueryKeys.all,
      'summary',
      normalizeComputeMetricsScopeParams(params),
    ] as const,
  forecast: (params: ComputeForecastQueryParams) =>
    [
      ...computeRecommendationsQueryKeys.all,
      'forecast',
      normalizeComputeForecastParams(params),
    ] as const,
  openCount: (params: ComputeMetricsScopeQueryParams) =>
    [
      ...computeRecommendationsQueryKeys.all,
      'open-count',
      normalizeComputeMetricsScopeParams(params),
    ] as const,
};

// ─── Per-column filter options (023 T006) ────────────────────────────────────

/**
 * Keys the values offered for one filterable column.
 *
 * Deliberately **outside** the eleven list namespaces: the options describe the
 * perimeter, not the current selection, so they must not be invalidated when a
 * filter changes — and their scope is the same for two columns of the same view,
 * which is what makes reopening a combo instant.
 *
 * The scope is passed through as given, `column_filter` excluded: keeping it in
 * the key would cache one option list per active selection, i.e. exactly the
 * coupling the endpoint refuses server-side.
 */
export const computeFilterOptionsQueryKeys = {
  all: ['compute-filter-options'] as const,
  options: (
    view: string,
    column: string,
    params: Record<string, unknown>,
    q: string | undefined
  ) => {
    // Copie puis retrait, plutôt qu'une déstructuration avec variable ignorée : la
    // règle `no-unused-vars` du projet ne reconnaît pas le préfixe `_`.
    const scope: Record<string, unknown> = { ...params };
    delete scope.column_filter;
    return [
      ...computeFilterOptionsQueryKeys.all,
      view,
      column,
      scope,
      q?.trim() || 'none',
    ] as const;
  },
};

// ─── Unity Catalog usage tracking (024) ──────────────────────────────────────

export interface UcUsageScopeQueryParams {
  catalog?: string;
  schema?: string;
  tables?: string[];
  include_deleted?: boolean;
}

export interface UcUsagePeriodQueryParams extends UcUsageScopeQueryParams {
  period_start?: string;
  period_end?: string;
}

/**
 * Le multi-select de tables rend un ordre qui dépend des clics de l'utilisateur
 * : trier puis joindre garde une seule entrée de cache pour une même sélection.
 */
function normalizeUcUsageScope(params: UcUsageScopeQueryParams) {
  return {
    catalog: params.catalog || 'all',
    schema: params.schema || 'all',
    tables: [...(params.tables ?? [])].sort().join(',') || 'all',
    // Les tables supprimées font partie du périmètre (spec 027) : hors de la clé,
    // cocher la case resservirait le cache filtré autrement.
    include_deleted: params.include_deleted ? 'with-deleted' : 'active-only',
  };
}

function normalizeUcUsagePeriod(params: UcUsagePeriodQueryParams) {
  return {
    ...normalizeUcUsageScope(params),
    // `none` et non `null` : tant qu'aucune période n'est appliquée, la requête
    // n'est pas émise — la clé doit rester stable et lisible.
    period_start: params.period_start || 'none',
    period_end: params.period_end || 'none',
  };
}

function normalizeUcUsagePage(params: { page?: number; page_size?: number }) {
  return { page: params.page ?? 1, page_size: params.page_size ?? 25 };
}

export const ucUsageQueryKeys = {
  all: ['uc-usage'] as const,
  detail: (kind: 'table' | 'consumer', id: string, params: UcUsagePeriodQueryParams) =>
    [...ucUsageQueryKeys.all, 'details', kind, id, normalizeUcUsagePeriod(params)] as const,
  charts: (
    view: 'tables' | 'consumers' | 'finops' | 'writes' | 'cost-changes',
    params: UcUsagePeriodQueryParams
  ) => [...ucUsageQueryKeys.all, 'charts', view, normalizeUcUsagePeriod(params)] as const,
  filterOptions: (params: {
    catalog?: string;
    schema?: string;
    search?: string;
    include_deleted?: boolean;
  }) =>
    [
      ...ucUsageQueryKeys.all,
      'filter-options',
      params.catalog || 'all',
      params.schema || 'all',
      params.search?.trim() || 'none',
      params.include_deleted ? 'with-deleted' : 'active-only',
    ] as const,
  overview: (params: UcUsagePeriodQueryParams) =>
    [...ucUsageQueryKeys.all, 'overview', normalizeUcUsagePeriod(params)] as const,
  tables: (
    params: UcUsagePeriodQueryParams & {
      search?: string;
      sort?: string;
      direction?: 'asc' | 'desc';
      column_filter?: string[];
      page?: number;
      page_size?: number;
    }
  ) =>
    [
      ...ucUsageQueryKeys.all,
      'tables',
      normalizeUcUsagePeriod(params),
      params.search?.trim() || 'none',
      params.sort ?? 'popularity',
      params.direction ?? 'desc',
      [...(params.column_filter ?? [])].sort(),
      normalizeUcUsagePage(params),
    ] as const,
  topConsumers: (tableFullName: string, params: UcUsagePeriodQueryParams) =>
    [
      ...ucUsageQueryKeys.all,
      'top-consumers',
      tableFullName,
      normalizeUcUsagePeriod(params),
    ] as const,
  consumers: (
    params: UcUsagePeriodQueryParams & {
      search?: string;
      consumer_type?: string;
      sort?: string;
      direction?: 'asc' | 'desc';
      column_filter?: string[];
      page?: number;
      page_size?: number;
    }
  ) =>
    [
      ...ucUsageQueryKeys.all,
      'consumers',
      normalizeUcUsagePeriod(params),
      params.search?.trim() || 'none',
      params.consumer_type || 'all',
      params.sort ?? 'cost',
      params.direction ?? 'desc',
      [...(params.column_filter ?? [])].sort(),
      normalizeUcUsagePage(params),
    ] as const,
  finopsKpis: (params: UcUsagePeriodQueryParams) =>
    [...ucUsageQueryKeys.all, 'finops-kpis', normalizeUcUsagePeriod(params)] as const,
  costByTable: (
    params: UcUsagePeriodQueryParams & {
      search?: string;
      sort?: string;
      direction?: string;
      column_filter?: string[];
      page?: number;
      page_size?: number;
    }
  ) =>
    [
      ...ucUsageQueryKeys.all,
      'cost-by-table',
      normalizeUcUsagePeriod(params),
      params.search?.trim() || 'none',
      params.sort ?? 'cost',
      params.direction ?? 'desc',
      [...(params.column_filter ?? [])].sort(),
      normalizeUcUsagePage(params),
    ] as const,
  trends: (
    params: UcUsageScopeQueryParams & {
      metrics?: string[];
      period_start?: string;
      period_end?: string;
    }
  ) =>
    [
      ...ucUsageQueryKeys.all,
      'trends',
      normalizeUcUsagePeriod(params),
      [...(params.metrics ?? [])].sort().join(',') || 'all',
    ] as const,
  attention: (params: UcUsageScopeQueryParams & { limit?: number }) =>
    [
      ...ucUsageQueryKeys.all,
      'attention',
      normalizeUcUsageScope(params),
      params.limit ?? 3,
    ] as const,
  recommendations: (
    params: UcUsageScopeQueryParams & {
      category?: string;
      severity?: string;
      object_type?: string;
      age_bucket?: string;
      sort?: string;
      page?: number;
      page_size?: number;
    }
  ) =>
    [
      ...ucUsageQueryKeys.all,
      'recommendations',
      normalizeUcUsageScope(params),
      params.category || 'all',
      params.severity || 'all',
      params.object_type || 'all',
      params.age_bucket || 'all',
      params.sort || 'savings',
      normalizeUcUsagePage(params),
    ] as const,
  governanceKpis: (params: UcUsageScopeQueryParams) =>
    [...ucUsageQueryKeys.all, 'governance-kpis', normalizeUcUsageScope(params)] as const,
  governanceCharts: (params: UcUsageScopeQueryParams) =>
    [...ucUsageQueryKeys.all, 'governance-charts', normalizeUcUsageScope(params)] as const,
  recommendationCharts: (params: UcUsageScopeQueryParams) =>
    [...ucUsageQueryKeys.all, 'recommendation-charts', normalizeUcUsageScope(params)] as const,
  registry: (
    params: UcUsageScopeQueryParams & {
      search?: string;
      signal?: string;
      inactivity?: string;
      missing_tag?: string;
      sort?: string;
      page?: number;
      page_size?: number;
    }
  ) =>
    [
      ...ucUsageQueryKeys.all,
      'registry',
      normalizeUcUsageScope(params),
      params.signal || 'all',
      params.inactivity || 'all',
      params.missing_tag || 'all',
      params.search?.trim() || 'none',
      params.sort ?? 'severity',
      normalizeUcUsagePage(params),
    ] as const,
};
