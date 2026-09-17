import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AdminFullResponse, AdminUser } from '../types/api';
import { renderWithProviders, screen, userEvent, waitFor } from '../test/render';
import Admin from './Admin';

vi.mock('../api/dcmApiClient', () => ({
  createAlertRule: vi.fn(),
  createAdminLandingZone: vi.fn(),
  createAdminUser: vi.fn(),
  createMaintenanceWindow: vi.fn(),
  createNotificationChannel: vi.fn(),
  deactivateAdminLandingZone: vi.fn(),
  deactivateAdminUser: vi.fn(),
  deleteAdminUser: vi.fn(),
  deleteAlertRule: vi.fn(),
  deleteMaintenanceWindow: vi.fn(),
  deleteNotificationChannel: vi.fn(),
  exportAuditLog: vi.fn(),
  getAdminFull: vi.fn(),
  getCurrentDcmUser: vi.fn(),
  listLandingZones: vi.fn(),
  getDcmApiErrorMessage: vi.fn((error: unknown, fallback: string) => error instanceof Error ? error.message : fallback),
  getRetentionStats: vi.fn(),
  listAdminAccessRequests: vi.fn(),
  listAdminLandingZones: vi.fn(),
  listAdminUsers: vi.fn(),
  listAlertRules: vi.fn(),
  listAuditLog: vi.fn(),
  listCollectorStatus: vi.fn(),
  listMaintenanceWindows: vi.fn(),
  listNotificationChannels: vi.fn(),
  listRetentionPolicies: vi.fn(),
  patchAdminKpiConfig: vi.fn(),
  patchRetentionPolicies: vi.fn(),
  listReferenceProjects: vi.fn(),
  replaceAdminUserProjects: vi.fn(),
  reviewAdminAccessRequest: vi.fn(),
  testAlertRule: vi.fn(),
  testNotificationChannel: vi.fn(),
  updateAdminUserRole: vi.fn(),
}));

import {
  deleteAdminUser,
  getAdminFull,
  getCurrentDcmUser,
  listLandingZones,
  listReferenceProjects,
  replaceAdminUserProjects,
  updateAdminUserRole,
} from '../api/dcmApiClient';

const defaultAdminUser: AdminUser = {
  id: 'user-001',
  entra_oid: 'entra-user-001',
  email: 'user@example.com',
  display_name: 'DCM User',
  role: 'viewer',
  platform_role: 'user',
  is_active: true,
  created_at: '2026-05-27T10:00:00Z',
  last_login_at: null,
  lz_ids: ['lz-001'],
  projects: [],
};

function createAdminFullFixture(overrides: Partial<AdminFullResponse> = {}): AdminFullResponse {
  return {
    users: {
      items: [defaultAdminUser],
      total: 1,
      limit: 200,
      offset: 0,
    },
    landingZones: {
      items: [
        {
          lz_id: 'lz-001',
          display_name: 'Landing Zone 001',
          cloud_provider: 'azure',
          region: 'westeurope',
          environment: 'prod',
          ba_name: 'Data',
          collector_names: ['azure-adf'],
          is_active: true,
          registered_at: '2026-05-27T10:00:00Z',
          registered_by: 'admin-001',
          notes: null,
          user_count: 1,
        },
        {
          lz_id: 'lz-002',
          display_name: 'Landing Zone 002',
          cloud_provider: 'aws',
          region: 'eu-west-1',
          environment: 'prod',
          ba_name: 'Data',
          collector_names: ['aws-glue'],
          is_active: true,
          registered_at: '2026-05-27T10:00:00Z',
          registered_by: 'admin-001',
          notes: null,
          user_count: 0,
        },
        {
          lz_id: 'lz-003',
          display_name: 'Landing Zone 003',
          cloud_provider: 'azure',
          region: 'westeurope',
          environment: 'dev',
          ba_name: 'Data',
          collector_names: ['azure-adf'],
          is_active: true,
          registered_at: '2026-05-27T10:00:00Z',
          registered_by: 'admin-001',
          notes: null,
          user_count: 0,
        },
      ],
      total: 3,
    },
    alertRules: { items: [], total: 0 },
    collectors: { items: [], total: 0 },
    channels: { items: [], total: 0 },
    accessRequests: {
      items: [],
      total: 0,
      pending_total: 0,
      limit: 200,
      offset: 0,
    },
    kpiConfig: { items: [], values: {} },
    retentionPolicies: { items: [], values: {} },
    retentionStats: { items: [], total: 0 },
    maintenanceWindows: { items: [], total: 0 },
    auditLog: { items: [], total: 0, limit: 100, offset: 0 },
    ...overrides,
  };
}

