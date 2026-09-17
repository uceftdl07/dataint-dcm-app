/**
 * TypeScript types matching dcm-backend API responses.
 * Mirrors the Lakebase PostgreSQL SERVING schema.
 */

// ─── Shared ────────────────────────────────────────────────────────────────
// ─── Business types from the POC ISO migration ───────────────────────────────

// Dashboard Types
export interface DashboardOverviewPOC {
  activeServices: number;
  monthlyCost: number;
  budget: number;
  activeJobs: number;
  activeAlerts: number;
  timestamp: string;
  services: ServiceStatus[];
  costTrend: CostTrend;
}

export interface ServiceStatus {
  serviceName: string;
  serviceType: string;
  status: string;
  monthlyCost: number;
  healthStatus: string;
  lastUpdated: string;
}

export interface CostTrend {
  percentageChange: number;
  direction: 'up' | 'down' | 'stable';
  savings: number;
  period: string;
}

export interface ServiceMetrics {
  serviceType: string;
  metrics: Record<string, unknown>;
  timestamp: string;
}

export interface RecentActivity {
  id: string;
  activityType: string;
  serviceName: string;
  description: string;
  status: string;
  cost?: number;
  timestamp: string;
  icon: string;
}

// Databricks Types
export interface DatabricksCluster {
  clusterId: string;
  clusterName: string;
  state: string;
  numWorkers: number;
  nodeTypeId: string;
  runtimeVersion: string;
  cpuUtilization: number;
  memoryUtilization: number;
  hourlyCost: number;
  createdDate: string;
  terminatedDate?: string;
  createdBy: string;
  tags: string[];
  workspaceName: string;
}

export interface DatabricksMetrics {
  clusterId: string;
  cpuUtilization: number;
  memoryUtilization: number;
  cost: number;
  activeJobs: number;
  completedJobs: number;
  failedJobs: number;
  timestamp: string;
  recentExecutions?: JobExecution[];
}

export interface DatabricksJob {
  jobId: string;
  jobName: string;
  clusterId: string;
  status: string;
  duration?: number;
  startTime: string;
  endTime?: string;
  jobType: string;
  cost: number;
  errorMessage?: string;
  createdBy: string;
  workspaceName: string;
}

export interface JobExecution {
  executionId: string;
  jobId: string;
  status: string;
  startTime: string;
  endTime?: string;
  duration?: number;
  errorMessage?: string;
  metrics: Record<string, unknown>;
}

// Data Factory Types
export interface DataFactoryPipeline {
  pipelineName: string;
  pipelineType: string;
  status: string;
  lastExecutionTime?: string;
  lastExecutionDuration?: number;
  lastExecutionStatus: string;
  monthlyCost: number;
  executionsToday: number;
  successRate: number;
  createdDate: string;
  createdBy: string;
  tags: string[];
  factoryName?: string;
  description?: string;
}

export interface DataFactoryMetrics {
  pipelineName: string;
  status: string;
  duration: number;
  cost: number;
  startTime: string;
  endTime: string;
  successfulRuns: number;
  failedRuns: number;
  totalRuns: number;
  successRate: number;
}

export interface PipelineRunPOC {
  runId: string;
  pipelineName: string;
  status: string;
  runStart: string;
  runEnd?: string;
  duration?: number;
  cost: number;
  triggeredBy: string;
  errorMessage?: string;
  parameters: Record<string, unknown>;
  activityRuns?: ActivityRun[];
}

export interface ActivityRun {
  activityName: string;
  activityType: string;
  status: string;
  start: string;
  end?: string;
  duration?: number;
  errorMessage?: string;
}

export interface IntegrationRuntime {
  name: string;
  type: string;
  status: string;
  location: string;
  nodeCount?: number;
  cpuUtilization?: number;
  memoryUtilization?: number;
  lastHeartbeat: string;
  version: string;
}

// FinOps Types
export interface CostSummaryPOC {
  currentMonthCost: number;
  lastMonthCost: number;
  budget: number;
  budgetUsedPercentage: number;
  savings: number;
  forecastedCost: number;
  trend: CostTrend;
  lastUpdated: string;
}

export interface ServiceCost {
  serviceName: string;
  serviceType: string;
  monthlyCost: number;
  dailyCost: number;
  budgetPercentage: number;
  trend: CostTrend;
  recommendations: CostOptimizationRecommendation[];
  resourceGroup: string;
  subscriptionId: string;
}

export interface Budget {
  budgetId: string;
  budgetName: string;
  amount: number;
  spentAmount: number;
  remainingAmount: number;
  spentPercentage: number;
  period: string;
  startDate: string;
  endDate: string;
  alerts: BudgetAlert[];
  status: string;
}

export interface BudgetAlert {
  thresholdPercentage: number;
  isTriggered: boolean;
  triggeredDate?: string;
  notificationEmails: string[];
}

export interface CostOptimizationRecommendation {
  recommendationId: string;
  title: string;
  description: string;
  category: string;
  potentialMonthlySavings: number;
  priority: string;
  serviceName: string;
  serviceType: string;
  actionRequired: string;
  estimatedImplementationTimeMinutes: number;
  impact: string;
  createdDate: string;
  status: string;
}

export interface ReservedInstance {
  reservationId: string;
  reservationName: string;
  serviceType: string;
  scope: string;
  region: string;
  termYears: number;
  monthlyCost: number;
  monthlySavings: number;
  savingsPercentage: number;
  startDate: string;
  endDate: string;
  status: string;
  instanceCount: number;
  instanceSize: string;
}

// Alert Types
export interface Alert {
  alertId: string;
  alertName: string;
  serviceName: string;
  serviceType: string;
  severity: 'Critical' | 'Warning' | 'Info';
  status: 'Active' | 'Resolved' | 'Snoozed';
  description: string;
  currentValue?: number;
  thresholdValue?: number;
  unit?: string;
  triggeredDate: string;
  resolvedDate?: string;
  snoozeUntil?: string;
  resolution?: string;
  resolvedBy?: string;
  duration?: number;
  metadata: Record<string, unknown>;
}

export interface AlertRule {
  ruleId: string;
  ruleName: string;
  serviceName: string;
  serviceType: string;
  metricName: string;
  operator: string;
  thresholdValue: number;
  unit: string;
  evaluationFrequencyMinutes: number;
  windowSizeMinutes: number;
  severity: string;
  isEnabled: boolean;
  createdDate: string;
  lastTriggered?: string;
  triggeredCount: number;
  notificationChannels: LegacyNotificationChannel[];
}

export interface LegacyNotificationChannel {
  type: string;
  address: string;
  isEnabled: boolean;
  configuration?: string;
}

export interface AlertStatistics {
  activeAlertsCount: number;
  resolvedAlertsCount: number;
  criticalAlertsCount: number;
  warningAlertsCount: number;
  infoAlertsCount: number;
  averageResolutionTimeMinutes: number;
  alertRulesCount: number;
  enabledRulesCount: number;
  periodStart: string;
  periodEnd: string;
  trendData: AlertTrend[];
}

export interface AlertTrend {
  date: string;
  alertsCount: number;
  resolvedCount: number;
  averageResolutionTimeMinutes: number;
}

// Common Types
export interface ApiError {
  message: string;
  details?: string;
  timestamp: string;
}
// ─── Shared ────────────────────────────────────────────────────────────────

export type CloudProvider = 'azure' | 'aws';
export type PipelineStatus = 'running' | 'succeeded' | 'failed' | 'cancelled';
export type ComputeState = 'running' | 'terminated' | 'error' | 'unknown';
export type AlertSeverity = 'low' | 'medium' | 'high' | 'critical';
export type AlertStatus = 'active' | 'resolved' | 'dismissed';
export type DatabaseType =
  | 'sqlserver'
  | 'postgresql'
  | 'mysql'
  | 'cosmosdb'
  | 'redshift'
  | 'rds_mysql'
  | 'rds_postgres'
  | 'rds_oracle'
  | 'aurora';

export interface DatePeriod {
  start: string; // ISO date
  end: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Health ────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: 'ok' | 'degraded';
  database: 'ok' | 'unreachable';
  timestamp: string;
  service: string;
}

// ─── Dashboard ─────────────────────────────────────────────────────────────

export interface DashboardOverview {
  total_pipelines: number;
  total_adf_pipelines: number;
  total_databricks_pipelines: number;
  failed_pipelines_24h: number;
  active_clusters: number;
  /** Home-page fields are optional while older dashboard API deployments remain supported. */
  failed_databricks_jobs_24h?: number | null;
  active_sql_warehouses?: number | null;
  as_of?: string | null;
  cost_ytd_usd?: number | null;
  cost_ytd_previous_year_usd?: number | null;
  cost_ytd_delta_usd?: number | null;
  cost_ytd_delta_pct?: number | null;
  cost_ytd_monthly?: HomeFinOpsTrendPoint[];
  alert_breakdown?: HomeAlertBreakdown;
  total_cost_usd: number;
  open_alerts: number;
  cloud_coverage: CloudProvider[];
  period: DatePeriod;
}

export interface HomeFinOpsTrendPoint {
  month: string;
  current_year_usd: number;
  previous_year_usd: number | null;
}

export interface HomeAlertBreakdown {
  critical?: number;
  high?: number;
  medium?: number;
  low?: number;
}

// ─── Pipelines ─────────────────────────────────────────────────────────────

export interface PipelineRun {
  run_id: string;
  pipeline_id: string;
  pipeline_name: string;
  cloud_provider: CloudProvider;
  /** Absent on Databricks-sourced runs (gold_dbx_workflow_runs has no source_lz_id, only workspace_id below). */
  source_lz_id?: string | null;
  workspace_id?: string | null;
  pipeline_type?: string | null;
  // account and region removed: obsolete fields
  trigger_type: string | null;
  status: PipelineStatus;
  start_time: string | null;
  end_time: string | null;
  duration_seconds: number | null;
  error_message: string | null;
  // collected_at removed: obsolete field
}

export type PipelineListResponse = PaginatedResponse<PipelineRun>;

export interface PipelineRunsResponse {
  pipeline_name: string;
  runs: PipelineRun[];
}

// ─── Clusters ──────────────────────────────────────────────────────────────

export interface ComputeMetric {
  compute_resource_id: string;
  resource_name: string;
  compute_type: string | null;
  cloud_provider: CloudProvider;
  source_lz_id: string;
  subscription_or_account_id: string | null;
  workspace_id?: string | null;
  state: ComputeState;
  num_workers: number | null;
  autoscale_min: number | null;
  autoscale_max: number | null;
  node_type: string | null;
  spark_version: string | null;
  avg_cpu_utilization_pct: number | null;
  avg_mem_utilization_pct: number | null;
  tags: Record<string, unknown>;
  collected_at: string;
}

export interface ComputeResponse {
  items: ComputeMetric[];
}

// ─── Costs ─────────────────────────────────────────────────────────────────

export interface ServiceCostSummary {
  service_name: string;
  cloud_provider: CloudProvider;
  cost_usd: number;
}

export interface CostSummary {
  total_usd: number;
  by_cloud: Record<string, number>;
  by_service: ServiceCostSummary[];
  period: DatePeriod;
}

export interface ServiceCostDetail {
  service_name: string;
  cloud_provider: CloudProvider;
  subscription_or_account_id: string | null;
  source_lz_id: string | null;
  total_cost_usd: number;
  avg_budget_consumed_pct: number | null;
  period: DatePeriod;
}

export interface CostsByServiceResponse {
  items: ServiceCostDetail[];
}

// ─── Data Product Usage ─────────────────────────────────────────────────────

export interface DataProductUsageCloudSummary {
  cloud_provider: CloudProvider;
  data_product_count: number;
  consumer_count: number;
  request_count: number;
  data_read_bytes: number;
  data_written_bytes: number;
  cost_usd: number;
}

export interface DataProductUsageOverview {
  total_data_products: number;
  active_consumers: number;
  request_count: number;
  rows_read: number;
  rows_written: number;
  data_read_bytes: number;
  data_written_bytes: number;
  duration_seconds: number;
  cost_usd: number;
  last_used_at: string | null;
  by_cloud: DataProductUsageCloudSummary[];
  period: DatePeriod;
}

export interface DataProductUsageTrend {
  period_start: string;
  data_product_count: number;
  consumer_count: number;
  request_count: number;
  rows_read: number;
  rows_written: number;
  data_read_bytes: number;
  data_written_bytes: number;
  cost_usd: number;
}

