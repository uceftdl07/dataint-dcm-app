import type { ComponentType } from 'react';

export interface ProtectedRouteDefinition {
  path: string;
  importPage: () => Promise<{ default: ComponentType }>;
}

export const protectedRoutes = [
  { path: '/dashboard', importPage: () => import('./pages/Dashboard') },
  { path: '/pipelines', importPage: () => import('./pages/Pipelines') },
  { path: '/pipelines/:view', importPage: () => import('./pages/PipelinesFocusPage') },
  { path: '/datafactory', importPage: () => import('./pages/DataFactory') },
  { path: '/datafactory/:view', importPage: () => import('./pages/DataFactoryFocusPage') },
  { path: '/datafactoryalerts', importPage: () => import('./pages/DataFactoryAlerts') },
  { path: '/datafactoryfinops', importPage: () => import('./pages/DataFactoryFinOps') },
  { path: '/datafactorygovernance', importPage: () => import('./pages/DataFactoryGovernance') },
  { path: '/clusters', importPage: () => import('./pages/Clusters') },
  { path: '/clusters/:view', importPage: () => import('./pages/ClustersFocusPage') },
  { path: '/costs', importPage: () => import('./pages/Costs') },
  { path: '/costs/:view', importPage: () => import('./pages/CostsFocusPage') },
  { path: '/alerts', importPage: () => import('./pages/Alerts') },
  { path: '/alerts/:view', importPage: () => import('./pages/AlertsFocusPage') },
  { path: '/databases', importPage: () => import('./pages/Databases') },
  { path: '/databases/:view', importPage: () => import('./pages/DatabaseFocusPage') },
  { path: '/databasealerts', importPage: () => import('./pages/DatabaseAlerts') },
  { path: '/databasefinops', importPage: () => import('./pages/DatabaseFinOps') },
  { path: '/databasegovernance', importPage: () => import('./pages/DatabaseGovernance') },
  { path: '/databricks', importPage: () => import('./pages/Databricks') },
  { path: '/databricks/overview', importPage: () => import('./pages/LakeflowOverview') },
  {
    path: '/databricks/insights/:slug',
    importPage: () => import('./pages/DatabricksInsightDetail'),
  },
  { path: '/databricks/insights', importPage: () => import('./pages/DatabricksInsights') },
  { path: '/databricks/finops', importPage: () => import('./pages/DatabricksFinOps') },
  { path: '/databricks/alerts', importPage: () => import('./pages/DatabricksAlerts') },
  { path: '/databricks/governance', importPage: () => import('./pages/DatabricksGovernance') },
  {
    path: '/databricks/pipelines',
    importPage: () => import('./pages/DatabricksComingSoon'),
  },
  {
    path: '/databricks/workflows',
    importPage: () => import('./pages/LakeflowJobs'),
  },
  {
    path: '/databricks/workflows/:workflowId/runs/:runId',
    importPage: () => import('./pages/LakeflowRunDetail'),
  },
  {
    path: '/databricks/workflows/:workflowId',
    importPage: () => import('./pages/LakeflowJobDetail'),
  },
  { path: '/databricks/cluster', importPage: () => import('./pages/ComputeClusters') },
  {
    path: '/databricks/sql-warehouse',
    importPage: () => import('./pages/ComputeSqlWarehouses'),
  },
  { path: '/databricks/job-compute', importPage: () => import('./pages/ComputeJobs') },
  {
    path: '/databricks/pipeline-compute',
    importPage: () => import('./pages/ComputePipelines'),
  },
  // Declared before `/databricks/:view` below, like every other static Databricks
  // route: the catch-all matches `serverless` as a `:view` and would render
  // `DatabricksFocusPage` instead of this page.
  { path: '/databricks/serverless', importPage: () => import('./pages/ComputeServerless') },
  {
    path: '/databricks/compute/recommendations',
    importPage: () => import('./pages/ComputeRecommendationsForecast'),
  },
  { path: '/databricks/finops-v2', importPage: () => import('./pages/DatabricksComingSoon') },
  {
    path: '/databricks/data-product-usage',
    importPage: () => import('./pages/DatabricksComingSoon'),
  },
  { path: '/databricks/usage-tables', importPage: () => import('./pages/UsageTablesUc') },
  {
    path: '/databricks/usage-governance',
    importPage: () => import('./pages/UsageGovernance'),
  },
  { path: '/databricks/:view', importPage: () => import('./pages/DatabricksFocusPage') },
  { path: '/unitycatalogexplorer', importPage: () => import('./pages/UnityCatalogExplorer') },
  { path: '/data-product-usage', importPage: () => import('./pages/DataProductUsage') },
  {
    path: '/data-product-usage/:view',
    importPage: () => import('./pages/DataProductUsageFocusPage'),
  },
  { path: '/monitoringreports', importPage: () => import('./pages/MonitoringReports') },
  { path: '/security', importPage: () => import('./pages/Security') },
  { path: '/governance', importPage: () => import('./pages/Governance') },
  { path: '/talk-to-data', importPage: () => import('./pages/TalkToYourData') },
  { path: '/admin', importPage: () => import('./pages/Admin') },
  { path: '/users', importPage: () => import('./pages/Users') },
  { path: '/projects', importPage: () => import('./pages/Projects') },
  { path: '/projects/:projectId', importPage: () => import('./pages/ProjectDetail') },
  { path: '/guide/lz-onboarding', importPage: () => import('./pages/LzOnboardingGuide') },
  { path: '/status', importPage: () => import('./pages/CollectionStatus') },
  { path: '/settings', importPage: () => import('./pages/Settings') },
] satisfies ProtectedRouteDefinition[];

export const routeRedirects = [
  { from: '/talk-to-your-data', to: '/talk-to-data' },
  { from: '/collection-status', to: '/status' },
  { from: '/database', to: '/databases' },
  { from: '/database/dashboard', to: '/databases' },
  { from: '/database/alerts', to: '/databasealerts' },
  { from: '/database/finops', to: '/databasefinops' },
  { from: '/database/governance', to: '/databasegovernance' },
  { from: '/databricks-genie-obs', to: '/databricks/insights/genie-obs' },
  { from: '/databricksalerts', to: '/databricks/alerts' },
  { from: '/databricksfinops', to: '/databricks/finops' },
  { from: '/databricksgovernance', to: '/databricks/governance' },
  { from: '/databricks/security-alerts', to: '/databricks/alerts' },
  { from: '/databricks/costs', to: '/databricks/finops' },
] as const;
