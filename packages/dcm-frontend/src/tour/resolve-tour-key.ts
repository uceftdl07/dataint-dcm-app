/** Map current pathname to a stable tour definition key. */
export function resolveTourKey(pathname: string): string {
  const routes: Array<{ pattern: RegExp; key: string }> = [
    { pattern: /^\/dashboard$/, key: 'dashboard' },
    { pattern: /^\/datafactory$/, key: 'datafactory' },
    { pattern: /^\/datafactory\//, key: 'datafactory-focus' },
    { pattern: /^\/pipelines$/, key: 'pipelines' },
    { pattern: /^\/pipelines\//, key: 'pipelines-focus' },
    { pattern: /^\/datafactoryalerts$/, key: 'datafactory-alerts' },
    { pattern: /^\/datafactoryfinops$/, key: 'datafactory-finops' },
    { pattern: /^\/datafactorygovernance$/, key: 'datafactory-governance' },
    { pattern: /^\/databricks$/, key: 'databricks' },
    { pattern: /^\/databricks\//, key: 'databricks-focus' },
    { pattern: /^\/unitycatalogexplorer$/, key: 'unity-catalog' },
    { pattern: /^\/data-product-usage$/, key: 'data-product-usage' },
    { pattern: /^\/data-product-usage\//, key: 'data-product-usage-focus' },
    { pattern: /^\/monitoringreports$/, key: 'monitoring-reports' },
    { pattern: /^\/databases$/, key: 'databases' },
    { pattern: /^\/databases\//, key: 'databases-focus' },
    { pattern: /^\/databasealerts$/, key: 'database-alerts' },
    { pattern: /^\/databasefinops$/, key: 'database-finops' },
    { pattern: /^\/databasegovernance$/, key: 'database-governance' },
    { pattern: /^\/clusters$/, key: 'clusters' },
    { pattern: /^\/clusters\//, key: 'clusters-focus' },
    { pattern: /^\/costs$/, key: 'costs' },
    { pattern: /^\/costs\//, key: 'costs-focus' },
    { pattern: /^\/alerts$/, key: 'alerts' },
    { pattern: /^\/alerts\//, key: 'alerts-focus' },
    { pattern: /^\/security$/, key: 'security' },
    { pattern: /^\/governance$/, key: 'governance' },
    { pattern: /^\/users$/, key: 'users' },
    { pattern: /^\/talk-to-data$/, key: 'talk-to-data' },
    { pattern: /^\/status$/, key: 'status' },
    { pattern: /^\/settings$/, key: 'settings' },
    { pattern: /^\/admin$/, key: 'admin' },
  ];

  const match = routes.find((route) => route.pattern.test(pathname));
  return match?.key ?? 'generic';
}

export function pageHasGlobalFilters(tourKey: string): boolean {
  return !['talk-to-data', 'admin'].includes(tourKey);
}

export function pageHasWorkspaceFilter(tourKey: string): boolean {
  return (
    tourKey === 'databricks' ||
    tourKey === 'databricks-focus' ||
    tourKey.startsWith('databricks-') ||
    tourKey === 'unity-catalog' ||
    tourKey === 'data-product-usage' ||
    tourKey === 'data-product-usage-focus' ||
    tourKey === 'monitoring-reports'
  );
}
