import {
  ChevronDown,
  Download,
  FolderKanban,
  KeyRound,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  Trash2,
  UserCog,
  UserPlus,
  Users,
  X,
} from 'lucide-react';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  createAlertRule,
  createAdminLandingZone,
  approveAdminUser,
  createAdminUser,
  createMaintenanceWindow,
  deactivateAdminLandingZone,
  deactivateAdminUser,
  deleteAdminUser,
  deleteAlertRule,
  deleteMaintenanceWindow,
  exportAuditLog,
  getDcmApiErrorMessage,
  patchAdminKpiConfig,
  patchRetentionPolicies,
  replaceAdminUserProjects,
  reviewAdminAccessRequest,
  testAlertRule,
  updateAdminUserRole,
  type AdminLandingZoneCreate,
  type AdminUserCreate,
  type AlertRuleCreate,
  type AuditLogParams,
  type MaintenanceWindowCreate,
} from '../api/dcmApiClient';
import { ListPagination } from '../components/domain/list-pagination';
import RequireAdmin from '../components/RequireAdmin';
import { EntraIDUserSelector } from '../components/EntraIDUserSelector';
import { AdminEmbeddedDashboardsTab } from '../components/AdminEmbeddedDashboardsTab';
import { AdminProjectsTab } from '../components/AdminProjectsTab';
import { useClientPagination } from '../hooks/useClientPagination';
import { useAdminQueries } from '../hooks/useAdminQueries';
import { useReferenceProjects } from '../hooks/useProjectsQueries';
import {
  Content,
  ContentActions,
  ContentDescription,
  ContentHeader,
  ContentMain,
} from '../components/layout/content';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { FieldLabel, Input, Select } from '../components/ui/input';
import { Skeleton } from '../components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { useToast } from '../hooks/useToast';
import { cn } from '../lib/utils';
import type {
  AccessRequest,
  AdminLandingZone,
  AdminAlertRule,
  AdminUser,
  AdminUserProject,
  AdminUserProjectInput,
  AuditLogEntry,
  CollectorStatus,
  DcmRole,
  KpiConfigItem,
  MaintenanceWindow,
  NotificationChannel,
  ProjectRole,
  RetentionPolicy,
  RetentionStatsItem,
} from '../types/api';

type AdminTabId =
  | 'users'
  | 'projects'
  | 'landing-zones'
  | 'alert-rules'
  | 'access-requests'
  | 'collectors'
  | 'kpi'
  | 'retention'
  | 'maintenance'
  | 'embedded-dashboards'
  | 'audit';

interface AdminData {
  users: AdminUser[];
  landingZones: AdminLandingZone[];
  channels: NotificationChannel[];
  accessRequests: AccessRequest[];
  accessRequestsTotal: number;
  accessRequestsPendingTotal: number;
  alertRules: AdminAlertRule[];
  collectors: CollectorStatus[];
  kpiItems: KpiConfigItem[];
  kpiValues: Record<string, number>;
  retentionPolicies: RetentionPolicy[];
  retentionValues: Record<string, number>;
  retentionStats: RetentionStatsItem[];
  maintenanceWindows: MaintenanceWindow[];
  auditLog: AuditLogEntry[];
  auditTotal: number;
}

type UserEditDraft = { projects: AdminUserProjectInput[] };

/**
 * Administration is deliberately down to access governance: who gets in
 * (Access Control) and the projects that scope what they see (Projects). The
 * other surfaces — landing zones, alert rules, collectors, KPI thresholds,
 * retention, maintenance, DBX embeds, audit trail — keep their code and their
 * `AdminTabId`, but are no longer reachable from here.
 */
const adminTabs = [
  {
    id: 'users',
    label: 'Access Control',
    description: 'Roles & LZ scope',
    icon: Users,
    tone: 'blue',
  },
  {
    id: 'projects',
    label: 'Projects',
    description: 'Validate & scope',
    icon: FolderKanban,
    tone: 'teal',
  },
] satisfies Array<{
  id: AdminTabId;
  label: string;
  description: string;
  icon: typeof Users;
  tone: string;
}>;

const ACCESS_REQUESTS_PAGE_SIZE = 10;
const USERS_PAGE_SIZE = 10;

/** A `?tab=` pointing at a retired tab lands on Access Control rather than nowhere. */
function parseAdminTab(value: string | null): AdminTabId {
  const normalized = value?.trim();
  if (adminTabs.some((tab) => tab.id === normalized)) {
    return normalized as AdminTabId;
  }
  return 'users';
}

const LZ_REGISTRATION_PREFIX = '[LZ REGISTRATION]';

function isLzRegistrationRequest(request: AccessRequest): boolean {
  return request.justification.trim().startsWith(LZ_REGISTRATION_PREFIX);
}

function formatAccessRequestLabel(request: AccessRequest): string {
  if (isLzRegistrationRequest(request)) {
    return 'Landing zone registration';
  }

  switch (request.request_type) {
    case 'new_account':
      return 'New portal access';
    case 'reactivation':
      return 'Account reactivation';
    case 'scope_extension':
      return 'Landing zone scope';
    default:
      return request.request_type;
  }
}

function accessRequestLabelVariant(request: AccessRequest): 'info' | 'warning' | 'secondary' {
  if (isLzRegistrationRequest(request)) {
    return 'secondary';
  }

  switch (request.request_type) {
    case 'new_account':
      return 'info';
    case 'reactivation':
      return 'warning';
    default:
      return 'secondary';
  }
}

function formatAccessRequestJustification(request: AccessRequest): string {
  if (!isLzRegistrationRequest(request)) {
    return request.justification;
  }

  return request.justification
    .trim()
    .replace(/^\[LZ REGISTRATION\]\s*/i, '')
    .trim();
}

function AccessRequestStatusBadges({
  request,
  hasPortalAccess,
}: {
  request: AccessRequest;
  hasPortalAccess: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Badge
        variant={
          request.status === 'pending'
            ? 'warning'
            : request.status === 'approved'
              ? 'success'
              : 'destructive'
        }
        className="text-[10px]"
      >
        {request.status}
      </Badge>
      {hasPortalAccess && (
        <Badge variant="info" className="text-[10px]">
          Access granted
        </Badge>
      )}
      {request.status === 'approved' && !hasPortalAccess && (
        <Badge variant="warning" className="text-[10px]">
          No account
        </Badge>
      )}
    </div>
  );
}

function AccessRequestActionButtons({
  request,
  existingUser,
  hasPortalAccess,
  manageAccessLabel,
  mutating,
  onOpenAccessControl,
  onApprove,
  onReject,
  hideAccessControl = false,
  compact = false,
}: {
  request: AccessRequest;
  existingUser: AdminUser | undefined;
  hasPortalAccess: boolean;
  manageAccessLabel: string;
  mutating: boolean;
  onOpenAccessControl: (request: AccessRequest) => void;
  onApprove: (request: AccessRequest) => void;
  onReject: (request: AccessRequest) => void;
  hideAccessControl?: boolean;
  compact?: boolean;
}) {
  const buttonClass = compact ? 'h-8 w-full px-2 text-xs' : 'h-8 min-w-[7.5rem] px-2 text-xs';

  return (
    <div
      className={`flex flex-col gap-1.5 ${compact ? 'sm:max-w-xs' : 'min-w-[7.5rem] items-stretch'}`}
    >
      {!hideAccessControl && (
        <Button size="sm" className={buttonClass} onClick={() => onOpenAccessControl(request)}>
          {existingUser ? <UserCog /> : <UserPlus />}
          {manageAccessLabel}
        </Button>
      )}
      {request.status === 'pending' && !hasPortalAccess && (
        <>
          <Button
            size="sm"
            variant="secondary"
            className={buttonClass}
            onClick={() => onApprove(request)}
            disabled={Boolean(mutating)}
          >
            Mark done
          </Button>
          <Button
            size="sm"
            variant="destructive"
            className={buttonClass}
            onClick={() => onReject(request)}
            disabled={Boolean(mutating)}
          >
            Reject
          </Button>
        </>
      )}
    </div>
  );
}

function AccessRequestLandingZones({ request }: { request: AccessRequest }) {
  if (request.requested_lz_ids.length === 0) {
    return <span className="text-xs text-muted-foreground">All LZs</span>;
  }

  return (
    <div className="flex flex-wrap gap-1">
      {request.requested_lz_ids.map((lzId) => (
        <Badge
          key={lzId}
          variant="outline"
          className="max-w-full truncate font-mono text-[10px]"
          title={lzId}
        >
          {lzId}
        </Badge>
      ))}
    </div>
  );
}

const defaultUserForm: AdminUserCreate = {
  email: '',
  display_name: '',
  entra_oid: '',
  role: 'viewer',
  lz_ids: [],
};

const defaultLandingZoneForm: AdminLandingZoneCreate = {
  lz_id: '',
  display_name: '',
  cloud_provider: 'azure',
  region: '',
  environment: '',
  ba_name: '',
  collector_names: [],
  notes: '',
};

const alertDefaults: AlertRuleCreate = {
  name: '',
  description: '',
  metric_domain: 'pipeline',
  condition_field: 'failure_rate_pct',
  condition_operator: 'gte',
  condition_threshold: 10,
  eval_window_hours: 24,
  severity: 'warning',
  applies_to_lz_ids: null,
  notification_channel_ids: [],
  cooldown_minutes: 60,
  is_active: true,
};

