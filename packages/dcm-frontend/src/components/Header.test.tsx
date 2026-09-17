import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useGlobalTimeRange } from '../contexts/time-range';
import { fireEvent, renderWithProviders, screen, userEvent, waitFor } from '../test/render';
import type { LandingZonesResponse, ProjectSummary } from '../types/api';
import Header from './Header';

vi.mock('../api/dcmApiClient', () => ({
  // `emptyOn404` narrows on this class before deciding to swallow the failure.
  DcmApiError: class DcmApiError extends Error {},
  listDatabricksWorkspaces: vi.fn(),
  listLandingZones: vi.fn(),
  listProjects: vi.fn(),
}));

vi.mock('./HeaderNotificationBell', () => ({
  HeaderNotificationBell: () => <button type="button">Notifications</button>,
}));

// The guide button reaches for the tour context, which lives above the app shell
// and not in the test providers.
vi.mock('./DcmGuideButton', () => ({
  DcmGuideButton: () => <button type="button">Guide</button>,
}));

import { listDatabricksWorkspaces, listLandingZones, listProjects } from '../api/dcmApiClient';

const landingZonesFixture = {
  items: [
    {
      lz_id: 'lz-001',
      lz_name: 'analytics-prod',
      cloud_provider: 'azure',
      subscription_or_account_id: 'sub-001',
      environment: 'prod',
      ba_name: 'Analytics',
      valid_from: '2026-01-01',
    },
    {
      lz_id: 'lz-002',
      lz_name: 'billing-dev',
      cloud_provider: 'azure',
      subscription_or_account_id: 'sub-002',
      environment: 'dev',
      ba_name: 'Billing',
      valid_from: '2026-01-01',
    },
  ],
  total: 2,
} satisfies LandingZonesResponse;

const projectFixture: ProjectSummary = {
  id: 'Payments',
  name: 'Payments monitoring',
  businessAppId: 'Payments',
  status: 'active',
  role: 'admin',
  lzScope: ['lz-001'],
  effectiveLzScope: ['lz-001'],
  dbxScope: ['adb-305973814376'],
  memberCount: 3,
};

function PeriodProbe() {
  const { timeRange } = useGlobalTimeRange();

  return <output aria-label="Period active">{timeRange.description}</output>;
}

// `/databricks/workspaces` returns canonical ids, while a project's `dbxScope`
// keeps the `adb-` form of the reference dimension — see `projectFixture`.
const workspacesFixture = {
  items: [
    {
      workspace_id: '305973814376',
      display_name: 'example-cluster',
      source_lz_id: 'lz-001',
      cluster_count: 2,
    },
    {
      workspace_id: '999888777',
      display_name: 'staging-eu',
      source_lz_id: 'lz-002',
      cluster_count: 1,
    },
  ],
};

const apiMocks = {
  listDatabricksWorkspaces: vi.mocked(listDatabricksWorkspaces),
  listLandingZones: vi.mocked(listLandingZones),
  listProjects: vi.mocked(listProjects),
};

