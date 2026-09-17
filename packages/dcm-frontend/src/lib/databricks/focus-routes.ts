import type { DatabricksFocusView } from './focus-view';
import type { ComputeState } from '../../types/api';

const GLOBAL_ROUTE_PREFIXES = ['/clusters', '/costs', '/alerts', '/security', '/governance', '/dashboard', '/pipelines'];

export function isDatabricksScopedPath(path: string): boolean {
  const pathname = path.split('?')[0]?.split('#')[0] ?? path;
  return pathname === '/databricks' || pathname.startsWith('/databricks/');
}

export function assertDatabricksWidgetTarget(path: string): string {
  if (!isDatabricksScopedPath(path)) {
    throw new Error(`Databricks widget navigation must stay under /databricks/**, got: ${path}`);
  }
  if (GLOBAL_ROUTE_PREFIXES.some((prefix) => path === prefix || path.startsWith(`${prefix}/`))) {
    throw new Error(`Databricks widget navigation must not target global pages, got: ${path}`);
  }
  return path;
}

export function buildDatabricksFocusPath(
  view: DatabricksFocusView,
  params?: { state?: ComputeState; jobStatus?: string },
): string {
  const search = new URLSearchParams();
  if (params?.state) {
    search.set('state', params.state);
  }
  if (params?.jobStatus) {
    search.set('jobStatus', params.jobStatus);
  }
  const query = search.toString();
  return assertDatabricksWidgetTarget(`/databricks/${view}${query ? `?${query}` : ''}`);
}

/** Canonical /databricks/** module pages (menu + legacy redirects). */
export const DATABRICKS_MODULE_FOCUS_PATHS = {
  alerts: assertDatabricksWidgetTarget('/databricks/alerts'),
  costs: assertDatabricksWidgetTarget('/databricks/finops'),
  governance: assertDatabricksWidgetTarget('/databricks/governance'),
  overview: '/databricks',
} as const;

/** All Databricks dashboard widget click targets (acceptance: /databricks/** only). */
export const DATABRICKS_WIDGET_TARGETS = {
  workspaces: buildDatabricksFocusPath('workspaces'),
  landingZones: buildDatabricksFocusPath('workspaces'),
  clusters: buildDatabricksFocusPath('clusters'),
  running: buildDatabricksFocusPath('clusters', { state: 'running' }),
  errors: buildDatabricksFocusPath('clusters', { state: 'error' }),
  jobs: buildDatabricksFocusPath('jobs'),
  securityAlerts: DATABRICKS_MODULE_FOCUS_PATHS.alerts,
  governance: DATABRICKS_MODULE_FOCUS_PATHS.governance,
  averageCpu: buildDatabricksFocusPath('clusters'),
  averageMemory: buildDatabricksFocusPath('clusters'),
  databricksCost: DATABRICKS_MODULE_FOCUS_PATHS.costs,
  clusterHourly: buildDatabricksFocusPath('clusters'),
} as const;

export function assertAllDatabricksWidgetTargetsScoped(): void {
  for (const path of Object.values(DATABRICKS_WIDGET_TARGETS)) {
    assertDatabricksWidgetTarget(path);
  }
}
