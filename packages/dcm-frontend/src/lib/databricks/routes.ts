const DATABRICKS_MODULE_ROUTES = [
  '/databricks',
  '/unitycatalogexplorer',
  '/data-product-usage',
  '/monitoringreports',
] as const;

const DATABRICKS_INSIGHTS_ROUTE_PREFIX = '/databricks/insights';

/**
 * Routes du module Usage des tables UC. Les huit tables `gold_dbx_usage_*` ne
 * portent ni `workspace_id` ni `source_lz_id`, et une table Unity Catalog
 * n'appartient pas à un workspace : les filtres Workspace / LZ du bandeau n'y
 * filtreraient rien tout en laissant croire le contraire (FR-010, FR-019). Le
 * sélecteur de période, lui, reste — c'est lui qu'alimente Appliquer.
 */
const UC_USAGE_ROUTES = ['/databricks/usage-tables', '/databricks/usage-governance'] as const;

export function isUcUsageRoute(pathname: string): boolean {
  return UC_USAGE_ROUTES.some((route) => pathname === route || pathname.startsWith(`${route}/`));
}

function isDatabricksRoute(pathname: string): boolean {
  return pathname === '/databricks' || pathname.startsWith('/databricks/');
}

export function isDatabricksInsightsRoute(pathname: string): boolean {
  return (
    pathname === DATABRICKS_INSIGHTS_ROUTE_PREFIX ||
    pathname.startsWith(`${DATABRICKS_INSIGHTS_ROUTE_PREFIX}/`)
  );
}

export function isDatabricksModuleRoute(pathname: string): boolean {
  return DATABRICKS_MODULE_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`)
  );
}

export function showsDatabricksWorkspaceFilter(pathname: string): boolean {
  if (isDatabricksInsightsRoute(pathname) || isUcUsageRoute(pathname)) {
    return false;
  }
  return isDatabricksRoute(pathname);
}

export function showsGlobalHeaderFilters(pathname: string): boolean {
  if (pathname.startsWith('/talk-to-data') || pathname === '/admin') {
    return false;
  }
  return !isDatabricksInsightsRoute(pathname);
}

/**
 * Show the landing-zone filter on every module page that carries global header
 * filters (Databricks pages included).
 *
 * Workspace-keyed Databricks tables (`gold_dbx_workflow_*`, `gold_dbx_compute_*`)
 * carry no `source_lz_id`, so the backend resolves the selected landing zone to
 * its Databricks workspaces (`dim_dbx_workspace` ⋈ `dim_landing_zone`) and
 * narrows on `workspace_id` instead. The control therefore scopes every
 * Databricks page, and each route still resolves its own authorization scope
 * server-side — showing it never widens what a caller may read.
 */
export function showsLandingZoneFilter(pathname: string): boolean {
  if (isUcUsageRoute(pathname)) {
    return false;
  }
  return showsGlobalHeaderFilters(pathname);
}

/**
 * Pages dont **aucun** tableau ne lit une plage de dates libre : chacun lit un
 * instantané pré-agrégé par fenêtre (Daily / 7d / 30d / 90d), choisie sur la page.
 *
 * Le serveur reçoit encore `period_start`/`period_end` sur ces routes, mais ne fait
 * que les renvoyer dans le bloc `period` de la réponse : un sélecteur de dates dans
 * l'en-tête n'y filtre rien et laisse croire le contraire. Les endpoints qui, eux,
 * filtrent vraiment sur des bornes (requêtes lentes, détail et courbes du tiroir)
 * les calculent depuis la page.
 */
const PREDEFINED_WINDOW_ROUTES = [
  '/databricks/cluster',
  '/databricks/sql-warehouse',
  '/databricks/job-compute',
  '/databricks/pipeline-compute',
  // Serverless (025) : mêmes instantanés par fenêtre, plus un pavé de gouvernance
  // qui est un instantané 90 jours sans fenêtre du tout — deux raisons pour qu'un
  // sélecteur de dates d'en-tête n'y filtre rien.
  '/databricks/serverless',
] as const;

export function showsGlobalHeaderDateRange(pathname: string): boolean {
  if (!showsGlobalHeaderFilters(pathname)) {
    return false;
  }
  return !PREDEFINED_WINDOW_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`)
  );
}

/** Hide 30d/90d/6m/1y presets on Overview — keep From/To for custom ranges. */
export function showsGlobalHeaderTimePresets(pathname: string): boolean {
  // Les presets écrivent dans la **même** plage que From/To : là où elle est
  // masquée, les afficher seuls laisserait un contrôle qui ne filtre rien.
  if (!showsGlobalHeaderDateRange(pathname)) {
    return false;
  }
  return pathname !== '/databricks/overview';
}
