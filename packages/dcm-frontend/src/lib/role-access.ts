/**
 * Client-side role matrix — mirrors tech-lead spec.
 * viewer / project member: read-only access to every DCM data interface,
 *   scoped to the project's LZ + Databricks workspaces by the backend.
 * admin: viewer scope + platform user management + Admin UI feature.
 * super_admin: admin + Admin UI page.
 */

import type {
  CurrentDcmUser,
  DcmPermissions,
  DcmRole,
  PlatformRole,
  ProjectRequestStatus,
  ProjectRole,
  ProjectScopeType,
  ProjectStatus,
} from '../types/api';
const P = {
  dashboard: 'page:dashboard',
  datafactory: 'page:datafactory',
  pipelines: 'page:pipelines',
  clusters: 'page:clusters',
  alerts: 'page:alerts',
  security: 'page:security',
  costs: 'page:costs',
  governance: 'page:governance',
  users: 'page:users',
  databricks: 'page:databricks',
  databases: 'page:databases',
  unityCatalog: 'page:unity-catalog',
  talkToData: 'page:talk-to-data',
  projects: 'page:projects',
  settings: 'page:settings',
  status: 'page:status',
  admin: 'page:admin',
  wPipelines: 'widget:dashboard:pipelines',
  wFailures: 'widget:dashboard:failures',
  wClusters: 'widget:dashboard:clusters',
  wCost: 'widget:dashboard:cost_total',
  wAlerts: 'widget:dashboard:alerts',
  wGovernance: 'widget:dashboard:governance',
  wFinops: 'widget:dashboard:finops_card',
  wDfCard: 'widget:dashboard:datafactory_card',
  wDbxCard: 'widget:dashboard:databricks_card',
  wDbCard: 'widget:dashboard:databases_card',
  fAdmin: 'feature:admin_ui',
} as const;

/** viewer / project member — read-only access to every DCM data interface. */
const VIEWER_ACCESS = [
  P.dashboard,
  P.datafactory,
  P.pipelines,
  P.databricks,
  P.databases,
  P.clusters,
  P.costs,
  P.alerts,
  P.security,
  P.governance,
  P.talkToData,
  P.status,
  P.projects,
  P.settings,
  P.wPipelines,
  P.wFailures,
  P.wClusters,
  P.wAlerts,
  P.wCost,
  P.wGovernance,
  P.wFinops,
  P.wDfCard,
  P.wDbxCard,
  P.wDbCard,
];

/** Legacy flat roles collapse onto the project viewer scope. */
const DATA_ARCHITECT_ACCESS = [...VIEWER_ACCESS];

/** Legacy flat roles collapse onto the project viewer scope. */
const MANAGER_ACCESS = [...VIEWER_ACCESS];

/**
 * admin — viewer scope + platform user management + Admin UI feature.
 * `P.unityCatalog` is admin-only: the raw-table explorer reads an arbitrary
 * `catalog.schema.table`, so the backend cannot narrow it to a project scope and
 * refuses it to project members (`require_unrestricted_scope`).
 */
const ADMIN_ACCESS = [...VIEWER_ACCESS, P.users, P.unityCatalog, P.fAdmin];

/** super_admin — admin + Admin UI page */
const SUPER_ADMIN_ACCESS = [...ADMIN_ACCESS, P.admin];

const ROLE_MATRIX: Record<DcmRole, readonly string[]> = {
  pending: [],
  viewer: VIEWER_ACCESS,
  data_architect: DATA_ARCHITECT_ACCESS,
  manager: MANAGER_ACCESS,
  admin: ADMIN_ACCESS,
  super_admin: SUPER_ADMIN_ACCESS,
};

export function buildPermissionsForRole(role: DcmRole | string | undefined): DcmPermissions {
  const resolved = (role && role in ROLE_MATRIX ? role : 'viewer') as DcmRole;
  const allowed = [...ROLE_MATRIX[resolved]];
  return {
    role: resolved,
    pages: allowed.filter((k) => k.startsWith('page:')),
    widgets: allowed.filter((k) => k.startsWith('widget:')),
    features: allowed.filter((k) => k.startsWith('feature:')),
    allowed,
  };
}