function splitCsv(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatDateTime(value: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function dateTimeLocalFromNow(hoursFromNow: number): string {
  const date = new Date(Date.now() + hoursFromNow * 60 * 60 * 1000);
  date.setSeconds(0, 0);
  return date.toISOString().slice(0, 16);
}

function statusVariant(active: boolean) {
  return active ? 'success' : 'secondary';
}

function statusLabel(active: boolean): string {
  return active ? 'Active' : 'Inactive';
}

function projectMembershipToDraft(projects: AdminUserProject[]): AdminUserProjectInput[] {
  return projects.map((project) => ({ project_id: project.id, role: project.role }));
}

// Order-independent equality on the {project_id -> role} mapping.
function sameProjectMembership(
  draft: AdminUserProjectInput[],
  current: AdminUserProject[]
): boolean {
  if (draft.length !== current.length) return false;
  const currentRoles = new Map(current.map((project) => [project.id, project.role]));
  return draft.every((item) => currentRoles.get(item.project_id) === item.role);
}

function getUserDraft(user: AdminUser): UserEditDraft {
  return { projects: projectMembershipToDraft(user.projects) };
}

function hasUserDraftChanged(user: AdminUser, draft: UserEditDraft): boolean {
  return !sameProjectMembership(draft.projects, user.projects);
}

function findAdminUserByEmail(users: AdminUser[], email: string): AdminUser | undefined {
  const normalized = email.trim().toLowerCase();
  return users.find((user) => user.email.trim().toLowerCase() === normalized);
}

function AdminProjectMembershipSelector({
  value,
  onChange,
  options,
  loading,
  ariaLabel,
}: {
  value: AdminUserProjectInput[];
  onChange: (next: AdminUserProjectInput[]) => void;
  options: { id: string; name: string }[];
  loading: boolean;
  ariaLabel: string;
}) {
  const selectedIds = new Set(value.map((item) => item.project_id));
  const available = options.filter((option) => !selectedIds.has(option.id));
  const nameById = new Map(options.map((option) => [option.id, option.name]));
  return (
    <div className="grid gap-2">
      <Select
        aria-label={ariaLabel}
        className="h-11 w-full rounded-2xl bg-background/95 focus-visible:ring-tdf-blue-border"
        value=""
        disabled={loading}
        onChange={(event) => {
          const projectId = event.target.value;
          if (!projectId) return;
          onChange([...value, { project_id: projectId, role: 'viewer' }]);
        }}
      >
        <option value="">{loading ? 'Loading projects…' : 'Add a project…'}</option>
        {available.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </Select>
      {value.map((item) => {
        const label = nameById.get(item.project_id) ?? item.project_id;
        return (
          <div key={item.project_id} className="flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate text-sm text-foreground">{label}</span>
            <Select
              className="h-9 w-28"
              aria-label={`Role for ${label}`}
              value={item.role}
              onChange={(event) =>
                onChange(
                  value.map((current) =>
                    current.project_id === item.project_id
                      ? { ...current, role: event.target.value as ProjectRole }
                      : current
                  )
                )
              }
            >
              <option value="viewer">Viewer</option>
              <option value="admin">Admin</option>
            </Select>
            <Button
              size="sm"
              variant="ghost"
              aria-label={`Remove ${label}`}
              onClick={() =>
                onChange(value.filter((current) => current.project_id !== item.project_id))
              }
            >
              <X />
            </Button>
          </div>
        );
      })}
    </div>
  );
}

function scrollAdminPanelTo(elementId: string, block: ScrollLogicalPosition = 'center') {
  window.requestAnimationFrame(() => {
    document.getElementById(elementId)?.scrollIntoView?.({ behavior: 'smooth', block });
  });
}

function formatRoleLabel(role: DcmRole): string {
  switch (role) {
    case 'pending':
      return 'Pending approval';
    case 'super_admin':
      return 'DCM Super Administrator';
    case 'admin':
      return 'DCM Administrator';
    case 'manager':
      return 'Business Manager';
    case 'data_architect':
      return 'Data Architect';
    default:
      return 'Read-only Viewer';
  }
}

// Two-level model: platform tier is binary — super_admin is a Platform admin,
// everyone else is a Member whose data access comes from project membership.
function platformTierLabel(role: DcmRole): string {
  return role === 'super_admin' ? 'Platform admin' : 'Member';
}

/**
 * Is this row a platform admin? Reads `platform_role`, the authority every
 * administration guard checks, with the same legacy fallback as the backend's
 * `resolves_to_platform_admin` for rows created before that column existed.
 */
function isRowPlatformAdmin(user: AdminUser): boolean {
  return user.platform_role === 'super_admin' || user.role === 'super_admin';
}

function formatCloudProvider(value: string): string {
  return value === 'aws' ? 'AWS' : 'Microsoft Azure';
}

function formatOperatorLabel(value: string): string {
  switch (value) {
    case 'gt':
      return 'greater than';
    case 'gte':
      return 'greater than or equal';
    case 'lt':
      return 'less than';
    case 'lte':
      return 'less than or equal';
    case 'eq':
      return 'equals';
    default:
      return value;
  }
}

function formatSeverityLabel(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function summaryToneClass(tone: string): string {
  switch (tone) {
    case 'success':
      return 'from-[color-mix(in_oklch,var(--tdf-green)_18%,transparent)] to-transparent text-[var(--tdf-green)]';
    case 'warning':
      return 'from-[color-mix(in_oklch,var(--tdf-purple)_16%,transparent)] to-transparent text-[var(--tdf-purple)]';
    case 'destructive':
      return 'from-[color-mix(in_oklch,var(--tdf-red)_14%,transparent)] to-transparent text-[var(--tdf-red)]';
    default:
      return 'from-[color-mix(in_oklch,var(--tdf-blue)_16%,transparent)] to-transparent text-[var(--tdf-blue)]';
  }
}

function tabToneClass(tone: string, active: boolean): string {
  if (!active) {
    return 'border-border/50 bg-card/90 text-foreground shadow-[0_12px_30px_rgb(15_23_42_/_6%)] hover:-translate-y-0.5 hover:border-tdf-blue-border/70 hover:bg-card hover:text-tdf-blue hover:shadow-[0_18px_45px_rgb(15_23_42_/_10%)]';
  }

  switch (tone) {
    case 'green':
      return 'border-success-border bg-success-subtle text-success shadow-[0_18px_45px_rgb(34_197_94_/_14%)]';
    case 'red':
      return 'border-danger-border bg-danger-subtle text-danger shadow-[0_18px_45px_rgb(239_68_68_/_13%)]';
    case 'purple':
      return 'border-purple-border bg-purple-subtle text-purple shadow-[0_18px_45px_rgb(124_58_237_/_14%)]';
    case 'teal':
      return 'border-[color-mix(in_oklch,var(--tdf-teal)_40%,transparent)] bg-[color-mix(in_oklch,var(--tdf-teal)_9%,transparent)] text-[var(--tdf-teal)] shadow-[0_18px_45px_rgb(20_184_166_/_14%)]';
    default:
      return 'border-tdf-blue-border bg-tdf-blue-subtle text-tdf-blue shadow-[0_18px_45px_rgb(37_99_235_/_14%)]';
  }
}

const adminControlClass = 'h-11 rounded-2xl bg-background/95 focus-visible:ring-tdf-blue-border';

function AdminField({
  label,
  hint,
  className,
  children,
}: {
  label: string;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={`grid gap-1.5 ${className ?? ''}`}>
      <FieldLabel>{label}</FieldLabel>
      {children}
      {hint && <span className="text-xs leading-5 text-muted-foreground">{hint}</span>}
    </label>
  );
}

function EmptyRows({ colSpan, message }: { colSpan: number; message: string }) {
  return (
    <TableRow>
      <TableCell colSpan={colSpan} className="py-10 text-center text-sm text-muted-foreground">
        {message}
      </TableCell>
    </TableRow>
  );
}

function AdminPanelCard({
  title,
  description,
  children,
  actions,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <Card className="border-border/70 bg-card/95 shadow-[0_20px_60px_rgb(15_23_42_/_9%)]">
      <CardHeader className="border-b border-border/60 bg-[linear-gradient(135deg,color-mix(in_oklch,var(--tdf-blue)_8%,transparent),color-mix(in_oklch,var(--tdf-teal)_6%,transparent))]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="text-lg font-semibold tracking-[-0.02em]">{title}</CardTitle>
            <CardDescription className="mt-1 max-w-3xl">{description}</CardDescription>
          </div>
          {actions}
        </div>
      </CardHeader>
      <CardContent className="space-y-5">{children}</CardContent>
    </Card>
  );
}

const AdminContent: React.FC = () => {
  const toast = useToast();
  const [searchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<AdminTabId>(() =>
    parseAdminTab(searchParams.get('tab'))
  );
  const [mutating, setMutating] = useState<string | null>(null);
  const [userEdits, setUserEdits] = useState<Record<string, UserEditDraft>>({});
  const [kpiDraft, setKpiDraft] = useState<Record<string, number>>({});
  const [retentionDraft, setRetentionDraft] = useState<Record<string, number>>({});
  const [auditFilters, setAuditFilters] = useState<AuditLogParams>({ limit: 50, offset: 0 });
  const [userForm, setUserForm] = useState<AdminUserCreate>(defaultUserForm);
  const [userSearch, setUserSearch] = useState('');
  const [userRoleFilter, setUserRoleFilter] = useState<'' | 'pending' | 'super_admin' | 'member'>(
    ''
  );
  const [userStatusFilter, setUserStatusFilter] = useState<'' | 'active' | 'inactive'>('');
  const [userScopeFilter, setUserScopeFilter] = useState<'' | 'all' | 'scoped'>('');
  const [accessRequestStatusFilter, setAccessRequestStatusFilter] = useState<
    AccessRequest['status'] | ''
  >('pending');
  const [accessRequestPage, setAccessRequestPage] = useState(1);
  const [createUserExpanded, setCreateUserExpanded] = useState(false);

  const [landingZoneForm, setLandingZoneForm] =
    useState<AdminLandingZoneCreate>(defaultLandingZoneForm);
  const [collectorNamesText, setCollectorNamesText] = useState('');

  const [alertForm, setAlertForm] = useState<AlertRuleCreate>(alertDefaults);
  const [alertLzText, setAlertLzText] = useState('');
  const [maintenanceForm, setMaintenanceForm] = useState<MaintenanceWindowCreate>({
    name: '',
    description: '',
    lz_ids: null,
    starts_at: dateTimeLocalFromNow(1),
    ends_at: dateTimeLocalFromNow(3),
    suppress_alerts: true,
  });
  const [maintenanceLzText, setMaintenanceLzText] = useState('');

  const referenceProjectsQuery = useReferenceProjects();
  const projectOptions = useMemo(
    () =>
      (referenceProjectsQuery.data?.items ?? []).map((project) => ({
        id: project.id,
        name: project.name,
      })),
    [referenceProjectsQuery.data?.items]
  );

  const adminQuery = useAdminQueries({
    accessRequestStatus: accessRequestStatusFilter || undefined,
    accessRequestPage,
    accessRequestPageSize: ACCESS_REQUESTS_PAGE_SIZE,
    auditLimit: auditFilters.limit ?? 50,
    auditOffset: auditFilters.offset ?? 0,
  });

  const data = useMemo<AdminData>(() => {
    const bundle = adminQuery.data;
    return {
      users: bundle.users.items,
      landingZones: bundle.landingZones.items,
      channels: bundle.channels.items,
      accessRequests: bundle.accessRequests.items,
      accessRequestsTotal: bundle.accessRequests.total,
      accessRequestsPendingTotal: bundle.accessRequests.pending_total,
      alertRules: bundle.alertRules.items,
      collectors: bundle.collectors.items,
      kpiItems: bundle.kpiConfig.items,
      kpiValues: bundle.kpiConfig.values,
      retentionPolicies: bundle.retentionPolicies.items,
      retentionValues: bundle.retentionPolicies.values,
      retentionStats: bundle.retentionStats.items,
      maintenanceWindows: bundle.maintenanceWindows.items,
      auditLog: bundle.auditLog.items,
      auditTotal: bundle.auditLog.total,
    };
  }, [adminQuery.data]);

  const loading = adminQuery.isLoading;
  const loadingDetails = adminQuery.isFetching && !adminQuery.isLoading;
  const error = adminQuery.error
    ? getDcmApiErrorMessage(adminQuery.error, 'Unable to load DCM administration data.')
    : null;

  const load = useCallback(() => {
    void adminQuery.refetch();
  }, [adminQuery]);

  useEffect(() => {
    setKpiDraft(adminQuery.data.kpiConfig.values);
    setRetentionDraft(adminQuery.data.retentionPolicies.values);
  }, [adminQuery.data]);

  useEffect(() => {
    setActiveTab(parseAdminTab(searchParams.get('tab')));
  }, [searchParams]);

  const runMutation = useCallback(
    async (label: string, action: () => Promise<unknown>) => {
      setMutating(label);
      try {
        await action();
        toast.showSuccess('Administration updated', label);
        load();
      } catch (err) {
        toast.showError('Administration error', getDcmApiErrorMessage(err, 'Mutation failed.'));
      } finally {
        setMutating(null);
      }
    },
    [load, toast]
  );

  // Only what the two remaining tabs are about, all of it from the users payload:
  // a user with no project sees no data, so that count is the one to watch.
  const adminSummary = useMemo(
    () => [
      { label: 'Managed Identities', value: data.users.length, tone: 'info', icon: Users },
      {
        label: 'Platform Admins',
        value: data.users.filter((user) => user.platform_role === 'super_admin').length,
        tone: 'success',
        icon: ShieldCheck,
      },
      {
        label: 'Without a Project',
        value: data.users.filter((user) => user.projects.length === 0).length,
        tone: 'warning',
        icon: FolderKanban,
      },
      {
        label: 'Inactive Accounts',
        value: data.users.filter((user) => !user.is_active).length,
        tone: 'destructive',
        icon: KeyRound,
      },
    ],
    [data.users]
  );

  const filteredUsers = useMemo(() => {
    const query = userSearch.trim().toLowerCase();

    return data.users.filter((user) => {
      const matchesSearch =
        !query ||
        [
          user.display_name,
          user.email,
          user.entra_oid,
          user.id,
          user.role,
          formatRoleLabel(user.role),
          ...user.projects.map((project) => project.name),
        ]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(query));
      const matchesRole =
        !userRoleFilter ||
        (userRoleFilter === 'member'
          ? !isRowPlatformAdmin(user) && user.role !== 'pending'
          : userRoleFilter === 'super_admin'
            ? isRowPlatformAdmin(user)
            : user.role === userRoleFilter);
      const matchesStatus =
        !userStatusFilter || (userStatusFilter === 'active' ? user.is_active : !user.is_active);
      const matchesScope =
        !userScopeFilter ||
        (userScopeFilter === 'all' ? user.projects.length === 0 : user.projects.length > 0);

      return matchesSearch && matchesRole && matchesStatus && matchesScope;
    });
  }, [data.users, userRoleFilter, userScopeFilter, userSearch, userStatusFilter]);

  const pendingUsersCount = useMemo(
    () => data.users.filter((user) => user.role === 'pending').length,
    [data.users]
  );
  const hasUserFilters = Boolean(
    userSearch.trim() || userRoleFilter || userStatusFilter || userScopeFilter
  );
  const userPagination = useClientPagination(filteredUsers, USERS_PAGE_SIZE);
  const accessRequestTotalPages = Math.max(
    1,
    Math.ceil(data.accessRequestsTotal / ACCESS_REQUESTS_PAGE_SIZE)
  );
  const accessRequestStartIndex =
    data.accessRequestsTotal === 0 ? 0 : (accessRequestPage - 1) * ACCESS_REQUESTS_PAGE_SIZE;
  const accessRequestEndIndex = Math.min(
    accessRequestStartIndex + data.accessRequests.length,
    data.accessRequestsTotal
  );

  useEffect(() => {
    if (accessRequestPage > accessRequestTotalPages) {
      setAccessRequestPage(accessRequestTotalPages);
    }
  }, [accessRequestPage, accessRequestTotalPages]);

  const openAccessControlForRequest = useCallback(
    (request: AccessRequest) => {
      const existingUser = findAdminUserByEmail(data.users, request.email);
      setUserSearch(request.email);
      setActiveTab('users');
      setCreateUserExpanded(true);

      if (existingUser) {
        setUserEdits((prev) => ({
          ...prev,
          [existingUser.id]: getUserDraft(existingUser),
        }));
        setUserForm(defaultUserForm);
        scrollAdminPanelTo(`admin-user-row-${existingUser.id}`);
        return;
      }

      setUserForm({
        email: request.email,
        display_name: request.display_name || '',
        entra_oid: request.entra_oid || '',
        role: 'viewer',
        lz_ids: [],
      });
      scrollAdminPanelTo('admin-user-create-form', 'start');
    },
    [data.users]
  );

  const saveUserEdit = (user: AdminUser) => {
    const draft = userEdits[user.id] ?? getUserDraft(user);
    return runMutation(`Saved ${user.email}`, () =>
      replaceAdminUserProjects(user.id, draft.projects)
    );
  };

  const changePlatformTier = (user: AdminUser, promote: boolean) => {
    if (
      promote &&
      !window.confirm(
        `Grant platform admin to ${user.email}? They will see and manage every project and all platform settings.`
      )
    ) {
      return;
    }
    return runMutation(
      promote ? `Granted platform admin to ${user.email}` : `Set ${user.email} to member`,
      () => updateAdminUserRole(user.id, promote ? 'super_admin' : 'viewer')
    );
  };

  /**
   * Delete a user outright — this is irreversible and revokes their data access
   * everywhere at once (memberships, pending requests, LZ rows go with the
   * account), so it asks for confirmation first. Deactivate is the reversible
   * option next to it.
   */
  const deleteUser = (user: AdminUser) => {
    if (
      !window.confirm(
        `Delete ${user.email}? Their project memberships and pending requests are removed with the account. This cannot be undone — use Deactivate to suspend access instead.`
      )
    ) {
      return;
    }
    return runMutation(`Deleted ${user.email}`, () => deleteAdminUser(user.id));
  };

  const createUserFromForm = () => {
    const email = userForm.email.trim();
    if (findAdminUserByEmail(data.users, email)) {
      toast.showError(
        'User already exists',
        `${email} is already registered in DCM. Edit the existing user below.`
      );
      setUserSearch(email);
      scrollAdminPanelTo(`admin-user-row-${findAdminUserByEmail(data.users, email)!.id}`);
      return;
    }

    return runMutation(`Created ${email}`, async () => {
      await createAdminUser({
        email,
        display_name: userForm.display_name || null,
        entra_oid: userForm.entra_oid || null,
        role: userForm.role,
        lz_ids: [],
      });
      setUserForm(defaultUserForm);
    });
  };

  const createLandingZoneFromForm = () =>
    runMutation('Landing Zone created', async () => {
      await createAdminLandingZone({
        ...landingZoneForm,
        collector_names: splitCsv(collectorNamesText),
        region: landingZoneForm.region || null,
        environment: landingZoneForm.environment || null,
        ba_name: landingZoneForm.ba_name || null,
        notes: landingZoneForm.notes || null,
      });
      setLandingZoneForm(defaultLandingZoneForm);
      setCollectorNamesText('');
    });

  const createAlertRuleFromForm = () =>
    runMutation('Alert rule created', () =>
      createAlertRule({
        ...alertForm,
        applies_to_lz_ids: alertLzText ? splitCsv(alertLzText) : null,
      })
    );

  const saveKpiDraft = () =>
    runMutation('KPI thresholds saved', () => patchAdminKpiConfig(kpiDraft));
  const saveRetentionDraft = () =>
    runMutation('Retention policies saved', () => patchRetentionPolicies(retentionDraft));

  const createMaintenanceFromForm = () =>
    runMutation('Maintenance window created', () =>
      createMaintenanceWindow({
        ...maintenanceForm,
        lz_ids: maintenanceLzText ? splitCsv(maintenanceLzText) : null,
        description: maintenanceForm.description || null,
        starts_at: new Date(maintenanceForm.starts_at).toISOString(),
        ends_at: new Date(maintenanceForm.ends_at).toISOString(),
      })
    );

  const downloadAuditCsv = async () => {
    setMutating('Export audit CSV');
    try {
      const csv = await exportAuditLog(auditFilters);
      const blobUrl = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = 'dcm-audit-log.csv';
      link.click();
      URL.revokeObjectURL(blobUrl);
    } catch (err) {
      toast.showError('Export failed', getDcmApiErrorMessage(err, 'Unable to export audit log.'));
    } finally {
      setMutating(null);
    }
  };

  return (
    <Content className="mx-auto w-full max-w-[1700px]">
      <ContentHeader className="block">
        <div className="relative overflow-hidden rounded-[2rem] border border-[color-mix(in_oklch,var(--tdf-blue)_20%,white)] bg-[linear-gradient(135deg,var(--tdf-blue),var(--tdf-teal))] p-6 text-white shadow-[0_24px_70px_rgb(15_23_42_/_18%)]">
          <div className="pointer-events-none absolute -right-16 -top-20 size-56 rounded-full bg-white/20 blur-2xl" />
          <div className="pointer-events-none absolute bottom-0 right-8 h-1.5 w-44 rounded-full bg-[var(--tdf-red)] shadow-[5rem_0_0_var(--tdf-green),10rem_0_0_var(--tdf-purple)]" />
          <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/15 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-white/90 backdrop-blur">
                <ShieldCheck size={14} />
                DCM Administration
              </div>
              <div>
                <h2 className="text-3xl font-semibold tracking-[-0.04em] text-white md:text-4xl">
                  DCM Control Center
                </h2>
                <ContentDescription className="mt-2 max-w-2xl text-sm text-white/80">
                  Govern access, landing zone scope, alerting, collectors, KPI thresholds, retention
                  and audit evidence from one operational console.
                </ContentDescription>
              </div>
            </div>
            <ContentActions className="flex flex-wrap items-center justify-start gap-2 lg:justify-end">
              <Badge
                variant={error ? 'destructive' : 'success'}
                className="h-8 border-white/20 px-3"
              >
                {error ? 'Admin API unavailable' : 'Admin API connected'}
              </Badge>
              <Button
                variant="secondary"
                size="sm"
                className="bg-white text-[var(--tdf-blue)] hover:bg-white/95"
                onClick={load}
                disabled={loading || loadingDetails || Boolean(mutating)}
              >
                <RefreshCw />
                Refresh data
              </Button>
            </ContentActions>
          </div>
        </div>
      </ContentHeader>

      <ContentMain>
        {error && (
          <Card className="border-danger-border bg-danger-subtle">
            <CardContent className="text-sm text-danger">{error}</CardContent>
          </Card>
        )}

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {adminSummary.map((item) => {
            const Icon = item.icon;
            return (
              <Card key={item.label} interactive className="relative overflow-hidden">
                <div
                  className={`absolute inset-x-0 top-0 h-1 bg-current ${summaryToneClass(item.tone)}`}
                />
                <CardContent
                  className={`space-y-4 bg-gradient-to-br ${summaryToneClass(item.tone)}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                      {item.label}
                    </p>
                    <span className="flex size-9 items-center justify-center rounded-2xl bg-white/80 shadow-sm shadow-slate-950/5">
                      <Icon size={17} />
                    </span>
                  </div>
                  {loading ? (
                    <Skeleton className="h-9 w-20" />
                  ) : (
                    <p className="text-4xl font-semibold tracking-[-0.04em] text-foreground">
                      {item.value}
                    </p>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>

        <Tabs className="gap-5">
          <TabsList className="grid w-full grid-cols-1 gap-3 bg-transparent p-0 text-foreground sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
            {adminTabs.map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <TabsTrigger
                  key={tab.id}
                  active={isActive}
                  onClick={() => setActiveTab(tab.id)}
                  className={`group h-auto justify-start rounded-[1.4rem] border p-3.5 text-left data-[state=active]:after:hidden ${tabToneClass(tab.tone, isActive)}`}
                >
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-white/80 text-current shadow-sm shadow-slate-950/5 dark:bg-white/10">
                    <tab.icon size={17} />
                  </span>
                  <span className="min-w-0">
                    <span className="flex items-center gap-2">
                      <span className="block truncate text-sm font-semibold">{tab.label}</span>
                    </span>
                    <span className="block truncate text-[11px] font-medium opacity-75">
                      {tab.description}
                    </span>
                  </span>
                  <span className="ml-auto hidden rounded-full bg-white/70 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] opacity-80 transition group-hover:opacity-100 xl:inline-flex dark:bg-white/10">
                    {isActive ? 'Open' : 'Go'}
                  </span>
                </TabsTrigger>
              );
            })}
          </TabsList>

          <TabsContent className="space-y-4">
            {loading && !error ? (
              <Card>
                <CardContent className="space-y-3">
                  <Skeleton className="h-10 rounded-xl" />
                  <Skeleton className="h-32 rounded-xl" />
                  <Skeleton className="h-32 rounded-xl" />
                </CardContent>
              </Card>
            ) : (
              <>
                {activeTab === 'users' && (
                  <>
                    <AdminPanelCard
                      title="Identity Access Management"
                      description="Add Entra ID users, assign DCM roles, deactivate accounts and manage the projects each user can access."
                    >
                      <div className="grid gap-4">
                        <div
                          id="admin-user-create-form"
                          className="rounded-[1.75rem] border border-tdf-blue-border/30 bg-[linear-gradient(135deg,color-mix(in_oklch,var(--tdf-blue)_8%,transparent),color-mix(in_oklch,var(--tdf-teal)_7%,transparent))] p-4 shadow-sm shadow-slate-950/5 sm:p-5"
                        >
                          <button
                            type="button"
                            className="flex w-full items-start justify-between gap-3 text-left"
                            onClick={() => setCreateUserExpanded((expanded) => !expanded)}
                            aria-expanded={createUserExpanded}
                            aria-controls="admin-user-create-form-panel"
                          >
                            <div>
                              <p className="text-base font-semibold tracking-[-0.02em] text-foreground">
                                Create a DCM identity
                              </p>
                              <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
                                Search Entra ID or fill the fields manually. Collapse this panel to
                                focus on existing users.
                              </p>
                            </div>
                            <div className="flex shrink-0 items-center gap-2">
                              <Badge variant="info">Access Control</Badge>
                              <ChevronDown
                                className={cn(
                                  'size-5 text-muted-foreground transition-transform duration-200',
                                  createUserExpanded && 'rotate-180'
                                )}
                              />
                            </div>
                          </button>

                          {createUserExpanded && (
                            <div id="admin-user-create-form-panel" className="mt-5">
                              {/* EntraID User Selector */}
                              <div>
                                <AdminField
                                  label="Recherche EntraID"
                                  hint="Recherchez et sélectionnez un utilisateur depuis l'annuaire corporate"
                                >
                                  <EntraIDUserSelector
                                    onSelectUser={(user) => {
                                      setUserForm((prev) => ({
                                        ...prev,
                                        email: user.mail || user.userPrincipalName,
                                        display_name: user.displayName,
                                        entra_oid: user.id,
                                      }));
                                    }}
                                    placeholder="Rechercher par nom ou email..."
                                  />
                                </AdminField>
                              </div>

                              <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                                <AdminField
                                  label="Entra ID email"
                                  className="sm:col-span-2 xl:col-span-1"
                                >
                                  <Input
                                    className={adminControlClass}
                                    value={userForm.email}
                                    onChange={(event) =>
                                      setUserForm((prev) => ({
                                        ...prev,
                                        email: event.target.value,
                                      }))
                                    }
                                    placeholder="user@domain.com"
                                  />
                                </AdminField>
                                <AdminField label="Display name">
                                  <Input
                                    className={adminControlClass}
                                    value={userForm.display_name ?? ''}
                                    onChange={(event) =>
                                      setUserForm((prev) => ({
                                        ...prev,
                                        display_name: event.target.value,
                                      }))
                                    }
                                    placeholder="Optional"
                                  />
                                </AdminField>
                                <AdminField
                                  label="Project membership"
                                  hint="Data access comes from project membership. Create the user, then assign projects from the list below."
                                  className="sm:col-span-2"
                                >
                                  <p className="rounded-2xl bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
                                    New users start with no project access. Assign projects from the
                                    Projects column once created.
                                  </p>
                                </AdminField>
                              </div>

                              <div className="mt-5 flex flex-col gap-3 border-t border-white/40 pt-4 sm:flex-row sm:items-center sm:justify-between">
                                <p className="text-sm text-muted-foreground">
                                  New users are active immediately and auditable from the Audit
                                  Trail tab.
                                </p>
                                <Button
                                  className="h-11 px-5"
                                  onClick={createUserFromForm}
                                  disabled={!userForm.email.trim() || Boolean(mutating)}
                                >
                                  Create user
                                </Button>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </AdminPanelCard>

                    <section className="space-y-4 rounded-[1.75rem] bg-card/95 p-3 shadow-[0_16px_45px_rgb(15_23_42_/_7%)] ring-1 ring-border/50 sm:p-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="min-w-0">
                          <h3 className="text-base font-semibold tracking-[-0.02em] text-foreground">
                            Existing users
                          </h3>
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            Search by identity or role, then edit project membership inline.
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Badge variant="secondary">
                            {filteredUsers.length}/{data.users.length} identities
                          </Badge>
                          <Badge variant="success">
                            {data.users.filter((user) => user.is_active).length} active
                          </Badge>
                          {pendingUsersCount > 0 && (
                            <Badge variant="warning">{pendingUsersCount} pending</Badge>
                          )}
                          <Button
                            size="sm"
                            variant={userRoleFilter === 'pending' ? 'default' : 'secondary'}
                            onClick={() => {
                              setUserRoleFilter((current) =>
                                current === 'pending' ? '' : 'pending'
                              );
                              setUserStatusFilter('');
                            }}
                          >
                            Pending queue
                          </Button>
                        </div>
                      </div>

                      <div className="grid gap-3 rounded-[1.5rem] bg-muted/35 p-3 md:grid-cols-[minmax(14rem,1.3fr)_repeat(3,minmax(9rem,0.7fr))_auto]">
                        <label className="grid gap-1.5">
                          <FieldLabel>Search users</FieldLabel>
                          <div className="relative">
                            <Search
                              size={15}
                              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                            />
                            <Input
                              className={`${adminControlClass} pl-9`}
                              value={userSearch}
                              onChange={(event) => setUserSearch(event.target.value)}
                              placeholder="email, name, role, project..."
                            />
                          </div>
                        </label>
                        <label className="grid gap-1.5">
                          <FieldLabel>Platform tier</FieldLabel>
                          <Select
                            className={`w-full ${adminControlClass}`}
                            value={userRoleFilter}
                            onChange={(event) =>
                              setUserRoleFilter(
                                event.target.value as '' | 'pending' | 'super_admin' | 'member'
                              )
                            }
                          >
                            <option value="">All tiers</option>
                            <option value="pending">{formatRoleLabel('pending')}</option>
                            <option value="super_admin">Platform admin</option>
                            <option value="member">Member</option>
                          </Select>
                        </label>
                        <label className="grid gap-1.5">
                          <FieldLabel>Status</FieldLabel>
                          <Select
                            className={`w-full ${adminControlClass}`}
                            value={userStatusFilter}
                            onChange={(event) =>
                              setUserStatusFilter(event.target.value as '' | 'active' | 'inactive')
                            }
                          >
                            <option value="">All statuses</option>
                            <option value="active">Active</option>
                            <option value="inactive">Inactive</option>
                          </Select>
                        </label>
                        <label className="grid gap-1.5">
                          <FieldLabel>Projects</FieldLabel>
                          <Select
                            className={`w-full ${adminControlClass}`}
                            value={userScopeFilter}
                            onChange={(event) =>
                              setUserScopeFilter(event.target.value as '' | 'all' | 'scoped')
                            }
                          >
                            <option value="">All members</option>
                            <option value="all">No project</option>
                            <option value="scoped">Has project</option>
                          </Select>
                        </label>
                        <div className="flex items-end">
                          <Button
                            variant="secondary"
                            className="h-11 w-full"
                            onClick={() => {
                              setUserSearch('');
                              setUserRoleFilter('');
                              setUserStatusFilter('');
                              setUserScopeFilter('');
                            }}
                            disabled={!hasUserFilters}
                          >
                            <X />
                            Clear
                          </Button>
                        </div>
                      </div>

                      <Table className="table-fixed">
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-[34%] px-4">Identity</TableHead>
                            <TableHead className="w-[26%]">Platform tier</TableHead>
                            <TableHead className="w-[40%]">Projects</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filteredUsers.length === 0 ? (
                            <EmptyRows
                              colSpan={3}
                              message={
                                data.users.length === 0
                                  ? 'No DCM users yet.'
                                  : 'No user matches the current filters.'
                              }
                            />
                          ) : (
                            userPagination.pageItems.map((user) => {
                              const draft = userEdits[user.id] ?? getUserDraft(user);
                              const hasPendingChanges = hasUserDraftChanged(user, draft);
                              return (
                                <TableRow
                                  key={user.id}
                                  id={`admin-user-row-${user.id}`}
                                  className="border-b border-border/50"
                                >
                                  <TableCell className="whitespace-normal px-4">
                                    <div className="min-w-0 space-y-1">
                                      <div className="flex flex-wrap items-center gap-2">
                                        <p className="font-semibold text-foreground">
                                          {user.display_name || user.email}
                                        </p>
                                        <Badge variant={statusVariant(user.is_active)}>
                                          {statusLabel(user.is_active)}
                                        </Badge>
                                      </div>
                                      <p className="break-all text-xs text-muted-foreground">
                                        {user.email}
                                      </p>
                                      <p className="hidden break-all font-mono text-[11px] text-muted-foreground xl:block">
                                        {user.entra_oid || user.id}
                                      </p>
                                    </div>
                                  </TableCell>
                                  <TableCell className="whitespace-normal">
                                    <div className="grid gap-2">
                                      <Badge
                                        variant={isRowPlatformAdmin(user) ? 'info' : 'secondary'}
                                        aria-label={`Tier for ${user.email}`}
                                      >
                                        {user.role === 'pending'
                                          ? formatRoleLabel('pending')
                                          : platformTierLabel(
                                              isRowPlatformAdmin(user) ? 'super_admin' : 'viewer'
                                            )}
                                      </Badge>
                                      {user.role !== 'pending' &&
                                        (isRowPlatformAdmin(user) ? (
                                          <Button
                                            size="sm"
                                            variant="secondary"
                                            onClick={() => changePlatformTier(user, false)}
                                            disabled={Boolean(mutating)}
                                          >
                                            Set as member
                                          </Button>
                                        ) : (
                                          <Button
                                            size="sm"
                                            variant="secondary"
                                            onClick={() => changePlatformTier(user, true)}
                                            disabled={Boolean(mutating)}
                                          >
                                            <ShieldCheck />
                                            Make platform admin
                                          </Button>
                                        ))}
                                    </div>
                                  </TableCell>
                                  <TableCell className="whitespace-normal">
                                    <div className="grid gap-2">
                                      <div className="flex flex-wrap gap-1.5">
                                        {user.projects.length === 0 ? (
                                          <Badge variant="secondary">No project access</Badge>
                                        ) : (
                                          user.projects.map((project) => (
                                            <Badge
                                              key={project.id}
                                              variant="outline"
                                              className="bg-background/80"
                                            >
                                              {project.name} · {project.role}
                                            </Badge>
                                          ))
                                        )}
                                        {hasPendingChanges && (
                                          <Badge variant="warning">Unsaved</Badge>
                                        )}
                                      </div>
                                      <AdminProjectMembershipSelector
                                        options={projectOptions}
                                        loading={referenceProjectsQuery.isLoading}
                                        value={draft.projects}
                                        onChange={(projects) =>
                                          setUserEdits((prev) => ({
                                            ...prev,
                                            [user.id]: { ...draft, projects },
                                          }))
                                        }
                                        ariaLabel={`Project membership for ${user.email}`}
                                      />
                                      <div className="flex flex-wrap justify-end gap-2">
                                        {user.role === 'pending' ? (
                                          <Button
                                            size="sm"
                                            onClick={() =>
                                              runMutation(`Approved ${user.email}`, () =>
                                                approveAdminUser(user.id, {
                                                  role: 'viewer',
                                                  lz_ids: [],
                                                })
                                              )
                                            }
                                            disabled={Boolean(mutating)}
                                          >
                                            <UserPlus />
                                            Approve
                                          </Button>
                                        ) : (
                                          <>
                                            <Button
                                              size="sm"
                                              variant="secondary"
                                              onClick={() => saveUserEdit(user)}
                                              disabled={!hasPendingChanges || Boolean(mutating)}
                                            >
                                              <Save />
                                              Save
                                            </Button>
                                            <Button
                                              size="sm"
                                              variant="destructive"
                                              onClick={() =>
                                                runMutation(`Deactivated ${user.email}`, () =>
                                                  deactivateAdminUser(user.id)
                                                )
                                              }
                                              disabled={!user.is_active || Boolean(mutating)}
                                            >
                                              Deactivate
                                            </Button>
                                            <Button
                                              size="sm"
                                              variant="outline"
                                              aria-label={`Delete ${user.email}`}
                                              onClick={() => deleteUser(user)}
                                              disabled={Boolean(mutating)}
                                            >
                                              <Trash2 />
                                              Delete
                                            </Button>
                                          </>
                                        )}
                                      </div>
                                    </div>
                                  </TableCell>
                                </TableRow>
                              );
                            })
                          )}
                        </TableBody>
                      </Table>
                      <ListPagination
                        currentPage={userPagination.currentPage}
                        endIndex={userPagination.endIndex}
                        hasNextPage={userPagination.hasNextPage}
                        hasPreviousPage={userPagination.hasPreviousPage}
                        onNext={userPagination.nextPage}
                        onPrevious={userPagination.previousPage}
                        startIndex={userPagination.startIndex}
                        totalItems={userPagination.totalItems}
                        totalPages={userPagination.totalPages}
                      />
                    </section>
                  </>
                )}

                {activeTab === 'projects' && <AdminProjectsTab />}

                {activeTab === 'landing-zones' && (
                  <AdminPanelCard
                    title="Landing Zone Registry"
                    description="Register monitored landing zones, attach collector metadata and deactivate zones without losing history."
                  >
                    <div className="rounded-3xl border border-border/70 bg-[linear-gradient(135deg,color-mix(in_oklch,var(--tdf-green)_7%,transparent),color-mix(in_oklch,var(--tdf-blue)_4%,transparent))] p-4 shadow-sm shadow-slate-950/5">
                      <div className="grid gap-4 xl:grid-cols-12">
                        <label className="grid gap-1.5 xl:col-span-3">
                          <FieldLabel>Landing zone ID</FieldLabel>
                          <Input
                            value={landingZoneForm.lz_id}
                            onChange={(event) =>
                              setLandingZoneForm((prev) => ({ ...prev, lz_id: event.target.value }))
                            }
                            placeholder="azure-lz-prod-fr"
                          />
                        </label>
                        <label className="grid gap-1.5 xl:col-span-3">
                          <FieldLabel>Business name</FieldLabel>
                          <Input
                            value={landingZoneForm.display_name}
                            onChange={(event) =>
                              setLandingZoneForm((prev) => ({
                                ...prev,
                                display_name: event.target.value,
                              }))
                            }
                            placeholder="Landing Zone Production"
                          />
                        </label>
                        <label className="grid gap-1.5 sm:max-xl:col-span-1 xl:col-span-2">
                          <FieldLabel>Cloud provider</FieldLabel>
                          <Select
                            className="w-full"
                            value={landingZoneForm.cloud_provider}
                            onChange={(event) =>
                              setLandingZoneForm((prev) => ({
                                ...prev,
                                cloud_provider: event.target.value,
                              }))
                            }
                          >
                            <option value="azure">Microsoft Azure</option>
                            <option value="aws">AWS</option>
                          </Select>
                        </label>
                        <label className="grid gap-1.5 xl:col-span-2">
                          <FieldLabel>Environment</FieldLabel>
                          <Input
                            value={landingZoneForm.environment ?? ''}
                            onChange={(event) =>
                              setLandingZoneForm((prev) => ({
                                ...prev,
                                environment: event.target.value,
                              }))
                            }
                            placeholder="prod"
                          />
                        </label>
                        <label className="grid gap-1.5 xl:col-span-2">
                          <FieldLabel>Region</FieldLabel>
                          <Input
                            value={landingZoneForm.region ?? ''}
                            onChange={(event) =>
                              setLandingZoneForm((prev) => ({
                                ...prev,
                                region: event.target.value,
                              }))
                            }
                            placeholder="westeurope"
                          />
                        </label>
                        <label className="grid gap-1.5 xl:col-span-2">
                          <FieldLabel>Business area</FieldLabel>
                          <Input
                            value={landingZoneForm.ba_name ?? ''}
                            onChange={(event) =>
                              setLandingZoneForm((prev) => ({
                                ...prev,
                                ba_name: event.target.value,
                              }))
                            }
                            placeholder="Data"
                          />
                        </label>
                        <label className="grid gap-1.5 xl:col-span-4">
                          <FieldLabel>Collectors</FieldLabel>
                          <Input
                            value={collectorNamesText}
                            onChange={(event) => setCollectorNamesText(event.target.value)}
                            placeholder="azure-adf, databricks"
                          />
                        </label>
                        <label className="grid gap-1.5 xl:col-span-4">
                          <FieldLabel>Notes</FieldLabel>
                          <Input
                            value={landingZoneForm.notes ?? ''}
                            onChange={(event) =>
                              setLandingZoneForm((prev) => ({ ...prev, notes: event.target.value }))
                            }
                            placeholder="optional"
                          />
                        </label>
                        <div className="flex items-end xl:col-span-2">
                          <Button
                            className="w-full"
                            onClick={createLandingZoneFromForm}
                            disabled={
                              Boolean(mutating) ||
                              !landingZoneForm.lz_id.trim() ||
                              !landingZoneForm.display_name.trim()
                            }
                          >
                            Create Landing Zone
                          </Button>
                        </div>
                      </div>
                    </div>
                    <Table className="min-w-[900px]">
                      <TableHeader>
                        <TableRow>
                          <TableHead>Landing zone</TableHead>
                          <TableHead>Cloud</TableHead>
                          <TableHead>Environment</TableHead>
                          <TableHead>Users</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {data.landingZones.length === 0 ? (
                          <EmptyRows colSpan={6} message="No landing zones registered yet." />
                        ) : (
                          data.landingZones.map((lz) => (
                            <TableRow key={lz.lz_id}>
                              <TableCell className="min-w-72">
                                <p className="font-medium">{lz.display_name}</p>
                                <p className="text-xs text-muted-foreground">{lz.lz_id}</p>
                              </TableCell>
                              <TableCell>{formatCloudProvider(lz.cloud_provider)}</TableCell>
                              <TableCell>{lz.environment ?? '-'}</TableCell>
                              <TableCell>{lz.user_count}</TableCell>
                              <TableCell>
                                <Badge variant={statusVariant(lz.is_active)}>
                                  {statusLabel(lz.is_active)}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-right">
                                <Button
                                  size="sm"
                                  variant="destructive"
                                  onClick={() =>
                                    runMutation(`Deactivated ${lz.lz_id}`, () =>
                                      deactivateAdminLandingZone(lz.lz_id)
                                    )
                                  }
                                  disabled={!lz.is_active || Boolean(mutating)}
                                >
                                  Deactivate
                                </Button>
                              </TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </AdminPanelCard>
                )}

                {activeTab === 'access-requests' && (
                  <AdminPanelCard
                    title="Access request inbox"
                    description="Portal access requests from users. Open Access Control to create accounts or adjust roles and landing zone scope."
                    actions={
                      <Badge variant={data.accessRequestsPendingTotal > 0 ? 'warning' : 'success'}>
                        {data.accessRequestsPendingTotal} pending
                      </Badge>
                    }
                  >
                    <div className="grid gap-3 rounded-[1.5rem] bg-muted/35 p-3 md:grid-cols-[minmax(12rem,0.8fr)_auto]">
                      <label className="grid gap-1.5">
                        <FieldLabel>Status</FieldLabel>
                        <Select
                          className={`w-full ${adminControlClass}`}
                          value={accessRequestStatusFilter}
                          onChange={(event) => {
                            setAccessRequestPage(1);
                            setAccessRequestStatusFilter(
                              event.target.value as AccessRequest['status'] | ''
                            );
                          }}
                        >
                          <option value="pending">Pending</option>
                          <option value="approved">Approved</option>
                          <option value="rejected">Rejected</option>
                          <option value="">All statuses</option>
                        </Select>
                      </label>
                      <div className="flex items-end">
                        <Button
                          variant="secondary"
                          className="h-11 w-full md:w-auto"
                          onClick={load}
                          disabled={loading || Boolean(mutating)}
                        >
                          <RefreshCw />
                          Refresh inbox
                        </Button>
                      </div>
                    </div>

                    {data.accessRequests.length === 0 ? (
                      <div className="rounded-2xl border border-dashed border-border/70 px-4 py-10 text-center text-sm text-muted-foreground">
                        {accessRequestStatusFilter === 'pending'
                          ? 'No pending access requests.'
                          : 'No access requests match the current filter.'}
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {data.accessRequests.map((request) => {
                          const existingUser = findAdminUserByEmail(data.users, request.email);
                          const hasPortalAccess = Boolean(existingUser?.is_active);
                          const manageAccessLabel = existingUser ? 'Manage access' : 'Grant access';
                          const lzRegistration = isLzRegistrationRequest(request);

                          return (
                            <div
                              key={request.id}
                              className="space-y-3 rounded-[1.25rem] border border-border/70 bg-card/95 p-4 shadow-sm shadow-slate-950/5 xl:grid xl:grid-cols-[minmax(0,1fr)_minmax(10.5rem,0.42fr)] xl:items-start xl:gap-5 xl:space-y-0"
                            >
                              <div className="min-w-0 space-y-2">
                                <div className="min-w-0">
                                  <p className="truncate font-semibold text-foreground">
                                    {request.display_name}
                                  </p>
                                  <p
                                    className="truncate text-xs text-muted-foreground"
                                    title={request.email}
                                  >
                                    {request.email}
                                  </p>
                                  <p className="mt-1 text-[11px] text-muted-foreground">
                                    {formatDateTime(request.requested_at)}
                                  </p>
                                </div>

                                <div className="flex flex-wrap items-center gap-2">
                                  <Badge
                                    variant={accessRequestLabelVariant(request)}
                                    className="whitespace-normal text-[10px]"
                                  >
                                    {formatAccessRequestLabel(request)}
                                  </Badge>
                                  {!lzRegistration && (
                                    <AccessRequestLandingZones request={request} />
                                  )}
                                </div>

                                <p className="text-sm leading-6 text-muted-foreground">
                                  {formatAccessRequestJustification(request)}
                                </p>
                              </div>

                              <div className="flex flex-col gap-2 border-t border-border/50 pt-3 xl:border-t-0 xl:pt-0">
                                <AccessRequestStatusBadges
                                  request={request}
                                  hasPortalAccess={hasPortalAccess}
                                />
                                <AccessRequestActionButtons
                                  compact
                                  request={request}
                                  existingUser={existingUser}
                                  hasPortalAccess={hasPortalAccess}
                                  manageAccessLabel={manageAccessLabel}
                                  mutating={Boolean(mutating)}
                                  hideAccessControl={lzRegistration}
                                  onOpenAccessControl={openAccessControlForRequest}
                                  onApprove={(item) =>
                                    runMutation(`Approved ${item.email}`, () =>
                                      reviewAdminAccessRequest(item.id, 'approved')
                                    )
                                  }
                                  onReject={(item) =>
                                    runMutation(`Rejected ${item.email}`, () =>
                                      reviewAdminAccessRequest(item.id, 'rejected')
                                    )
                                  }
                                />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    <ListPagination
                      currentPage={accessRequestPage}
                      endIndex={accessRequestEndIndex}
                      hasNextPage={accessRequestPage < accessRequestTotalPages}
                      hasPreviousPage={accessRequestPage > 1}
                      onNext={() =>
                        setAccessRequestPage((page) => Math.min(accessRequestTotalPages, page + 1))
                      }
                      onPrevious={() => setAccessRequestPage((page) => Math.max(1, page - 1))}
                      startIndex={accessRequestStartIndex}
                      totalItems={data.accessRequestsTotal}
                      totalPages={accessRequestTotalPages}
                    />
                  </AdminPanelCard>
                )}

                {activeTab === 'alert-rules' && (
                  <AdminPanelCard
                    title="Alert Rules"
                    description="Define metric conditions, target scope and dry-run checks before enabling operational alerts."
                  >
                    <div className="grid gap-3 rounded-3xl border border-border/70 bg-[linear-gradient(135deg,color-mix(in_oklch,var(--tdf-red)_5%,transparent),color-mix(in_oklch,var(--tdf-purple)_5%,transparent))] p-4 lg:grid-cols-4">
                      <label className="grid gap-1">
                        <FieldLabel>Rule name</FieldLabel>
                        <Input
                          value={alertForm.name}
                          onChange={(event) =>
                            setAlertForm((prev) => ({ ...prev, name: event.target.value }))
                          }
                        />
                      </label>
                      <label className="grid gap-1">
                        <FieldLabel>Metric domain</FieldLabel>
                        <Select
                          value={alertForm.metric_domain}
                          onChange={(event) =>
                            setAlertForm((prev) => ({ ...prev, metric_domain: event.target.value }))
                          }
                        >
                          <option value="pipeline">pipeline</option>
                          <option value="cluster">cluster</option>
                          <option value="cost">cost</option>
                          <option value="security">security</option>
                          <option value="governance">governance</option>
                        </Select>
                      </label>
                      <label className="grid gap-1">
                        <FieldLabel>Metric field</FieldLabel>
                        <Input
                          value={alertForm.condition_field}
                          onChange={(event) =>
                            setAlertForm((prev) => ({
                              ...prev,
                              condition_field: event.target.value,
                            }))
                          }
                        />
                      </label>
                      <label className="grid gap-1">
                        <FieldLabel>Operator</FieldLabel>
                        <Select
                          value={alertForm.condition_operator}
                          onChange={(event) =>
                            setAlertForm((prev) => ({
                              ...prev,
                              condition_operator: event.target.value,
                            }))
                          }
                        >
                          <option value="gt">greater than</option>
                          <option value="gte">greater than or equal</option>
                          <option value="lt">less than</option>
                          <option value="lte">less than or equal</option>
                          <option value="eq">equals</option>
                        </Select>
                      </label>
                      <label className="grid gap-1">
                        <FieldLabel>Threshold</FieldLabel>
                        <Input
                          type="number"
                          value={alertForm.condition_threshold}
                          onChange={(event) =>
                            setAlertForm((prev) => ({
                              ...prev,
                              condition_threshold: Number(event.target.value),
                            }))
                          }
                        />
                      </label>
                      <label className="grid gap-1">
                        <FieldLabel>Severity</FieldLabel>
                        <Select
                          value={alertForm.severity}
                          onChange={(event) =>
                            setAlertForm((prev) => ({
                              ...prev,
                              severity: event.target.value as AlertRuleCreate['severity'],
                            }))
                          }
                        >
                          <option value="info">Info</option>
                          <option value="warning">Warning</option>
                          <option value="critical">Critical</option>
                        </Select>
                      </label>
                      <label className="grid gap-1">
                        <FieldLabel>Notification channel</FieldLabel>
                        <Select
                          value={alertForm.notification_channel_ids?.[0] ?? ''}
                          onChange={(event) =>
                            setAlertForm((prev) => ({
                              ...prev,
                              notification_channel_ids: event.target.value
                                ? [event.target.value]
                                : [],
                            }))
                          }
                        >
                          <option value="">No notification</option>
                          {data.channels
                            .filter((channel) => channel.is_active)
                            .map((channel) => (
                              <option key={channel.id} value={channel.id}>
                                {channel.name}
                              </option>
                            ))}
                        </Select>
                      </label>
                      <label className="grid gap-1">
                        <FieldLabel>Landing zone scope</FieldLabel>
                        <Input
                          value={alertLzText}
                          onChange={(event) => setAlertLzText(event.target.value)}
                          placeholder="empty = all zones"
                        />
                      </label>
                      <div className="lg:col-span-4">
                        <Button onClick={createAlertRuleFromForm} disabled={Boolean(mutating)}>
                          Create alert rule
                        </Button>
                      </div>
                    </div>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Rule</TableHead>
                          <TableHead>Condition</TableHead>
                          <TableHead>Severity</TableHead>
                          <TableHead>Scope</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {data.alertRules.length === 0 ? (
                          <EmptyRows colSpan={6} message="No alert rules configured yet." />
                        ) : (
                          data.alertRules.map((rule) => (
                            <TableRow key={rule.id}>
                              <TableCell>
                                <p className="font-medium">{rule.name}</p>
                                <p className="text-xs text-muted-foreground">{rule.description}</p>
                              </TableCell>
                              <TableCell>
                                {rule.metric_domain}.{rule.condition_field}{' '}
                                {formatOperatorLabel(rule.condition_operator)}{' '}
                                {rule.condition_threshold}
                              </TableCell>
                              <TableCell>
                                <Badge
                                  variant={
                                    rule.severity === 'critical'
                                      ? 'destructive'
                                      : rule.severity === 'warning'
                                        ? 'warning'
                                        : 'info'
                                  }
                                >
                                  {formatSeverityLabel(rule.severity)}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                {rule.applies_to_lz_ids.length
                                  ? rule.applies_to_lz_ids.join(', ')
                                  : 'All LZs'}
                              </TableCell>
                              <TableCell>
                                <Badge variant={statusVariant(rule.is_active)}>
                                  {statusLabel(rule.is_active)}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                <div className="flex justify-end gap-2">
                                  <Button
                                    size="sm"
                                    variant="secondary"
                                    onClick={() =>
                                      runMutation(`Tested ${rule.name}`, () =>
                                        testAlertRule(rule.id)
                                      )
                                    }
                                    disabled={Boolean(mutating)}
                                  >
                                    Test
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="destructive"
                                    onClick={() =>
                                      runMutation(`Disabled ${rule.name}`, () =>
                                        deleteAlertRule(rule.id)
                                      )
                                    }
                                    disabled={!rule.is_active || Boolean(mutating)}
                                  >
                                    Disable
                                  </Button>
                                </div>
                              </TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </AdminPanelCard>
                )}

                {activeTab === 'collectors' && (
                  <AdminPanelCard
                    title="Collector Health"
                    description="Track each collector run status, freshness and last error by landing zone. Freshness is computed by the API."
                  >
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Landing zone</TableHead>
                          <TableHead>Collector</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead>Last run</TableHead>
                          <TableHead>Duration</TableHead>
                          <TableHead>Metrics</TableHead>
                          <TableHead>Last error</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {data.collectors.length === 0 ? (
                          <EmptyRows colSpan={7} message="No collector status received yet." />
                        ) : (
                          data.collectors.map((collector) => (
                            <TableRow key={`${collector.lz_id}-${collector.collector_name}`}>
                              <TableCell>{collector.lz_id}</TableCell>
                              <TableCell>{collector.collector_name}</TableCell>
                              <TableCell>
                                <Badge
                                  variant={
                                    collector.is_stale || collector.last_run_status === 'error'
                                      ? 'destructive'
                                      : 'success'
                                  }
                                >
                                  {collector.is_stale
                                    ? 'stale'
                                    : (collector.last_run_status ?? 'unknown')}
                                </Badge>
                              </TableCell>
                              <TableCell>{formatDateTime(collector.last_run_at)}</TableCell>
                              <TableCell>{collector.last_run_duration_s ?? '-'}</TableCell>
                              <TableCell>{collector.metrics_collected ?? '-'}</TableCell>
                              <TableCell className="max-w-md truncate">
                                {collector.last_error ?? '-'}
                              </TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </AdminPanelCard>
                )}

                {activeTab === 'kpi' && (
                  <AdminPanelCard
                    title="KPI Thresholds"
                    description="Tune warning and critical values used by monitoring cards and operational health indicators."
                    actions={
                      <Button size="sm" onClick={saveKpiDraft} disabled={Boolean(mutating)}>
                        <Save />
                        Save
                      </Button>
                    }
                  >
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                      {data.kpiItems.map((item) => (
                        <label
                          key={item.config_key}
                          className="grid gap-2 rounded-2xl border border-border/70 bg-card p-4 shadow-sm shadow-slate-950/5"
                        >
                          <FieldLabel>{item.config_key}</FieldLabel>
                          <Input
                            type="number"
                            value={kpiDraft[item.config_key] ?? item.config_value}
                            onChange={(event) =>
                              setKpiDraft((prev) => ({
                                ...prev,
                                [item.config_key]: Number(event.target.value),
                              }))
                            }
                          />
                          <span className="text-xs text-muted-foreground">{item.description}</span>
                        </label>
                      ))}
                    </div>
                  </AdminPanelCard>
                )}

                {activeTab === 'retention' && (
                  <AdminPanelCard
                    title="Retention Policies"
                    description="Set minimum data retention periods by metric table and review available Unity Catalog storage stats."
                    actions={
                      <Button size="sm" onClick={saveRetentionDraft} disabled={Boolean(mutating)}>
                        <Save />
                        Save
                      </Button>
                    }
                  >
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                      {data.retentionPolicies.map((policy) => {
                        const stats = data.retentionStats.find(
                          (item) => item.metric_table === policy.metric_table
                        );
                        return (
                          <label
                            key={policy.metric_table}
                            className="grid gap-2 rounded-2xl border border-border/70 bg-card p-4 shadow-sm shadow-slate-950/5"
                          >
                            <FieldLabel>{policy.metric_table}</FieldLabel>
                            <Input
                              type="number"
                              min={7}
                              value={retentionDraft[policy.metric_table] ?? policy.retention_days}
                              onChange={(event) =>
                                setRetentionDraft((prev) => ({
                                  ...prev,
                                  [policy.metric_table]: Number(event.target.value),
                                }))
                              }
                            />
                            <span className="text-xs text-muted-foreground">
                              {stats
                                ? `${stats.num_files ?? '-'} files · ${stats.size_in_bytes ?? '-'} bytes`
                                : 'Stats unavailable'}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  </AdminPanelCard>
                )}

                {activeTab === 'maintenance' && (
                  <AdminPanelCard
                    title="Maintenance Windows"
                    description="Suppress alert noise during planned work across all zones or a targeted landing zone scope."
                  >
                    <div className="grid gap-3 rounded-3xl border border-border/70 bg-[linear-gradient(135deg,color-mix(in_oklch,var(--tdf-teal)_7%,transparent),color-mix(in_oklch,var(--tdf-blue)_4%,transparent))] p-4 lg:grid-cols-5">
                      <label className="grid gap-1">
                        <FieldLabel>Window name</FieldLabel>
                        <Input
                          value={maintenanceForm.name}
                          onChange={(event) =>
                            setMaintenanceForm((prev) => ({ ...prev, name: event.target.value }))
                          }
                        />
                      </label>
                      <label className="grid gap-1">
                        <FieldLabel>Start time</FieldLabel>
                        <Input
                          type="datetime-local"
                          value={maintenanceForm.starts_at}
                          onChange={(event) =>
                            setMaintenanceForm((prev) => ({
                              ...prev,
                              starts_at: event.target.value,
                            }))
                          }
                        />
                      </label>
                      <label className="grid gap-1">
                        <FieldLabel>End time</FieldLabel>
                        <Input
                          type="datetime-local"
                          value={maintenanceForm.ends_at}
                          onChange={(event) =>
                            setMaintenanceForm((prev) => ({ ...prev, ends_at: event.target.value }))
                          }
                        />
                      </label>
                      <label className="grid gap-1">
                        <FieldLabel>Landing zone IDs</FieldLabel>
                        <Input
                          value={maintenanceLzText}
                          onChange={(event) => setMaintenanceLzText(event.target.value)}
                          placeholder="empty = all zones"
                        />
                      </label>
                      <div className="flex items-end">
                        <Button onClick={createMaintenanceFromForm} disabled={Boolean(mutating)}>
                          Create
                        </Button>
                      </div>
                    </div>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Window</TableHead>
                          <TableHead>Start</TableHead>
                          <TableHead>End</TableHead>
                          <TableHead>Scope</TableHead>
                          <TableHead>Suppress alerts</TableHead>
                          <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {data.maintenanceWindows.length === 0 ? (
                          <EmptyRows colSpan={6} message="No maintenance windows planned yet." />
                        ) : (
                          data.maintenanceWindows.map((windowItem) => (
                            <TableRow key={windowItem.id}>
                              <TableCell>
                                <p className="font-medium">{windowItem.name}</p>
                                <p className="text-xs text-muted-foreground">
                                  {windowItem.description}
                                </p>
                              </TableCell>
                              <TableCell>{formatDateTime(windowItem.starts_at)}</TableCell>
                              <TableCell>{formatDateTime(windowItem.ends_at)}</TableCell>
                              <TableCell>
                                {windowItem.lz_ids.length
                                  ? windowItem.lz_ids.join(', ')
                                  : 'All LZs'}
                              </TableCell>
                              <TableCell>
                                <Badge
                                  variant={windowItem.suppress_alerts ? 'warning' : 'secondary'}
                                >
                                  {windowItem.suppress_alerts ? 'Yes' : 'No'}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-right">
                                <Button
                                  size="sm"
                                  variant="destructive"
                                  onClick={() =>
                                    runMutation(`Deleted ${windowItem.name}`, () =>
                                      deleteMaintenanceWindow(windowItem.id)
                                    )
                                  }
                                  disabled={Boolean(mutating)}
                                >
                                  <Trash2 />
                                  Delete
                                </Button>
                              </TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </AdminPanelCard>
                )}

                {activeTab === 'embedded-dashboards' && <AdminEmbeddedDashboardsTab />}

                {activeTab === 'audit' && (
                  <AdminPanelCard
                    title="Audit Trail"
                    description="Review sensitive administration actions ordered by most recent activity."
                    actions={
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={downloadAuditCsv}
                        disabled={Boolean(mutating)}
                      >
                        <Download />
                        Export CSV
                      </Button>
                    }
                  >
                    <div className="grid gap-3 rounded-3xl border border-border/70 bg-[linear-gradient(135deg,color-mix(in_oklch,var(--tdf-blue)_6%,transparent),color-mix(in_oklch,var(--tdf-grey)_5%,transparent))] p-4 md:grid-cols-4">
                      <label className="grid gap-1">
                        <FieldLabel>Action</FieldLabel>
                        <Input
                          value={auditFilters.action ?? ''}
                          onChange={(event) =>
                            setAuditFilters((prev) => ({
                              ...prev,
                              action: event.target.value || undefined,
                              offset: 0,
                            }))
                          }
                          placeholder="user.role.update"
                        />
                      </label>
                      <label className="grid gap-1">
                        <FieldLabel>Target type</FieldLabel>
                        <Input
                          value={auditFilters.target_type ?? ''}
                          onChange={(event) =>
                            setAuditFilters((prev) => ({
                              ...prev,
                              target_type: event.target.value || undefined,
                              offset: 0,
                            }))
                          }
                          placeholder="user"
                        />
                      </label>
                      <label className="grid gap-1">
                        <FieldLabel>Actor</FieldLabel>
                        <Input
                          value={auditFilters.actor_user_id ?? ''}
                          onChange={(event) =>
                            setAuditFilters((prev) => ({
                              ...prev,
                              actor_user_id: event.target.value || undefined,
                              offset: 0,
                            }))
                          }
                        />
                      </label>
                      <div className="flex items-end">
                        <Button variant="secondary" onClick={load} disabled={Boolean(mutating)}>
                          Apply filters
                        </Button>
                      </div>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {data.auditTotal} audit entries matching filters.
                    </p>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Date</TableHead>
                          <TableHead>Actor</TableHead>
                          <TableHead>Action</TableHead>
                          <TableHead>Target</TableHead>
                          <TableHead>IP</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {data.auditLog.length === 0 ? (
                          <EmptyRows
                            colSpan={5}
                            message="No audit entries match the current filters."
                          />
                        ) : (
                          data.auditLog.map((entry) => (
                            <TableRow key={entry.id}>
                              <TableCell>{formatDateTime(entry.created_at)}</TableCell>
                              <TableCell>{entry.actor_user_id}</TableCell>
                              <TableCell>
                                <Badge variant="outline">{entry.action}</Badge>
                              </TableCell>
                              <TableCell>
                                {entry.target_type}:{entry.target_id ?? '-'}
                              </TableCell>
                              <TableCell>{entry.ip_address ?? '-'}</TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </AdminPanelCard>
                )}
              </>
            )}
          </TabsContent>
        </Tabs>
      </ContentMain>
    </Content>
  );
};

const Admin: React.FC = () => (
  <RequireAdmin>
    <AdminContent />
  </RequireAdmin>
);

export default Admin;
