import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../test/render';
import Sidebar from './Sidebar';
import DatabricksComingSoon from '../pages/DatabricksComingSoon';

vi.mock('@azure/msal-react', () => ({
  useMsal: () => ({
    instance: { logoutRedirect: vi.fn() },
    accounts: [{ name: 'Test User', username: 'test@example.com' }],
  }),
}));

vi.mock('../hooks/useCurrentDcmUser', () => ({
  useCurrentDcmUser: vi.fn(),
}));

vi.mock('../hooks/useRolePermissions', () => ({
  useRolePermissions: vi.fn(),
}));

vi.mock('../contexts/theme', () => ({
  useTheme: () => ({ theme: 'light', toggleTheme: vi.fn() }),
}));

vi.mock('../tour/TourContext', () => ({
  useTour: () => ({ startWelcomeTour: vi.fn() }),
}));

import { useCurrentDcmUser } from '../hooks/useCurrentDcmUser';
import { useRolePermissions } from '../hooks/useRolePermissions';

const useCurrentDcmUserMock = vi.mocked(useCurrentDcmUser);
const useRolePermissionsMock = vi.mocked(useRolePermissions);

function mockUser(role: 'admin' | 'viewer' | 'super_admin') {
  useCurrentDcmUserMock.mockReturnValue({
    user: {
      id: 'user-001',
      entra_oid: 'entra-001',
      email: 'test@example.com',
      display_name: 'Test User',
      role,
      is_active: true,
      lz_ids: [],
    },
    loading: false,
    error: null,
    reload: vi.fn(),
  });
}

describe('Sidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1400 });
    mockUser('admin');
    useRolePermissionsMock.mockReturnValue({
      canAccess: () => true,
      role: 'admin',
      permissions: [],
    } as ReturnType<typeof useRolePermissions>);
  });

  it('groups both existing Usage routes and opens the active group', async () => {
    renderWithProviders(<Sidebar />, { route: '/databricks/usage-tables' });
    const usage = screen.getByRole('button', { name: /^Usage,/ });
    expect(usage).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('link', { name: 'UC tables' })).toHaveAttribute(
      'href',
      '/databricks/usage-tables'
    );
    expect(screen.getByRole('link', { name: 'Governance & Recommendations' })).toHaveAttribute(
      'href',
      '/databricks/usage-governance'
    );
    await userEvent.click(usage);
    expect(screen.queryByRole('link', { name: 'UC tables' })).not.toBeInTheDocument();
  });

  it('renders exactly 3 top-level main nav items', () => {
    renderWithProviders(<Sidebar />, { route: '/dashboard' });

    const nav = screen.getByRole('navigation');
    expect(nav.querySelectorAll(':scope > a').length).toBe(2);
    expect(nav.querySelectorAll(':scope > div > button').length).toBe(1);
    expect(screen.getByRole('link', { name: /^home$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /databricks/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /talk to your data/i })).toBeInTheDocument();
  });

  it('does not render hidden routes in the main nav', () => {
    renderWithProviders(<Sidebar />, { route: '/dashboard' });

    expect(document.querySelector('a[href="/costs"]')).toBeNull();
    expect(document.querySelector('a[href="/security"]')).toBeNull();
    expect(document.querySelector('a[href="/datafactory"]')).toBeNull();
    expect(document.querySelector('a[href="/clusters"]')).toBeNull();
  });

  it('renders Settings section with Administration + My Projects for admin', () => {
    renderWithProviders(<Sidebar />, { route: '/dashboard' });

    expect(screen.getByText('Settings')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /^administration$/i })).toHaveAttribute(
      'href',
      '/admin'
    );
    expect(screen.getByRole('link', { name: /my projects/i })).toHaveAttribute('href', '/projects');

    const settings = screen.getByTestId('sidebar-settings');
    expect(settings.querySelectorAll('a')).toHaveLength(2);
  });

  it('hides Administration for non-admin users', () => {
    mockUser('viewer');
    useRolePermissionsMock.mockReturnValue({
      canAccess: (key: string) => key !== 'page:admin',
      role: 'viewer',
      permissions: [],
    } as ReturnType<typeof useRolePermissions>);

    renderWithProviders(<Sidebar />, { route: '/dashboard' });

    expect(screen.getByText('Settings')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /^administration$/i })).not.toBeInTheDocument();
    expect(document.querySelector('a[href="/admin"]')).toBeNull();
    expect(screen.getByRole('link', { name: /my projects/i })).toHaveAttribute('href', '/projects');

    const settings = screen.getByTestId('sidebar-settings');
    expect(settings.querySelectorAll('a')).toHaveLength(1);
  });

  it('renders Databricks hub with Overview, Jobs & Pipelines, and collapsible Compute', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Sidebar />, { route: '/dashboard' });

    await user.click(screen.getByRole('button', { name: /databricks/i }));

    expect(document.querySelector('a[href="/databricks/overview"]')).toBeInTheDocument();
    expect(document.querySelector('a[href="/databricks/workflows"]')).toBeInTheDocument();
    expect(screen.getByText(/jobs & pipelines/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /lakeflow/i })).not.toBeInTheDocument();
    expect(document.querySelector('a[href="/databricks/pipelines"]')).toBeNull();
    expect(screen.getByRole('button', { name: /compute/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /compute/i }));
    expect(document.querySelector('a[href="/databricks/cluster"]')).toBeInTheDocument();
    expect(document.querySelector('a[href="/databricks/sql-warehouse"]')).toBeInTheDocument();

    expect(document.querySelector('a[href="/databricks/finops-v2"]')).toBeInTheDocument();
    expect(document.querySelector('a[href="/databricks/data-product-usage"]')).toBeInTheDocument();

    expect(document.querySelector('a[href="/databricks/lakeflow"]')).toBeNull();
    expect(document.querySelector('a[href="/databricks/alerts"]')).toBeNull();
    expect(document.querySelector('a[href="/unitycatalogexplorer"]')).toBeNull();
  });
});

describe('DatabricksComingSoon', () => {
  it('renders title and group for pipelines without Lakeflow secondary tabs', () => {
    renderWithProviders(<DatabricksComingSoon />, { route: '/databricks/pipelines' });

    expect(screen.getByRole('heading', { name: /pipelines/i })).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: /lakeflow sections/i })).toBeNull();
    expect(screen.getByText(/coming soon/i)).toBeInTheDocument();
  });
});