const catalogLandingZonesFixture = {
  items: [
    {
      lz_id: 'lz-001',
      lz_name: 'Landing Zone 001',
      cloud_provider: 'azure',
      subscription_or_account_id: 'sub-001',
      environment: 'prod',
      ba_name: 'Data',
      valid_from: '2026-05-27T10:00:00Z',
    },
    {
      lz_id: 'lz-002',
      lz_name: 'Landing Zone 002',
      cloud_provider: 'aws',
      subscription_or_account_id: 'acct-002',
      environment: 'prod',
      ba_name: 'Data',
      valid_from: '2026-05-27T10:00:00Z',
    },
    {
      lz_id: 'lz-003',
      lz_name: 'Landing Zone 003',
      cloud_provider: 'azure',
      subscription_or_account_id: 'sub-003',
      environment: 'dev',
      ba_name: 'Data',
      valid_from: '2026-05-27T10:00:00Z',
    },
  ],
  total: 3,
};

const apiMocks = {
  deleteAdminUser: vi.mocked(deleteAdminUser),
  getAdminFull: vi.mocked(getAdminFull),
  getCurrentDcmUser: vi.mocked(getCurrentDcmUser),
  listLandingZones: vi.mocked(listLandingZones),
  listReferenceProjects: vi.mocked(listReferenceProjects),
  replaceAdminUserProjects: vi.mocked(replaceAdminUserProjects),
  updateAdminUserRole: vi.mocked(updateAdminUserRole),
};

function mockStagedAdminFull(
  fixtureFactory: (params?: { accessRequestStatus?: string; sections?: string }) => AdminFullResponse,
) {
  apiMocks.getAdminFull.mockImplementation(async (params) => {
    const fixture = fixtureFactory(params);
    if (params?.sections === 'core') {
      return {
        users: fixture.users,
        landingZones: fixture.landingZones,
        accessRequests: fixture.accessRequests,
        channels: fixture.channels,
        alertRules: fixture.alertRules,
      };
    }
    if (params?.sections === 'extended') {
      return {
        collectors: fixture.collectors,
        kpiConfig: fixture.kpiConfig,
        retentionPolicies: fixture.retentionPolicies,
        retentionStats: fixture.retentionStats,
        maintenanceWindows: fixture.maintenanceWindows,
        auditLog: fixture.auditLog,
      };
    }
    return fixture;
  });
}

