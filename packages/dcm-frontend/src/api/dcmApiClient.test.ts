import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  createAdminUser,
  getCostSummary,
  getCostsByService,
  getDashboardOverview,
  getDataProductUsageOverview,
  getHealth,
  getPendingApiRequestCount,
  getGovernanceScore,
  getKpiConfig,
  getTopDataProductConsumers,
  listPipelines,
  listSecurityAlerts,
  listStandardChecks,
  registerTokenGetter,
  replaceAdminUserLzAccess,
  updateAdminUserRole,
} from './dcmApiClient';

const fetchMock = vi.fn<typeof fetch>();

function createJsonResponse(body: unknown, options: { ok?: boolean; status?: number; text?: string } = {}) {
  return {
    ok: options.ok ?? true,
    status: options.status ?? 200,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(options.text ?? ''),
  } as Response;
}

describe('dcmApiClient', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.com');
    vi.stubEnv('VITE_ENABLE_AUTH', 'true');
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
    registerTokenGetter(async () => null);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('adds the bearer token without logging auth details', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    registerTokenGetter(async () => 'secret-token');
    fetchMock.mockResolvedValue(createJsonResponse({ status: 'ok' }));

    await getHealth();

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/health'),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer secret-token',
        }),
      }),
    );
    expect(logSpy).not.toHaveBeenCalled();
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it('adds the bearer token to all DCM endpoint helpers', async () => {
    registerTokenGetter(async () => 'secret-token');
    fetchMock.mockResolvedValue(createJsonResponse({ items: [], total: 0 }));

    await Promise.all([
      getDashboardOverview(),
      listPipelines({ status: 'failed' }),
      getCostSummary(),
      getCostsByService(),
      listSecurityAlerts({ status: 'active' }),
      getGovernanceScore(),
      getKpiConfig(),
      listStandardChecks({ check_state: 'no_compliant' }),
      getDataProductUsageOverview(),
      getTopDataProductConsumers({ metric: 'request_count' }),
    ]);

    expect(fetchMock).toHaveBeenCalledTimes(10);
    fetchMock.mock.calls.forEach(([, init]) => {
      expect(init).toEqual(expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer secret-token',
        }),
      }));
    });
  });

  it('calls admin role and Landing Zone access endpoints with JSON payloads', async () => {
    registerTokenGetter(async () => 'secret-token');
    fetchMock.mockResolvedValue(createJsonResponse({
      id: 'user-001',
      email: 'user@example.com',
      role: 'manager',
      lz_ids: ['lz-001'],
    }));

    await createAdminUser({
      email: 'user@example.com',
      role: 'viewer',
      lz_ids: ['lz-001'],
    });
    await updateAdminUserRole('user-001', 'manager');
    await replaceAdminUserLzAccess('user-001', ['lz-002', 'lz-003']);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining('/api/v1/admin/users'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ email: 'user@example.com', role: 'viewer', lz_ids: ['lz-001'] }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining('/api/v1/admin/users/user-001/role'),
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ role: 'manager' }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      expect.stringContaining('/api/v1/admin/users/user-001/lz-access'),
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ lz_ids: ['lz-002', 'lz-003'] }),
      }),
    );
  });

  it('adds the bearer token to local development API targets when auth is enabled', async () => {
    const tokenGetter = vi.fn(async () => 'secret-token');

    vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000');
    registerTokenGetter(tokenGetter);
    fetchMock.mockResolvedValue(createJsonResponse({ status: 'ok' }));

    await getHealth();

    expect(tokenGetter).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/health'),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer secret-token',
        }),
      }),
    );
  });

  it('adds DCM dev headers when authentication is disabled', async () => {
    vi.stubEnv('VITE_ENABLE_AUTH', 'false');
    vi.stubEnv('VITE_DCM_DEV_ROLE', 'admin');
    vi.stubEnv('VITE_DCM_DEV_USER_ID', 'dev-super-admin');
    vi.stubEnv('VITE_DCM_DEV_EMAIL', 'dev.admin@example.com');
    vi.stubEnv('VITE_DCM_DEV_DISPLAY_NAME', 'Dev Super Admin');
    fetchMock.mockResolvedValue(createJsonResponse({ status: 'ok' }));

    await getHealth();

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/health'),
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-DCM-Role': 'admin',
          'X-DCM-User-Id': 'dev-super-admin',
          'X-DCM-Email': 'dev.admin@example.com',
          'X-DCM-Display-Name': 'Dev Super Admin',
        }),
      }),
    );
  });

  it('surfaces API errors and always clears pending request state', async () => {
    registerTokenGetter(async () => 'secret-token');
    fetchMock.mockResolvedValue(createJsonResponse({}, {
      ok: false,
      status: 503,
      text: 'Service unavailable',
    }));

    await expect(getHealth()).rejects.toThrow('DCM API 503: Service unavailable');
    expect(getPendingApiRequestCount()).toBe(0);
  });

  it('normalizes backend governance aliases used by the UI', async () => {
    registerTokenGetter(async () => 'secret-token');
    fetchMock
      .mockResolvedValueOnce(createJsonResponse({
        by_landing_zone: [
          {
            cloud_provider: 'azure',
            compliant_count: 8,
            non_compliant_count: 2,
            score_pct: 80,
            source_lz_id: 'lz-crm',
            subscription_or_account_id: 'sub-1',
            total_evaluated: 10,
          },
        ],
        compliant_count: 8,
        global_score_pct: 80,
        non_compliant_count: 2,
        total_evaluated: 10,
      }))
      .mockResolvedValueOnce(createJsonResponse({
        items: [
          {
            check_effect: 'audit',
            check_id: 'check-1',
            check_name: 'Require HTTPS',
            check_state: 'non_compliant',
            cloud_provider: 'azure',
            evaluated_at: '2026-03-20T10:00:00Z',
            non_check_reasons: ['HTTPS traffic is disabled'],
            resource_id: 'storage-1',
            resource_name: 'Storage 1',
            resource_type: 'Microsoft.Storage/storageAccounts',
            source_lz_id: 'lz-crm',
            subscription_or_account_id: 'sub-1',
          },
        ],
        limit: 100,
        offset: 0,
        total: 1,
      }));

    const score = await getGovernanceScore();
    const checks = await listStandardChecks({ check_state: 'no_compliant' });

    expect(score.no_compliant_count).toBe(2);
    expect(score.by_landing_zone[0].no_compliant_count).toBe(2);
    expect(checks.items[0].no_check_reasons).toEqual(['HTTPS traffic is disabled']);
    expect(String(fetchMock.mock.calls[1][0])).toContain('check_state=non_compliant');
  });
});
