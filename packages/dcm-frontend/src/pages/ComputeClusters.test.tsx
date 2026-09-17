import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  computeClustersCostFixture,
  computeClustersEfficiencyFixture,
  computeClustersGovernanceFixture,
  computeClustersOverviewFixture,
  computeClusterDetailFixture,
  computeClusterLifetimeTrendFixture,
  computeClusterTrendFixture,
} from '../test/fixtures/compute-clusters';
import { renderWithProviders, screen, userEvent, waitFor, within } from '../test/render';
import ComputeClusters from './ComputeClusters';

vi.mock('../api/dcmApiClient', () => ({
  getComputeClustersOverview: vi.fn(),
  listComputeClustersCost: vi.fn(),
  listComputeClustersEfficiency: vi.fn(),
  listComputeClustersGovernance: vi.fn(),
  getComputeClusterDetail: vi.fn(),
  getComputeClusterCostTrend: vi.fn(),
  getComputeClusterLifetimeTrend: vi.fn(),
  listDatabricksWorkspaces: vi.fn(),
}));

import {
  getComputeClustersOverview,
  getComputeClusterDetail,
  getComputeClusterCostTrend,
  getComputeClusterLifetimeTrend,
  listComputeClustersCost,
  listComputeClustersEfficiency,
  listComputeClustersGovernance,
  listDatabricksWorkspaces,
} from '../api/dcmApiClient';

const apiMocks = {
  getComputeClustersOverview: vi.mocked(getComputeClustersOverview),
  listComputeClustersCost: vi.mocked(listComputeClustersCost),
  listComputeClustersEfficiency: vi.mocked(listComputeClustersEfficiency),
  listComputeClustersGovernance: vi.mocked(listComputeClustersGovernance),
  getComputeClusterDetail: vi.mocked(getComputeClusterDetail),
  getComputeClusterCostTrend: vi.mocked(getComputeClusterCostTrend),
  getComputeClusterLifetimeTrend: vi.mocked(getComputeClusterLifetimeTrend),
  listDatabricksWorkspaces: vi.mocked(listDatabricksWorkspaces),
};

async function openCostDrawer() {
  const user = userEvent.setup();
  renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

  await user.click(await screen.findByRole('tab', { name: 'Cost' }));
  // Scoped to the table: the "Top costly" KPI card names the same cluster.
  const table = await screen.findByRole('table');
  await user.click(await within(table).findByText('etl_ingestion_prod'));
  await screen.findByRole('dialog', { name: 'Cluster details' });

  return user;
}

/**
 * Bornes attendues, recalculées ici sans passer par l'implémentation : cette page
 * n'a plus de sélecteur de dates, ses plages sont ancrées sur aujourd'hui.
 */
function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