describe('Header', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.listLandingZones.mockResolvedValue(landingZonesFixture);
    apiMocks.listDatabricksWorkspaces.mockResolvedValue(workspacesFixture);
    apiMocks.listProjects.mockResolvedValue([]);
  });

  it('renders compact scope and applies a custom date range', async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <>
        <Header />
        <PeriodProbe />
      </>,
      { route: '/dashboard' }
    );

    expect(screen.getByRole('button', { name: /Landing zone filter/i })).toBeInTheDocument();
    expect(screen.getByLabelText('Start date')).toBeInTheDocument();
    expect(screen.getByLabelText('End date')).toBeInTheDocument();
    expect(screen.queryByText('Data Connect Monitoring')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '1 month' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Apply' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '30d' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '90d' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '6m' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '1y' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '90d' }));
    expect(screen.getByLabelText('Period active')).toHaveTextContent('90 days');

    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2020-01-01' } });
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2020-01-31' } });

    expect(screen.getByLabelText('Period active')).toHaveTextContent('2020-01-01 - 2020-01-31');
    await waitFor(() => expect(apiMocks.listLandingZones).toHaveBeenCalled());
  });

  it('shows both the landing zone and workspace filters on /databricks routes', async () => {
    // The workflow and compute tables are keyed on workspace_id; the backend
    // resolves the selected landing zone to its workspaces, so both filters are
    // offered on Databricks pages and stay in sync.
    const { unmount: unmountDashboard } = renderWithProviders(<Header />, { route: '/dashboard' });

    expect(await screen.findByRole('button', { name: /Landing zone filter/i })).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Databricks workspace filter/i })
    ).not.toBeInTheDocument();
    expect(apiMocks.listDatabricksWorkspaces).not.toHaveBeenCalled();
    unmountDashboard();
    // The dashboard render above did fetch the catalog; only the next one matters.
    apiMocks.listLandingZones.mockClear();

    const { unmount: unmountDatabricks } = renderWithProviders(<Header />, {
      route: '/databricks',
    });

    expect(
      await screen.findByRole('button', { name: /Databricks workspace filter/i })
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Landing zone filter/i })).toBeInTheDocument();
    await waitFor(() => expect(apiMocks.listDatabricksWorkspaces).toHaveBeenCalled());
    await waitFor(() => expect(apiMocks.listLandingZones).toHaveBeenCalled());
    unmountDatabricks();

    renderWithProviders(<Header />, { route: '/databases' });
    expect(
      screen.queryByRole('button', { name: /Databricks workspace filter/i })
    ).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Landing zone filter/i })).toBeInTheDocument();
  });

  it('keeps both filters on the Databricks pages whose tables are LZ-keyed', async () => {
    // Alerts, FinOps and Governance read source_lz_id-bearing tables, so the
    // landing zone stays their only working dimension.
    renderWithProviders(<Header />, { route: '/databricks/alerts' });

    expect(await screen.findByRole('button', { name: /Landing zone filter/i })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Databricks workspace filter/i })
    ).toBeInTheDocument();
  });

  it('shows workspace display_name in filter summary when one workspace selected', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Header />, { route: '/databricks' });

    const filterButton = await screen.findByRole('button', {
      name: /Databricks workspace filter/i,
    });
    await user.click(filterButton);

    const stagingOption = await screen.findByRole('checkbox', { name: /staging-eu/i });
    await user.click(stagingOption);

    expect(filterButton).toHaveTextContent('example-cluster');
    expect(filterButton).not.toHaveTextContent('305973814376');
  });

  it('offers a project filter only to accounts that belong to one', async () => {
    const { unmount } = renderWithProviders(<Header />, { route: '/dashboard' });

    await waitFor(() => expect(apiMocks.listProjects).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: 'Project filter' })).not.toBeInTheDocument();
    unmount();

    apiMocks.listProjects.mockResolvedValue([projectFixture]);
    renderWithProviders(<Header />, { route: '/dashboard' });

    expect(await screen.findByRole('button', { name: 'Project filter' })).toHaveTextContent(
      'All my projects'
    );
  });

  it('narrows the landing zone and workspace filters to the picked project scope', async () => {
    apiMocks.listProjects.mockResolvedValue([projectFixture]);
    const user = userEvent.setup();
    // One of the few routes that carries both dimensions at once.
    renderWithProviders(<Header />, { route: '/databricks/alerts' });

    const projectFilter = await screen.findByRole('button', { name: 'Project filter' });
    // Both landing zones are on offer as long as no project narrows the view.
    await user.click(screen.getByRole('button', { name: /Landing zone filter/i }));
    expect(screen.getByRole('checkbox', { name: 'billing-dev' })).toBeInTheDocument();

    await user.click(projectFilter);
    await user.click(screen.getByRole('option', { name: /Payments monitoring/ }));

    expect(projectFilter).toHaveTextContent('Payments monitoring');
    // The LZ filter now holds the project scope, and offers nothing outside it.
    const landingZoneFilter = screen.getByRole('button', { name: /Landing zone filter/i });
    expect(landingZoneFilter).toHaveTextContent('analytics-prod');
    await user.click(landingZoneFilter);
    expect(screen.getByRole('checkbox', { name: 'analytics-prod' })).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: 'billing-dev' })).not.toBeInTheDocument();

    // Same on the workspace side: only what the project's dbx scope grants — and
    // `adb-305973814376` must match the canonical `305973814376` the API returns.
    await user.click(screen.getByRole('button', { name: /Databricks workspace filter/i }));
    expect(screen.getByRole('checkbox', { name: /example-cluster/ })).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: /staging-eu/ })).not.toBeInTheDocument();
  });

  it('applies the resolved landing zones, not the registered scope values', async () => {
    // `dcm_project_lz_scope` may hold a subscription id — the Azure source view
    // names it `lz_id`. Narrowing on the raw column left the selector empty and
    // sent an id no monitoring row carries, so every page came back blank.
    apiMocks.listProjects.mockResolvedValue([
      { ...projectFixture, lzScope: ['sub-001'], effectiveLzScope: ['lz-001'] },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<Header />, { route: '/dashboard' });

    const projectFilter = await screen.findByRole('button', { name: 'Project filter' });
    await user.click(projectFilter);
    await user.click(screen.getByRole('option', { name: /Payments monitoring/ }));

    const landingZoneFilter = screen.getByRole('button', { name: /Landing zone filter/i });
    expect(landingZoneFilter).toHaveTextContent('analytics-prod');
    await user.click(landingZoneFilter);
    expect(screen.getByRole('checkbox', { name: 'analytics-prod' })).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: 'billing-dev' })).not.toBeInTheDocument();
  });

  it('leaves the landing zone filter open when a project resolves to none', async () => {
    // A grant on a landing zone the monitoring data has not reached yet resolves
    // to nothing. Applying an empty selection would be a `1 = 0` on every page,
    // while the server-side project scope already restricts what comes back.
    apiMocks.listProjects.mockResolvedValue([
      { ...projectFixture, lzScope: ['lz-not-yet-collected'], effectiveLzScope: [] },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<Header />, { route: '/databricks/alerts' });

    const projectFilter = await screen.findByRole('button', { name: 'Project filter' });
    await user.click(projectFilter);
    await user.click(screen.getByRole('option', { name: /Payments monitoring/ }));

    expect(screen.getByRole('button', { name: /Landing zone filter/i })).toHaveTextContent(
      /all landing zones/i
    );
    // The workspace dimension still narrows: it is granted directly.
    await user.click(screen.getByRole('button', { name: /Databricks workspace filter/i }));
    expect(screen.getByRole('checkbox', { name: /example-cluster/ })).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: /staging-eu/ })).not.toBeInTheDocument();
  });

  it('keeps a granted workspace whose landing zone is unknown', async () => {
    // The live gold_dbx_workflow_runs has no source_lz_id, so a workspace known
    // only from there carries none. Applying the project LZ selection used to
    // drop it, leaving "No workspaces" on every Databricks page.
    apiMocks.listProjects.mockResolvedValue([
      { ...projectFixture, dbxScope: ['adb-305973814376', '444555'] },
    ]);
    apiMocks.listDatabricksWorkspaces.mockResolvedValue({
      items: [
        ...workspacesFixture.items,
        {
          workspace_id: '444555',
          display_name: 'dbw-no-lz',
          source_lz_id: null,
          cluster_count: 3,
        },
      ],
    });
    const user = userEvent.setup();
    // A route where the LZ selection still narrows the workspace list — that
    // narrowing is what used to drop the unknown-LZ workspace.
    renderWithProviders(<Header />, { route: '/databricks/alerts' });

    const projectFilter = await screen.findByRole('button', { name: 'Project filter' });
    await user.click(projectFilter);
    await user.click(screen.getByRole('option', { name: /Payments monitoring/ }));

    await user.click(screen.getByRole('button', { name: /Databricks workspace filter/i }));
    expect(screen.getByRole('checkbox', { name: /example-cluster/ })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /dbw-no-lz/ })).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: /staging-eu/ })).not.toBeInTheDocument();
  });

  it('narrows workspaces by the landing zone selection on every Databricks route', async () => {
    // The LZ filter is offered on all Databricks pages now (the backend maps it
    // to workspaces), so a project's LZ scope narrows the workspace list the same
    // way whether or not the page also reads source_lz_id-bearing tables.
    apiMocks.listProjects.mockResolvedValue([
      { ...projectFixture, dbxScope: ['adb-305973814376', '999888777'] },
    ]);
    const user = userEvent.setup();

    async function pickProjectThenOpenWorkspaces() {
      await user.click(await screen.findByRole('button', { name: 'Project filter' }));
      await user.click(screen.getByRole('option', { name: /Payments monitoring/ }));
      await user.click(screen.getByRole('button', { name: /Databricks workspace filter/i }));
    }

    // A page that also reads source_lz_id-bearing tables narrows as before.
    const { unmount } = renderWithProviders(<Header />, { route: '/databricks/alerts' });
    await pickProjectThenOpenWorkspaces();
    expect(screen.getByRole('checkbox', { name: /example-cluster/ })).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: /staging-eu/ })).not.toBeInTheDocument();
    unmount();

    // Same project, same scope — a workspace-keyed page now narrows identically.
    renderWithProviders(<Header />, { route: '/databricks' });
    await pickProjectThenOpenWorkspaces();
    expect(screen.getByRole('checkbox', { name: /example-cluster/ })).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: /staging-eu/ })).not.toBeInTheDocument();
  });

  it('hides global filters on Talk to Data', () => {
    renderWithProviders(<Header />, { route: '/talk-to-data' });

    expect(screen.getByRole('heading', { name: 'Talk to your Data' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Landing zone filter/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Start date')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('End date')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '30d' })).not.toBeInTheDocument();
    expect(apiMocks.listLandingZones).not.toHaveBeenCalled();
  });

  it('hides global filters on Databricks Insights', () => {
    renderWithProviders(<Header />, { route: '/databricks/insights' });

    // Insights left the sidebar menu, so the header falls back to the app title —
    // what matters here is that the route still carries no global filter.
    expect(screen.getByRole('heading', { name: 'Data connect' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Landing zone filter/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Start date')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Databricks workspace filter/i })
    ).not.toBeInTheDocument();
    expect(apiMocks.listLandingZones).not.toHaveBeenCalled();
  });

  it('hides range presets on Databricks Overview but keeps From/To dates', () => {
    renderWithProviders(<Header />, { route: '/databricks/overview' });

    expect(screen.getByRole('heading', { name: 'Databricks Overview' })).toBeInTheDocument();
    expect(screen.getByLabelText('Start date')).toBeInTheDocument();
    expect(screen.getByLabelText('End date')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '30d' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '90d' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Go back to previous page/i })).toBeInTheDocument();
  });

  it.each(['/databricks/cluster', '/databricks/sql-warehouse'])(
    'hides the date range on %s, where tables read a predefined window',
    (route) => {
      renderWithProviders(<Header />, { route });

      expect(screen.queryByLabelText('Start date')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('End date')).not.toBeInTheDocument();
      // The presets write into that same range, so they go with it.
      expect(screen.queryByRole('button', { name: '30d' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: '90d' })).not.toBeInTheDocument();
      // What still narrows these pages stays.
      expect(screen.getByRole('button', { name: /Landing zone filter/i })).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: /Databricks workspace filter/i })
      ).toBeInTheDocument();
    }
  );

  it('hides duplicate back button on focus drill-down pages', () => {
    renderWithProviders(<Header />, { route: '/databricks/workspaces' });

    expect(screen.getByRole('heading', { name: 'Workspace overview' })).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Go back to previous page/i })
    ).not.toBeInTheDocument();
  });
});
