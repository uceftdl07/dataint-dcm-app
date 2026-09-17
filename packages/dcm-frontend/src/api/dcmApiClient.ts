import type { UcUsageWriteCharts, UcUsageCostChanges, UcUsageEntityDetail } from '../types/api';
/**
 * DCM API client — wraps all calls to dcm-backend via API Gateway.
 *
 * When MSAL is initialized, an Entra ID Bearer token is injected by the
 * request interceptor.
 *
 * Base URL resolution:
 *   - Development: relative /api  (Vite proxy → http://localhost:8080)
 *   - Production:  VITE_API_BASE_URL  (API Gateway endpoint)
 */

import type {
  AccessRequest,
  AccessRequestCreate,
  AccessRequestsResponse,
  LzScopeRequestCreate,
  AccessRequestLandingZonesResponse,
  ReferenceBusinessApplicationsResponse,
  ReferenceProjectsResponse,
  AdminLandingZonesResponse,
  AdminAlertRule,
  AdminUser,
  AdminUserProjectInput,
  ActivityRun,
  AdminUsersResponse,
  ActivityRunsResponse,
  AlertFiringsResponse,
  AlertRulesResponse,
  AlertRuleTestResult,
  AuditLogResponse,
  ChatRequest,
  ChatResponse,
  ComputeResponse,
  ComputeMetric,
  CollectorStatusResponse,
  CostSummary,
  CostsByServiceResponse,
  CurrentDcmUser,
  DcmPermissions,
  DataProductUsageOverview,
  DataProductUsageResponse,
  DataProductUsageTrendsResponse,
  DatabasesResponse,
  DashboardFullResponse,
  DashboardOverview,
  EntraIDUsersResponse,
  GovernanceScore,
  HealthResponse,
  KpiConfigResponse,
  LandingZonesResponse,
  LandingZonesAccessOverviewResponse,
  MaintenanceWindow,
  MaintenanceWindowsResponse,
  MonitoringReportsFullResponse,
  NotificationChannel,
  NotificationChannelsResponse,
  PipelineListResponse,
  PipelineRun,
  PipelineRunsResponse,
  ProjectSummary,
  ProjectDetail,
  ProjectMember,
  ProjectJoinRequest,
  ProjectScopeRequest,
  ProjectCreatePayload,
  ProjectJoinRequestCreatePayload,
  ProjectMemberAddPayload,
  ProjectScopeRequestCreatePayload,
  ProjectRequestDecisionPayload,
  ProjectRejectPayload,
  ProjectRegisterPayload,
  ProjectRegisterResponse,
  ProjectJoinPublicPayload,
  ProjectJoinPublicResponse,
  ProjectRole,
  RetentionPoliciesResponse,
  RetentionStatsResponse,
  SecurityAlertsResponse,
  SecurityAlert,
  StandardCheck,
  StandardChecksResponse,
  StandardCheckState,
  TopDataProductConsumersResponse,
  UnityCatalogExplorerFullResponse,
  UnityCatalogExplorerResponse,
  UnityCatalogGenericQueryRequest,
  UserNotificationPreferences,
  UserNotificationPreferencesUpdate,
  UnityCatalogSchemasResponse,
  UnityCatalogTableMetadataResponse,
  UnityCatalogTablePreviewResponse,
  UnityCatalogTablesResponse,
  UsersResponse,
  LandingZoneScore,
  LakeflowOverviewResponse,
  LakeflowJobsListResponse,
  LakeflowJobDetailResponse,
  LakeflowJobRunsResponse,
  LakeflowRunTasksResponse,
  ComputeClustersOverviewResponse,
  ComputeClustersCostResponse,
  ComputeClustersEfficiencyResponse,
  ComputeClustersGovernanceResponse,
  ComputeClusterDetailResponse,
  ComputeClusterCostTrendResponse,
  ComputeClusterLifetimeTrendResponse,
  ComputeClusterWindowDays,
  ComputeMetricTrendGranularity,
  ComputeWarehousesOverviewResponse,
  ComputeWarehousesCostResponse,
  ComputeWarehousesQueryPerformanceResponse,
  ComputeWarehousesSlowQueriesResponse,
  ComputeWarehouseDetailResponse,
  ComputeWarehouseCostTrendResponse,
  ComputeWarehouseWindowDays,
  ComputeJobWindowDays,
  ComputeJobsOverviewResponse,
  ComputeJobsCostResponse,
  ComputeJobsEfficiencyResponse,
  ComputeJobDetailResponse,
  ComputeJobCostTrendResponse,
  ComputeJobUptimeTrendResponse,
  ComputePipelinesOverviewResponse,
  ComputePipelinesCostResponse,
  ComputePipelinesEfficiencyResponse,
  ComputePipelineDetailResponse,
  ComputePipelineCostTrendResponse,
  ComputePipelineUptimeTrendResponse,
  ComputeServerlessOverviewResponse,
  ComputeServerlessSurfacesResponse,
  ComputeServerlessCostTrendResponse,
  ComputeServerlessGovernanceResponse,
  ComputeServerlessLeversResponse,
  ComputeServerlessObjectsResponse,
  ComputeServerlessObjectDetailResponse,
  ComputeServerlessObjectCostTrendResponse,
  ComputeRecommendationsResponse,
  ComputeRecommendationsSummaryResponse,
  ComputeForecastResponse,
  ComputeColumnFilterOptions,
  ComputeFilterView,
  UcUsageAttentionResponse,
  UcUsageConsumerRow,
  UcUsageCostByTableRow,
  UcUsageFilterOptions,
  UcUsageFinopsKpis,
  UcUsageForecastMetric,
  UcUsageForecastSeriesResponse,
  UcUsageGovernanceKpis,
  UcUsageGovernanceCharts,
  UcUsageRecommendationCharts,
  UcUsageGovernanceSignal,
  UcUsageInactivityBucket,
  UcUsageMissingTag,
  UcUsageRecommendationAgeBucket,
  UcUsageListEnvelope,
  UcUsageOverview,
  UcUsageTableCharts,
  UcUsageConsumerCharts,
  UcUsageFinopsCharts,
  UcUsageRecommendationsResponse,
  UcUsageRegistryRow,
  UcUsageTableRow,
  UcUsageTopConsumersResponse,
} from '../types/api';

// ─── Base URL ──────────────────────────────────────────────────────────────

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.trim();

const API_BASE = API_BASE_URL ? `${API_BASE_URL}/api/v1` : '/api/v1'; // resolved by Vite proxy in dev

// ─── Token injection ───────────────────────────────────────────────────────

let _tokenGetter: ((forceRefresh?: boolean) => Promise<string | null>) | null = null;

/**
 * Register a function that resolves an Entra ID Bearer token.
 * Called once from main.tsx when MSAL is initialized.
 */
export function registerTokenGetter(
  getter: (forceRefresh?: boolean) => Promise<string | null>
): void {
  _tokenGetter = getter;
}

type ApiLoadingListener = () => void;

const apiLoadingListeners = new Set<ApiLoadingListener>();
let pendingRequestCount = 0;
const API_REQUEST_TIMEOUT_MS = 30_000;

interface DcmApiErrorDetail {
  [key: string]: unknown;
  database?: string;
  error?: string;
  status?: string;
}

export class DcmApiError extends Error {
  readonly statusCode: number;
  readonly detail: DcmApiErrorDetail | null;
  readonly responseText: string;

  constructor(statusCode: number, responseText: string, detail: DcmApiErrorDetail | null) {
    super(`DCM API ${statusCode}: ${responseText}`);
    this.name = 'DcmApiError';
    this.statusCode = statusCode;
    this.detail = detail;
    this.responseText = responseText;
  }
}

function parseErrorDetail(responseText: string): DcmApiErrorDetail | null {
  try {
    const parsed = JSON.parse(responseText) as unknown;
    const detail =
      parsed && typeof parsed === 'object' && 'detail' in parsed
        ? (parsed as { detail?: unknown }).detail
        : parsed;

    return detail && typeof detail === 'object' && !Array.isArray(detail)
      ? (detail as DcmApiErrorDetail)
      : null;
  } catch {
    return null;
  }
}

export function isDcmDatabaseUnavailableError(error: unknown): boolean {
  if (error instanceof DcmApiError) {
    return (
      error.statusCode === 503 &&
      error.detail?.status === 'degraded' &&
      error.detail?.database === 'unreachable'
    );
  }

  const message = error instanceof Error ? error.message : String(error);
  return (
    message.includes('Database pool not initialized') ||
    message.includes('"database":"unreachable"') ||
    message.includes('"database": "unreachable"')
  );
}

export function getDcmApiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof DcmApiError && typeof error.detail?.error === 'string') {
    return error.detail.error;
  }
  return error instanceof Error ? error.message : fallback;
}

function notifyApiLoadingListeners(): void {
  apiLoadingListeners.forEach((listener) => listener());
}

function startApiRequest(): void {
  pendingRequestCount += 1;
  notifyApiLoadingListeners();
}

function finishApiRequest(): void {
  pendingRequestCount = Math.max(0, pendingRequestCount - 1);
  notifyApiLoadingListeners();
}

export function getPendingApiRequestCount(): number {
  return pendingRequestCount;
}

export function subscribeToApiLoading(listener: ApiLoadingListener): () => void {
  apiLoadingListeners.add(listener);

  return () => {
    apiLoadingListeners.delete(listener);
  };
}

function shouldAttachAuthHeader(): boolean {
  return import.meta.env.VITE_ENABLE_AUTH === 'true';
}

function getDcmDevHeaders(): Record<string, string> {
  if (import.meta.env.VITE_ENABLE_AUTH === 'true') {
    return {};
  }

  const devHeaders: Record<string, string> = {
    'X-DCM-Role': import.meta.env.VITE_DCM_DEV_ROLE?.trim() || 'viewer',
    'X-DCM-User-Id': import.meta.env.VITE_DCM_DEV_USER_ID?.trim() || 'dev-user',
    'X-DCM-Email': import.meta.env.VITE_DCM_DEV_EMAIL?.trim() || 'dev.user@example.com',
    'X-DCM-Display-Name': import.meta.env.VITE_DCM_DEV_DISPLAY_NAME?.trim() || 'DCM Dev User',
  };

  const entraOid = import.meta.env.VITE_DCM_DEV_ENTRA_OID?.trim();
  if (entraOid) {
    devHeaders['X-DCM-Entra-Oid'] = entraOid;
  }

  const lzIds = import.meta.env.VITE_DCM_DEV_LZ_IDS?.trim();
  if (lzIds) {
    devHeaders['X-DCM-LZ-Ids'] = lzIds;
  }

  return devHeaders;
}