export interface DataProductUsageTrendsResponse {
  grain: 'day' | 'week' | 'month';
  items: DataProductUsageTrend[];
  period: DatePeriod;
}

export interface DataProductConsumerUsage {
  consumer_id: string;
  consumer_name: string | null;
  cloud_provider: CloudProvider;
  source_lz_id: string;
  subscription_or_account_id: string | null;
  data_product_count: number;
  request_count: number;
  rows_read: number;
  rows_written: number;
  data_read_bytes: number;
  data_written_bytes: number;
  duration_seconds: number;
  cost_usd: number;
  metric_value: number;
  last_used_at: string | null;
}

export interface TopDataProductConsumersResponse {
  metric: string;
  items: DataProductConsumerUsage[];
  period: DatePeriod;
}

export interface DataProductUsage {
  usage_date: string;
  data_product_id: string;
  data_product_name: string | null;
  consumer_id: string;
  consumer_name: string | null;
  cloud_provider: CloudProvider;
  source_lz_id: string;
  subscription_or_account_id: string | null;
  request_count: number;
  rows_read: number;
  rows_written: number;
  data_read_bytes: number;
  data_written_bytes: number;
  duration_seconds: number;
  cost_usd: number;
  last_used_at: string | null;
}

export interface DataProductUsageResponse extends PaginatedResponse<DataProductUsage> {
  period: DatePeriod;
}

// ─── Databases ─────────────────────────────────────────────────────────────

export interface DatabaseMetric {
  db_id: string;
  db_name: string | null;
  db_type: DatabaseType;
  server_name: string | null;
  resource_group?: string | null;
  region: string | null;
  availability_zone?: string | null;
  cloud_provider: CloudProvider;
  source_lz_id: string;
  subscription_or_account_id: string | null;
  cpu_percent: number | null;
  memory_percent: number | null;
  storage_used_gb: number | null;
  storage_limit_gb?: number | null;
  storage_used_pct?: number | null;
  storage_cost_impact_usd?: number | null;
  active_connections?: number | null;
  dtus_used?: number | null;
  is_available: boolean;
  tags?: Record<string, unknown>;
  collected_at: string;
  ingested_at?: string | null;
}

export interface DatabasesResponse {
  items: DatabaseMetric[];
}

// ─── Security ──────────────────────────────────────────────────────────────

export interface SecurityAlert {
  alert_id: string;
  cloud_provider: CloudProvider;
  source_lz_id: string;
  // Obsolete fields removed: account, region
  severity: AlertSeverity;
  title: string;
  description: string | null;
  status: AlertStatus;
  resource_id: string | null;
  resource_type: string | null;
  detected_at: string;
  // resolved_at and collected_at removed: obsolete fields
}

export type SecurityAlertsResponse = PaginatedResponse<SecurityAlert>;

// ─── Activity Runs ──────────────────────────────────────────────────────────

export type ActivityRunStatus = 'succeeded' | 'failed' | 'running' | 'cancelled' | 'skipped';
export type ActivityType =
  | 'copy'
  | 'databricks_notebook'
  | 'lookup'
  | 'for_each'
  | 'wait'
  | 'web_activity'
  | 'execute_pipeline'
  | 'glue_job_node'
  | 'unknown';

export interface ActivityRun {
  pipeline_run_id: string;
  pipeline_name: string;
  activity_name: string;
  activity_type: ActivityType;
  cloud_provider: CloudProvider;
  source_lz_id: string;
  subscription_or_account_id: string | null;
  status: string;
  start_time: string | null;
  end_time: string | null;
  duration_seconds: number | null;
  rows_read: number | null;
  rows_written: number | null;
  data_read_bytes: number | null;
  data_written_bytes: number | null;
  error_message: string | null;
  tags: Record<string, unknown>;
  collected_at: string;
  ingested_at: string;
}

export type ActivityRunsResponse = PaginatedResponse<ActivityRun>;

// ─── Users ──────────────────────────────────────────────────────────────────

export type UserType = 'databricks' | 'aws_iam' | 'azure_ad';

export interface UserMetric {
  user_id: string;
  user_name: string;
  display_name: string | null;
  cloud_provider: CloudProvider;
  source_lz_id: string;
  subscription_or_account_id: string | null;
  user_type: UserType;
  is_active: boolean;
  last_activity_at: string | null;
  groups: string[];
  roles: string[];
}

export interface UsersResponse extends PaginatedResponse<UserMetric> {
  active_count: number;
  inactive_count: number;
}

// ─── Standard Checks (Governance) ────────────────────────────────────────────

export type StandardCheckState = 'compliant' | 'no_compliant' | 'non_compliant' | 'unknown';

export interface StandardCheck {
  check_id: string;
  check_name: string;
  cloud_provider: CloudProvider;
  source_lz_id: string;
  subscription_or_account_id: string | null;
  check_state: StandardCheckState;
  resource_id: string | null;
  resource_name: string | null;
  resource_type: string | null;
  check_effect: string | null;
  no_check_reasons: string[];
  evaluated_at: string;
}

export type StandardChecksResponse = PaginatedResponse<StandardCheck>;

export interface LandingZoneScore {
  cloud_provider: CloudProvider;
  source_lz_id: string;
  subscription_or_account_id: string | null;
  compliant_count: number;
  no_compliant_count: number;
  total_evaluated: number;
  score_pct: number | null;
}

export interface GovernanceScore {
  global_score_pct: number | null;
  compliant_count: number;
  no_compliant_count: number;
  total_evaluated: number;
  by_landing_zone: LandingZoneScore[];
}

export interface DashboardFullResponse {
  overview: DashboardOverview;
  governance: GovernanceScore;
  costs: CostSummary;
  pipelines: PipelineRun[];
  computes: ComputeMetric[];
  databases: DatabaseMetric[];
  alerts: SecurityAlert[];
}

export interface MonitoringReportsFullResponse {
  data_product_usage: DataProductUsageResponse;
  usage_trends: DataProductUsageTrendsResponse;
  standard_checks: StandardChecksResponse;
  landing_zones: LandingZonesResponse;
  security_alerts: SecurityAlertsResponse;
  computes: ComputeResponse;
  pipelines: PipelineListResponse;
  cost_summary: CostSummary;
  costs_by_service: CostsByServiceResponse;
  governance: GovernanceScore;
}

// ─── Unity Catalog Explorer ────────────────────────────────────────────────

export type UnityCatalogCellValue = string | number | boolean | null;

export interface UnityCatalogItem {
  Name: string;
  Type: string;
  IsMonitoringRelevant: boolean;
  RecommendedForExploration: boolean;
}

export interface UnityCatalogSchema {
  Name: string;
  IsTargetSchema: boolean;
}

export interface UnityCatalogTable {
  Name: string;
  Type: string;
  Format: string;
  Owner: string;
  FullName: string;
  IsMonitoringTable: boolean;
}

export interface UnityCatalogColumn {
  Name: string;
  Type: string;
  Nullable: boolean;
  Comment?: string | null;
}

export interface UnityCatalogTableMetadata {
  FullName: string;
  Type: string;
  Format: string;
  Owner: string;
  CreatedAt?: string | null;
  ColumnsCount: number;
  Columns: UnityCatalogColumn[];
}

export interface UnityCatalogQueryResult {
  Status: string;
  FullTableName: string;
  RowsRetrieved: number;
  TotalRows?: number | null;
  ColumnsCount: number;
  Columns: string[];
  Data: UnityCatalogCellValue[][];
  Rows?: Array<Record<string, UnityCatalogCellValue>>;
  SqlQuery: string;
  ExecutionTime: number;
  data?: {
    columns: string[];
    rows: Array<Record<string, UnityCatalogCellValue>>;
  };
}

export interface UnityCatalogPagination {
  CurrentPage: number;
  PageSize: number;
  Offset: number;
  TotalRows?: number | null;
  TotalPages?: number | null;
  HasNextPage: boolean;
  HasPreviousPage: boolean;
  NextOffset?: number | null;
  PreviousOffset?: number | null;
}

export interface UnityCatalogExplorerResponse {
  Status: string;
  Catalogs: UnityCatalogItem[];
  catalogs?: UnityCatalogItem[];
}

export interface UnityCatalogExplorerFullResponse extends UnityCatalogExplorerResponse {
  Schemas: UnityCatalogSchema[];
  schemas?: UnityCatalogSchema[];
  Tables: UnityCatalogTable[];
  tables?: UnityCatalogTable[];
}

export interface UnityCatalogSchemasResponse {
  Status: string;
  Schemas: UnityCatalogSchema[];
  schemas?: UnityCatalogSchema[];
}

export interface UnityCatalogTablesResponse {
  Status: string;
  Tables: UnityCatalogTable[];
  tables?: UnityCatalogTable[];
}

export interface UnityCatalogTableMetadataResponse {
  Status: string;
  Table: UnityCatalogTableMetadata;
  table?: UnityCatalogTableMetadata;
}

export interface UnityCatalogTablePreviewResponse {
  Status: string;
  Table: UnityCatalogQueryResult;
  table?: UnityCatalogQueryResult;
  Pagination?: UnityCatalogPagination;
  pagination?: UnityCatalogPagination;
}

export interface UnityCatalogGenericQueryRequest {
  /** Omit to let the server use its configured catalog. */
  catalogName?: string;
  /**
   * Omit to let the server use its configured schema. The monitoring schema is
   * environment-specific (`…__d` in dev, `…__p` in prod), so a hardcoded value
   * here would point one environment at another's data.
   */
  schemaName?: string;
  tableName: string;
  columns?: string[];
  whereClause?: string;
  orderBy?: string;
  limit?: number;
  offset?: number;
}

export interface LandingZoneDetail {
  lz_id: string;
  lz_name: string;
  cloud_provider: CloudProvider;
  subscription_or_account_id: string | null;
  // region removed: obsolete field
  environment: string | null;
  ba_name: string | null;
  valid_from: string | null;
}

export interface LandingZonesResponse {
  items: LandingZoneDetail[];
  total: number;
}

export type LandingZoneCollectionHealth = 'healthy' | 'degraded' | 'unhealthy' | 'unknown';

export interface LandingZoneAccessOverviewItem extends LandingZoneDetail {
  has_access: boolean;
  collectors_total?: number;
  collectors_ok?: number;
  last_collection_at?: string | null;
  collection_health?: LandingZoneCollectionHealth;
}

export interface LandingZonesAccessOverviewResponse {
  items: LandingZoneAccessOverviewItem[];
  total: number;
  granted_count: number;
  denied_count: number;
  unrestricted_access: boolean;
}

export interface AccessRequestLandingZone {
  lz_id: string;
  lz_name: string;
  cloud_provider: CloudProvider;
  environment: string | null;
  ba_name: string | null;
}

export interface AccessRequestLandingZonesResponse {
  items: AccessRequestLandingZone[];
  total: number;
}

// ─── Project-registration reference catalog (feature 016) ────────────────────
// Public login catalog: Business Application id + name only. LZ / cloud-account /
// Databricks inventory is resolved server-side on authenticated register.

export interface ReferenceBusinessApplication {
  businessApplicationId: string;
  businessApplicationName: string;
}

export interface ReferenceBusinessApplicationsResponse {
  items: ReferenceBusinessApplication[];
  total: number;
}

// Joinable DCM projects backing the login "Join a project" form. Unlike the
// registration form (which lists Business Applications), the join form must list
// real `dcm_projects` rows so the visitor requests to join by project id.
export interface ReferenceProject {
  id: string;
  name: string;
  businessAppId: string;
  status: ProjectStatus;
}

export interface ReferenceProjectsResponse {
  items: ReferenceProject[];
  total: number;
}

// ─── DCM Admin ──────────────────────────────────────────────────────────────

export type DcmRole = 'pending' | 'viewer' | 'data_architect' | 'manager' | 'admin' | 'super_admin';

export interface DcmPermissions {
  role: DcmRole;
  pages: string[];
  widgets: string[];
  features: string[];
  allowed: string[];
}
export type NotificationChannelType = 'teams' | 'email';
export type AdminAlertSeverity = 'info' | 'warning' | 'critical';