export function getDefaultHomeRoute(role: DcmRole | string | undefined): string {
  const permissions = buildPermissionsForRole(role);
  if (permissions.allowed.includes(P.dashboard)) return '/dashboard';
  if (permissions.allowed.includes(P.clusters)) return '/clusters';
  if (permissions.allowed.includes(P.pipelines)) return '/pipelines';
  return '/projects';
}

// ─── Two-level project access matrix (feature 015) ───────────────────────────
// Combines platform_role (platform tier) with the per-project role (project tier).
// A super_admin is implicitly admin of every project.

/**
 * True when the caller holds the platform super_admin tier.
 *
 * Mirrors `resolves_to_platform_admin` on the backend, including its transition
 * fallback: rows created before `platform_role` existed carry their authority in
 * the lifecycle `role`, so honouring both keeps the UI gate and the API guards
 * from disagreeing (a divergence used to grant `/admin` while every project
 * validation call 403-ed).
 */
export function isPlatformAdmin(user: CurrentDcmUser | null | undefined): boolean {
  return user?.platform_role === 'super_admin' || user?.role === 'super_admin';
}

/** Caller's role in a given project, or null when not a member. */
export function projectRoleFor(
  user: CurrentDcmUser | null | undefined,
  projectId: string
): ProjectRole | null {
  return user?.projects?.find((p) => p.project_id === projectId)?.role ?? null;
}

/** True when the caller may administer the project (super_admin or project admin). */
export function isProjectAdmin(
  user: CurrentDcmUser | null | undefined,
  projectId: string
): boolean {
  return isPlatformAdmin(user) || projectRoleFor(user, projectId) === 'admin';
}

/** True when the caller belongs to at least one active project. */
export function hasActiveProject(user: CurrentDcmUser | null | undefined): boolean {
  return Boolean(user?.projects?.some((p) => p.status === 'active'));
}

const PLATFORM_ROLE_LABELS: Record<PlatformRole, string> = {
  user: 'Member',
  super_admin: 'Platform admin',
};

const PROJECT_ROLE_LABELS: Record<ProjectRole, string> = {
  viewer: 'Project viewer',
  admin: 'Project admin',
};

const PROJECT_STATUS_LABELS: Record<ProjectStatus, string> = {
  pending_validation: 'Pending validation',
  active: 'Active',
  archived: 'Archived',
  rejected: 'Rejected',
};

const PROJECT_REQUEST_STATUS_LABELS: Record<ProjectRequestStatus, string> = {
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
};

const PROJECT_SCOPE_TYPE_LABELS: Record<ProjectScopeType, string> = {
  lz: 'Landing Zone',
  dbx_workspace: 'Databricks workspace',
};

export function platformRoleLabel(role: PlatformRole | undefined): string {
  return role ? PLATFORM_ROLE_LABELS[role] : PLATFORM_ROLE_LABELS.user;
}

export function projectRoleLabel(role: ProjectRole | null | undefined): string {
  return role ? PROJECT_ROLE_LABELS[role] : '—';
}

export function projectStatusLabel(status: ProjectStatus): string {
  return PROJECT_STATUS_LABELS[status];
}

/** Badge variant per project status — one mapping for every surface. */
export type ProjectStatusVariant = 'success' | 'warning' | 'secondary' | 'destructive';

const PROJECT_STATUS_VARIANTS: Record<ProjectStatus, ProjectStatusVariant> = {
  active: 'success',
  pending_validation: 'warning',
  archived: 'secondary',
  rejected: 'destructive',
};

export function projectStatusVariant(status: ProjectStatus): ProjectStatusVariant {
  return PROJECT_STATUS_VARIANTS[status];
}

export function projectRequestStatusLabel(status: ProjectRequestStatus): string {
  return PROJECT_REQUEST_STATUS_LABELS[status];
}

export function projectScopeTypeLabel(scopeType: ProjectScopeType): string {
  return PROJECT_SCOPE_TYPE_LABELS[scopeType];
}