// ─── Core fetch helper ─────────────────────────────────────────────────────

type ApiMethod = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';

interface ApiRequestOptions {
  params?: Record<string, string | number | boolean | string[] | undefined>;
  method?: ApiMethod;
  body?: unknown;
  parseAs?: 'json' | 'text';
  /** Public endpoints (e.g. landing access request) work without Entra token */
  skipAuth?: boolean;
  /** Background/bootstrap calls — do not drive the global loading overlay */
  silent?: boolean;
}

const TRANSIENT_HTTP_STATUSES = new Set([502, 503, 504]);
const MAX_TRANSIENT_RETRIES = 2;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
  attempt = 0
): Promise<T> {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);

  if (options.params) {
    Object.entries(options.params).forEach(([key, value]) => {
      if (value === undefined || value === null) {
        return;
      }
      if (Array.isArray(value)) {
        // Empty arrays must still appear in the query string so the backend can
        // distinguish "no filter" (param absent) from "explicit empty selection".
        if (value.length === 0) {
          url.searchParams.append(key, '');
          return;
        }
        value.forEach((item) => {
          url.searchParams.append(key, String(item));
        });
        return;
      }
      url.searchParams.set(key, String(value));
    });
  }

  const trackLoading = !options.silent;
  if (trackLoading) {
    startApiRequest();
  }

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), API_REQUEST_TIMEOUT_MS);

  try {
    const headers: Record<string, string> = {
      ...getDcmDevHeaders(),
    };
    if (options.body !== undefined) {
      headers['Content-Type'] = 'application/json';
    }

    const tokenGetter = _tokenGetter;
    if (tokenGetter && shouldAttachAuthHeader() && !options.skipAuth) {
      const token = await tokenGetter(attempt > 0); // force refresh on retry
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      } else {
        console.error('❌ [API] Auth enabled but token unavailable');
        throw new Error('Authentication token unavailable. Please sign in again.');
      }
    }

    const response = await fetch(url.toString(), {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    });

    if (!response.ok) {
      const detail = await response.text();
      const error = new DcmApiError(response.status, detail, parseErrorDetail(detail));

      // Retry once on 401 with fresh token
      if (response.status === 401 && attempt === 0 && tokenGetter && shouldAttachAuthHeader()) {
        console.warn('⚠️ [API] 401 Unauthorized — retrying with fresh token...');
        return apiRequest<T>(path, options, attempt + 1);
      }

      // Retry transient gateway / restart errors (avoids hard refresh after ECS recycle)
      if (TRANSIENT_HTTP_STATUSES.has(response.status) && attempt < MAX_TRANSIENT_RETRIES) {
        const delayMs = 400 * 2 ** attempt;
        console.warn(
          `⚠️ [API] ${response.status} on ${path} — retry ${attempt + 1}/${MAX_TRANSIENT_RETRIES} in ${delayMs}ms`
        );
        await sleep(delayMs);
        return apiRequest<T>(path, options, attempt + 1);
      }

      throw error;
    }

    if (options.parseAs === 'text') {
      return response.text() as Promise<T>;
    }

    return response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('DCM API request timed out. Verify the backend is running and reachable.');
    }
    // CORS / connection drop during ALB drain often surfaces as TypeError: Failed to fetch
    if (error instanceof TypeError && attempt < MAX_TRANSIENT_RETRIES) {
      const delayMs = 400 * 2 ** attempt;
      console.warn(
        `⚠️ [API] network error on ${path} — retry ${attempt + 1}/${MAX_TRANSIENT_RETRIES} in ${delayMs}ms`
      );
      await sleep(delayMs);
      return apiRequest<T>(path, options, attempt + 1);
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
    if (trackLoading) {
      finishApiRequest();
    }
  }
}

type ApiFetchOptions = {
  silent?: boolean;
};

async function apiFetch<T>(
  path: string,
  params?: Record<string, string | string[] | number | boolean | undefined>,
  fetchOptions?: ApiFetchOptions
): Promise<T> {
  return apiRequest<T>(path, { params, silent: fetchOptions?.silent });
}

// ─── Health ────────────────────────────────────────────────────────────────

export async function getHealth(): Promise<HealthResponse> {
  return apiFetch('/health');
}

// ─── Dashboard ─────────────────────────────────────────────────────────────

export interface DashboardParams {
  [key: string]: string | number | boolean | undefined;
  start_date?: string;
  end_date?: string;
  cloud_provider?: string;
  source_lz_id?: string;
}

export async function getDashboardOverview(params?: DashboardParams): Promise<DashboardOverview> {
  return apiFetch('/dashboard/overview', params);
}

export interface DashboardFullParams extends DashboardParams {
  workspace_id?: string;
  workspace_ids?: string[];
}

export async function getDashboardFull(
  params?: DashboardFullParams
): Promise<DashboardFullResponse> {
  return apiFetch('/dashboard/full', params);
}

// ─── Monitoring Reports ─────────────────────────────────────────────────────

export interface MonitoringReportsFullParams {
  [key: string]: string | number | boolean | string[] | undefined;
  start_date?: string;
  end_date?: string;
  cloud_provider?: string;
  source_lz_id?: string;
  source_lz_ids?: string[];
  subscription_or_account_id?: string;
  usage_limit?: number;
  list_limit?: number;
  trend_grain?: 'day' | 'week' | 'month';
}

interface MonitoringReportsFullApiResponse {
  data_product_usage: DataProductUsageResponse;
  usage_trends: DataProductUsageTrendsResponse;
  standard_checks: StandardChecksApiResponse;
  landing_zones: LandingZonesResponse;
  security_alerts: SecurityAlertsResponse;
  computes: ComputeResponse;
  pipelines: PipelineListResponse;
  cost_summary: CostSummary;
  costs_by_service: CostsByServiceResponse;
  governance: GovernanceScoreApi;
}

export async function getMonitoringReportsFull(
  params?: MonitoringReportsFullParams
): Promise<MonitoringReportsFullResponse> {
  const response = await apiFetch<MonitoringReportsFullApiResponse>(
    '/monitoring-reports/full',
    params
  );
  return {
    ...response,
    standard_checks: {
      ...response.standard_checks,
      items: (response.standard_checks.items ?? []).map(normalizeStandardCheck),
    },
    governance: normalizeGovernanceScore(response.governance),
  };
}

// ─── Pipelines ─────────────────────────────────────────────────────────────

export interface PipelineListParams {
  [key: string]: string | number | boolean | undefined;
  cloud_provider?: string;
  pipeline_type?: string;
  status?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;
  offset?: number;
}

export async function listPipelines(params?: PipelineListParams): Promise<PipelineListResponse> {
  return apiFetch('/pipelines', params);
}

export interface PipelineRunsParams {
  [key: string]: string | number | boolean | undefined;
  start_date?: string;
  end_date?: string;
  limit?: number;
}

export async function getPipelineRuns(
  pipelineName: string,
  params?: PipelineRunsParams
): Promise<PipelineRunsResponse> {
  return apiFetch(`/pipelines/${encodeURIComponent(pipelineName)}/runs`, params);
}

// ─── Clusters ──────────────────────────────────────────────────────────────

export interface ComputeListParams {
  [key: string]: string | number | boolean | string[] | undefined;
  cloud_provider?: string;
  workspace_id?: string;
  workspace_ids?: string[];
  state?: string;
}

export async function listComputes(params?: ComputeListParams): Promise<ComputeResponse> {
  return apiFetch('/clusters', params);
}

// ─── Databricks ────────────────────────────────────────────────────────────

export interface DatabricksWorkspace {
  workspace_id: string;
  display_name: string;
  /** Null when the only source that knows the workspace has no LZ column. */
  source_lz_id: string | null;
  cluster_count: number;
}

export interface DatabricksWorkspacesResponse {
  items: DatabricksWorkspace[];
}

export async function listDatabricksWorkspaces(): Promise<DatabricksWorkspacesResponse> {
  return apiFetch('/databricks/workspaces', undefined, { silent: true });
}

export interface EmbeddedDashboard {
  dashboard_slug: string;
  title: string;
  description: string | null;
  workspace_host: string;
  workspace_id: string;
  dashboard_id: string;
  scope: 'global' | 'workspace' | 'landing_zone' | string;
  source_lz_id: string | null;
  menu_group: string;
  sort_order: number;
  embed_url: string;
  direct_url: string;
}

export interface EmbeddedDashboardsResponse {
  items: EmbeddedDashboard[];
}

export async function listEmbeddedDashboards(
  menuGroup = 'insights'
): Promise<EmbeddedDashboardsResponse> {
  const params = new URLSearchParams();
  if (menuGroup) {
    params.set('menu_group', menuGroup);
  }
  const query = params.toString();
  return apiFetch(`/databricks/embedded-dashboards${query ? `?${query}` : ''}`);
}

export async function getEmbeddedDashboard(slug: string): Promise<EmbeddedDashboard> {
  return apiFetch(`/databricks/embedded-dashboards/${encodeURIComponent(slug)}`);
}

export interface AdminEmbeddedDashboard extends EmbeddedDashboard {
  enabled: boolean;
}

export interface AdminEmbeddedDashboardsResponse {
  items: AdminEmbeddedDashboard[];
}

export interface AdminEmbeddedDashboardCreate {
  dashboard_slug: string;
  title: string;
  description?: string | null;
  workspace_host: string;
  workspace_id: string;
  dashboard_id: string;
  scope?: 'global' | 'workspace' | 'landing_zone' | string;
  source_lz_id?: string | null;
  menu_group?: string;
  sort_order?: number;
  enabled?: boolean;
}

export type AdminEmbeddedDashboardUpdate = Partial<
  Omit<AdminEmbeddedDashboardCreate, 'dashboard_slug'>
>;

export async function listAdminEmbeddedDashboards(): Promise<AdminEmbeddedDashboardsResponse> {
  return apiFetch('/admin/embedded-dashboards');
}

