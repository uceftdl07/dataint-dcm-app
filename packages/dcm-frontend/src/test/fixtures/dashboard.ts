import type {
  ComputeResponse,
  CostSummary,
  DashboardFullResponse,
  DashboardOverview,
  DatabasesResponse,
  GovernanceScore,
  PipelineListResponse,
  SecurityAlertsResponse,
} from '../../types/api';

const period = {
  start: '2026-04-25',
  end: '2026-05-25',
};

export const dashboardOverviewFixture: DashboardOverview = {
  total_pipelines: 42,
  total_adf_pipelines: 30,
  total_databricks_pipelines: 12,
  failed_pipelines_24h: 2,
  failed_databricks_jobs_24h: 2,
  active_clusters: 3,
  active_sql_warehouses: 4,
  as_of: '2026-05-25T10:30:00Z',
  cost_ytd_usd: 12500.5,
  cost_ytd_previous_year_usd: 10000,
  cost_ytd_delta_usd: 2500.5,
  cost_ytd_delta_pct: 25.005,
  cost_ytd_monthly: [
    { month: '2026-01', current_year_usd: 2100, previous_year_usd: 1800 },
    { month: '2026-02', current_year_usd: 2300, previous_year_usd: 1900 },
    { month: '2026-03', current_year_usd: 2500, previous_year_usd: 2000 },
    { month: '2026-04', current_year_usd: 2700, previous_year_usd: 2100 },
    { month: '2026-05', current_year_usd: 2900.5, previous_year_usd: 2200 },
  ],
  alert_breakdown: { critical: 1, high: 0, medium: 2, low: 0 },
  total_cost_usd: 1250.5,
  open_alerts: 3,
  cloud_coverage: ['azure', 'aws'],
  period,
};

export const governanceScoreFixture: GovernanceScore = {
  global_score_pct: 87,
  compliant_count: 13,
  no_compliant_count: 2,
  total_evaluated: 15,
  by_landing_zone: [],
};

export const costSummaryFixture: CostSummary = {
  total_usd: 1250.5,
  by_cloud: {
    azure: 950.25,
    aws: 300.25,
  },
  by_service: [
    {
      service_name: 'Databricks',
      cloud_provider: 'azure',
      cost_usd: 850,
    },
  ],
  period,
};

export const pipelineListFixture: PipelineListResponse = {
  items: [
    {
      run_id: 'run-1',
      pipeline_id: 'pipe-1',
      pipeline_name: 'Daily ingestion',
      cloud_provider: 'azure',
      source_lz_id: 'lz-001',
      pipeline_type: 'adf',
      trigger_type: 'schedule',
      status: 'succeeded',
      start_time: '2026-05-25T08:00:00Z',
      end_time: '2026-05-25T08:05:00Z',
      duration_seconds: 300,
      error_message: null,
    },
  ],
  total: 1,
  limit: 8,
  offset: 0,
};

export const computeResponseFixture: ComputeResponse = {
  items: [
    {
      compute_resource_id: 'cluster-1',
      resource_name: 'analytics-cluster',
      compute_type: 'databricks',
      cloud_provider: 'azure',
      source_lz_id: 'lz-001',
      subscription_or_account_id: 'sub-001',
      workspace_id: 'workspace-001',
      state: 'running',
      num_workers: 4,
      autoscale_min: 2,
      autoscale_max: 8,
      node_type: 'Standard_DS3_v2',
      spark_version: '14.3',
      avg_cpu_utilization_pct: 35,
      avg_mem_utilization_pct: 60,
      tags: {},
      collected_at: '2026-05-25T08:10:00Z',
    },
  ],
};

export const databasesResponseFixture: DatabasesResponse = {
  items: [
    {
      db_id: 'db-1',
      db_name: 'monitoring',
      db_type: 'postgresql',
      server_name: 'db-server',
      region: 'westeurope',
      availability_zone: null,
      cloud_provider: 'azure',
      source_lz_id: 'lz-001',
      subscription_or_account_id: 'sub-001',
      cpu_percent: 21,
      memory_percent: 45,
      storage_used_gb: 120,
      storage_limit_gb: 512,
      storage_cost_impact_usd: 80,
      active_connections: 12,
      is_available: true,
      tags: {},
      collected_at: '2026-05-25T08:10:00Z',
      ingested_at: '2026-05-25T08:11:00Z',
    },
  ],
};

export const securityAlertsResponseFixture: SecurityAlertsResponse = {
  items: [
    {
      alert_id: 'alert-1',
      cloud_provider: 'azure',
      source_lz_id: 'lz-001',
      severity: 'high',
      title: 'Public storage account',
      description: 'A storage account allows public access.',
      status: 'active',
      resource_id: 'storage-1',
      resource_type: 'storage',
      detected_at: '2026-05-25T08:00:00Z',
    },
  ],
  total: 1,
  limit: 8,
  offset: 0,
};

export const dashboardFullFixture: DashboardFullResponse = {
  overview: dashboardOverviewFixture,
  governance: governanceScoreFixture,
  costs: costSummaryFixture,
  pipelines: pipelineListFixture.items,
  computes: computeResponseFixture.items,
  databases: databasesResponseFixture.items,
  alerts: securityAlertsResponseFixture.items,
};
