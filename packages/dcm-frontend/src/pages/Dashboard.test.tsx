import { Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { dashboardFullFixture } from '../test/fixtures/dashboard';
import { renderWithProviders, screen, userEvent, waitFor } from '../test/render';
import Dashboard from './Dashboard';

vi.mock('../api/dcmApiClient', () => ({
  getDashboardFull: vi.fn(),
  getKpiConfig: vi.fn(),
  getCurrentDcmUser: vi.fn(),
  getDcmPermissions: vi.fn(),
}));

vi.mock('../hooks/useCurrentDcmUser', () => ({
  useCurrentDcmUser: () => ({
    user: { display_name: 'Maher Lezhari' },
    loading: false,
    error: null,
    reload: vi.fn(),
  }),
}));

vi.mock('../hooks/useRolePermissions', () => ({
  useRolePermissions: () => ({
    canAccess: () => true,
    loading: false,
    error: null,
    permissions: { role: 'viewer', pages: [], widgets: [], features: [], allowed: [] },
  }),
}));

import { getDashboardFull, getKpiConfig } from '../api/dcmApiClient';

const apiMocks = {
  getDashboardFull: vi.mocked(getDashboardFull),
  getKpiConfig: vi.mocked(getKpiConfig),
};

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getDashboardFull.mockResolvedValue(dashboardFullFixture);
    apiMocks.getKpiConfig.mockResolvedValue({
      items: [],
      values: {
        pipeline_failure_rate_warning_pct: 10,
        pipeline_failure_rate_critical_pct: 30,
        open_alerts_warning_count: 5,
        open_alerts_critical_count: 20,
        compliance_score_warning_pct: 80,
        compliance_score_critical_pct: 60,
      },
    });
  });

  it('renders the scoped home summary with the current user and backend values', async () => {
    renderWithProviders(<Dashboard />, { route: '/dashboard' });

    expect(await screen.findByRole('heading', { name: /Welcome, Maher/i })).toBeInTheDocument();
    expect(
      await screen.findByText('Failed jobs during the last rolling 24 hours')
    ).toBeInTheDocument();
    expect(screen.getByText(/Last synchronization:/)).toHaveTextContent('25 May 2026');
    expect(screen.getByText('Active clusters').nextElementSibling).toHaveTextContent('3');
    expect(screen.getByText('Active SQL Warehouses').nextElementSibling).toHaveTextContent('4');
    expect(screen.getByText('$12.5K')).toBeInTheDocument();
    expect(screen.getByText('▲ 25.0% vs same period last year')).toBeInTheDocument();
    expect(screen.getByText('3', { selector: 'p' })).toBeInTheDocument();
    expect(screen.getByText('1 Critical')).toBeInTheDocument();
    expect(screen.getByText('2 Medium')).toBeInTheDocument();
    expect(screen.getByRole('figure', { name: 'Monthly YTD cost trend' })).toBeInTheDocument();
  });

  it('makes each active card an accessible link to its existing route', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/databricks/workflows" element={<p>Workflow destination</p>} />
      </Routes>,
      { route: '/dashboard' }
    );

    const jobs = await screen.findByRole('link', { name: 'Open Jobs & Pipelines' });
    expect(jobs).toHaveAttribute('href', '/databricks/workflows');
    expect(screen.getByRole('link', { name: 'Open Compute' })).toHaveAttribute(
      'href',
      '/databricks/cluster'
    );
    expect(screen.getByRole('link', { name: 'Open Usage tracking' })).toHaveAttribute(
      'href',
      '/databricks/data-product-usage'
    );
    expect(screen.getByRole('link', { name: 'Open FinOps' })).toHaveAttribute(
      'href',
      '/databricks/finops-v2'
    );
    expect(screen.getByRole('link', { name: 'Open Active alerts' })).toHaveAttribute(
      'href',
      '/databricks/alerts'
    );

    jobs.focus();
    await user.keyboard('{Enter}');
    expect(await screen.findByText('Workflow destination')).toBeInTheDocument();
  });

  it('shows roadmap cards as disabled and non-interactive', async () => {
    renderWithProviders(<Dashboard />, { route: '/dashboard' });

    await screen.findByRole('heading', { name: 'Cognite' });
    expect(
      screen.getByRole('heading', { name: 'Cognite' }).closest('[aria-disabled="true"]')
    ).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Cognite/i })).not.toBeInTheDocument();
  });

  it('shows an explicit loading state', () => {
    apiMocks.getDashboardFull.mockReturnValue(new Promise(() => undefined));

    renderWithProviders(<Dashboard />, { route: '/dashboard' });

    expect(screen.getByLabelText('Loading dashboard')).toBeInTheDocument();
  });

  it('shows an actionable error without fallback metric values', async () => {
    apiMocks.getDashboardFull.mockRejectedValue(new Error('Backend unavailable'));

    renderWithProviders(<Dashboard />, { route: '/dashboard' });

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Dashboard unavailable');
    expect(alert).toHaveTextContent('Backend unavailable');
    expect(screen.queryByRole('link', { name: 'Open Jobs & Pipelines' })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(apiMocks.getDashboardFull).toHaveBeenCalledTimes(2));
  });
});