export async function createAdminEmbeddedDashboard(
  payload: AdminEmbeddedDashboardCreate
): Promise<AdminEmbeddedDashboard> {
  return apiFetch('/admin/embedded-dashboards', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateAdminEmbeddedDashboard(
  slug: string,
  payload: AdminEmbeddedDashboardUpdate
): Promise<AdminEmbeddedDashboard> {
  return apiFetch(`/admin/embedded-dashboards/${encodeURIComponent(slug)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function deleteAdminEmbeddedDashboard(slug: string): Promise<void> {
  await apiFetch(`/admin/embedded-dashboards/${encodeURIComponent(slug)}`, {
    method: 'DELETE',
  });
}

export interface DatabricksFullParams {
  start_date?: string;
  end_date?: string;
  cloud_provider?: string;
  source_lz_id?: string;
  source_lz_ids?: string[];
  subscription_or_account_id?: string;
  workspace_id?: string;
  workspace_ids?: string[];
  list_limit?: number;
}

export interface DatabricksFullResponse {
  computes: { items: ComputeMetric[] };
  governance: GovernanceScore;
  pipelines: { items: PipelineRun[] };
  activities: { items: ActivityRun[] };
  costs: { items: ServiceCostDetail[] };
  alerts: { items: SecurityAlert[] };
  checks: { items: StandardCheck[] };
  period: { start: string; end: string };
}

export async function getDatabricksFull(
  params?: DatabricksFullParams
): Promise<DatabricksFullResponse> {
  return apiFetch('/databricks/full', params);
}

// ─── Lakeflow Overview ─────────────────────────────────────────────────────

export interface LakeflowOverviewParams {
  [key: string]: string | string[] | undefined;
  window?: 'today' | '7d' | '30d';
  start_date?: string;
  end_date?: string;
  source_lz_id?: string;
  source_lz_ids?: string[];
  workspace_id?: string;
  workspace_ids?: string[];
}

export async function getLakeflowOverview(
  params?: LakeflowOverviewParams
): Promise<LakeflowOverviewResponse> {
  return apiFetch('/lakeflow/overview', params);
}

export interface LakeflowJobsParams {
  [key: string]: string | string[] | number | boolean | undefined;
  window?: string;
  start_date?: string;
  end_date?: string;
  source_lz_id?: string;
  source_lz_ids?: string[];
  workspace_id?: string;
  workspace_ids?: string[];
  search?: string;
  status?: string[];
  trigger_type?: string[];
  owner?: string[];
  /** Repeatable `<column>:<value>` — see `ComputeMetricsPageParams.column_filter`. */
  column_filter?: string[];
  drift_only?: boolean;
  no_runs?: boolean;
  with_retries?: boolean;
  sort?: string;
  order?: string;
  page?: number;
  page_size?: number;
}

export async function getLakeflowJobs(
  params?: LakeflowJobsParams
): Promise<LakeflowJobsListResponse> {
  return apiFetch('/lakeflow/jobs', params);
}

export async function getLakeflowJob(
  workflowId: string,
  params?: LakeflowJobsParams
): Promise<LakeflowJobDetailResponse> {
  return apiFetch(`/lakeflow/jobs/${encodeURIComponent(workflowId)}`, params);
}

export async function getLakeflowJobRuns(
  workflowId: string,
  params?: LakeflowJobsParams
): Promise<LakeflowJobRunsResponse> {
  return apiFetch(`/lakeflow/jobs/${encodeURIComponent(workflowId)}/runs`, params);
}

export async function getLakeflowRunTasks(
  workflowId: string,
  runId: string,
  params?: {
    failed_only?: boolean;
    source_lz_id?: string;
    source_lz_ids?: string[];
    workspace_ids?: string[];
  }
): Promise<LakeflowRunTasksResponse> {
  return apiFetch(
    `/lakeflow/jobs/${encodeURIComponent(workflowId)}/runs/${encodeURIComponent(runId)}/tasks`,
    params
  );
}

/**
 * Twin of `getComputeFilterOptions` for the two Lakeflow views, same response shape.
 *
 * A separate route rather than a `view` parameter on the compute one because the two
 * prefixes do not resolve the same perimeter (`AllowedScope` against
 * `allowed_lz_ids`/`allowed_workspace_ids`); each refuses the other's views.
 */
export interface LakeflowFilterOptionsParams {
  [key: string]: string | string[] | number | boolean | undefined;
  view: 'lakeflow-jobs' | 'lakeflow-job-runs';
  column: string;
  window?: string;
  start_date?: string;
  end_date?: string;
  source_lz_id?: string;
  source_lz_ids?: string[];
  workspace_id?: string;
  workspace_ids?: string[];
  /** Narrows the `lakeflow-job-runs` view to the workflow the page is showing. */
  workflow_id?: string;
  q?: string;
  limit?: number;
}

export async function getLakeflowFilterOptions(
  params: LakeflowFilterOptionsParams
): Promise<ComputeColumnFilterOptions> {
  return apiFetch('/lakeflow/filter-options', params);
}

// ─── Databricks Compute Metrics (T001) ───────────────────────────────────────

export interface ComputeMetricsScopeParams {
  [key: string]: string | string[] | number | boolean | undefined;
  period_start?: string;
  period_end?: string;
  source_lz_id?: string;
  source_lz_ids?: string[];
  workspace_id?: string;
  workspace_ids?: string[];
  cloud_provider?: string;
}

export interface ComputeMetricsPageParams extends ComputeMetricsScopeParams {
  page?: number;
  page_size?: number;
  /**
   * Repeatable `<column>:<value>`, declared once here for the nine compute list
   * views. Applied **server-side** over the whole perimeter: the eleven tables
   * paginate on the server, so a filter kept in the component would only ever see
   * the 25 rows of the current page. An unknown key is answered 422, never as a
   * silently empty page — see `getComputeFilterOptions` for the accepted keys.
   */
  column_filter?: string[];
}

/**
 * The three list views and the detail read a `*_rolling` table: they take the
 * window instead of a free period. `period_start`/`period_end` stay accepted by
 * the backend but no longer narrow those responses.
 */
export interface ComputeClustersWindowParams extends ComputeMetricsScopeParams {
  window_days?: ComputeClusterWindowDays;
}

export interface ComputeClustersCostParams extends ComputeMetricsPageParams {
  window_days?: ComputeClusterWindowDays;
  search?: string;
  sku_group?: string;
  sort?: 'cost_desc' | 'name' | 'rank';
}

/** Sort keys the overview endpoint allowlists; anything else falls back to cost. */
export type ComputeClustersOverviewSort =
  | 'cluster'
  | 'workspace'
  | 'cluster_type'
  | 'cost'
  | 'cost_prev'
  | 'cluster_lifetime'
  | 'cluster_lifetime_prev'
  | 'utilization'
  | 'governance';

/**
 * The overview pages, sorts and searches on the server. It has to: there are
 * 1.4 M rolling rows at `window_days=90`, so a client-side filter would only ever
 * see whatever slice the server happened to send.
 */
export interface ComputeClustersOverviewParams extends ComputeMetricsPageParams {
  window_days?: ComputeClusterWindowDays;
  search?: string;
  utilization_status?: string;
  sort?: ComputeClustersOverviewSort;
  sort_direction?: 'asc' | 'desc';
}

export async function getComputeClustersOverview(
  params?: ComputeClustersOverviewParams
): Promise<ComputeClustersOverviewResponse> {
  return apiFetch('/databricks/compute/clusters/overview', params);
}

export async function listComputeClustersCost(
  params?: ComputeClustersCostParams
): Promise<ComputeClustersCostResponse> {
  return apiFetch('/databricks/compute/clusters/cost', params);
}

export interface ComputeClustersEfficiencyParams extends ComputeMetricsPageParams {
  window_days?: ComputeClusterWindowDays;
  utilization_status?: string;
  is_zombie?: boolean;
}

export async function listComputeClustersEfficiency(
  params?: ComputeClustersEfficiencyParams
): Promise<ComputeClustersEfficiencyResponse> {
  return apiFetch('/databricks/compute/clusters/efficiency', params);
}

export interface ComputeClustersGovernanceParams extends ComputeMetricsPageParams {
  severity?: string;
  missing_tags?: boolean;
  dbr_obsolete?: boolean;
}

export async function listComputeClustersGovernance(
  params?: ComputeClustersGovernanceParams
): Promise<ComputeClustersGovernanceResponse> {
  return apiFetch('/databricks/compute/clusters/governance', params);
}

export async function getComputeClusterDetail(
  clusterId: string,
  params?: ComputeClustersWindowParams
): Promise<ComputeClusterDetailResponse> {
  return apiFetch(`/databricks/compute/clusters/${encodeURIComponent(clusterId)}`, params);
}

/**
 * Both per-cluster trends serve a ≈90-point series over `period_start`/
 * `period_end`, so they read the `*_daily` tables and take no `window_days`.
 */
export interface ComputeClusterTrendParams extends ComputeMetricsScopeParams {
  granularity?: ComputeMetricTrendGranularity;
}

export type ComputeClusterCostTrendParams = ComputeClusterTrendParams;

export async function getComputeClusterCostTrend(
  clusterId: string,
  params?: ComputeClusterTrendParams
): Promise<ComputeClusterCostTrendResponse> {
  return apiFetch(
    `/databricks/compute/clusters/${encodeURIComponent(clusterId)}/cost-trend`,
    params
  );
}

export async function getComputeClusterLifetimeTrend(
  clusterId: string,
  params?: ComputeClusterTrendParams
): Promise<ComputeClusterLifetimeTrendResponse> {
  return apiFetch(
    `/databricks/compute/clusters/${encodeURIComponent(clusterId)}/lifetime-trend`,
    params
  );
}

/**
 * The three warehouse list views read a `*_rolling` table: they take the window
 * instead of a free period. `/warehouses/slow-queries` and the two per-warehouse
 * endpoints keep the daily grain and take no `window_days`.
 */
export interface ComputeWarehousesCostParams extends ComputeMetricsPageParams {
  window_days?: ComputeWarehouseWindowDays;
  search?: string;
  warehouse_size?: string;
  sort?: 'cost_desc' | 'name';
}

/** Sort keys the overview endpoint allowlists; anything else falls back to cost. */
export type ComputeWarehousesOverviewSort =
  | 'warehouse'
  | 'workspace'
  | 'size'
  | 'type'
  | 'cost'
  | 'queries'
  | 'failure'
  | 'latency';

export interface ComputeWarehousesOverviewParams extends ComputeMetricsPageParams {
  window_days?: ComputeWarehouseWindowDays;
  search?: string;
  warehouse_size?: string;
  min_failure_rate_pct?: number;
  sort?: ComputeWarehousesOverviewSort;
  sort_direction?: 'asc' | 'desc';
}

export async function getComputeWarehousesOverview(
  params?: ComputeWarehousesOverviewParams
): Promise<ComputeWarehousesOverviewResponse> {
  return apiFetch('/databricks/compute/warehouses/overview', params);
}

export async function listComputeWarehousesCost(
  params?: ComputeWarehousesCostParams
): Promise<ComputeWarehousesCostResponse> {
  return apiFetch('/databricks/compute/warehouses/cost', params);
}

export interface ComputeWarehousesQueryPerformanceParams extends ComputeMetricsPageParams {
  window_days?: ComputeWarehouseWindowDays;
  min_failure_rate_pct?: number;
  has_spill?: boolean;
  min_latency_p95_ms?: number;
}

export async function listComputeWarehousesQueryPerformance(
  params?: ComputeWarehousesQueryPerformanceParams
): Promise<ComputeWarehousesQueryPerformanceResponse> {
  return apiFetch('/databricks/compute/warehouses/query-performance', params);
}

export interface ComputeWarehousesSlowQueriesParams extends ComputeMetricsPageParams {
  warehouse_id?: string;
  reason?: string;
}

export async function listComputeWarehousesSlowQueries(
  params?: ComputeWarehousesSlowQueriesParams
): Promise<ComputeWarehousesSlowQueriesResponse> {
  return apiFetch('/databricks/compute/warehouses/slow-queries', params);
}

export async function getComputeWarehouseDetail(
  warehouseId: string,
  params?: ComputeMetricsScopeParams
): Promise<ComputeWarehouseDetailResponse> {
  return apiFetch(`/databricks/compute/warehouses/${encodeURIComponent(warehouseId)}`, params);
}

export interface ComputeWarehouseCostTrendParams extends ComputeMetricsScopeParams {
  granularity?: ComputeMetricTrendGranularity;
}

export async function getComputeWarehouseCostTrend(
  warehouseId: string,
  params?: ComputeWarehouseCostTrendParams
): Promise<ComputeWarehouseCostTrendResponse> {
  return apiFetch(
    `/databricks/compute/warehouses/${encodeURIComponent(warehouseId)}/cost-trend`,
    params
  );
}

/**
 * Job and pipeline compute read the same four `*_rolling` windows as clusters and
 * warehouses, at the stable grain (`job_id`, `dlt_pipeline_id`). They take the
 * window instead of a free period and, unlike warehouses, no `column_filter`.
 */
export interface ComputeJobsCostParams extends ComputeMetricsPageParams {
  window_days?: ComputeJobWindowDays;
  search?: string;
  sort?: 'cost_desc' | 'name';
}

export type ComputeJobsOverviewParams = ComputeJobsCostParams;

/** The two detail endpoints read the same `*_rolling` snapshot: window, no paging. */
export interface ComputeStableGrainWindowParams extends ComputeMetricsScopeParams {
  window_days?: ComputeJobWindowDays;
}

export async function getComputeJobsOverview(
  params?: ComputeJobsOverviewParams
): Promise<ComputeJobsOverviewResponse> {
  return apiFetch('/databricks/compute/jobs/overview', params);
}

export async function listComputeJobsCost(
  params?: ComputeJobsCostParams
): Promise<ComputeJobsCostResponse> {
  return apiFetch('/databricks/compute/jobs/cost', params);
}

/**
 * Sort keys the two `efficiency` endpoints allowlist; anything else falls back to
 * `savings_desc`. A different set from the cost views, which have no savings.
 */
export type ComputeStableGrainEfficiencySort = 'savings_desc' | 'uptime' | 'name';

export interface ComputeJobsEfficiencyParams extends ComputeMetricsPageParams {
  window_days?: ComputeJobWindowDays;
  search?: string;
  sort?: ComputeStableGrainEfficiencySort;
}

export async function listComputeJobsEfficiency(
  params?: ComputeJobsEfficiencyParams
): Promise<ComputeJobsEfficiencyResponse> {
  return apiFetch('/databricks/compute/jobs/efficiency', params);
}

export async function getComputeJobDetail(
  jobId: string,
  params?: ComputeStableGrainWindowParams
): Promise<ComputeJobDetailResponse> {
  return apiFetch(`/databricks/compute/jobs/${encodeURIComponent(jobId)}`, params);
}

/**
 * The per-grain trends serve a ≈90-point series over `period_start`/`period_end`,
 * so they read the `*_daily` tables and take no `window_days`.
 */
export interface ComputeStableGrainTrendParams extends ComputeMetricsScopeParams {
  granularity?: ComputeMetricTrendGranularity;
}

export async function getComputeJobCostTrend(
  jobId: string,
  params?: ComputeStableGrainTrendParams
): Promise<ComputeJobCostTrendResponse> {
  return apiFetch(`/databricks/compute/jobs/${encodeURIComponent(jobId)}/cost-trend`, params);
}

/**
 * `uptime-trend`, not `lifetime-trend` like the cluster homologue: "lifetime" has
 * no meaning for a cluster destroyed at the end of each run — the quantity tracked
 * is the grain's **cumulated** uptime.
 */
export async function getComputeJobUptimeTrend(
  jobId: string,
  params?: ComputeStableGrainTrendParams
): Promise<ComputeJobUptimeTrendResponse> {
  return apiFetch(`/databricks/compute/jobs/${encodeURIComponent(jobId)}/uptime-trend`, params);
}

export interface ComputePipelinesCostParams extends ComputeMetricsPageParams {
  window_days?: ComputeJobWindowDays;
  search?: string;
  sort?: 'cost_desc' | 'name';
}

export type ComputePipelinesOverviewParams = ComputePipelinesCostParams;

export async function getComputePipelinesOverview(
  params?: ComputePipelinesOverviewParams
): Promise<ComputePipelinesOverviewResponse> {
  return apiFetch('/databricks/compute/pipelines/overview', params);
}

export async function listComputePipelinesCost(
  params?: ComputePipelinesCostParams
): Promise<ComputePipelinesCostResponse> {
  return apiFetch('/databricks/compute/pipelines/cost', params);
}

export interface ComputePipelinesEfficiencyParams extends ComputeMetricsPageParams {
  window_days?: ComputeJobWindowDays;
  search?: string;
  sort?: ComputeStableGrainEfficiencySort;
}

export async function listComputePipelinesEfficiency(
  params?: ComputePipelinesEfficiencyParams
): Promise<ComputePipelinesEfficiencyResponse> {
  return apiFetch('/databricks/compute/pipelines/efficiency', params);
}

export async function getComputePipelineDetail(
  pipelineId: string,
  params?: ComputeStableGrainWindowParams
): Promise<ComputePipelineDetailResponse> {
  return apiFetch(`/databricks/compute/pipelines/${encodeURIComponent(pipelineId)}`, params);
}

export async function getComputePipelineCostTrend(
  pipelineId: string,
  params?: ComputeStableGrainTrendParams
): Promise<ComputePipelineCostTrendResponse> {
  return apiFetch(
    `/databricks/compute/pipelines/${encodeURIComponent(pipelineId)}/cost-trend`,
    params
  );
}

export async function getComputePipelineUptimeTrend(
  pipelineId: string,
  params?: ComputeStableGrainTrendParams
): Promise<ComputePipelineUptimeTrendResponse> {
  return apiFetch(
    `/databricks/compute/pipelines/${encodeURIComponent(pipelineId)}/uptime-trend`,
    params
  );
}

// ─── Databricks Compute Metrics — Serverless (025) ───────────────────────────

/**
 * The five aggregate endpoints and the two per-object ones, all under
 * `/databricks/compute/serverless/*`.
 *
 * Which of them takes `window_days` is not a detail: `overview`, `surfaces`, `levers`
 * and `objects` read a `*_rolling` snapshot and take it, while `cost-trend` reads the
 * daily table and `governance` reads a 90-day snapshot — sending a window to those two
 * would suggest the response follows it.
 */
export interface ComputeServerlessWindowParams extends ComputeMetricsScopeParams {
  window_days?: ComputeJobWindowDays;
}

export type ComputeServerlessOverviewParams = ComputeServerlessWindowParams;

export async function getComputeServerlessOverview(
  params?: ComputeServerlessOverviewParams
): Promise<ComputeServerlessOverviewResponse> {
  return apiFetch('/databricks/compute/serverless/overview', params);
}

/** Sort keys the surfaces endpoint allowlists; anything else falls back to cost. */
export type ComputeServerlessSurfacesSort =
  | 'cost'
  | 'surface'
  | 'dbu'
  | 'objects'
  | 'runs'
  | 'delta';

export interface ComputeServerlessSurfacesParams extends ComputeServerlessWindowParams {
  sort?: ComputeServerlessSurfacesSort;
  sort_direction?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
}

export async function listComputeServerlessSurfaces(
  params?: ComputeServerlessSurfacesParams
): Promise<ComputeServerlessSurfacesResponse> {
  return apiFetch('/databricks/compute/serverless/surfaces', params);
}

/**
 * Daily serverless cost — read from the **daily** table, so no `window_days`. Without
 * `surface` the series is split across the top surfaces by spend and the rest folded
 * into `OTHER_SURFACES`.
 */
export interface ComputeServerlessCostTrendParams extends ComputeMetricsScopeParams {
  granularity?: ComputeMetricTrendGranularity;
  surface?: string;
}

export async function getComputeServerlessCostTrend(
  params?: ComputeServerlessCostTrendParams
): Promise<ComputeServerlessCostTrendResponse> {
  return apiFetch('/databricks/compute/serverless/cost-trend', params);
}

/**
 * Coverage per (workspace, surface). Takes **no** `window_days`: the governance table
 * is a 90-day snapshot with its own cadence, and it legends its own span in
 * `governance_period`.
 */
export interface ComputeServerlessGovernanceParams extends ComputeMetricsPageParams {
  sort?:
    | 'cost'
    | 'workspace'
    | 'surface'
    | 'owner_tag'
    | 'cost_center_tag'
    | 'budget_policy'
    | 'identity';
  sort_direction?: 'asc' | 'desc';
}

export async function listComputeServerlessGovernance(
  params?: ComputeServerlessGovernanceParams
): Promise<ComputeServerlessGovernanceResponse> {
  return apiFetch('/databricks/compute/serverless/governance', params);
}

export type ComputeServerlessLeversParams = ComputeServerlessWindowParams;

export async function getComputeServerlessLevers(
  params?: ComputeServerlessLeversParams
): Promise<ComputeServerlessLeversResponse> {
  return apiFetch('/databricks/compute/serverless/levers', params);
}

/** Sort keys the objects endpoint allowlists; anything else falls back to cost. */
export type ComputeServerlessObjectsSort =
  | 'cost'
  | 'object'
  | 'surface'
  | 'workspace'
  | 'dbu'
  | 'runs'
  | 'cost_per_run'
  | 'delta';

export interface ComputeServerlessObjectsParams extends ComputeMetricsPageParams {
  window_days?: ComputeJobWindowDays;
  surface?: string;
  search?: string;
  sort?: ComputeServerlessObjectsSort;
  sort_direction?: 'asc' | 'desc';
}

export async function listComputeServerlessObjects(
  params?: ComputeServerlessObjectsParams
): Promise<ComputeServerlessObjectsResponse> {
  return apiFetch('/databricks/compute/serverless/objects', params);
}

/**
 * `surface` is **required** on both per-object endpoints, and it is a query parameter
 * rather than part of the path because it completes the identity: the same `object_id`
 * is legitimately billed under two surfaces.
 */
export interface ComputeServerlessObjectDetailParams extends ComputeServerlessWindowParams {
  surface: string;
}

export async function getComputeServerlessObjectDetail(
  objectId: string,
  params: ComputeServerlessObjectDetailParams
): Promise<ComputeServerlessObjectDetailResponse> {
  return apiFetch(`/databricks/compute/serverless/objects/${encodeURIComponent(objectId)}`, params);
}

export interface ComputeServerlessObjectCostTrendParams extends ComputeMetricsScopeParams {
  surface: string;
  granularity?: ComputeMetricTrendGranularity;
}

export async function getComputeServerlessObjectCostTrend(
  objectId: string,
  params: ComputeServerlessObjectCostTrendParams
): Promise<ComputeServerlessObjectCostTrendResponse> {
  return apiFetch(
    `/databricks/compute/serverless/objects/${encodeURIComponent(objectId)}/cost-trend`,
    params
  );
}

export interface ComputeRecommendationsParams extends ComputeMetricsPageParams {
  object_type?: string;
  category?: string;
  severity?: string;
  status?: string;
  search?: string;
  sort?: 'severity' | 'savings' | 'since' | 'object' | 'status' | 'category';
  order?: 'asc' | 'desc';
}

export async function getComputeRecommendations(
  params?: ComputeRecommendationsParams
): Promise<ComputeRecommendationsResponse> {
  return apiFetch('/databricks/compute/recommendations', params);
}

export async function getComputeRecommendationsSummary(
  params?: ComputeMetricsScopeParams
): Promise<ComputeRecommendationsSummaryResponse> {
  return apiFetch('/databricks/compute/recommendations/summary', params);
}

export interface ComputeForecastParams extends ComputeMetricsScopeParams {
  metric_name?: string;
  object_type?: string;
  object_id?: string;
}

export async function getComputeForecast(
  params?: ComputeForecastParams
): Promise<ComputeForecastResponse> {
  return apiFetch('/databricks/compute/forecast', params);
}

/**
 * Values offered for one filterable column, over the caller's whole perimeter.
 *
 * Deliberately takes the view's **scope** (perimeter, cloud, window, period) and
 * never a `column_filter`: the list describes the perimeter, not the current
 * selection. Sending the active filters would empty the lists of every other
 * column, and the user could no longer widen what they had just narrowed.
 */
export interface ComputeFilterOptionsParams extends ComputeMetricsScopeParams {
  view: ComputeFilterView;
  column: string;
  q?: string;
  limit?: number;
  window_days?: number;
}

export async function getComputeFilterOptions(
  params: ComputeFilterOptionsParams
): Promise<ComputeColumnFilterOptions> {
  return apiFetch('/databricks/compute/filter-options', params);
}

export interface DataFactoryFullParams {
  start_date?: string;
  end_date?: string;
  source_lz_id?: string;
  source_lz_ids?: string[];
  list_limit?: number;
}

export interface DataFactoryFullResponse {
  pipelines: { items: PipelineRun[]; total: number };
  period: { start: string; end: string };
}

export async function getDataFactoryFull(
  params?: DataFactoryFullParams
): Promise<DataFactoryFullResponse> {
  return apiFetch('/datafactory/full', params);
}

// ─── Costs ─────────────────────────────────────────────────────────────────

export interface CostParams {
  [key: string]: string | number | boolean | undefined;
  start_date?: string;
  end_date?: string;
  cloud_provider?: string;
  source_lz_id?: string;
}

export async function getCostSummary(params?: CostParams): Promise<CostSummary> {
  return apiFetch('/costs/summary', params);
}

export async function getCostsByService(params?: CostParams): Promise<CostsByServiceResponse> {
  return apiFetch('/costs/by-service', params);
}

export interface FinOpsPageBundleParams {
  start_date: string;
  end_date: string;
  cloud_provider?: string;
}

export interface FinOpsPageBundleData {
  summary: CostSummary;
  byService: CostsByServiceResponse;
}

interface FinOpsPageBundleApi {
  summary: CostSummary;
  by_service: CostsByServiceResponse;
}

export async function getFinOpsPageBundle(
  params: FinOpsPageBundleParams
): Promise<FinOpsPageBundleData> {
  const response = await apiFetch<FinOpsPageBundleApi>('/costs/page-bundle', params);
  return {
    summary: response.summary,
    byService: response.by_service,
  };
}

// ─── Data Product Usage ─────────────────────────────────────────────────────

export interface DataProductUsageParams {
  [key: string]: string | number | boolean | undefined;
  start_date?: string;
  end_date?: string;
  cloud_provider?: string;
  source_lz_id?: string;
  subscription_or_account_id?: string;
  data_product_id?: string;
  consumer_id?: string;
}

export interface DataProductUsageTrendParams extends DataProductUsageParams {
  grain?: 'day' | 'week' | 'month';
}

export interface TopDataProductConsumersParams extends DataProductUsageParams {
  metric?: string;
  limit?: number;
}

export interface DataProductUsageListParams extends DataProductUsageParams {
  limit?: number;
  offset?: number;
}

export async function getDataProductUsageOverview(
  params?: DataProductUsageParams
): Promise<DataProductUsageOverview> {
  return apiFetch('/data-product-usage/overview', params);
}

export async function getDataProductUsageTrends(
  params?: DataProductUsageTrendParams
): Promise<DataProductUsageTrendsResponse> {
  return apiFetch('/data-product-usage/trends', params);
}

export async function getTopDataProductConsumers(
  params?: TopDataProductConsumersParams
): Promise<TopDataProductConsumersResponse> {
  return apiFetch('/data-product-usage/top-consumers', params);
}

export async function listDataProductUsage(
  params?: DataProductUsageListParams
): Promise<DataProductUsageResponse> {
  return apiFetch('/data-product-usage', params);
}

// ─── Unity Catalog Explorer ─────────────────────────────────────────────────

export async function getUnityCatalogExplorerFull(params: {
  catalogName: string;
  schemaName?: string;
}): Promise<UnityCatalogExplorerFullResponse> {
  return apiFetch('/unity-catalog/explorer/full', {
    catalogName: params.catalogName,
    schemaName: params.schemaName,
  });
}

export async function getUnityCatalogExplorerData(): Promise<UnityCatalogExplorerResponse> {
  return apiFetch('/unity-catalog/explorer');
}

export async function testUnityCatalogSchemas(
  catalogName: string
): Promise<UnityCatalogSchemasResponse> {
  return apiFetch('/unity-catalog/schemas', { catalogName });
}

export async function testUnityCatalogTables(
  catalogName: string,
  schemaName: string
): Promise<UnityCatalogTablesResponse> {
  return apiFetch('/unity-catalog/tables', { catalogName, schemaName });
}

export async function getUnityCatalogTableMetadata(
  catalogName: string,
  schemaName: string,
  tableName: string
): Promise<UnityCatalogTableMetadataResponse> {
  return apiFetch(`/unity-catalog/tables/${encodeURIComponent(tableName)}/metadata`, {
    catalogName,
    schemaName,
  });
}

export async function getUnityCatalogTablePreview(
  catalogName: string,
  schemaName: string,
  tableName: string,
  limit = 100,
  offset = 0,
  orderBy?: string,
  includeTotal = false
): Promise<UnityCatalogTablePreviewResponse> {
  return apiFetch(`/unity-catalog/tables/${encodeURIComponent(tableName)}/preview`, {
    catalogName,
    schemaName,
    limit,
    offset,
    orderBy,
    includeTotal,
  });
}

export async function queryUnityCatalogTableGeneric(
  request: UnityCatalogGenericQueryRequest
): Promise<UnityCatalogTablePreviewResponse['Table']> {
  return apiRequest('/unity-catalog/query', { method: 'POST', body: request });
}

// ─── Databases ─────────────────────────────────────────────────────────────

export interface DatabaseListParams {
  [key: string]: string | number | boolean | undefined;
  cloud_provider?: string;
  db_type?: string;
  is_available?: boolean;
}

export async function listDatabases(params?: DatabaseListParams): Promise<DatabasesResponse> {
  return apiFetch('/databases', params);
}

// ─── Security ──────────────────────────────────────────────────────────────

export interface SecurityAlertParams {
  [key: string]: string | number | boolean | string[] | undefined;
  severity?: string;
  status?: string;
  cloud_provider?: string;
  source_lz_id?: string;
  source_lz_ids?: string[];
  start_date?: string;
  end_date?: string;
  limit?: number;
  offset?: number;
}

export async function listSecurityAlerts(
  params?: SecurityAlertParams
): Promise<SecurityAlertsResponse> {
  return apiFetch('/security/alerts', params);
}

export interface AlertsPageBundleParams {
  start_date: string;
  end_date: string;
  cloud_provider?: string;
  limit?: number;
}

export interface AlertsPageBundleData {
  items: SecurityAlert[];
  total: number;
}

export async function getAlertsPageBundle(
  params: AlertsPageBundleParams
): Promise<AlertsPageBundleData> {
  const response = await apiFetch<SecurityAlertsResponse>('/security/alerts/page-bundle', params);
  return {
    items: response.items ?? [],
    total: response.total ?? 0,
  };
}

// ─── Activities ─────────────────────────────────────────────────────────────

export interface ActivityListParams {
  [key: string]: string | number | boolean | undefined;
  pipeline_run_id?: string;
  pipeline_name?: string;
  cloud_provider?: string;
  source_lz_id?: string;
  subscription_or_account_id?: string;
  status?: string;
  activity_type?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;
  offset?: number;
}

export async function listActivities(params?: ActivityListParams): Promise<ActivityRunsResponse> {
  return apiFetch('/activities', params);
}

// ─── Users ──────────────────────────────────────────────────────────────────

export interface UserListParams {
  [key: string]: string | number | boolean | undefined;
  cloud_provider?: string;
  source_lz_id?: string;
  subscription_or_account_id?: string;
  user_type?: string;
  is_active?: boolean;
  search?: string;
  limit?: number;
  offset?: number;
}

export async function listUsers(params?: UserListParams): Promise<UsersResponse> {
  return apiFetch('/users', params);
}

// ─── Standard Checks (Governance) ────────────────────────────────────────────

export interface GovernanceScoreParams {
  [key: string]: string | number | boolean | undefined;
  cloud_provider?: string;
  source_lz_id?: string;
  subscription_or_account_id?: string;
  since?: string;
}

interface LandingZoneScoreApi extends Omit<LandingZoneScore, 'no_compliant_count'> {
  no_compliant_count?: number | null;
  non_compliant_count?: number | null;
}

interface GovernanceScoreApi extends Omit<
  GovernanceScore,
  'by_landing_zone' | 'no_compliant_count'
> {
  by_landing_zone?: LandingZoneScoreApi[];
  no_compliant_count?: number | null;
  non_compliant_count?: number | null;
}

function getNonCompliantCount(item: {
  no_compliant_count?: number | null;
  non_compliant_count?: number | null;
}): number {
  return item.no_compliant_count ?? item.non_compliant_count ?? 0;
}

function normalizeGovernanceScore(score: GovernanceScoreApi): GovernanceScore {
  return {
    by_landing_zone: (score.by_landing_zone ?? []).map((landingZoneScore) => ({
      cloud_provider: landingZoneScore.cloud_provider,
      compliant_count: landingZoneScore.compliant_count ?? 0,
      no_compliant_count: getNonCompliantCount(landingZoneScore),
      score_pct: landingZoneScore.score_pct ?? null,
      source_lz_id: landingZoneScore.source_lz_id,
      subscription_or_account_id: landingZoneScore.subscription_or_account_id ?? null,
      total_evaluated: landingZoneScore.total_evaluated ?? 0,
    })),
    compliant_count: score.compliant_count ?? 0,
    global_score_pct: score.global_score_pct ?? null,
    no_compliant_count: getNonCompliantCount(score),
    total_evaluated: score.total_evaluated ?? 0,
  };
}

export async function getGovernanceScore(params?: GovernanceScoreParams): Promise<GovernanceScore> {
  const response = await apiFetch<GovernanceScoreApi>('/standard-checks/score', params);
  return normalizeGovernanceScore(response);
}

export interface StandardCheckListParams {
  [key: string]: string | number | boolean | undefined;
  cloud_provider?: string;
  source_lz_id?: string;
  subscription_or_account_id?: string;
  check_state?: string;
  resource_type?: string;
  check_name?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;
  offset?: number;
}

interface StandardCheckApi extends Omit<StandardCheck, 'no_check_reasons'> {
  no_check_reasons?: string[] | string | null;
  non_check_reasons?: string[] | string | null;
}

interface StandardChecksApiResponse extends Omit<StandardChecksResponse, 'items'> {
  items: StandardCheckApi[];
}

function normalizeCheckStateForApi(state: string | undefined): string | undefined {
  return state === 'no_compliant' ? 'non_compliant' : state;
}

function normalizeReasonList(reasons: StandardCheckApi['no_check_reasons']): string[] {
  if (Array.isArray(reasons)) return reasons.map(String);
  if (typeof reasons === 'string') return [reasons];
  return [];
}

function normalizeStandardCheck(check: StandardCheckApi): StandardCheck {
  return {
    ...check,
    check_state: check.check_state as StandardCheckState,
    no_check_reasons: normalizeReasonList(check.no_check_reasons ?? check.non_check_reasons),
  };
}

export async function listStandardChecks(
  params?: StandardCheckListParams
): Promise<StandardChecksResponse> {
  const response = await apiFetch<StandardChecksApiResponse>('/standard-checks', {
    ...params,
    check_state: normalizeCheckStateForApi(params?.check_state),
  });

  return {
    ...response,
    items: (response.items ?? []).map(normalizeStandardCheck),
  };
}

export interface GovernancePageBundleParams {
  start_date: string;
  end_date: string;
  cloud_provider?: string;
  limit?: number;
}

export interface GovernancePageBundleData {
  score: GovernanceScore;
  checks: StandardCheck[];
  totalChecks: number;
}

interface GovernancePageBundleApi {
  score: GovernanceScore;
  checks: StandardChecksApiResponse;
}

export async function getGovernancePageBundle(
  params: GovernancePageBundleParams
): Promise<GovernancePageBundleData> {
  const response = await apiFetch<GovernancePageBundleApi>('/standard-checks/page-bundle', params);
  return {
    score: normalizeGovernanceScore(response.score),
    checks: (response.checks.items ?? []).map(normalizeStandardCheck),
    totalChecks: response.checks.total ?? 0,
  };
}

export interface LandingZoneListParams {
  [key: string]: string | number | boolean | undefined;
  cloud_provider?: string;
  environment?: string;
  ba_name?: string;
}

export async function listLandingZones(
  params?: LandingZoneListParams
): Promise<LandingZonesResponse> {
  return apiFetch('/landing-zones/details', params, { silent: true });
}

export async function listLandingZonesAccessOverview(
  params?: LandingZoneListParams
): Promise<LandingZonesAccessOverviewResponse> {
  return apiFetch('/landing-zones/access-overview', params);
}

export async function listAccessRequestLandingZones(): Promise<AccessRequestLandingZonesResponse> {
  return apiRequest('/access-requests/landing-zones', { skipAuth: true });
}

export async function listReferenceBusinessApplications(): Promise<ReferenceBusinessApplicationsResponse> {
  return apiRequest('/reference/business-applications', { skipAuth: true });
}

export async function listReferenceProjects(): Promise<ReferenceProjectsResponse> {
  return apiRequest('/reference/projects', { skipAuth: true });
}

// ─── DCM Auth / Admin ──────────────────────────────────────────────────────

export async function getCurrentDcmUser(): Promise<CurrentDcmUser> {
  return apiFetch('/auth/me', undefined, { silent: true });
}

export async function getDcmPermissions(): Promise<DcmPermissions> {
  return apiFetch('/auth/permissions', undefined, { silent: true });
}

export async function getNotificationPreferences(): Promise<UserNotificationPreferences> {
  return apiFetch('/users/me/notification-preferences', undefined, { silent: true });
}

export async function updateNotificationPreferences(
  payload: UserNotificationPreferencesUpdate
): Promise<UserNotificationPreferences> {
  return apiRequest('/users/me/notification-preferences', {
    method: 'PUT',
    body: payload,
  });
}

export interface AdminUserListParams {
  [key: string]: string | number | boolean | undefined;
  role?: string;
  is_active?: boolean;
  search?: string;
  limit?: number;
  offset?: number;
}

export async function listAdminUsers(params?: AdminUserListParams): Promise<AdminUsersResponse> {
  return apiFetch('/admin/users', params);
}

export type AdminBundleSection = 'all' | 'core' | 'extended';

export interface AdminFullParams {
  accessRequestStatus?: AccessRequest['status'] | '';
  accessRequestLimit?: number;
  accessRequestOffset?: number;
  auditLimit?: number;
  auditOffset?: number;
  sections?: AdminBundleSection;
}

export interface AdminFullResponse {
  users: AdminUsersResponse;
  landingZones: AdminLandingZonesResponse;
  alertRules: AlertRulesResponse;
  collectors: CollectorStatusResponse;
  channels: NotificationChannelsResponse;
  accessRequests: AccessRequestsResponse;
  kpiConfig: KpiConfigResponse;
  retentionPolicies: RetentionPoliciesResponse;
  retentionStats: RetentionStatsResponse;
  maintenanceWindows: MaintenanceWindowsResponse;
  auditLog: AuditLogResponse;
}

export async function getAdminFull(params?: AdminFullParams): Promise<Partial<AdminFullResponse>> {
  return apiFetch('/admin/full', {
    accessRequestStatus: params?.accessRequestStatus || undefined,
    accessRequestLimit: params?.accessRequestLimit,
    accessRequestOffset: params?.accessRequestOffset,
    auditLimit: params?.auditLimit,
    auditOffset: params?.auditOffset,
    sections: params?.sections && params.sections !== 'all' ? params.sections : undefined,
  });
}

export interface AdminUserCreate {
  email: string;
  display_name?: string | null;
  entra_oid?: string | null;
  role: AdminUser['role'];
  lz_ids?: string[];
}

export async function createAdminUser(payload: AdminUserCreate): Promise<AdminUser> {
  return apiRequest('/admin/users', {
    method: 'POST',
    body: payload,
  });
}

export async function getAdminUser(userId: string): Promise<AdminUser> {
  return apiFetch(`/admin/users/${encodeURIComponent(userId)}`);
}

export async function updateAdminUserRole(
  userId: string,
  role: AdminUser['role']
): Promise<AdminUser> {
  return apiRequest(`/admin/users/${encodeURIComponent(userId)}/role`, {
    method: 'PATCH',
    body: { role },
  });
}

/**
 * Delete a user and everything that grants them access (memberships, pending
 * requests, LZ rows). Refused for the caller's own account and for the last
 * remaining platform admin.
 */
export async function deleteAdminUser(userId: string): Promise<void> {
  // 204 No Content — `parseAs: 'text'` keeps `response.json()` off an empty body.
  await apiRequest(`/admin/users/${encodeURIComponent(userId)}`, {
    method: 'DELETE',
    parseAs: 'text',
  });
}

export async function deactivateAdminUser(userId: string): Promise<AdminUser> {
  return apiRequest(`/admin/users/${encodeURIComponent(userId)}/deactivate`, {
    method: 'PATCH',
  });
}

export async function approveAdminUser(
  userId: string,
  payload: { role: AdminUser['role']; lz_ids: string[] }
): Promise<AdminUser> {
  return apiRequest(`/admin/users/${encodeURIComponent(userId)}/approve`, {
    method: 'POST',
    body: payload,
  });
}

export async function replaceAdminUserLzAccess(
  userId: string,
  lzIds: string[]
): Promise<AdminUser> {
  return apiRequest(`/admin/users/${encodeURIComponent(userId)}/lz-access`, {
    method: 'PUT',
    body: { lz_ids: lzIds },
  });
}

export async function replaceAdminUserProjects(
  userId: string,
  projects: AdminUserProjectInput[]
): Promise<AdminUser> {
  return apiRequest(`/admin/users/${encodeURIComponent(userId)}/projects`, {
    method: 'PUT',
    body: { projects },
  });
}

export interface EntraIDUserSearchParams {
  q: string;
  limit?: number;
}

export async function searchEntraIDUsers(
  params: EntraIDUserSearchParams
): Promise<EntraIDUsersResponse> {
  return apiFetch('/admin/entra-users/search', params);
}

export async function submitAccessRequest(payload: AccessRequestCreate): Promise<void> {
  return apiRequest('/access-requests', {
    method: 'POST',
    body: payload,
    skipAuth: true,
  });
}

export async function submitLzScopeRequest(payload: LzScopeRequestCreate): Promise<void> {
  return apiRequest('/users/me/lz-access-requests', {
    method: 'POST',
    body: payload,
  });
}

export interface AdminAccessRequestListParams {
  [key: string]: string | number | boolean | undefined;
  status?: AccessRequest['status'];
  limit?: number;
  offset?: number;
}

export async function listAdminAccessRequests(
  params?: AdminAccessRequestListParams
): Promise<AccessRequestsResponse> {
  return apiFetch('/admin/access-requests', params);
}

export async function reviewAdminAccessRequest(
  requestId: string,
  status: Extract<AccessRequest['status'], 'approved' | 'rejected'>
): Promise<AccessRequest> {
  return apiRequest(`/admin/access-requests/${encodeURIComponent(requestId)}`, {
    method: 'PATCH',
    body: { status },
  });
}

// ─── Project Access Governance (feature 015) ─────────────────────────────────

export async function listProjects(): Promise<ProjectSummary[]> {
  return apiFetch('/projects', undefined, { silent: true });
}

export async function createProject(payload: ProjectCreatePayload): Promise<ProjectSummary> {
  return apiRequest('/projects', { method: 'POST', body: payload });
}

export async function getProject(projectId: string): Promise<ProjectDetail> {
  return apiFetch(`/projects/${encodeURIComponent(projectId)}`);
}

export async function validateProject(projectId: string): Promise<ProjectDetail> {
  return apiRequest(`/projects/${encodeURIComponent(projectId)}/validate`, {
    method: 'POST',
  });
}

/**
 * Refuse a pending project creation. Frees its Business Application so another
 * team can register on it, and records `reason` for the requester.
 */
export async function rejectProject(
  projectId: string,
  payload: ProjectRejectPayload
): Promise<ProjectDetail> {
  return apiRequest(`/projects/${encodeURIComponent(projectId)}/reject`, {
    method: 'POST',
    body: payload,
  });
}

/**
 * Delete a project and everything attached to it (platform_admin only): scope,
 * memberships and open requests. Rejecting only refuses a *pending* creation, so
 * this is the only way out for a project activated by mistake. Members keep their
 * DCM account — they simply stop being members.
 */
export async function deleteProject(projectId: string): Promise<void> {
  return apiRequest(`/projects/${encodeURIComponent(projectId)}`, {
    method: 'DELETE',
    parseAs: 'text',
  });
}

export async function listProjectMembers(projectId: string): Promise<ProjectMember[]> {
  return apiFetch(`/projects/${encodeURIComponent(projectId)}/members`);
}

export async function updateProjectMemberRole(
  projectId: string,
  userId: string,
  role: ProjectRole
): Promise<ProjectMember> {
  return apiRequest(
    `/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(userId)}`,
    { method: 'PATCH', body: { role } }
  );
}

export async function addProjectMember(
  projectId: string,
  payload: ProjectMemberAddPayload
): Promise<ProjectMember> {
  return apiRequest(`/projects/${encodeURIComponent(projectId)}/members`, {
    method: 'POST',
    body: payload,
  });
}

export async function removeProjectMember(projectId: string, userId: string): Promise<void> {
  return apiRequest(
    `/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(userId)}`,
    { method: 'DELETE', parseAs: 'text' }
  );
}

export async function createProjectJoinRequest(
  projectId: string,
  payload: ProjectJoinRequestCreatePayload
): Promise<ProjectJoinRequest> {
  return apiRequest(`/projects/${encodeURIComponent(projectId)}/join-requests`, {
    method: 'POST',
    body: payload,
  });
}

export async function listProjectJoinRequests(projectId: string): Promise<ProjectJoinRequest[]> {
  return apiFetch(`/projects/${encodeURIComponent(projectId)}/join-requests`);
}

/**
 * Platform-admin queue: every pending join request across all projects, so a
 * request never waits for a project admin who never logs in.
 */
export async function listAllJoinRequests(): Promise<ProjectJoinRequest[]> {
  return apiFetch('/join-requests', undefined, { silent: true });
}

export async function decideProjectJoinRequest(
  requestId: string,
  payload: ProjectRequestDecisionPayload
): Promise<ProjectJoinRequest> {
  return apiRequest(`/join-requests/${encodeURIComponent(requestId)}/decide`, {
    method: 'POST',
    body: payload,
  });
}

/** Returns one row per requested item — the batch shares `requestedAt`. */
export async function createProjectScopeRequest(
  projectId: string,
  payload: ProjectScopeRequestCreatePayload
): Promise<ProjectScopeRequest[]> {
  return apiRequest(`/projects/${encodeURIComponent(projectId)}/scope-requests`, {
    method: 'POST',
    body: payload,
  });
}

export async function listScopeRequests(): Promise<ProjectScopeRequest[]> {
  return apiFetch('/scope-requests');
}

export async function decideScopeRequest(
  requestId: string,
  payload: ProjectRequestDecisionPayload
): Promise<ProjectScopeRequest> {
  return apiRequest(`/scope-requests/${encodeURIComponent(requestId)}/decide`, {
    method: 'POST',
    body: payload,
  });
}

// ─── Self-service register / join from the login page (feature 016) ──────────
// The caller must be signed in (Entra token attached): the backend derives the
// requester identity from the verified token, never from a client-supplied email.

export async function registerProjectPublic(
  payload: ProjectRegisterPayload
): Promise<ProjectRegisterResponse> {
  return apiRequest('/projects/register', { method: 'POST', body: payload });
}

export async function requestJoinProjectPublic(
  payload: ProjectJoinPublicPayload
): Promise<ProjectJoinPublicResponse> {
  return apiRequest('/projects/join', { method: 'POST', body: payload });
}

export interface AdminLandingZoneCreate {
  lz_id: string;
  display_name: string;
  cloud_provider: string;
  region?: string | null;
  environment?: string | null;
  ba_name?: string | null;
  collector_names?: string[];
  notes?: string | null;
}

export type AdminLandingZonePatch = Partial<Omit<AdminLandingZoneCreate, 'lz_id'>>;

export async function listAdminLandingZones(): Promise<AdminLandingZonesResponse> {
  return apiFetch('/admin/landing-zones');
}

export async function createAdminLandingZone(payload: AdminLandingZoneCreate) {
  return apiRequest('/admin/landing-zones', {
    method: 'POST',
    body: payload,
  });
}

export async function updateAdminLandingZone(lzId: string, payload: AdminLandingZonePatch) {
  return apiRequest(`/admin/landing-zones/${encodeURIComponent(lzId)}`, {
    method: 'PATCH',
    body: payload,
  });
}

export async function deactivateAdminLandingZone(lzId: string) {
  return apiRequest(`/admin/landing-zones/${encodeURIComponent(lzId)}/deactivate`, {
    method: 'PATCH',
  });
}

export interface NotificationChannelCreate {
  name: string;
  channel_type: 'teams' | 'email';
  config: Record<string, unknown>;
  is_active?: boolean;
}

export async function listNotificationChannels(): Promise<NotificationChannelsResponse> {
  return apiFetch('/admin/notification-channels');
}

export async function createNotificationChannel(
  payload: NotificationChannelCreate
): Promise<NotificationChannel> {
  return apiRequest('/admin/notification-channels', {
    method: 'POST',
    body: payload,
  });
}

export async function updateNotificationChannel(
  channelId: string,
  payload: Partial<Pick<NotificationChannelCreate, 'name' | 'config' | 'is_active'>>
): Promise<NotificationChannel> {
  return apiRequest(`/admin/notification-channels/${encodeURIComponent(channelId)}`, {
    method: 'PATCH',
    body: payload,
  });
}

export async function deleteNotificationChannel(channelId: string): Promise<NotificationChannel> {
  return apiRequest(`/admin/notification-channels/${encodeURIComponent(channelId)}`, {
    method: 'DELETE',
  });
}

export async function testNotificationChannel(
  channelId: string
): Promise<{ message: string; status: string }> {
  return apiRequest(`/admin/notification-channels/${encodeURIComponent(channelId)}/test`, {
    method: 'POST',
  });
}

export interface AlertRuleCreate {
  name: string;
  description?: string | null;
  metric_domain: string;
  condition_field: string;
  condition_operator: string;
  condition_threshold: number;
  eval_window_hours: number;
  severity: 'info' | 'warning' | 'critical';
  applies_to_lz_ids?: string[] | null;
  notification_channel_ids?: string[];
  cooldown_minutes?: number;
  is_active?: boolean;
}

export async function listAlertRules(): Promise<AlertRulesResponse> {
  return apiFetch('/admin/alert-rules');
}

export async function createAlertRule(payload: AlertRuleCreate): Promise<AdminAlertRule> {
  return apiRequest('/admin/alert-rules', {
    method: 'POST',
    body: payload,
  });
}

export async function updateAlertRule(
  ruleId: string,
  payload: Partial<AlertRuleCreate>
): Promise<AdminAlertRule> {
  return apiRequest(`/admin/alert-rules/${encodeURIComponent(ruleId)}`, {
    method: 'PATCH',
    body: payload,
  });
}

export async function deleteAlertRule(ruleId: string): Promise<AdminAlertRule> {
  return apiRequest(`/admin/alert-rules/${encodeURIComponent(ruleId)}`, {
    method: 'DELETE',
  });
}

export async function testAlertRule(ruleId: string): Promise<AlertRuleTestResult> {
  return apiRequest(`/admin/alert-rules/${encodeURIComponent(ruleId)}/test`, {
    method: 'POST',
  });
}

export async function listAlertRuleFirings(ruleId: string): Promise<AlertFiringsResponse> {
  return apiFetch(`/admin/alert-rules/${encodeURIComponent(ruleId)}/firings`);
}

export async function listCollectorStatus(): Promise<CollectorStatusResponse> {
  return apiFetch('/admin/collectors/status');
}

export async function getAdminKpiConfig(): Promise<KpiConfigResponse> {
  return apiFetch('/admin/kpi-config');
}

export async function getKpiConfig(): Promise<KpiConfigResponse> {
  return apiFetch('/kpi-config');
}

export async function patchAdminKpiConfig(
  values: Record<string, number>
): Promise<Pick<KpiConfigResponse, 'values'>> {
  return apiRequest('/admin/kpi-config', {
    method: 'PATCH',
    body: values,
  });
}

export async function listRetentionPolicies(): Promise<RetentionPoliciesResponse> {
  return apiFetch('/admin/retention-policies');
}

export async function patchRetentionPolicies(
  values: Record<string, number>
): Promise<Pick<RetentionPoliciesResponse, 'values'>> {
  return apiRequest('/admin/retention-policies', {
    method: 'PATCH',
    body: values,
  });
}

export async function getRetentionStats(): Promise<RetentionStatsResponse> {
  return apiFetch('/admin/retention-policies/stats');
}

export interface MaintenanceWindowCreate {
  name: string;
  description?: string | null;
  lz_ids?: string[] | null;
  starts_at: string;
  ends_at: string;
  suppress_alerts?: boolean;
}

export async function listMaintenanceWindows(): Promise<MaintenanceWindowsResponse> {
  return apiFetch('/admin/maintenance-windows');
}

export async function createMaintenanceWindow(
  payload: MaintenanceWindowCreate
): Promise<MaintenanceWindow> {
  return apiRequest('/admin/maintenance-windows', {
    method: 'POST',
    body: payload,
  });
}

export async function updateMaintenanceWindow(
  windowId: string,
  payload: Partial<MaintenanceWindowCreate>
): Promise<MaintenanceWindow> {
  return apiRequest(`/admin/maintenance-windows/${encodeURIComponent(windowId)}`, {
    method: 'PATCH',
    body: payload,
  });
}

export async function deleteMaintenanceWindow(
  windowId: string
): Promise<{ status: string; id: string }> {
  return apiRequest(`/admin/maintenance-windows/${encodeURIComponent(windowId)}`, {
    method: 'DELETE',
  });
}

export interface AuditLogParams {
  [key: string]: string | number | boolean | undefined;
  actor_user_id?: string;
  action?: string;
  target_type?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;
  offset?: number;
}

export async function listAuditLog(params?: AuditLogParams): Promise<AuditLogResponse> {
  return apiFetch('/admin/audit-log', params);
}

export async function exportAuditLog(
  params?: Omit<AuditLogParams, 'limit' | 'offset'>
): Promise<string> {
  return apiRequest('/admin/audit-log/export', {
    params,
    parseAs: 'text',
  });
}

export async function postChat(request: ChatRequest): Promise<ChatResponse> {
  return apiRequest<ChatResponse>('/chat', {
    method: 'POST',
    body: request,
  });
}

// ─── Unity Catalog usage tracking (024) ────────────────────────────────────

/**
 * Aucun paramètre de scope LZ / workspace / cloud : les huit tables gold
 * `gold_dbx_usage_*` n'en portent aucun (FR-010, FR-019).
 */
export interface UcUsageScopeParams {
  [key: string]: string | string[] | number | boolean | undefined;
  catalog?: string;
  schema?: string;
  tables?: string[];
  /**
   * Garde les tables supprimées de Unity Catalog dans l'analyse (spec 027).
   * Absent = `false` côté serveur : elles sortent des listes, des KPI, des
   * classements, des graphiques et des totaux de pagination **avant** agrégation.
   * Les deux ressources de grain consommateur — `/consumers` et
   * `/charts/consumers` — l'ignorent : elles ne portent aucune clé table.
   */
  include_deleted?: boolean;
}

/** Bornes **obligatoires** : l'API refuse d'inventer une période (FR-017). */
export interface UcUsagePeriodParams extends UcUsageScopeParams {
  period_start: string;
  period_end: string;
}

export interface UcUsageTablesParams extends UcUsagePeriodParams {
  search?: string;
  sort?:
    | 'popularity'
    | 'cost'
    | 'latency'
    | 'failure_rate'
    | 'writes'
    | 'rows_written'
    | 'consumers'
    | 'freshness'
    | 'table_name'
    | 'read_bytes';
  direction?: 'asc' | 'desc';
  column_filter?: string[];
  page?: number;
  page_size?: number;
}

export interface UcUsageConsumersParams extends UcUsagePeriodParams {
  search?: string;
  consumer_type?: string;
  sort?:
    | 'cost'
    | 'requests'
    | 'distinct_tables'
    | 'writes'
    | 'rows_written'
    | 'name'
    | 'read_bytes';
  direction?: 'asc' | 'desc';
  column_filter?: string[];
  page?: number;
  page_size?: number;
}

export interface UcUsageCostByTableParams extends UcUsagePeriodParams {
  search?: string;
  sort?: 'cost' | 'cost_per_request' | 'requests' | 'read_bytes' | 'forecast' | 'table_name';
  direction?: 'asc' | 'desc';
  column_filter?: string[];
  page?: number;
  page_size?: number;
}

export interface UcUsageTrendsParams extends UcUsageScopeParams {
  metrics?: UcUsageForecastMetric[];
  /** Bornes du réalisé : omises, l'API ne renvoie que la prévision. */
  period_start?: string;
  period_end?: string;
}

export interface UcUsageAttentionParams extends UcUsageScopeParams {
  limit?: number;
}

export interface UcUsageRecommendationsParams extends UcUsageScopeParams {
  category?: string;
  severity?: string;
  object_type?: string;
  age_bucket?: UcUsageRecommendationAgeBucket;
  sort?: 'savings' | 'age';
  page?: number;
  page_size?: number;
}

export interface UcUsageRegistryParams extends UcUsageScopeParams {
  signal?: UcUsageGovernanceSignal;
  inactivity?: UcUsageInactivityBucket;
  missing_tag?: UcUsageMissingTag;
  search?: string;
  sort?: 'severity' | 'table_name' | 'fanout';
  page?: number;
  page_size?: number;
}

export interface UcUsageFilterOptionsParams {
  [key: string]: string | number | boolean | undefined;
  catalog?: string;
  schema?: string;
  search?: string;
  limit?: number;
  /** Rend les tables supprimées sélectionnables dans le filtre (spec 027). */
  include_deleted?: boolean;
}

export async function getUcUsageFilterOptions(
  params?: UcUsageFilterOptionsParams
): Promise<UcUsageFilterOptions> {
  return apiFetch('/uc-usage/filters/options', params);
}

export async function getUcUsageOverview(params: UcUsagePeriodParams): Promise<UcUsageOverview> {
  return apiFetch('/uc-usage/overview', params);
}

export async function getUcUsageTableCharts(
  params: UcUsagePeriodParams
): Promise<UcUsageTableCharts> {
  return apiFetch('/uc-usage/charts/tables', params);
}

export async function getUcUsageConsumerCharts(
  params: UcUsagePeriodParams
): Promise<UcUsageConsumerCharts> {
  return apiFetch('/uc-usage/charts/consumers', params);
}

export async function getUcUsageFinopsCharts(
  params: UcUsagePeriodParams
): Promise<UcUsageFinopsCharts> {
  return apiFetch('/uc-usage/charts/finops', params);
}

export async function listUcUsageTables(
  params: UcUsageTablesParams
): Promise<UcUsageListEnvelope<UcUsageTableRow>> {
  return apiFetch('/uc-usage/tables', params);
}

export async function getUcUsageTableTopConsumers(
  tableFullName: string,
  params: UcUsagePeriodParams
): Promise<UcUsageTopConsumersResponse> {
  return apiFetch(`/uc-usage/tables/${encodeURIComponent(tableFullName)}/top-consumers`, params);
}

export async function listUcUsageConsumers(
  params: UcUsageConsumersParams
): Promise<UcUsageListEnvelope<UcUsageConsumerRow>> {
  return apiFetch('/uc-usage/consumers', params);
}

export async function getUcUsageFinopsKpis(
  params: UcUsagePeriodParams
): Promise<UcUsageFinopsKpis> {
  return apiFetch('/uc-usage/finops/kpis', params);
}

export async function listUcUsageCostByTable(
  params: UcUsageCostByTableParams
): Promise<UcUsageListEnvelope<UcUsageCostByTableRow>> {
  return apiFetch('/uc-usage/finops/cost-by-table', params);
}

export async function getUcUsageFinopsTrends(
  params?: UcUsageTrendsParams
): Promise<UcUsageForecastSeriesResponse> {
  return apiFetch('/uc-usage/finops/trends', params);
}

export async function getUcUsageAttention(
  params?: UcUsageAttentionParams
): Promise<UcUsageAttentionResponse> {
  return apiFetch('/uc-usage/attention', params);
}

export async function listUcUsageRecommendations(
  params?: UcUsageRecommendationsParams
): Promise<UcUsageRecommendationsResponse> {
  return apiFetch('/uc-usage/recommendations', params);
}

export async function getUcUsageGovernanceKpis(
  params?: UcUsageScopeParams
): Promise<UcUsageGovernanceKpis> {
  return apiFetch('/uc-usage/governance/kpis', params);
}

export async function getUcUsageGovernanceCharts(
  params?: UcUsageScopeParams
): Promise<UcUsageGovernanceCharts> {
  return apiFetch('/uc-usage/governance/charts', params);
}

export async function getUcUsageRecommendationCharts(
  params?: UcUsageScopeParams
): Promise<UcUsageRecommendationCharts> {
  return apiFetch('/uc-usage/recommendations/charts', params);
}

export async function listUcUsageGovernanceRegistry(
  params?: UcUsageRegistryParams
): Promise<UcUsageListEnvelope<UcUsageRegistryRow>> {
  return apiFetch('/uc-usage/governance/registry', params);
}

export async function getUcUsageWriteCharts(
  params: UcUsagePeriodParams
): Promise<UcUsageWriteCharts> {
  return apiFetch('/uc-usage/charts/writes', params);
}

export async function getUcUsageCostChanges(
  params: UcUsagePeriodParams
): Promise<UcUsageCostChanges> {
  return apiFetch('/uc-usage/charts/cost-changes', params);
}

export async function getUcUsageEntityDetail(
  params: UcUsagePeriodParams & { entity_kind: 'table' | 'consumer'; entity_id: string }
): Promise<UcUsageEntityDetail> {
  return apiFetch('/uc-usage/details', params);
}