export interface CurrentDcmUser {
  id: string;
  entra_oid: string;
  email: string;
  display_name: string | null;
  role: DcmRole;
  is_active: boolean;
  lz_ids: string[];
  /** Platform-level role (feature 015). Absent on pre-015 backends. */
  platform_role?: PlatformRole;
  /** Project memberships of the caller (feature 015). Absent on pre-015 backends. */
  projects?: ProjectMembershipRef[];
}

// ─── Project Access Governance (feature 015) ─────────────────────────────────
// Contract source of truth: specs/015-project-access-governance/contracts/projects-api.md
// `/v1/projects*` payloads are camelCase; `/auth/me` stays snake_case (documented deviation).

export type PlatformRole = 'user' | 'super_admin';
export type ProjectRole = 'viewer' | 'admin';
/** `rejected` is terminal and frees the Business Application for another team. */
export type ProjectStatus = 'pending_validation' | 'active' | 'archived' | 'rejected';
export type ProjectRequestStatus = 'pending' | 'approved' | 'rejected';
export type ProjectScopeType = 'lz' | 'dbx_workspace';

/** Membership entry exposed by the snake_case `/auth/me` payload. */
export interface ProjectMembershipRef {
  project_id: string;
  name: string;
  role: ProjectRole;
  status: ProjectStatus;
}

export interface ProjectSummary {
  id: string;
  name: string;
  businessAppId: string;
  status: ProjectStatus;
  /** Caller's role in the project; null when super_admin sees a project they don't belong to. */
  role: ProjectRole | null;
  /** Both scope dimensions and the member count come with the list, so the
   *  administration table shows what a project grants without an N+1 fan-out. */
  lzScope: string[];
  /** Landing-zone ids the grants actually resolve to — what a monitoring filter
   *  matches. `lzScope` holds the registered values, which a scope mutation has
   *  to address but which may be subscription ids; a workspace-only project has
   *  no registered LZ at all yet still covers the workspace's landing zone.
   *  Filter selectors on this, never on `lzScope`. */
  effectiveLzScope: string[];
  dbxScope: string[];
  memberCount: number;
}

export interface ProjectDetail extends ProjectSummary {
  createdBy: string;
  createdAt: string;
  validatedBy: string | null;
  validatedAt: string | null;
  /** Why a platform admin rejected the project (or a request). */
  decisionReason: string | null;
}

export interface ProjectMember {
  userId: string;
  displayName: string;
  role: ProjectRole;
  addedAt: string;
}

export interface ProjectJoinRequest {
  id: string;
  projectId: string;
  userId: string;
  displayName: string;
  requestedRole: ProjectRole;
  status: ProjectRequestStatus;
  justification: string | null;
  requestedAt: string;
}

export interface ProjectScopeRequest {
  id: string;
  projectId: string;
  scopeType: ProjectScopeType;
  scopeRef: string;
  status: ProjectRequestStatus;
  justification: string | null;
  requestedBy: string;
  requestedAt: string;
}

export interface ProjectCreatePayload {
  businessAppId: string;
  name: string;
  lzScope: string[];
  dbxScope: string[];
}

export interface ProjectJoinRequestCreatePayload {
  requestedRole?: ProjectRole;
  justification?: string;
}

export interface ProjectMemberAddPayload {
  email: string;
  role?: ProjectRole;
}

/** One landing zone / workspace asked for inside a scope request. */
export interface ProjectScopeRequestItemPayload {
  scopeType: ProjectScopeType;
  scopeRef: string;
}

/**
 * `POST /projects/{id}/scope-requests` body — one submission, several items.
 *
 * The backend writes one row per item and shares `requestedAt` + `justification`
 * across them, so the review queue can present the batch as a single request
 * while a platform admin can still grant part of it.
 */
export interface ProjectScopeRequestCreatePayload {
  items: ProjectScopeRequestItemPayload[];
  justification?: string;
}

export interface ProjectRequestDecisionPayload {
  decision: Extract<ProjectRequestStatus, 'approved' | 'rejected'>;
  /** Required by the backend when rejecting: the requester is told why. */
  reason?: string;
}

/** `POST /projects/{id}/reject` body — the reason is mandatory. */
export interface ProjectRejectPayload {
  reason: string;
}

// ─── Self-service register / join from the login page (feature 016) ──────────
// Self-service register / join: the caller is signed in (Entra token), so the
// backend derives the requester identity from the token — no email in the body.
// Wire format is camelCase, mirroring `/v1/projects*`.

/** One additional member declared in the Register form (not the requester). */
export interface ProjectRegisterMemberPayload {
  email: string;
  role: ProjectRole;
}

export interface ProjectRegisterPayload {
  businessAppId: string;
  name: string;
  members: ProjectRegisterMemberPayload[];
  lzScope: string[];
  dbxScope: string[];
}

export interface ProjectRegisterResponse {
  id: string;
  name: string;
  businessAppId: string;
  status: ProjectStatus;
  requesterEmail: string;
  memberCount: number;
}

export interface ProjectJoinPublicPayload {
  projectId: string;
  justification?: string;
}

export interface ProjectJoinPublicResponse {
  requestId: string;
  projectId: string;
  status: ProjectRequestStatus;
  routedTo: 'admins' | 'creator';
  recipientIds: string[];
}

export type NotificationMinSeverity = 'info' | 'warning' | 'critical';

export interface UserNotificationPreferences {
  show_pipeline: boolean;
  show_cluster: boolean;
  show_cost: boolean;
  show_security: boolean;
  show_governance: boolean;
  show_collector_status: boolean;
  min_severity: NotificationMinSeverity;
  hide_info: boolean;
  email_enabled: boolean;
  teams_digest_enabled: boolean;
  /** Empty = all landing zones the user can access. */
  notification_lz_ids: string[];
  updated_at: string | null;
  is_default: boolean;
}

export type UserNotificationPreferencesUpdate = Omit<
  UserNotificationPreferences,
  'updated_at' | 'is_default'
>;

export interface AdminUser {
  id: string;
  entra_oid: string;
  email: string;
  display_name: string | null;
  role: DcmRole;
  /** Platform tier — the authority every administration guard reads (feature 015). */
  platform_role: PlatformRole;
  is_active: boolean;
  created_at: string | null;
  last_login_at: string | null;
  lz_ids: string[];
  projects: AdminUserProject[];
}

// A user's project membership as shown in the Admin "Projects" editor — the
// effective data-access key (feature 016). `role` is the project role.
export interface AdminUserProject {
  id: string;
  name: string;
  role: ProjectRole;
  status: ProjectStatus;
}

// Body item for `PUT /admin/users/{id}/projects` (snake_case, like the rest of
// the admin API).
export interface AdminUserProjectInput {
  project_id: string;
  role: ProjectRole;
}

export type AdminUsersResponse = PaginatedResponse<AdminUser>;

export interface EntraIDUser {
  id: string;
  userPrincipalName: string;
  displayName: string;
  mail: string | null;
  jobTitle: string | null;
}

export interface EntraIDUsersResponse {
  items: EntraIDUser[];
  total: number;
  query: string;
}

export type AccessRequestType = 'new_account' | 'reactivation' | 'scope_extension';

export interface AccessRequest {
  id: string;
  email: string;
  display_name: string;
  entra_oid: string | null;
  justification: string;
  requested_lz_ids: string[];
  status: 'pending' | 'approved' | 'rejected';
  request_type: AccessRequestType;
  requested_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
}

export interface AccessRequestsResponse {
  items: AccessRequest[];
  total: number;
  pending_total: number;
  limit: number;
  offset: number;
}

export interface AccessRequestCreate {
  email: string;
  display_name: string;
  entra_oid?: string;
  justification: string;
  requested_lz_ids?: string[];
}

export interface LzScopeRequestCreate {
  requested_lz_ids: string[];
  justification: string;
}

export interface AdminLandingZone {
  lz_id: string;
  display_name: string;
  cloud_provider: CloudProvider;
  region: string | null;
  environment: string | null;
  ba_name: string | null;
  collector_names: string[];
  is_active: boolean;
  registered_at: string | null;
  registered_by: string | null;
  notes: string | null;
  user_count: number;
}

export interface AdminLandingZonesResponse {
  items: AdminLandingZone[];
  total: number;
}