describe('Admin page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getCurrentDcmUser.mockResolvedValue({
      id: 'admin-001',
      entra_oid: 'entra-admin-001',
      email: 'admin@example.com',
      display_name: 'Admin User',
      role: 'super_admin',
      is_active: true,
      lz_ids: [],
    });
    mockStagedAdminFull(() => createAdminFullFixture());
    apiMocks.listLandingZones.mockResolvedValue(catalogLandingZonesFixture);
    apiMocks.listReferenceProjects.mockResolvedValue({
      items: [
        { id: 'proj-1', name: 'Payments', businessAppId: 'ba-1', status: 'active' },
        { id: 'proj-2', name: 'Analytics', businessAppId: 'ba-1', status: 'active' },
      ],
      total: 2,
    });
    apiMocks.updateAdminUserRole.mockResolvedValue({
      ...defaultAdminUser,
      role: 'manager',
    });
    apiMocks.replaceAdminUserProjects.mockResolvedValue({
      ...defaultAdminUser,
      role: 'manager',
      projects: [{ id: 'proj-1', name: 'Payments', role: 'viewer', status: 'active' }],
    });
  });

  it('renders role and project membership management controls', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Admin />, { route: '/admin' });

    expect(await screen.findByText('Identity Access Management')).toBeInTheDocument();
    expect(screen.getByText('Add Entra ID users, assign DCM roles, deactivate accounts and manage the projects each user can access.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /create a dcm identity/i }));
    expect(screen.getByText('Entra ID email')).toBeInTheDocument();
    expect(screen.getByText('user@example.com')).toBeInTheDocument();
    expect(screen.getByLabelText('Project membership for user@example.com')).toBeInTheDocument();
  });

  it('exposes only access control and projects, whatever the ?tab= says', async () => {
    // Administration is down to access governance; a link to a retired tab
    // (landing zones, alert rules, access requests, audit…) lands on Access
    // Control instead of an empty page.
    renderWithProviders(<Admin />, { route: '/admin?tab=access-requests' });

    expect(await screen.findByText('Identity Access Management')).toBeInTheDocument();
    // Each tab is identified by its own description line.
    expect(screen.getByText('Roles & LZ scope')).toBeInTheDocument();
    expect(screen.getByText('Validate & scope')).toBeInTheDocument();
    expect(screen.queryByText('Review & grant portal access')).not.toBeInTheDocument();
    expect(screen.queryByText('Registry & collectors')).not.toBeInTheDocument();
    expect(screen.queryByText('Evidence & exports')).not.toBeInTheDocument();
    expect(screen.queryByText('Access request inbox')).not.toBeInTheDocument();
  });

  it('saves project membership edits from the users panel', async () => {
    const user = userEvent.setup();

    renderWithProviders(<Admin />, { route: '/admin' });

    await screen.findByText('user@example.com');
    await user.selectOptions(screen.getByLabelText('Project membership for user@example.com'), 'proj-1');
    await user.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(apiMocks.replaceAdminUserProjects).toHaveBeenCalledWith('user-001', [{ project_id: 'proj-1', role: 'viewer' }]);
    });
  });

  it('promotes a member to platform admin after confirmation', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const user = userEvent.setup();

    renderWithProviders(<Admin />, { route: '/admin' });

    await screen.findByText('user@example.com');
    await user.click(screen.getByRole('button', { name: /make platform admin/i }));

    await waitFor(() => {
      expect(apiMocks.updateAdminUserRole).toHaveBeenCalledWith('user-001', 'super_admin');
    });
    confirmSpy.mockRestore();
  });

  it('does not promote when the confirmation is dismissed', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const user = userEvent.setup();

    renderWithProviders(<Admin />, { route: '/admin' });

    await screen.findByText('user@example.com');
    await user.click(screen.getByRole('button', { name: /make platform admin/i }));

    expect(apiMocks.updateAdminUserRole).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('reads the platform tier from platform_role, not from the lifecycle role', async () => {
    mockStagedAdminFull(() =>
      createAdminFullFixture({
        users: {
          items: [{ ...defaultAdminUser, role: 'viewer', platform_role: 'super_admin' }],
          total: 1,
          limit: 200,
          offset: 0,
        },
      }),
    );
    renderWithProviders(<Admin />, { route: '/admin' });

    await screen.findByText('user@example.com');
    expect(screen.getByLabelText('Tier for user@example.com')).toHaveTextContent('Platform admin');
    // Already a platform admin → the demotion action is the one offered.
    expect(screen.getByRole('button', { name: /set as member/i })).toBeInTheDocument();
  });

  it('deletes a user after confirmation', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const user = userEvent.setup();

    renderWithProviders(<Admin />, { route: '/admin' });

    await screen.findByText('user@example.com');
    await user.click(screen.getByRole('button', { name: 'Delete user@example.com' }));

    await waitFor(() => {
      expect(apiMocks.deleteAdminUser).toHaveBeenCalledWith('user-001');
    });
    confirmSpy.mockRestore();
  });

  it('does not delete when the confirmation is dismissed', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const user = userEvent.setup();

    renderWithProviders(<Admin />, { route: '/admin' });

    await screen.findByText('user@example.com');
    await user.click(screen.getByRole('button', { name: 'Delete user@example.com' }));

    expect(apiMocks.deleteAdminUser).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
