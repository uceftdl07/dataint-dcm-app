/** Maps routes and UI blocks to DCM permission keys (mirrors dcm_role_permissions). */

export const ROUTE_PERMISSIONS: Record<string, string> = {
  '/dashboard': 'page:dashboard',
  '/datafactory': 'page:datafactory',
  '/pipelines': 'page:pipelines',
  '/datafactoryalerts': 'page:alerts',
  '/datafactoryfinops': 'page:costs',
  '/datafactorygovernance': 'page:governance',
  '/databricks': 'page:databricks',
  '/databricks/overview': 'page:databricks',
  '/databricks/pipelines': 'page:databricks',
  '/databricks/workflows': 'page:databricks',
  '/databricks/cluster': 'page:databricks',
  '/databricks/sql-warehouse': 'page:databricks',
  '/databricks/job-compute': 'page:databricks',
  '/databricks/pipeline-compute': 'page:databricks',
  '/databricks/serverless': 'page:databricks',
  '/databricks/compute/recommendations': 'page:databricks',
  '/databricks/finops-v2': 'page:databricks',
  '/databricks/data-product-usage': 'page:databricks',
  // Raw-table explorer — unscopeable, so it follows the admin-only permission the
  // backend enforces with ``require_unrestricted_scope``, not ``page:databricks``.
  '/unitycatalogexplorer': 'page:unity-catalog',
  // Mêmes motifs : les 8 tables `gold_dbx_usage_*` ne portent ni `source_lz_id`
  // ni `workspace_id`, donc aucun filtrage par lignes n'est exprimable (FR-021).
  '/databricks/usage-tables': 'page:unity-catalog',
  '/databricks/usage-governance': 'page:unity-catalog',
  '/data-product-usage': 'page:databricks',
  '/monitoringreports': 'page:databricks',
  '/databases': 'page:databases',
  '/databasealerts': 'page:alerts',
  '/databasefinops': 'page:costs',
  '/databasegovernance': 'page:governance',
  '/clusters': 'page:clusters',
  '/costs': 'page:costs',
  '/alerts': 'page:alerts',
  '/security': 'page:security',
  '/governance': 'page:governance',
  '/users': 'page:users',
  '/projects': 'page:projects',
  '/admin': 'page:admin',
  '/talk-to-data': 'page:talk-to-data',
  '/status': 'page:status',
  '/settings': 'page:settings',
};

export const DASHBOARD_WIDGET_PERMISSIONS = {
  pipelines: 'widget:dashboard:pipelines',
  failures: 'widget:dashboard:failures',
  clusters: 'widget:dashboard:clusters',
  costTotal: 'widget:dashboard:cost_total',
  alerts: 'widget:dashboard:alerts',
  governance: 'widget:dashboard:governance',
  datafactoryCard: 'widget:dashboard:datafactory_card',
  databricksCard: 'widget:dashboard:databricks_card',
  databasesCard: 'widget:dashboard:databases_card',
  finopsCard: 'widget:dashboard:finops_card',
} as const;

export type DashboardWidgetKey = keyof typeof DASHBOARD_WIDGET_PERMISSIONS;