describe('ComputeClusters', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getComputeClustersOverview.mockResolvedValue(computeClustersOverviewFixture);
    apiMocks.listComputeClustersCost.mockResolvedValue(computeClustersCostFixture);
    apiMocks.listComputeClustersEfficiency.mockResolvedValue(computeClustersEfficiencyFixture);
    apiMocks.listComputeClustersGovernance.mockResolvedValue(computeClustersGovernanceFixture);
    apiMocks.getComputeClusterDetail.mockResolvedValue(computeClusterDetailFixture);
    apiMocks.getComputeClusterCostTrend.mockResolvedValue(computeClusterTrendFixture);
    apiMocks.getComputeClusterLifetimeTrend.mockResolvedValue(computeClusterLifetimeTrendFixture);
    apiMocks.listDatabricksWorkspaces.mockResolvedValue({
      items: [
        {
          workspace_id: 'ws-1',
          display_name: 'dbw-analytics-prod',
          source_lz_id: 'lz-1',
          cluster_count: 4,
        },
      ],
    });
  });

  it('renders 4 tabs (no Reliability)', async () => {
    renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

    expect(await screen.findByRole('tab', { name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Cost' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Efficiency' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Governance' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /Reliability/i })).not.toBeInTheDocument();
  });

  it('offers exactly four static ranges and no free date entry', async () => {
    renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

    const group = await screen.findByRole('group', { name: 'Rolling window' });
    expect(within(group).getAllByRole('button')).toHaveLength(4);
    expect(within(group).getByRole('button', { name: 'Daily' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    for (const label of ['Last 7d', 'Last 30d', 'Last 90d']) {
      expect(within(group).getByRole('button', { name: label })).toHaveAttribute(
        'aria-pressed',
        'false'
      );
    }
    // No free period entry left on this page.
    expect(within(group).queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('sends the selected range as window_days on the list endpoints', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

    await waitFor(() => {
      expect(apiMocks.getComputeClustersOverview).toHaveBeenCalledWith(
        expect.objectContaining({ window_days: 1 })
      );
    });

    await user.click(await screen.findByRole('button', { name: 'Last 30d' }));

    await waitFor(() => {
      expect(apiMocks.getComputeClustersOverview).toHaveBeenCalledWith(
        expect.objectContaining({ window_days: 30 })
      );
    });
  });

  it('keeps the selected range when switching tabs', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

    await user.click(await screen.findByRole('button', { name: 'Last 90d' }));
    await user.click(screen.getByRole('tab', { name: 'Cost' }));

    expect(screen.getByRole('button', { name: 'Last 90d' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await waitFor(() => {
      expect(apiMocks.listComputeClustersCost).toHaveBeenCalledWith(
        expect.objectContaining({ window_days: 90 })
      );
    });
  });

  it('displays the covered period read from the API window, not from the chip', async () => {
    renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

    // `Daily` is selected, the fixture reports a 7-day window: the label follows
    // the data (a late pipeline run must not be hidden behind a computed range).
    expect(await screen.findByText('2026-08-07 → 2026-08-13')).toBeInTheDocument();
  });

  it('warns when no row has a previous Lifetime, and stays silent otherwise', async () => {
    // The default fixture mixes a comparable cluster with an ephemeral one: a "—" in
    // some rows is normal and must not raise the notice.
    const { unmount } = renderWithProviders(<ComputeClusters />, {
      route: '/databricks/cluster',
    });
    expect(await screen.findByText('2026-08-07 → 2026-08-13')).toBeInTheDocument();
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
    unmount();

    // Every row without a previous Lifetime means the upstream history is shorter than
    // two windows (research.md R7) — an entire empty column needs explaining.
    apiMocks.getComputeClustersOverview.mockResolvedValue({
      ...computeClustersOverviewFixture,
      items: computeClustersOverviewFixture.items.map((item) => ({
        ...item,
        uptime_hours_prev_window: null,
        uptime_hours_delta_pct: null,
      })),
    });
    renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

    const note = await screen.findByRole('note');
    expect(note).toHaveTextContent(/Lifetime and IDLE have no previous period/);
    // Cost keeps a far deeper history: its own comparison must not be disclaimed.
    expect(note).toHaveTextContent(/Cost comparisons are unaffected/);
  });

  it('pages, searches and sorts the Overview on the server', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

    // The footer counts the whole scope (137), not the two rows on the page.
    expect(await screen.findByText(/137/)).toBeInTheDocument();

    await waitFor(() => {
      expect(apiMocks.getComputeClustersOverview).toHaveBeenCalledWith(
        expect.objectContaining({ page: 1, page_size: 25, sort: 'cost', sort_direction: 'desc' })
      );
    });

    // A search must reach the endpoint: filtering the 25 rows on screen would leave
    // the 26th-and-beyond clusters unreachable by name.
    await user.type(screen.getByLabelText('Search overview clusters'), 'etl');
    await waitFor(() => {
      expect(apiMocks.getComputeClustersOverview).toHaveBeenCalledWith(
        expect.objectContaining({ search: 'etl', page: 1 })
      );
    });

    // Same for the status chip and for the column sort.
    await user.click(screen.getByRole('button', { name: 'Zombie' }));
    await waitFor(() => {
      expect(apiMocks.getComputeClustersOverview).toHaveBeenCalledWith(
        expect.objectContaining({ utilization_status: 'ZOMBIE' })
      );
    });

    await user.click(screen.getByRole('button', { name: /^Lifetime/ }));
    await waitFor(() => {
      expect(apiMocks.getComputeClustersOverview).toHaveBeenCalledWith(
        expect.objectContaining({ sort: 'cluster_lifetime', sort_direction: 'desc' })
      );
    });
  });

  it('asks for page 1 again when the range changes', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

    await user.click(await screen.findByRole('button', { name: /Next/ }));
    await waitFor(() => {
      expect(apiMocks.getComputeClustersOverview).toHaveBeenCalledWith(
        expect.objectContaining({ page: 2 })
      );
    });

    // Another range is another population: staying on page 2 could land past its end.
    await user.click(screen.getByRole('button', { name: 'Last 30d' }));
    await waitFor(() => {
      expect(apiMocks.getComputeClustersOverview).toHaveBeenCalledWith(
        expect.objectContaining({ window_days: 30, page: 1 })
      );
    });
  });

  it('keeps the search box reachable when the server returns nothing', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

    await screen.findByRole('table');
    apiMocks.getComputeClustersOverview.mockResolvedValue({
      ...computeClustersOverviewFixture,
      items: [],
      total: 0,
    });
    await user.type(screen.getByLabelText('Search overview clusters'), 'zzz');

    // The page-level empty state would unmount the toolbar with the input in it.
    expect(await screen.findByText('No clusters match these filters')).toBeInTheDocument();
    expect(screen.getByLabelText('Search overview clusters')).toHaveValue('zzz');
  });

  it('renders the Overview columns of FR-004 and nothing else', async () => {
    renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

    const table = await screen.findByRole('table');
    const headers = within(table)
      .getAllByRole('columnheader')
      .map((cell) => cell.textContent?.trim());

    expect(headers).toEqual([
      'Workspace',
      'Cluster',
      'Cost',
      'Prev cost',
      'Lifetime',
      'Prev lifetime',
      'Utilization',
      'Governance',
    ]);
  });

  it('renders a missing previous window as an em dash, never 0 nor NaN', async () => {
    renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

    const noHistoryRow = (await screen.findByText('job_run_once')).closest('tr');
    expect(noHistoryRow).not.toBeNull();
    const cells = within(noHistoryRow!)
      .getAllByRole('cell')
      .map((cell) => cell.textContent?.trim());

    // Prev cost, then prev lifetime.
    expect(cells[3]).toBe('—');
    expect(cells[5]).toBe('—');
    expect(cells.join(' ')).not.toMatch(/NaN/);
  });

  it('renders the Cost columns of FR-005 including the DBU unit cost', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

    await user.click(await screen.findByRole('tab', { name: 'Cost' }));

    const table = await screen.findByRole('table');
    const headers = within(table)
      .getAllByRole('columnheader')
      .map((cell) => cell.textContent?.trim());

    expect(headers).toEqual([
      'Workspace',
      'Cluster',
      'Cost',
      'Prev cost',
      'SKU group',
      'DBU cost',
      'DBU',
    ]);
    expect(screen.getByText('$0.241')).toBeInTheDocument();
  });

  it('renders the Efficiency columns of FR-006 with the autoscaling bounds', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

    await user.click(await screen.findByRole('tab', { name: 'Efficiency' }));

    const table = await screen.findByRole('table');
    const headers = within(table)
      .getAllByRole('columnheader')
      .map((cell) => cell.textContent?.trim());

    expect(headers).toEqual([
      'Workspace',
      'Cluster',
      'Driver node',
      'Worker node',
      'Autoscaling',
      'Nodes',
      'Lifetime',
      'Prev lifetime',
      'Idle',
      'Prev idle',
      'CPU avg',
      'CPU p95',
      'Mem avg',
      'Mem p95',
      'Status',
      'Recommended node',
      'Est. savings',
    ]);
    // Configured bounds, not the observed maximum (`worker_count_max` = 10).
    expect(screen.getByText('2 – 8')).toBeInTheDocument();
    // A percentage-point variation reads in points, never in per cent.
    expect(screen.getByText('-5.0 pts')).toBeInTheDocument();
  });

  it('leaves the Governance tab untouched', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

    await user.click(await screen.findByRole('tab', { name: 'Governance' }));

    const table = await screen.findByRole('table');
    const headers = within(table)
      .getAllByRole('columnheader')
      .map((cell) => cell.textContent?.trim());

    expect(headers).toEqual([
      'Cluster',
      'Owner tag',
      'Cost-center tag',
      'DBR',
      'Action',
      'Severity',
    ]);
    // The governance snapshot has no window: the endpoint must not receive one.
    await waitFor(() => {
      expect(apiMocks.listComputeClustersGovernance).toHaveBeenCalled();
    });
    expect(apiMocks.listComputeClustersGovernance.mock.calls[0]?.[0]).not.toHaveProperty(
      'window_days'
    );
  });

  it('shows an empty state when overview has zero items', async () => {
    apiMocks.getComputeClustersOverview.mockResolvedValue({
      ...computeClustersOverviewFixture,
      items: [],
      kpis: {
        total_cost_usd: 0,
        cost_delta_pct: null,
        active_clusters: 0,
        zombie_count: 0,
        open_recommendations: 0,
      },
    });

    renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

    expect(await screen.findByText('No clusters found')).toBeInTheDocument();
  });

  it('does not render the page-level drawer granularity control', async () => {
    renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

    await screen.findByRole('tab', { name: 'Overview' });
    expect(screen.queryByLabelText('Drawer cost trend granularity')).not.toBeInTheDocument();
  });

  it('calls efficiency endpoint when Zombie filter is selected', async () => {
    const user = userEvent.setup();

    renderWithProviders(<ComputeClusters />, { route: '/databricks/cluster' });

    await user.click(await screen.findByRole('tab', { name: 'Efficiency' }));
    await user.click(screen.getByRole('button', { name: 'Zombie' }));

    await waitFor(() => {
      expect(apiMocks.listComputeClustersEfficiency).toHaveBeenCalledWith(
        expect.objectContaining({ is_zombie: true })
      );
    });
  });

  it('opens the drawer with the technical specs and both trends', async () => {
    await openCostDrawer();

    const drawer = screen.getByRole('dialog', { name: 'Cluster details' });

    // Technical specs added by this feature.
    expect(within(drawer).getByText('Driver node')).toBeInTheDocument();
    expect(within(drawer).getByText('Standard_DS3_v2')).toBeInTheDocument();
    expect(within(drawer).getByText('2 – 8')).toBeInTheDocument();

    expect(within(drawer).getByText('Cost trend (≈90 days)')).toBeInTheDocument();
    expect(within(drawer).getByText('Lifetime trend (≈90 days)')).toBeInTheDocument();

    await waitFor(() => {
      expect(apiMocks.getComputeClusterDetail).toHaveBeenCalled();
      expect(apiMocks.getComputeClusterCostTrend).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ granularity: 'week' })
      );
      expect(apiMocks.getComputeClusterLifetimeTrend).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ granularity: 'week' })
      );
    });
  });

  it('anchors the tables and the drawer trends on today, not on a header range', async () => {
    // Les deux courbes du tiroir, elles, filtrent vraiment : ≈90 jours finissant
    // aujourd'hui, et non une plage globale devenue invisible sur cette page.
    await openCostDrawer();

    // Les quatre tableaux lisent un instantané par fenêtre : le serveur ne fait que
    // renvoyer ces bornes, la page en envoie donc une plage large et fixe plutôt que
    // les 30 jours par défaut de l'en-tête, désormais masqué ici.
    await waitFor(() => {
      expect(apiMocks.getComputeClustersOverview).toHaveBeenCalledWith(
        expect.objectContaining({ period_start: isoDaysAgo(364), period_end: isoDaysAgo(0) })
      );
    });

    await waitFor(() => {
      const expected = expect.objectContaining({
        period_start: isoDaysAgo(89),
        period_end: isoDaysAgo(0),
      });
      expect(apiMocks.getComputeClusterCostTrend).toHaveBeenCalledWith(
        expect.any(String),
        expected
      );
      expect(apiMocks.getComputeClusterLifetimeTrend).toHaveBeenCalledWith(
        expect.any(String),
        expected
      );
    });
  });

  it('switches each trend granularity independently', async () => {
    const user = await openCostDrawer();

    const lifetimeGroup = screen.getByRole('group', {
      name: 'Drawer lifetime trend granularity',
    });
    await user.click(within(lifetimeGroup).getByRole('button', { name: 'month' }));

    await waitFor(() => {
      expect(apiMocks.getComputeClusterLifetimeTrend).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ granularity: 'month' })
      );
    });

    // The cost trend keeps its own granularity.
    const costGroup = screen.getByRole('group', { name: 'Drawer cost trend granularity' });
    expect(within(costGroup).getByRole('button', { name: 'week' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(apiMocks.getComputeClusterCostTrend).not.toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ granularity: 'month' })
    );
  });

  it('renders the empty state, not an empty chart, when a trend has no point', async () => {
    apiMocks.getComputeClusterLifetimeTrend.mockResolvedValue({
      ...computeClusterLifetimeTrendFixture,
      items: [],
    });

    await openCostDrawer();

    expect(await screen.findByText('No lifetime data for this granularity')).toBeInTheDocument();
  });
});