export interface NotificationChannel {
  id: string;
  name: string;
  channel_type: NotificationChannelType;
  config: Record<string, unknown>;
  is_active: boolean;
  created_by: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface NotificationChannelsResponse {
  items: NotificationChannel[];
  total: number;
}

export interface AdminAlertRule {
  id: string;
  name: string;
  description: string | null;
  metric_domain: string;
  condition_field: string;
  condition_operator: string;
  condition_threshold: number;
  eval_window_hours: number;
  severity: AdminAlertSeverity;
  applies_to_lz_ids: string[];
  notification_channel_ids: string[];
  cooldown_minutes: number;
  is_active: boolean;
  created_by: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface AlertRulesResponse {
  items: AdminAlertRule[];
  total: number;
}

export interface AlertRuleTestResult {
  would_fire: boolean;
  measured_value: number | null;
  threshold: number;
  evaluated_at: string;
  results_by_lz?: Array<{
    lz_id: string;
    would_fire: boolean;
    measured_value: number | null;
  }>;
}

export interface AlertFiring {
  id: string;
  rule_id: string;
  lz_id: string;
  fired_at: string | null;
  resolved_at: string | null;
  measured_value: number | null;
  notification_sent: boolean;
  notification_error: string | null;
}

export interface AlertFiringsResponse {
  items: AlertFiring[];
  total: number;
}

export interface CollectorStatus {
  lz_id: string;
  collector_name: string;
  last_run_at: string | null;
  last_run_status: string | null;
  last_run_duration_s: number | null;
  metrics_collected: number | null;
  last_error: string | null;
  updated_at: string | null;
  is_stale: boolean;
}

export interface CollectorStatusResponse {
  items: CollectorStatus[];
  total: number;
}

export interface KpiConfigItem {
  config_key: string;
  config_value: number;
  description: string | null;
  updated_by: string | null;
  updated_at: string | null;
}

export interface KpiConfigResponse {
  items: KpiConfigItem[];
  values: Record<string, number>;
}

export interface RetentionPolicy {
  metric_table: string;
  retention_days: number;
  updated_by: string | null;
  updated_at: string | null;
}

export interface RetentionPoliciesResponse {
  items: RetentionPolicy[];
  values: Record<string, number>;
}

export interface RetentionStatsItem extends RetentionPolicy {
  num_files: number | null;
  size_in_bytes: number | null;
}

export interface RetentionStatsResponse {
  items: RetentionStatsItem[];
  total: number;
}

export interface MaintenanceWindow {
  id: string;
  name: string;
  description: string | null;
  lz_ids: string[];
  starts_at: string | null;
  ends_at: string | null;
  suppress_alerts: boolean;
  created_by: string;
  created_at: string | null;
}

export interface MaintenanceWindowsResponse {
  items: MaintenanceWindow[];
  total: number;
}

export interface AuditLogEntry {
  id: string;
  actor_user_id: string;
  action: string;
  target_type: string;
  target_id: string | null;
  before_state: string | null;
  after_state: string | null;
  ip_address: string | null;
  created_at: string | null;
}

export type AuditLogResponse = PaginatedResponse<AuditLogEntry>;

// ─── Talk-to-Data Chat ───────────────────────────────────────────────────────

export type ChatMessageRole = 'user' | 'assistant';

export interface ChatMessage {
  role: ChatMessageRole;
  content: string;
}

export interface ChatRequest {
  messages: ChatMessage[];
}

export interface ChatResponse {
  intent: string;
  thinking_steps: string[];
  text: string;
  source_label: string;
  sources: string[];
}

// ─── Lakeflow (Databricks Workflows) Overview ────────────────────────────────

export type LakeflowWindow = 'today' | '7d' | '30d' | 'custom';

export interface LakeflowSparklinePoint {
  t: string;
  v: number;
}

export interface LakeflowRunsByStatus {
  succeeded: number;
  failed: number;
  timed_out: number;
  cancelled: number;
}

export interface LakeflowActivity {
  concurrent_runs_active: number | null;
  concurrency_as_of: string | null;
  concurrency_sparkline: LakeflowSparklinePoint[];
  runs_total: number;
  runs_by_status: LakeflowRunsByStatus;
  runs_ko: number;
  runs_ko_delta: number | null;
  distinct_ko_workflows: number;
}

export interface LakeflowReliability {
  success_rate_24h_pct: number | null;
  success_rate_24h_n: number;
  success_rate_24h_delta: number | null;
  success_rate_7d_pct: number | null;
  success_rate_7d_n: number;
  success_rate_7d_delta: number | null;
  task_failure_rate_pct: number | null;
  tasks_failed: number;
  tasks_total: number;
}

export interface LakeflowPerformance {
  avg_duration_seconds: number | null;
  duration_drift_pct: number | null;
  baseline_avg_duration_seconds: number | null;
  p50: number | null;
  p95: number | null;
  p99: number | null;
  avg_queued_duration_seconds: number | null;
  avg_schedule_lag_seconds: number | null;
  max_schedule_lag_seconds: number | null;
}

export interface LakeflowTimelinePoint {
  date: string;
  succeeded: number;
  failed: number;
  timed_out: number;
  cancelled: number;
}

export interface LakeflowUnstableWorkflow {
  workflow_id: string;
  workflow_name: string;
  ko: number;
  total: number;
}

export interface LakeflowRecentError {
  workflow_name: string;
  run_id: string;
  start_time: string;
  error_message: string;
  run_page_url: string;
}

export interface LakeflowOverviewResponse {
  as_of: string;
  window: {
    key: LakeflowWindow;
    from: string;
    to: string;
    grain?: string;
  };
  activity: LakeflowActivity;
  reliability: LakeflowReliability;
  performance: LakeflowPerformance;
  timeline: LakeflowTimelinePoint[];
  top_unstable: LakeflowUnstableWorkflow[];
  recent_errors: LakeflowRecentError[];
}

// ─── Lakeflow Jobs (N1–N3) ───────────────────────────────────────────────────

export interface LakeflowJobHistoryBar {
  run_id: string;
  status: string | null;
  duration_seconds: number | null;
  start_time: string | null;
  retry_count: number | null;
}

export interface LakeflowJobListItem {
  workflow_id: string;
  workflow_name: string;
  source_lz_id: string | null;
  workspace_id: string | null;
  workspace_name: string | null;
  last_status: string | null;
  last_start_time: string | null;
  last_end_time: string | null;
  last_trigger_type: string | null;
  last_run_type: string | null;
  last_duration_seconds: number | null;
  owner: string | null;
  last_run_page_url: string | null;
  terminal_runs: number;
  succeeded_runs: number;
  failed_runs: number;
  timed_out_runs: number;
  cancelled_runs: number;
  success_rate_pct: number | null;
  success_rate_24h_pct: number | null;
  success_rate_24h_n: number;
  success_rate_7d_pct: number | null;
  success_rate_7d_n: number;
  avg_duration_seconds: number | null;
  duration_drift_pct: number | null;
  baseline_avg_14d: number | null;
  p50: number | null;
  p95: number | null;
  p99: number | null;
  avg_queued_duration_seconds: number | null;
  avg_schedule_lag_seconds: number | null;
  avg_retry_count: number | null;
  task_failure_rate_pct: number | null;
  /** Null when the job never ran on a JOB-type cluster (interactive/serverless only) — not the same as $0. */
  execution_cost_usd: number | null;
  history: LakeflowJobHistoryBar[];
  has_runs: boolean;
}

export interface LakeflowJobsListResponse {
  items: LakeflowJobListItem[];
  total: number;
  page: number;
  page_size: number;
  /** Sum of execution_cost_usd across every job matching the current filter, not just this page. */
  total_cost_usd: number | null;
  jobs_with_cost: number;
  window: { key: string; from: string; to: string };
  as_of?: string | null;
}

export interface LakeflowJobRun {
  run_id: string;
  workflow_id: string | null;
  workspace_id: string | null;
  source_lz_id: string | null;
  workspace_name: string | null;
  status: string | null;
  trigger_type: string | null;
  run_type: string | null;
  start_time: string | null;
  end_time: string | null;
  duration_seconds: number | null;
  queued_duration_seconds: number | null;
  execution_duration_seconds: number | null;
  schedule_lag_seconds: number | null;
  retry_count: number | null;
  tasks_total: number | null;
  tasks_failed: number | null;
  task_failure_rate: number | null;
  creator_user_name: string | null;
  cluster_instance_id: string | null;
  run_page_url: string | null;
  error_message: string | null;
  execution_date: string | null;
}

export interface LakeflowJobTask {
  run_id: string;
  task_id: string | null;
  task_key: string | null;
  status: string | null;
  start_time: string | null;
  end_time: string | null;
  duration_seconds: number | null;
  attempt_number: number | null;
  cluster_instance_id: string | null;
  error_message: string | null;
  execution_date: string | null;
}

export interface LakeflowJobDetailResponse {
  workflow: LakeflowJobListItem;
  window: { key: string; from: string; to: string };
}

export interface LakeflowJobRunsResponse {
  items: LakeflowJobRun[];
  total: number;
  page: number;
  page_size: number;
  matrix: {
    runs: LakeflowJobRun[];
    task_keys: string[];
    cells: Array<{
      run_id: string;
      task_key: string;
      status: string | null;
      duration_seconds: number | null;
    }>;
  };
  task_health: Array<{
    task_key: string;
    task_failure_rate_pct: number | null;
    p95_task_duration_seconds: number | null;
  }>;
  window: { key: string; from: string; to: string };
}

export interface LakeflowRunTasksResponse {
  run: LakeflowJobRun | null;
  items: LakeflowJobTask[];
  total: number;
}

// ─── Databricks Compute Metrics — Clusters ───────────────────────────────────

export interface ComputeMetricsPeriodRange {
  from: string;
  to: string;
}

/** The four rolling windows materialized in gold (`ROLLING_WINDOWS`). */
export type ComputeClusterWindowDays = 1 | 7 | 30 | 90;

/**
 * Window actually covered by a cluster list response. `from_date` and `to_date`
 * are read from the gold row (`window_start` / `as_of_date`) and are `null` when
 * no row is in scope — they are never derived from `today`.
 */
export interface ComputeClusterWindow {
  window_days: number;
  from_date: string | null;
  to_date: string | null;
}

export interface ComputeClustersOverviewKpis {
  total_cost_usd: number;
  cost_delta_pct: number | null;
  active_clusters: number;
  zombie_count: number;
  open_recommendations: number;
}

export interface ComputeClustersOverviewItem {
  cloud_provider: string;
  workspace_id: string;
  workspace_name: string | null;
  cluster_id: string;
  cluster_name: string | null;
  owner: string | null;
  cluster_type: string | null;
  cost_usd: number | null;
  cost_usd_prev_window: number | null;
  cost_delta_pct: number | null;
  cpu_util_p95_pct: number | null;
  idle_pct: number | null;
  uptime_hours: number | null;
  uptime_hours_prev_window: number | null;
  uptime_hours_delta_pct: number | null;
  utilization_status: string | null;
  severity: string | null;
}

export interface ComputeClustersOverviewResponse {
  kpis: ComputeClustersOverviewKpis;
  items: ComputeClustersOverviewItem[];
  /** Clusters matching the filters, all pages together — see `kpis.active_clusters`
   * for the count of clusters actually billed, which is a different number. */
  total: number;
  page: number;
  page_size: number;
  window: ComputeClusterWindow;
  period: ComputeMetricsPeriodRange;
}

export interface ComputeMetricsPage<TItem> {
  items: TItem[];
  total: number;
  page: number;
  page_size: number;
  period: ComputeMetricsPeriodRange;
}

/** A page read from a `*_rolling` table: it also legends the window it covers. */
export interface ComputeMetricsWindowedPage<TItem> extends ComputeMetricsPage<TItem> {
  window: ComputeClusterWindow;
}

export interface ComputeClusterCostItem {
  cloud_provider: string;
  workspace_id: string;
  workspace_name: string | null;
  cluster_id: string;
  cluster_name: string | null;
  owner: string | null;
  cost_center: string | null;
  sku_group: string | null;
  cluster_type: string | null;
  dbu_quantity: number | null;
  /** Unit cost of one DBU over the window; `null` when no DBU was billed. */
  dbu_cost: number | null;
  cost_usd: number | null;
  cost_usd_prev_window: number | null;
  cost_delta_pct: number | null;
  cost_rank: number | null;
  is_top_cost: boolean | null;
}

export type ComputeClustersCostResponse = ComputeMetricsWindowedPage<ComputeClusterCostItem>;

export interface ComputeClusterEfficiencyItem {
  cloud_provider: string;
  workspace_id: string;
  workspace_name: string | null;
  cluster_id: string;
  cluster_name: string | null;
  cluster_type: string | null;
  cpu_util_avg_pct: number | null;
  cpu_util_p95_pct: number | null;
  mem_util_avg_pct: number | null;
  mem_util_p95_pct: number | null;
  cpu_wait_avg_pct: number | null;
  idle_pct: number | null;
  idle_pct_prev_window: number | null;
  /** Variation in percentage *points* — never a per-cent variation. */
  idle_pct_delta_pts: number | null;
  uptime_hours: number | null;
  uptime_hours_prev_window: number | null;
  uptime_hours_delta_pct: number | null;
  worker_count_avg: number | null;
  /** Maximum observed per minute — not the configured autoscaling bound. */
  worker_count_max: number | null;
  autoscale_oscillation: number | null;
  autoscale_enabled: boolean | null;
  autoscale_min_workers: number | null;
  autoscale_max_workers: number | null;
  /** Set instead of the bounds above when the cluster has a fixed size. */
  configured_worker_count: number | null;
  driver_node_type: string | null;
  worker_node_type: string | null;
  is_zombie: boolean | null;
  utilization_status: string | null;
  recommended_node_type: string | null;
  rightsizing_reco: string | null;
  estimated_savings_usd: number | null;
}

export type ComputeClustersEfficiencyResponse =
  ComputeMetricsWindowedPage<ComputeClusterEfficiencyItem>;

export interface ComputeClusterGovernanceItem {
  cloud_provider: string;
  workspace_id: string;
  cluster_id: string;
  cluster_name: string | null;
  cluster_type: string | null;
  has_owner_tag: boolean | null;
  has_cost_center_tag: boolean | null;
  dbr_version: string | null;
  dbr_is_lts_current: boolean | null;
  node_oversized: boolean | null;
  is_single_node: boolean | null;
  recommended_action: string | null;
  severity: string | null;
  generated_at?: string | null;
}

export type ComputeClustersGovernanceResponse = ComputeMetricsPage<ComputeClusterGovernanceItem>;

export interface ComputeClusterDetailResponse {
  cloud_provider: string;
  workspace_id: string;
  cluster_id: string;
  cost: ComputeClusterCostItem | null;
  efficiency: ComputeClusterEfficiencyItem | null;
  governance: ComputeClusterGovernanceItem | null;
  window: ComputeClusterWindow;
  period: ComputeMetricsPeriodRange;
}

export type ComputeMetricTrendGranularity = 'day' | 'week' | 'month';

export interface ComputeClusterCostTrendPoint {
  bucket: string;
  cost_usd: number;
  dbu_quantity: number;
}

export interface ComputeClusterCostTrendResponse {
  items: ComputeClusterCostTrendPoint[];
  period: ComputeMetricsPeriodRange;
  granularity: ComputeMetricTrendGranularity;
}

export interface ComputeClusterLifetimeTrendPoint {
  bucket: string;
  uptime_hours: number;
  /** `null` — not `0` — when no day of the bucket carries a measure. */
  idle_pct: number | null;
}

export interface ComputeClusterLifetimeTrendResponse {
  items: ComputeClusterLifetimeTrendPoint[];
  period: ComputeMetricsPeriodRange;
  granularity: ComputeMetricTrendGranularity;
}

// ─── Databricks Compute Metrics — SQL Warehouses ─────────────────────────────

/**
 * The warehouse list views read the same four gold windows as the clusters, so
 * they share the types rather than re-declaring them: two identical unions would
 * be free to drift apart the day a fifth window is materialized.
 */
export type ComputeWarehouseWindowDays = ComputeClusterWindowDays;
export type ComputeWarehouseWindow = ComputeClusterWindow;

export interface ComputeWarehousesOverviewKpis {
  total_cost_usd: number;
  cost_delta_pct: number | null;
  active_warehouses: number;
  query_count: number;
  failed_count: number;
  open_recommendations: number;
}

export interface ComputeWarehousesOverviewItem {
  cloud_provider: string;
  source_lz_id: string;
  workspace_id: string;
  /** `workspace_name` as joined in gold — authoritative when present. */
  workspace_name: string | null;
  warehouse_id: string;
  warehouse_name: string | null;
  warehouse_size: string | null;
  /**
   * Compute form of the warehouse: `SERVERLESS`, `PRO` or `CLASSIC`. Three values and not
   * the `is_serverless` boolean below, because "not serverless" is not something a user
   * can act on — a pro warehouse and a classic one are configured and priced differently.
   *
   * `null` in two cases the UI shows the same way, as an em dash: the warehouse is billed
   * over the window but absent from the utilization snapshot, or its declared form
   * contradicts what it was billed as. Both are genuinely unknown, and defaulting either
   * to `CLASSIC` would state something gold does not.
   */
  warehouse_type: string | null;
  /**
   * Whether the warehouse is billed as serverless. Kept alongside `warehouse_type` rather
   * than replaced by it: this is the flag the backend keys the *arithmetic* off — which
   * efficiency figures are void, which savings cannot be cashed — while `warehouse_type`
   * is the vocabulary the Type column reads in. The two can never contradict each other.
   */
  is_serverless: boolean | null;
  cost_usd: number | null;
  query_count: number | null;
  failure_rate_pct: number | null;
  latency_p95_ms: number | null;
}

export interface ComputeWarehousesOverviewResponse {
  kpis: ComputeWarehousesOverviewKpis;
  items: ComputeWarehousesOverviewItem[];
  /** Warehouses matching the filters, all pages together — see `kpis.active_warehouses`
   * for the count of warehouses actually billed, which is a different number. */
  total: number;
  page: number;
  page_size: number;
  window: ComputeWarehouseWindow;
  period: ComputeMetricsPeriodRange;
}

export interface ComputeWarehouseCostItem {
  cloud_provider: string;
  source_lz_id: string;
  workspace_id: string;
  warehouse_id: string;
  warehouse_name: string | null;
  warehouse_size: string | null;
  dbu_quantity: number | null;
  cost_usd: number | null;
  /** Cost over the window of the same length immediately before. `null` — never
   * `0` — when the warehouse had no predecessor window. */
  cost_usd_prev_window: number | null;
  cost_delta_pct: number | null;
  query_count: number | null;
  cost_per_query_usd: number | null;
  top_consumer: string | null;
  /** First day covered by the window, read from gold. */
  window_start: string | null;
  /** Day the snapshot was computed — the window's last day. */
  as_of_date: string | null;
}

export type ComputeWarehousesCostResponse = ComputeMetricsWindowedPage<ComputeWarehouseCostItem>;

/**
 * What `/warehouses/{id}` returns: that endpoint still reads
 * `warehouse_cost_daily`, so it carries a day and its day-over-day comparison,
 * not a window. Typed apart so a window field cannot be read off a daily row.
 */
export type ComputeWarehouseCostSnapshot = Omit<
  ComputeWarehouseCostItem,
  'cost_usd_prev_window' | 'window_start' | 'as_of_date'
> & {
  cost_usd_prev_day: number | null;
  period_start: string | null;
};

export interface ComputeWarehouseQueryPerformanceItem {
  cloud_provider: string;
  source_lz_id: string;
  workspace_id: string;
  warehouse_id: string;
  warehouse_name: string | null;
  query_count: number | null;
  failed_count: number | null;
  failure_rate_pct: number | null;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  latency_p99_ms: number | null;
  queue_time_avg_ms: number | null;
  queue_time_p95_ms: number | null;
  spill_query_count: number | null;
  cache_hit_pct: number | null;
  bytes_scanned: number | null;
  rows_scanned: number | null;
  top_slow_statement_id: string | null;
  window_start: string | null;
  as_of_date: string | null;
}

export type ComputeWarehousesQueryPerformanceResponse =
  ComputeMetricsWindowedPage<ComputeWarehouseQueryPerformanceItem>;

/** Same split as {@link ComputeWarehouseCostSnapshot}, for the daily perf table. */
export type ComputeWarehouseQueryPerformanceSnapshot = Omit<
  ComputeWarehouseQueryPerformanceItem,
  'window_start' | 'as_of_date'
> & {
  period_start: string | null;
};

export interface ComputeWarehouseSlowQueryItem {
  cloud_provider: string;
  source_lz_id: string;
  workspace_id: string;
  warehouse_id: string;
  statement_id: string;
  warehouse_name: string | null;
  executed_by: string | null;
  start_time: string | null;
  duration_ms: number | null;
  status: string | null;
  reason: string | null;
  error_message: string | null;
  query_profile_url: string | null;
}

export interface ComputeWarehousesSlowQueriesResponse {
  enabled: boolean;
  items: ComputeWarehouseSlowQueryItem[];
  total: number;
  page: number;
  page_size: number;
  period: ComputeMetricsPeriodRange;
}

export interface ComputeWarehouseDetailResponse {
  cloud_provider: string | null;
  source_lz_id: string | null;
  workspace_id: string | null;
  warehouse_id: string;
  cost: ComputeWarehouseCostSnapshot | null;
  query_performance: ComputeWarehouseQueryPerformanceSnapshot | null;
  period: ComputeMetricsPeriodRange;
}

export interface ComputeWarehouseCostTrendResponse {
  items: ComputeClusterCostTrendPoint[];
  period: ComputeMetricsPeriodRange;
  granularity: ComputeMetricTrendGranularity;
}

// ─── Databricks Compute Metrics — Job compute (grain job_id) ─────────────────

/**
 * The job and pipeline list views read the same four gold windows as the
 * clusters and warehouses, so they reuse the window types rather than
 * re-declaring a union free to drift apart.
 */
export type ComputeJobWindowDays = ComputeClusterWindowDays;
export type ComputeJobWindow = ComputeClusterWindow;

/**
 * One pre-aggregated row per stable `job_id` and per window, read from
 * `gold_dbx_compute_job_cluster_cost_rolling`. Job clusters are ephemeral (a new
 * `cluster_id` per run), so the unit is the job, never the cluster. No
 * `source_lz_id`: the gold table is keyed on `workspace_id`.
 */
export interface ComputeJobCostItem {
  cloud_provider: string;
  workspace_id: string;
  job_id: string;
  /**
   * Which compute billed the job over the window: `CLASSIC`, `SERVERLESS`, or
   * `MIXED` when it billed both. A **label**, not a row dimension — the backend
   * collapses the gold grain back to one row per job, so this never duplicates a
   * job in the list. `ComputePipelineCostItem.compute_kind` is the opposite: there
   * it passes the gold grain through and a pipeline can appear twice.
   */
  compute_kind?: string | null;
  /** `job_name` joined in gold, already falling back to the id when empty. */
  job_name: string | null;
  /** Distinct job clusters seen over the window — the run count, not a live count. */
  cluster_count: number | null;
  dbu_quantity: number | null;
  cost_usd: number | null;
  /** Cost over the window of the same length immediately before. `null` — never
   * `0` — when the job had no predecessor window. */
  cost_usd_prev_window: number | null;
  cost_delta_pct: number | null;
  cost_rank: number | null;
  is_top_cost: boolean | null;
  /** First day covered by the window, read from gold. */
  window_start: string | null;
  /** Day the snapshot was computed — the window's last day. */
  as_of_date: string | null;
}

/**
 * A row of the **overview** tab: the cost row, plus the utilization figures the
 * tab shows beside it, LEFT JOINed from `gold_dbx_compute_job_efficiency_rolling`.
 *
 * The four fields are nullable **as a block**: a job billed without a single
 * measured minute keeps its row (024 SC-005) and then reads `—` on all of them,
 * never `0` — `0 h` would claim the job never ran, and `0 %` that it ran flat out.
 */
export interface ComputeJobsOverviewItem extends ComputeJobCostItem {
  /** Cumulated uptime of the job's clusters over the window, in hours. */
  uptime_hours: number | null;
  uptime_hours_prev_window: number | null;
  /** Variation vs the previous window, in per cent — derived server-side. */
  uptime_hours_delta_pct: number | null;
  /** Sizing verdict: `OVER`, `UNDER`, `OPTIMAL`. */
  utilization_status: string | null;
}

export interface ComputeJobsOverviewKpis {
  total_cost_usd: number;
  cost_delta_pct: number | null;
  active_jobs: number;
}

export interface ComputeJobsOverviewResponse {
  kpis: ComputeJobsOverviewKpis;
  items: ComputeJobsOverviewItem[];
  /** Jobs matching the filters, all pages together — see `kpis.active_jobs` for
   * the count of jobs actually billed, which is a different number. */
  total: number;
  page: number;
  page_size: number;
  window: ComputeJobWindow;
  period: ComputeMetricsPeriodRange;
}

export type ComputeJobsCostResponse = ComputeMetricsWindowedPage<ComputeJobCostItem>;

/**
 * Utilization metrics of a stable grain whose clusters are ephemeral — a job or a
 * DLT pipeline. The two grains carry the **same** metric set (both roll up
 * `cluster_efficiency_daily`), so it is declared once: two copies would drift.
 *
 * No `is_zombie` and no `cluster_name`/`cluster_type`, unlike
 * {@link ComputeClusterEfficiencyItem}: a JOB or PIPELINE cluster dies with its run,
 * so the flag would be `false` on every row and read as a control that passes
 * (024 R8), and the grain aggregates as many clusters as it had runs.
 */
export interface ComputeStableGrainEfficiency {
  cloud_provider: string;
  workspace_id: string;
  /** Clusters seen over the window — the run count, not a live count. */
  cluster_count: number | null;
  cpu_util_avg_pct: number | null;
  cpu_util_p95_pct: number | null;
  mem_util_avg_pct: number | null;
  mem_util_p95_pct: number | null;
  cpu_wait_avg_pct: number | null;
  idle_pct: number | null;
  idle_pct_prev_window: number | null;
  /** Variation in percentage *points* — never a per-cent variation. */
  idle_pct_delta_pts: number | null;
  /** Uptime **cumulated** over the window's runs, not a lifetime. */
  uptime_hours: number | null;
  uptime_hours_prev_window: number | null;
  /** An amount of hours, so its variation reads in per cent. */
  uptime_hours_delta_pct: number | null;
  active_hours: number | null;
  worker_count_avg: number | null;
  /** Maximum observed per minute — not the configured autoscaling bound. */
  worker_count_max: number | null;
  autoscale_oscillation: number | null;
  driver_node_type: string | null;
  worker_node_type: string | null;
  autoscale_enabled: boolean | null;
  autoscale_min_workers: number | null;
  autoscale_max_workers: number | null;
  /** Set instead of the bounds above when the clusters have a fixed size. */
  configured_worker_count: number | null;
  utilization_status: string | null;
  recommended_node_type: string | null;
  rightsizing_reco: string | null;
  estimated_savings_usd: number | null;
  window_days: number | null;
  window_start: string | null;
  as_of_date: string | null;
}

/** Row of `gold_dbx_compute_job_efficiency_rolling` (grain `job_id`). */
export interface ComputeJobEfficiencyItem extends ComputeStableGrainEfficiency {
  job_id: string;
  job_name: string | null;
}

export type ComputeJobsEfficiencyResponse = ComputeMetricsWindowedPage<ComputeJobEfficiencyItem>;

/**
 * Drawer payload of one job. **No `governance` key** — governance is a
 * cluster-level snapshot and stays on the all-purpose grain (024 C2); a `null`
 * would read as "measured, nothing found".
 *
 * `efficiency` is `null` for a job billed without a `node_timeline` row: a normal
 * answer whose cost is still real, never a reason to hide the row.
 */
export interface ComputeJobDetailResponse {
  cloud_provider: string | null;
  workspace_id: string | null;
  job_id: string;
  cost: ComputeJobCostItem | null;
  efficiency: ComputeJobEfficiencyItem | null;
  window: ComputeJobWindow;
  period: ComputeMetricsPeriodRange;
}

/**
 * Bucket of the uptime trend of a stable grain. Both components stay `null` —
 * never `0` — on a bucket with no measured hour, `idle_pct` being uptime-weighted.
 */
export interface ComputeUptimeTrendPoint {
  bucket: string;
  uptime_hours: number | null;
  idle_pct: number | null;
}

export interface ComputeUptimeTrendResponse {
  items: ComputeUptimeTrendPoint[];
  period: ComputeMetricsPeriodRange;
  granularity: ComputeMetricTrendGranularity;
}

export type ComputeJobCostTrendResponse = ComputeClusterCostTrendResponse;
export type ComputeJobUptimeTrendResponse = ComputeUptimeTrendResponse;

// ─── Databricks Compute Metrics — Pipeline (DLT) compute (grain dlt_pipeline_id) ─

/**
 * One pre-aggregated row per Lakeflow/DLT `dlt_pipeline_id` and per window, read
 * from `gold_dbx_compute_pipeline_cost_rolling`. Billing-direct, so there is no
 * cluster resolution step and hence no `cluster_count` — the ephemeral PIPELINE
 * cluster is never the unit. No `source_lz_id`: the gold table is keyed on
 * `workspace_id`.
 *
 * The route serves the **classic** compute only: this page is about the DLT cluster
 * compute, and a serverless pipeline is billed without any cluster (024 T008).
 */
export interface ComputePipelineCostItem {
  cloud_provider: string;
  workspace_id: string;
  dlt_pipeline_id: string;
  /** `pipeline_name` joined in gold, already falling back to the id when empty. */
  pipeline_name: string | null;
  /**
   * `CLASSIC` on every served row — the endpoints filter it. Kept in the payload so a
   * reader can tell which compute the page is about; no column shows it, for the same
   * reason `Cluster type` left the all-purpose page: it repeats one value per row.
   */
  compute_kind?: string | null;
  dbu_quantity: number | null;
  cost_usd: number | null;
  cost_usd_prev_window: number | null;
  cost_delta_pct: number | null;
  cost_rank: number | null;
  is_top_cost: boolean | null;
  window_start: string | null;
  as_of_date: string | null;
}

/**
 * A row of the **overview** tab, same shape as {@link ComputeJobsOverviewItem} at
 * this grain: the cost row plus the utilization figures LEFT JOINed from
 * `gold_dbx_compute_pipeline_efficiency_rolling`. The four fields stay `null` on a
 * classic pipeline that `node_timeline` never sampled — measured on dev, 7 of 181
 * such pipelines, all under $0.55 (024 SC-005). Serverless pipelines are **not**
 * served at all since T008, so they are no longer the reason a row shows "—".
 */
export interface ComputePipelinesOverviewItem extends ComputePipelineCostItem {
  /** Cumulated uptime of the pipeline's updates over the window, in hours. */
  uptime_hours: number | null;
  uptime_hours_prev_window: number | null;
  /** Variation vs the previous window, in per cent — derived server-side. */
  uptime_hours_delta_pct: number | null;
  /** Sizing verdict: `OVER`, `UNDER`, `OPTIMAL`. */
  utilization_status: string | null;
}

export interface ComputePipelinesOverviewKpis {
  total_cost_usd: number;
  cost_delta_pct: number | null;
  active_pipelines: number;
}

export interface ComputePipelinesOverviewResponse {
  kpis: ComputePipelinesOverviewKpis;
  items: ComputePipelinesOverviewItem[];
  total: number;
  page: number;
  page_size: number;
  window: ComputeJobWindow;
  period: ComputeMetricsPeriodRange;
}

export type ComputePipelinesCostResponse = ComputeMetricsWindowedPage<ComputePipelineCostItem>;

/**
 * Row of `gold_dbx_compute_pipeline_efficiency_rolling`. `cluster_count` **is**
 * carried here, unlike {@link ComputePipelineCostItem}: the efficiency rollup goes
 * through the `cluster_id → dlt_pipeline_id` mapping, so it knows how many PIPELINE
 * clusters ran, while the cost rollup is billing-direct. The two counts may differ
 * for the same pipeline — distinct sources, nothing to reconcile in the UI.
 */
export interface ComputePipelineEfficiencyItem extends ComputeStableGrainEfficiency {
  dlt_pipeline_id: string;
  pipeline_name: string | null;
}

export type ComputePipelinesEfficiencyResponse =
  ComputeMetricsWindowedPage<ComputePipelineEfficiencyItem>;

/**
 * Drawer payload of one DLT pipeline — **no `governance` key** (024 C2).
 * `efficiency` is `null` for a serverless pipeline: billed, but never measured by
 * `node_timeline`. Measured in dev on the 30-day window: the most expensive such
 * pipeline was billed $941 — these rows are shown with "—", not hidden.
 */
export interface ComputePipelineDetailResponse {
  cloud_provider: string | null;
  workspace_id: string | null;
  dlt_pipeline_id: string;
  cost: ComputePipelineCostItem | null;
  efficiency: ComputePipelineEfficiencyItem | null;
  window: ComputeJobWindow;
  period: ComputeMetricsPeriodRange;
}

export type ComputePipelineCostTrendResponse = ComputeClusterCostTrendResponse;
export type ComputePipelineUptimeTrendResponse = ComputeUptimeTrendResponse;

// ─── Databricks Compute Metrics — Recommendations & Forecast ─────────────────

export interface ComputeRecommendationItem {
  recommendation_id: string;
  cloud_provider: string;
  source_lz_id?: string;
  workspace_id: string;
  object_type: string;
  object_id: string;
  object_name: string | null;
  category: string;
  mode: string | null;
  title: string | null;
  detail: string | null;
  recommended_action: string | null;
  estimated_savings_usd: number | null;
  /** Period-scoped actual spend for the object (cluster/warehouse cost daily). */
  actual_cost_usd: number | null;
  severity: string | null;
  personas: string[] | null;
  status: string;
  first_seen_date: string | null;
  last_seen_date: string | null;
}

export type ComputeRecommendationsResponse = ComputeMetricsPage<ComputeRecommendationItem>;

export interface ComputeRecommendationsSummaryResponse {
  open_count: number;
  open_savings_usd: number;
  /** Sum of cluster+warehouse cost_usd over the selected period (same scope). */
  period_actual_cost_usd: number;
  resolved_30d_count: number;
  high_severity_open_count: number;
  period: ComputeMetricsPeriodRange;
}

export type ComputeForecastMetricName =
  | 'cost_usd'
  | 'dbu_quantity'
  | 'cpu_util_p95_pct'
  | 'query_count'
  | 'queue_time_p95_ms';

export interface ComputeForecastPoint {
  cloud_provider: string | null;
  source_lz_id?: string | null;
  object_type: string;
  object_id: string;
  metric_name: string;
  horizon_date: string;
  predicted_value: number | null;
  lower_bound: number | null;
  upper_bound: number | null;
  method: string | null;
}

export interface ComputeForecastActualPoint {
  horizon_date: string;
  metric_name: string;
  actual_value: number;
}

export interface ComputeForecastResponse {
  items: ComputeForecastPoint[];
  /** Observed daily series (cost_usd / dbu_quantity) for historical vs forecast. */
  actuals?: ComputeForecastActualPoint[];
  period: ComputeMetricsPeriodRange;
  metrics: string[];
}

// ─── Databricks Compute Metrics — Serverless (025) ───────────────────────────

/**
 * `run_count` is `number | null` in every model below, and the `null` half is the
 * point: eleven of the twelve serverless surfaces do not count runs, and no gold row
 * carries `run_count = 0`. A `0` would claim "measured, nothing ran" for a surface
 * that never reports runs — hence "—" in the UI, never a zero.
 *
 * `serverless_surface` is typed `string` and not the twelve-value union: the union
 * lives in `lib/compute/serverless-surfaces.ts` as a display vocabulary with a
 * fallback, so a thirteenth value appearing in gold renders as itself instead of
 * making the compiler certify something the server never promised.
 */
export interface ComputeMetricsOptionalPeriodRange {
  from: string | null;
  to: string | null;
}

/**
 * Serverless share of compute spend, in **dollars** — never in DBUs: a serverless DBU
 * and a classic DBU are different units at different prices, so their ratio is a share
 * of nothing. `pct` is `null` rather than `100` when the classic denominator cannot be
 * read. `unclassified_warehouse_cost_usd` is warehouse spend absent from the
 * utilization snapshot: proven neither serverless nor classic, and published as such.
 */
export interface ComputeServerlessShareBlock {
  pct: number | null;
  serverless_cost_usd: number;
  classic_cost_usd: number;
  classic_cluster_cost_usd: number;
  classic_warehouse_cost_usd: number;
  unclassified_warehouse_cost_usd: number;
}

export interface ComputeServerlessOverviewKpis {
  cost_usd: number;
  /** `null` — not `0` — when there is nothing to compare to. */
  cost_usd_prev_window: number | null;
  cost_delta_pct: number | null;
  dbu_quantity: number;
  run_count: number | null;
  surface_count: number;
  object_count: number;
  cost_usd_without_identity: number | null;
  /** A different notion from `without_identity`: workspace-grain spend, not a defect. */
  cost_usd_without_object_key: number | null;
  budget_policy_coverage_pct: number | null;
  owner_tag_coverage_pct: number | null;
  serverless_share: ComputeServerlessShareBlock | null;
}

/**
 * `governance_period` is **not** `period`: governance is a 90-day snapshot on its own
 * cadence, while the KPIs follow the rolling window. Serving one range for both would
 * make a 90-day coverage figure look like it was measured over the selected days.
 */
export interface ComputeServerlessOverviewResponse {
  kpis: ComputeServerlessOverviewKpis;
  governance_period: ComputeMetricsOptionalPeriodRange | null;
  window: ComputeClusterWindow;
  period: ComputeMetricsPeriodRange;
}

export interface ComputeServerlessSurfaceItem {
  serverless_surface: string;
  cost_usd: number | null;
  cost_usd_prev_window: number | null;
  dbu_quantity: number | null;
  run_count: number | null;
  object_count: number | null;
  workspace_count: number | null;
  cost_usd_with_object_key: number | null;
  cost_delta_pct: number | null;
  share_pct: number | null;
  object_key_coverage_pct: number | null;
}

export interface ComputeServerlessSurfacesResponse {
  items: ComputeServerlessSurfaceItem[];
  total: number;
  page: number;
  page_size: number;
  total_cost_usd: number;
  window: ComputeClusterWindow;
  period: ComputeMetricsPeriodRange;
}

export interface ComputeServerlessCostTrendItem {
  bucket: string;
  /**
   * One of the top surfaces by spend, or `OTHER_SURFACES` — spelled with the suffix
   * because `OTHER` is itself one of the twelve real surfaces, and a bucket named
   * after it would be indistinguishable from it.
   */
  serverless_surface: string;
  cost_usd: number;
  dbu_quantity: number;
  run_count: number | null;
}

export interface ComputeServerlessCostTrendResponse {
  items: ComputeServerlessCostTrendItem[];
  /** Legend order, by total spend over the whole period — never by the last bucket. */
  series: string[];
  period: ComputeMetricsPeriodRange;
  granularity: ComputeMetricTrendGranularity;
}

export interface ComputeServerlessBudgetPolicyEntry {
  /** There is no policy **name**: `system.billing` exposes no budget-policy table. */
  budget_policy_id: string | null;
  cost_usd: number | null;
}

/**
 * Row of the governance snapshot, at the (workspace, surface) grain.
 *
 * `identity_source_mix` is an unweighted **set**: the carrying field changes by surface
 * (warehouses `OWNED_BY`, apps `CREATED_BY`, jobs and notebooks `RUN_AS`), and "owner"
 * and "runner" are not the same rechargeability semantics.
 */
export interface ComputeServerlessGovernanceItem {
  cloud_provider: string;
  workspace_id: string;
  serverless_surface: string;
  cost_usd: number | null;
  cost_usd_with_owner_tag: number | null;
  owner_tag_coverage_pct: number | null;
  cost_usd_with_cost_center_tag: number | null;
  cost_center_tag_coverage_pct: number | null;
  cost_usd_with_budget_policy: number | null;
  budget_policy_coverage_pct: number | null;
  cost_usd_without_identity: number | null;
  identity_coverage_pct: number | null;
  cost_usd_without_object_key: number | null;
  identity_source_mix: string[];
  /** `0` and not `null` when nothing is attached — a measured fact, not an unknown. */
  budget_policy_count: number;
  budget_policy_inventory: ComputeServerlessBudgetPolicyEntry[] | null;
}

/**
 * Footer of the governance table, over the **filtered** population and not the page —
 * so it does not change when the user pages. The percentages come from the server's
 * dollars: an average of per-workspace percentages is not the percentage of the whole.
 */
export interface ComputeServerlessGovernanceTotals {
  cost_usd: number;
  owner_tag_coverage_pct: number | null;
  cost_center_tag_coverage_pct: number | null;
  budget_policy_coverage_pct: number | null;
  identity_coverage_pct: number | null;
  cost_usd_without_identity: number;
  cost_usd_without_object_key: number | null;
}

export interface ComputeServerlessGovernanceResponse {
  items: ComputeServerlessGovernanceItem[];
  total: number;
  page: number;
  page_size: number;
  totals: ComputeServerlessGovernanceTotals;
  /** The snapshot's own span — read from gold, never derived from today. */
  governance_period: ComputeMetricsOptionalPeriodRange;
  period: ComputeMetricsPeriodRange;
}

/**
 * One serverless object over the window. `serverless_surface` is part of the identity
 * and not a label: the same `object_id` appears under two surfaces for a handful of the
 * 20 583 objects measured in dev, which is why the detail endpoints require it.
 */
export interface ComputeServerlessObjectItem {
  cloud_provider: string;
  workspace_id: string;
  serverless_surface: string;
  /**
   * `null` — with `has_object_key: false` — on a row that has no listable object: the
   * whole of `GENIE`, `NETWORKING`, `PLATFORM_AUTO` and `OTHER`, plus a residue inside
   * surfaces that do have one. Those rows carry real cost and are kept, but the detail
   * endpoint answers 404 for them, so the UI must not offer a drill-down.
   */
  object_id: string | null;
  object_name: string | null;
  billing_origin_product: string | null;
  performance_target: string | null;
  budget_policy_id: string | null;
  identity_principal: string | null;
  identity_source: string | null;
  has_custom_tags: boolean | null;
  has_object_key: boolean | null;
  dbu_quantity: number | null;
  cost_usd: number | null;
  cost_usd_prev_window: number | null;
  cost_delta_pct: number | null;
  run_count: number | null;
  cost_per_run_p50_usd: number | null;
  cost_per_run_p95_usd: number | null;
  cost_per_run_p99_usd: number | null;
  cost_rank: number | null;
  is_top_cost: boolean | null;
}

export interface ComputeServerlessObjectsResponse {
  items: ComputeServerlessObjectItem[];
  total: number;
  page: number;
  page_size: number;
  total_cost_usd: number;
  /** Distinct objects in the filtered perimeter — not the same number as `total`. */
  object_count: number;
  window: ComputeClusterWindow;
  period: ComputeMetricsPeriodRange;
}

/**
 * `performance_target` bucket. `null` is a **fourth** value and not missing data: gold
 * also emits `MIXED` for an object seen under more than one target, so the observed
 * values are `PERFORMANCE_OPTIMIZED`, `STANDARD`, `MIXED` and unset — the unset one
 * carrying most of the dollars, which is why hiding it would hide the lever.
 */
export interface ComputeServerlessPerformanceTargetItem {
  performance_target: string | null;
  cost_usd: number | null;
  dbu_quantity: number | null;
  run_count: number | null;
  object_count: number | null;
  row_count: number | null;
  share_pct: number | null;
}

export interface ComputeServerlessPerformanceTargetBlock {
  items: ComputeServerlessPerformanceTargetItem[];
  total_cost_usd: number;
  unset_share_pct: number | null;
}

/**
 * One histogram bucket, whose `run_count` is a real `0` — unlike everywhere else in
 * this section: an empty band is a measurement, not an unknown.
 */
export interface ComputeServerlessCostPerRunBucket {
  from_usd: number;
  /** `null` on the open-ended last bucket. */
  to_usd: number | null;
  run_count: number;
}

/** Cost per run, over the objects that actually count runs. Note `p90`, not `p95`. */
export interface ComputeServerlessCostPerRunBlock {
  object_count: number;
  run_count: number | null;
  p50_usd: number | null;
  p90_usd: number | null;
  p99_usd: number | null;
  max_usd: number | null;
  max_object_p99_usd: number | null;
  histogram: ComputeServerlessCostPerRunBucket[];
}

/**
 * Serverless vs classic DLT, **per cloud**.
 *
 * `comparable` is `false` — and `failure_rate_pct` then `null` — below `min_requests`:
 * a percentage read off six requests is noise shaped like a metric. Rates are per
 * **requested execution**, deduplicated by `request_id` and restricted to the window,
 * so they are a measure of a period and never a property of a compute form.
 */
export interface ComputeServerlessDltComparisonItem {
  cloud_provider: string;
  /** `CLASSIC_COMPUTE` or `SERVERLESS_COMPUTE`. */
  compute_type: string;
  requests: number;
  outcome_requests: number;
  failed_requests: number;
  canceled_requests: number;
  failure_rate_pct: number | null;
  comparable: boolean;
  duration_p50_sec: number | null;
  duration_p95_sec: number | null;
  pipeline_count: number | null;
  failing_pipeline_count: number | null;
  failure_concentration_pct: number | null;
}

export interface ComputeServerlessDltComparisonBlock {
  items: ComputeServerlessDltComparisonItem[];
  /** Below this many requests a row is served with `comparable = false`. */
  min_requests: number;
  /** How many pipelines `failure_concentration_pct` is computed over. */
  top_failing_pipelines: number;
  window: ComputeMetricsPeriodRange | null;
}

/**
 * Two of the three blocks are nullable, and not only on a broken warehouse:
 * `cost_per_run` needs objects that count runs, `dlt_comparison` publishes nothing
 * below its request floor. `null` means "not measurable on this perimeter", which the
 * page renders as a stated absence. `performance_target` always exists — an empty
 * bucket list is itself the answer.
 */
export interface ComputeServerlessLeversResponse {
  performance_target: ComputeServerlessPerformanceTargetBlock;
  cost_per_run: ComputeServerlessCostPerRunBlock | null;
  dlt_comparison: ComputeServerlessDltComparisonBlock | null;
  window: ComputeClusterWindow;
  period: ComputeMetricsPeriodRange;
}

export interface ComputeServerlessObjectIdentity {
  serverless_surface: string;
  object_id: string;
  object_name: string | null;
  has_object_key: boolean | null;
  billing_origin_product: string | null;
  workspace_count: number;
  cloud_providers: string[];
}

export interface ComputeServerlessObjectTotals {
  cost_usd: number | null;
  cost_usd_prev_window: number | null;
  cost_delta_pct: number | null;
  dbu_quantity: number | null;
  run_count: number | null;
  /** `null`, not `0`, when no run was counted. */
  cost_per_run_mean_usd: number | null;
  max_object_p99_usd: number | null;
}

export interface ComputeServerlessObjectWindowRow {
  window_days: number;
  cost_usd: number | null;
  cost_usd_prev_window: number | null;
  dbu_quantity: number | null;
  run_count: number | null;
}

/** The list row plus the two snapshot columns only the drawer shows. */
export interface ComputeServerlessObjectDetailRow extends ComputeServerlessObjectItem {
  window_start: string | null;
  as_of_date: string | null;
}

/**
 * One object: its identity, its totals, and the rows those totals were summed from.
 * `workspaces` is served rather than folded away because the same `object_id` is
 * legitimately billed in several workspaces, and one set of figures under a title
 * naming the object would silently be one workspace's.
 */
export interface ComputeServerlessObjectDetailResponse {
  object: ComputeServerlessObjectIdentity;
  totals: ComputeServerlessObjectTotals;
  workspaces: ComputeServerlessObjectDetailRow[];
  cost_per_run_histogram: ComputeServerlessCostPerRunBucket[];
  windows: ComputeServerlessObjectWindowRow[];
  window: ComputeClusterWindow;
  period: ComputeMetricsPeriodRange;
}

export interface ComputeServerlessObjectCostTrendItem {
  bucket: string;
  cost_usd: number;
  dbu_quantity: number;
  run_count: number | null;
}

export interface ComputeServerlessObjectCostTrendResponse {
  items: ComputeServerlessObjectCostTrendItem[];
  /** How many workspaces were folded into the series. */
  workspace_count: number;
  period: ComputeMetricsPeriodRange;
  granularity: ComputeMetricTrendGranularity;
}

// ─── Per-column filters (023 T004/T006) ──────────────────────────────────────

/**
 * The thirteen views the server allowlists for `column_filter` and `filter-options`.
 *
 * Spelled out rather than typed as `string`: the server answers 422 on an unknown
 * view, and a typo in a table declaration should surface at compile time instead of
 * as a runtime 422 the user sees as a broken combo.
 */
export type ComputeFilterView =
  | 'clusters-overview'
  | 'clusters-cost'
  | 'clusters-efficiency'
  | 'clusters-governance'
  | 'warehouses-overview'
  | 'warehouses-cost'
  | 'warehouses-query-performance'
  | 'warehouses-slow-queries'
  | 'recommendations'
  | 'lakeflow-jobs'
  | 'lakeflow-job-runs'
  // 025: served by the generic `/filter-options` route, which reads the same
  // `FILTERABLE_COLUMNS` map — there is deliberately no `/serverless/filter-options`.
  | 'serverless-objects'
  | 'serverless-governance';

/**
 * `enum` — distinct values read from the source, with their counts.
 * `text` — free text, listed only once `q` narrows it enough.
 * `numeric` — thresholds **declared by the server**, offered as-is and never
 * interpolated by the UI.
 */
export type ComputeFilterColumnKind = 'enum' | 'numeric' | 'text';

export interface ComputeFilterOption {
  value: string;
  label: string;
  /** Absent on `numeric` and on derived booleans: there is no row count to show. */
  count?: number;
}

export interface ComputeColumnFilterOptions {
  view: string;
  column: string;
  kind: ComputeFilterColumnKind;
  label: string;
  options: ComputeFilterOption[];
  /** `true` = the list is a prefix of the real one; the user must narrow with `q`. */
  truncated: boolean;
  /**
   * Sent as `false` only when the source could not be read at all. Omitted on
   * success, so `enabled === false` is the one case the combo must present as
   * "this list cannot be built" rather than "no value in your perimeter".
   */
  enabled?: boolean;
}

/**
 * One value per column key — the shape the server accepts. Repeating a key is a
 * 422 by design (it refuses to guess between AND and OR), so the client cannot
 * hold two values for one column either.
 */
export type ComputeColumnFilterValues = Record<string, string>;

// ─── Unity Catalog usage tracking — /api/v1/uc-usage (024) ───────────────────

/**
 * Bornes renvoyées telles que reçues par l'API. Absentes des endpoints snapshot
 * (registre, KPI gouvernance, recommandations), dont les tables sources ne
 * portent aucune date de période.
 */
export interface UcUsagePeriod {
  start: string;
  end: string;
}

export interface UcUsageChartPoint {
  date: string;
  value: number | null;
}

export interface UcUsageChartSeries {
  key: string;
  label: string;
  cloud_provider?: string | null;
  entity_count?: number;
  points: UcUsageChartPoint[];
}

export interface UcUsageChartRank {
  key: string;
  label: string;
  cloud_provider: string | null;
  value: number | null;
  share_pct: number | null;
  consumer_type?: string | null;
  distinct_tables?: number;
}

export interface UcUsageActivityMatrix {
  grain: 'day' | 'week';
  columns: UcUsagePeriod[];
  rows: Array<{
    key: string;
    label: string;
    cloud_provider: string | null;
    cells: Array<{ value: number | null; observed_days: number; expected_days: number }>;
  }>;
}

export interface UcUsageChartEnvelope {
  period: UcUsagePeriod;
  filters: { catalog: string | null; schema: string | null; tables: string[] };
  grain: 'day';
}

export interface UcUsageTableChartBase extends UcUsageChartEnvelope {
  series: UcUsageChartSeries[];
  ranking: UcUsageChartRank[];
  summary: {
    total: number | null;
    entity_count: number;
    unmeasured_entity_count: number;
    top_5_total: number | null;
    other_total: number | null;
    top_5_share_pct: number | null;
    top_10_share_pct: number | null;
  };
}

export interface UcUsageTableCharts extends UcUsageTableChartBase {
  activity: UcUsageActivityMatrix;
  single_table_consumers: UcUsageChartRank[];
  ranking_mode: 'tables' | 'consumers';
}

export interface UcUsageConsumerCharts extends UcUsageChartEnvelope {
  total_requests: number | null;
  by_type: Array<UcUsageChartSeries & { total: number | null; share_pct: number | null }>;
  ranking: UcUsageChartRank[];
  previous_period: UcUsagePeriod;
  active_consumers: Array<
    UcUsageChartPoint & {
      previous_date: string;
      previous_value: number | null;
    }
  >;
}

export interface UcUsageFinopsCharts extends UcUsageTableChartBase {
  unit_cost: Array<
    UcUsageChartPoint & {
      request_count: number | null;
      costed_request_count: number | null;
      coverage_pct: number | null;
      cost_attribution_method: string | null;
      cost_basis: string | null;
    }
  >;
  cost_coverage_pct: number | null;
  cost_attribution_method: string | null;
  cost_basis: string | null;
}

export interface UcUsageListEnvelope<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  period?: UcUsagePeriod;
}

export type UcUsageForecastMetric =
  | 'request_count'
  | 'distinct_consumers'
  | 'estimated_cost_usd'
  | 'data_read_bytes';

export interface UcUsageForecastPoint {
  horizon_date: string | null;
  predicted_value: number | null;
  lower_bound: number | null;
  upper_bound: number | null;
}

/** Point **mesuré** de la période : un `null` reste un trou, jamais un zéro. */
export interface UcUsageObservedPoint {
  period_start: string | null;
  value: number | null;
}

export interface UcUsageForecastSeries {
  metric_name: UcUsageForecastMetric;
  /** Réalisé de la période appliquée — vide tant qu'aucune période n'est posée. */
  observed?: UcUsageObservedPoint[];
  points: UcUsageForecastPoint[];
}

/** Volume **observé**, jamais projeté : un `null` reste un `null`. */
export interface UcUsageWrittenBytesPoint {
  period_start: string | null;
  data_written_bytes: number | null;
}

export type UcUsageRecommendationCategory =
  | 'LIFECYCLE'
  | 'FRESHNESS'
  | 'GOVERNANCE'
  | 'RELIABILITY'
  | 'FINOPS';

export interface UcUsageRecommendation {
  recommendation_id: string;
  cloud_provider: string | null;
  object_type: string;
  object_id: string;
  object_name: string | null;
  category: string;
  mode: string | null;
  title: string;
  detail: string | null;
  recommended_action: string | null;
  /** Renseigné pour la seule catégorie LIFECYCLE « inutilisée » (FR-014). */
  estimated_savings_usd: number | null;
  severity: string;
  personas: string[];
  status: string;
  first_seen_date: string | null;
  last_seen_date: string | null;
  age_days: number | null;
}

export interface UcUsageOverview {
  tracked_tables: number | null;
  request_count: number | null;
  request_count_delta_pct: number | null;
  distinct_consumers: number | null;
  estimated_cost_usd: number | null;
  estimated_cost_usd_delta_pct: number | null;
  unused_tables: number | null;
  access_failure_rate_pct: number | null;
  trends: UcUsageForecastSeries[];
  written_bytes_series: UcUsageWrittenBytesPoint[];
  attention: UcUsageRecommendation[];
  period: UcUsagePeriod;
}

/**
 * Cycle de vie d'une table du catalogue Unity Catalog (spec 027). Présent sur
 * toute ressource de grain table, que la table soit supprimée ou non :
 * `is_deleted` n'est jamais nul, et `deleted_at` ne l'est que pour une table
 * vivante ou dont la date de suppression n'a pas été observée.
 */
export interface UcUsageLifecycle {
  is_deleted: boolean;
  deleted_at: string | null;
  lifecycle_state: 'ACTIVE' | 'DELETED' | 'UNKNOWN';
}

export interface UcUsageTableRow extends UcUsageLifecycle {
  table_full_name: string;
  catalog: string | null;
  schema: string | null;
  table_name: string | null;
  table_type: string | null;
  request_count: number | null;
  request_delta_pct: number | null;
  distinct_consumers: number | null;
  data_read_bytes: number | null;
  data_written_bytes?: number | null;
  rows_written?: number | null;
  estimated_cost_usd: number | null;
  cost_attribution_method: string | null;
  cost_basis: string | null;
  catalog_resolution_status: string | null;
  last_used_at: string | null;
  query_count: number | null;
  failed_count: number | null;
  failure_rate_pct: number | null;
  latency_p95_ms: number | null;
  freshness_lag_hours: number | null;
  freshness_basis: string | null;
  last_write_at: string | null;
}

export interface UcUsageTopConsumerRow {
  rank: number;
  consumer_id: string;
  consumer_name: string | null;
  /** Vocabulaire **ouvert** : une valeur inconnue s'affiche telle quelle. */
  consumer_type: string | null;
  request_count: number | null;
  estimated_cost_usd: number | null;
  last_used_at: string | null;
}

export interface UcUsageTopConsumersResponse extends UcUsageLifecycle {
  table_full_name: string;
  items: UcUsageTopConsumerRow[];
  period: UcUsagePeriod;
}

export interface UcUsageConsumerRow {
  rank: number | null;
  consumer_id: string;
  consumer_name: string | null;
  consumer_type: string | null;
  distinct_tables: number | null;
  request_count: number | null;
  data_read_bytes: number | null;
  data_written_bytes?: number | null;
  rows_written?: number | null;
  estimated_cost_usd: number | null;
  last_used_at: string | null;
}

export interface UcUsageFinopsTopCostlyTable {
  table_full_name: string;
  estimated_cost_usd: number | null;
}

export interface UcUsageFinopsKpis {
  total_cost_usd: number | null;
  request_count: number | null;
  costed_tables: number | null;
  avg_cost_per_request_usd: number | null;
  /** Toujours `true` : le dénominateur compte aussi les requêtes non chiffrées. */
  is_lower_bound: boolean;
  top_costly_table: UcUsageFinopsTopCostlyTable | null;
  period: UcUsagePeriod;
}

export interface UcUsageCostByTableRow extends UcUsageLifecycle {
  table_full_name: string;
  estimated_cost_usd: number | null;
  request_count: number | null;
  data_read_bytes: number | null;
  cost_per_request_usd: number | null;
  /** `null` pour une table sans ligne de prévision — jamais `0` (SC-005). */
  forecast_cost_usd_7d: number | null;
}

export interface UcUsageGovernanceKpis {
  unused_tables: number | null;
  stale_but_consumed_tables: number | null;
  critical_tables: number | null;
  tracked_tables: number | null;
}

export interface UcUsageRegistryRow extends UcUsageLifecycle {
  cloud_provider?: string | null;
  table_full_name: string;
  catalog: string | null;
  schema: string | null;
  table_name: string | null;
  table_type: string | null;
  /** `null` quand le tag UC est absent — l'UI affiche « Non renseigné ». */
  owner: string | null;
  last_operation: string | null;
  last_operation_at: string | null;
  last_operation_by: string | null;
  downstream_fanout: number | null;
  days_since_last_read: number | null;
  is_unused: boolean | null;
  is_orphan: boolean | null;
  is_stale_but_consumed: boolean | null;
  is_critical: boolean | null;
  recommended_action: string | null;
  severity: string | null;
}

export interface UcUsageRecommendationCounts {
  open_high: number | null;
  open_medium: number | null;
  open_total: number | null;
  estimated_savings_usd: number | null;
}

export interface UcUsageRecommendationsResponse extends UcUsageListEnvelope<UcUsageRecommendation> {
  counts: UcUsageRecommendationCounts;
}

export type UcUsageGovernanceSignal =
  | 'unused'
  | 'stale'
  | 'critical'
  | 'orphan'
  | 'unused_critical';
export type UcUsageInactivityBucket = '0_7' | '8_30' | '31_90' | 'over_90' | 'unobserved';
export type UcUsageMissingTag = 'owner' | 'domain' | 'cost_center' | 'classification';
export type UcUsageRecommendationAgeBucket = '0_7' | '8_30' | '31_90' | 'over_90' | 'unknown';

export interface UcUsageGovernancePoint {
  cloud_provider: string | null;
  table_full_name: string;
  catalog: string | null;
  schema: string | null;
  table_name: string | null;
  days_since_last_read: number | null;
  downstream_fanout: number | null;
  is_unused: boolean | null;
  is_critical: boolean | null;
  is_stale_but_consumed: boolean | null;
}

export interface UcUsageGovernanceMatrixRow {
  catalog: string | null;
  schema: string | null;
  cloud_provider: string | null;
  table_full_name: string | null;
  table_name: string | null;
  table_count: number;
  signals: Record<Exclude<UcUsageGovernanceSignal, 'unused_critical'>, number>;
}

export interface UcUsageGovernanceCharts {
  as_of: string | null;
  summary: {
    tracked_tables: number;
    unused_tables: number;
    stale_but_consumed_tables: number;
    critical_tables: number;
    orphan_tables: number;
    unused_critical_tables: number;
  };
  inactivity: Array<{ bucket: UcUsageInactivityBucket; count: number }>;
  tag_coverage: Array<{
    tag: UcUsageMissingTag;
    present_count: number;
    missing_count: number;
    unknown_count: number;
    total_count: number;
    coverage_pct: number | null;
  }>;
  matrix: {
    mode: 'table' | 'schema';
    total_rows: number;
    limit: number;
    rows: UcUsageGovernanceMatrixRow[];
  };
  scatter: {
    total: number;
    limit: number;
    unobserved_reads: number;
    points: UcUsageGovernancePoint[];
  };
}

export interface UcUsageSeverityDistribution {
  bucket: string;
  HIGH: number;
  MEDIUM: number;
  LOW: number;
  UNKNOWN: number;
  total: number;
}

export interface UcUsageRecommendationPriority {
  cloud_provider: string | null;
  table_full_name: string;
  open_total: number;
  open_high: number;
  open_medium: number;
  open_low: number;
  open_unknown: number;
  oldest_high_days: number | null;
  downstream_fanout: number | null;
}

export interface UcUsageRecommendationCharts {
  as_of: string | null;
  summary: {
    open_total: number;
    open_high: number;
    open_medium: number;
    affected_tables: number;
    old_high: number;
    reference_cost_usd: number | null;
    cost_candidates: number;
    cost_measured_tables: number;
  };
  categories: UcUsageSeverityDistribution[];
  ages: UcUsageSeverityDistribution[];
  priorities: UcUsageRecommendationPriority[];
}

export interface UcUsageForecastSeriesResponse {
  series: UcUsageForecastSeries[];
}

export interface UcUsageAttentionResponse {
  items: UcUsageRecommendation[];
}

export interface UcUsageFilterTableOption extends UcUsageLifecycle {
  table_full_name: string;
  catalog: string | null;
  schema: string | null;
}

/**
 * Valeurs proposables par les filtres, lues dans le registre du parc et non
 * dans les lignes affichées : les vues paginent côté serveur.
 */
export interface UcUsageFilterOptions {
  catalogs: string[];
  schemas: string[];
  tables: UcUsageFilterTableOption[];
  /** Liste plafonnée : le sélecteur invite alors à chercher. */
  truncated: boolean;
  limit: number;
}

export interface UcUsageDailyMetrics {
  date: string;
  request_count: number | null;
  data_read_bytes: number | null;
  data_written_bytes: number | null;
  rows_written: number | null;
  estimated_cost_usd: number | null;
}
export interface UcUsageEntitySelection {
  kind: 'table' | 'consumer';
  id: string;
  label: string;
}
export interface UcUsageEntityDetail extends UcUsageLifecycle {
  period: UcUsagePeriod;
  entity_kind: 'table' | 'consumer';
  entity_id: string;
  summary: Omit<UcUsageDailyMetrics, 'date'> & {
    observed_rows: number;
    counterpart_count: number;
    active_days: number;
    write_days: number;
  };
  daily: UcUsageDailyMetrics[];
  counterparts: Array<Omit<UcUsageDailyMetrics, 'date'> & { id: string; label: string }>;
}
export interface UcUsageWriteCharts {
  period: UcUsagePeriod;
  summary: {
    data_written_bytes: number | null;
    rows_written: number | null;
    tables_with_writes: number;
    written_without_reads: number;
  };
  daily: UcUsageDailyMetrics[];
  ranking: Array<{
    key: string;
    label: string;
    cloud_provider: string | null;
    value: number | null;
    rows_written: number | null;
    request_count: number | null;
  }>;
}
export interface UcUsageCostChanges {
  period: UcUsagePeriod;
  previous_period: UcUsagePeriod;
  current_total: number | null;
  previous_total: number | null;
  entity_count: number;
  items: Array<{
    key: string;
    label: string;
    cloud_provider: string | null;
    current_cost: number | null;
    previous_cost: number | null;
    delta_usd: number | null;
    delta_pct: number | null;
  }>;
}
