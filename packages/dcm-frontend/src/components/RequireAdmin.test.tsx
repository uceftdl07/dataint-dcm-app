import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '../test/render';
import RequireAdmin from './RequireAdmin';

vi.mock('../hooks/useCurrentDcmUser', () => ({
  useCurrentDcmUser: vi.fn(),
}));

import { useCurrentDcmUser } from '../hooks/useCurrentDcmUser';

const useCurrentDcmUserMock = vi.mocked(useCurrentDcmUser);

describe('RequireAdmin', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders children for platform admins', () => {
    useCurrentDcmUserMock.mockReturnValue({
      user: {
        id: 'admin-001',
        entra_oid: 'entra-admin-001',
        email: 'admin@example.com',
        display_name: 'Admin User',
        role: 'viewer',
        platform_role: 'super_admin',
        is_active: true,
        lz_ids: [],
      },
      loading: false,
      error: null,
      reload: vi.fn(),
    });

    render(<RequireAdmin><div>Admin content</div></RequireAdmin>);

    expect(screen.getByText('Admin content')).toBeInTheDocument();
  });

  it('renders children for a legacy super_admin row with no platform_role', () => {
    // TRANSITION — rows predating the platform_role backfill must not be locked out.
    useCurrentDcmUserMock.mockReturnValue({
      user: {
        id: 'admin-002',
        entra_oid: 'entra-admin-002',
        email: 'legacy@example.com',
        display_name: 'Legacy Admin',
        role: 'super_admin',
        is_active: true,
        lz_ids: [],
      },
      loading: false,
      error: null,
      reload: vi.fn(),
    });

    render(<RequireAdmin><div>Admin content</div></RequireAdmin>);

    expect(screen.getByText('Admin content')).toBeInTheDocument();
  });

  it('blocks a legacy data-admin who is not a platform admin', () => {
    useCurrentDcmUserMock.mockReturnValue({
      user: {
        id: 'legacy-001',
        entra_oid: 'entra-legacy-001',
        email: 'architect@example.com',
        display_name: 'Data Admin',
        role: 'admin',
        platform_role: 'user',
        is_active: true,
        lz_ids: ['lz-001'],
      },
      loading: false,
      error: null,
      reload: vi.fn(),
    });

    render(<RequireAdmin><div>Admin content</div></RequireAdmin>);

    expect(screen.queryByText('Admin content')).not.toBeInTheDocument();
    expect(screen.getByText('Administration access required')).toBeInTheDocument();
  });

  it('blocks non-super-admin users', () => {
    useCurrentDcmUserMock.mockReturnValue({
      user: {
        id: 'viewer-001',
        entra_oid: 'entra-viewer-001',
        email: 'viewer@example.com',
        display_name: 'Viewer User',
        role: 'viewer',
        is_active: true,
        lz_ids: ['lz-001'],
      },
      loading: false,
      error: null,
      reload: vi.fn(),
    });

    render(<RequireAdmin><div>Admin content</div></RequireAdmin>);

    expect(screen.queryByText('Admin content')).not.toBeInTheDocument();
    expect(screen.getByText('Administration access required')).toBeInTheDocument();
    expect(
      screen.getByText(/Your platform tier is Member; administration requires a platform admin\./)
    ).toBeInTheDocument();
  });
});
