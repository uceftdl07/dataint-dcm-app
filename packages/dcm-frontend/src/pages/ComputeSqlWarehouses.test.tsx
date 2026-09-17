import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  computeWarehousesCostFixture,
  computeWarehousesOverviewFixture,
  computeWarehousesQueryPerformanceFixture,
  computeWarehousesSlowQueriesFixture,
  computeWarehouseDetailFixture,
  computeWarehouseTrendFixture,
} from '../test/fixtures/compute-warehouses';
import { renderWithProviders, screen, userEvent, waitFor, within } from '../test/render';
import ComputeSqlWarehouses from './ComputeSqlWarehouses';

vi.mock('../api/dcmApiClient', () => ({
  getComputeWarehousesOverview: vi.fn(),
  getComputeFilterOptions: vi.fn(),
  listComputeWarehousesCost: vi.fn(),
  listComputeWarehousesQueryPerformance: vi.fn(),
  listComputeWarehousesSlowQueries: vi.fn(),
  getComputeWarehouseDetail: vi.fn(),
  getComputeWarehouseCostTrend: vi.fn(),
  listDatabricksWorkspaces: vi.fn(),
}));

import {
  getComputeFilterOptions,
  getComputeWarehouseCostTrend,
  getComputeWarehouseDetail,
  getComputeWarehousesOverview,
  listComputeWarehousesCost,
  listComputeWarehousesQueryPerformance,
  listComputeWarehousesSlowQueries,
  listDatabricksWorkspaces,
} from '../api/dcmApiClient';

const apiMocks = {
  getComputeWarehousesOverview: vi.mocked(getComputeWarehousesOverview),
  getComputeFilterOptions: vi.mocked(getComputeFilterOptions),
  listComputeWarehousesCost: vi.mocked(listComputeWarehousesCost),
  listComputeWarehousesQueryPerformance: vi.mocked(listComputeWarehousesQueryPerformance),
  listComputeWarehousesSlowQueries: vi.mocked(listComputeWarehousesSlowQueries),
  getComputeWarehouseDetail: vi.mocked(getComputeWarehouseDetail),
  getComputeWarehouseCostTrend: vi.mocked(getComputeWarehouseCostTrend),
  listDatabricksWorkspaces: vi.mocked(listDatabricksWorkspaces),
};

/**
 * Bornes attendues, recalculées ici sans passer par l'implémentation : ces pages
 * n'ont plus de sélecteur de dates, leurs plages sont ancrées sur aujourd'hui.
 */
function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

/** La sonde `enabled` appelle le même endpoint avec `page_size: 1` — à ignorer. */
function lastSlowQueriesCall() {
  const calls = apiMocks.listComputeWarehousesSlowQueries.mock.calls
    .map((call) => call[0])
    .filter((params) => params?.page_size === 25);
  return calls[calls.length - 1];
}

describe('ComputeSqlWarehouses', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getComputeWarehousesOverview.mockResolvedValue(computeWarehousesOverviewFixture);
    apiMocks.listComputeWarehousesCost.mockResolvedValue(computeWarehousesCostFixture);
    apiMocks.listComputeWarehousesQueryPerformance.mockResolvedValue(
      computeWarehousesQueryPerformanceFixture
    );
    apiMocks.listComputeWarehousesSlowQueries.mockResolvedValue(
      computeWarehousesSlowQueriesFixture
    );
    apiMocks.getComputeWarehouseDetail.mockResolvedValue(computeWarehouseDetailFixture);
    apiMocks.getComputeWarehouseCostTrend.mockResolvedValue(computeWarehouseTrendFixture);
    apiMocks.getComputeFilterOptions.mockResolvedValue({
      view: 'warehouses-overview',
      column: 'size',
      kind: 'enum',
      label: 'Size',
      options: [
        { value: 'small', label: 'Small', count: 4 },
        { value: 'medium', label: 'Medium', count: 12 },
      ],
      truncated: false,
    });
    apiMocks.listDatabricksWorkspaces.mockResolvedValue({
      items: [{ workspace_id: 'ws-1', display_name: 'dbw-analytics-prod', source_lz_id: 'lz-1' }],
    });
  });

  it('renders 3 tabs when slow queries API is disabled', async () => {
    apiMocks.listComputeWarehousesSlowQueries.mockResolvedValue({
      ...computeWarehousesSlowQueriesFixture,
      enabled: false,
      items: [],
      total: 0,
    });

    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    expect(await screen.findByRole('tab', { name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Cost' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Query performance' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Slow queries' })).not.toBeInTheDocument();
  });

  it('renders 4 tabs when slow queries API is enabled', async () => {
    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    expect(await screen.findByRole('tab', { name: 'Slow queries' })).toBeInTheDocument();
  });

  it('pages, searches and sorts the Overview on the server', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    // The footer counts the whole scope (96), not the single row on the page.
    expect(await screen.findByText(/96/)).toBeInTheDocument();

    await waitFor(() => {
      expect(apiMocks.getComputeWarehousesOverview).toHaveBeenCalledWith(
        expect.objectContaining({ page: 1, page_size: 25, sort: 'cost', sort_direction: 'desc' })
      );
    });

    // A search must reach the endpoint: filtering the 25 rows on screen would leave
    // every warehouse past the 25th unreachable by name.
    await user.type(screen.getByLabelText('Search overview warehouses'), 'analytics');
    await waitFor(() => {
      expect(apiMocks.getComputeWarehousesOverview).toHaveBeenCalledWith(
        expect.objectContaining({ search: 'analytics', page: 1 })
      );
    });

    // Same for the size select, the failure chip and the column sort.
    await user.selectOptions(screen.getByLabelText('Filter by warehouse size'), 'medium');
    await waitFor(() => {
      expect(apiMocks.getComputeWarehousesOverview).toHaveBeenCalledWith(
        expect.objectContaining({ warehouse_size: 'medium' })
      );
    });

    await user.click(screen.getByRole('button', { name: 'With failures' }));
    await waitFor(() => {
      expect(apiMocks.getComputeWarehousesOverview).toHaveBeenCalledWith(
        expect.objectContaining({ min_failure_rate_pct: 1 })
      );
    });

    await user.click(screen.getByRole('button', { name: /^Latency p95/ }));
    await waitFor(() => {
      expect(apiMocks.getComputeWarehousesOverview).toHaveBeenCalledWith(
        expect.objectContaining({ sort: 'latency', sort_direction: 'desc' })
      );
    });
  });

  it('asks for page 1 again when a filter changes', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    await user.click(await screen.findByRole('button', { name: /Next/ }));
    await waitFor(() => {
      expect(apiMocks.getComputeWarehousesOverview).toHaveBeenCalledWith(
        expect.objectContaining({ page: 2 })
      );
    });

    // A narrower scope is another population: staying on page 2 could land past its end.
    await user.click(screen.getByRole('button', { name: 'With failures' }));
    await waitFor(() => {
      expect(apiMocks.getComputeWarehousesOverview).toHaveBeenCalledWith(
        expect.objectContaining({ min_failure_rate_pct: 1, page: 1 })
      );
    });
  });

  it('keeps the search box reachable when the server returns nothing', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    await screen.findByRole('table');
    apiMocks.getComputeWarehousesOverview.mockResolvedValue({
      ...computeWarehousesOverviewFixture,
      items: [],
      total: 0,
    });
    await user.type(screen.getByLabelText('Search overview warehouses'), 'zzz');

    // The page-level empty state would unmount the toolbar with the input in it.
    expect(await screen.findByText('No warehouses match these filters')).toBeInTheDocument();
    expect(screen.getByLabelText('Search overview warehouses')).toHaveValue('zzz');
  });

  it('shows an empty state when overview has zero items', async () => {
    apiMocks.getComputeWarehousesOverview.mockResolvedValue({
      ...computeWarehousesOverviewFixture,
      items: [],
      kpis: {
        total_cost_usd: 0,
        cost_delta_pct: null,
        active_warehouses: 0,
        query_count: 0,
        failed_count: 0,
        open_recommendations: 0,
      },
    });

    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    expect(await screen.findByText('No warehouses found')).toBeInTheDocument();
  });

  it('opens the drawer when a cost row is clicked', async () => {
    const user = userEvent.setup();

    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    await user.click(await screen.findByRole('tab', { name: 'Cost' }));
    const warehouseLabels = await screen.findAllByText('Analytics WH');
    expect(warehouseLabels.length).toBeGreaterThan(0);

    await user.click(warehouseLabels[warehouseLabels.length - 1]!);

    expect(
      await screen.findByRole('dialog', { name: 'SQL Warehouse details' })
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'week' })).toHaveAttribute('aria-pressed', 'true');

    await waitFor(() => {
      expect(apiMocks.getComputeWarehouseDetail).toHaveBeenCalled();
      expect(apiMocks.getComputeWarehouseCostTrend).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ granularity: 'week' })
      );
    });
  });

  it('calls query performance endpoint when failure filter is selected', async () => {
    const user = userEvent.setup();

    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    await user.click(await screen.findByRole('tab', { name: 'Query performance' }));
    await user.click(screen.getByRole('button', { name: 'With failures' }));

    await waitFor(() => {
      expect(apiMocks.listComputeWarehousesQueryPerformance).toHaveBeenCalledWith(
        expect.objectContaining({ min_failure_rate_pct: 1 })
      );
    });
  });

  it('offers exactly four static ranges and no free date entry', async () => {
    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

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
    // The window selects a pre-aggregated row: no free period entry composes one.
    expect(within(group).queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('sends the selected range as window_days on the three windowed endpoints', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    await waitFor(() => {
      expect(apiMocks.getComputeWarehousesOverview).toHaveBeenCalledWith(
        expect.objectContaining({ window_days: 1 })
      );
    });

    await user.click(await screen.findByRole('button', { name: 'Last 30d' }));

    await waitFor(() => {
      expect(apiMocks.getComputeWarehousesOverview).toHaveBeenCalledWith(
        expect.objectContaining({ window_days: 30 })
      );
    });

    // Slow queries keeps the daily grain: it reads a daily table and takes no window.
    expect(apiMocks.listComputeWarehousesSlowQueries.mock.calls[0]?.[0]).not.toHaveProperty(
      'window_days'
    );
  });

  it('gives Slow queries its own dates, no longer read from the header', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    await user.click(await screen.findByRole('tab', { name: 'Slow queries' }));

    // Seul onglet dont l'endpoint filtre vraiment sur des bornes : il porte des
    // dates, pas une fenêtre pré-agrégée — et les deux groupes ne coexistent pas.
    const group = await screen.findByRole('group', { name: 'Slow queries range' });
    expect(within(group).getAllByRole('button')).toHaveLength(3);
    expect(within(group).getByRole('button', { name: 'Last 30d' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(screen.queryByRole('group', { name: 'Rolling window' })).not.toBeInTheDocument();

    // 30 jours par défaut, finissant aujourd'hui : le comportement de l'ancien
    // sélecteur d'en-tête, sans dépendre de sa plage.
    await waitFor(() => {
      expect(lastSlowQueriesCall()).toMatchObject({
        period_start: isoDaysAgo(29),
        period_end: isoDaysAgo(0),
      });
    });

    await user.click(within(group).getByRole('button', { name: 'Last 7d' }));

    await waitFor(() => {
      expect(lastSlowQueriesCall()).toMatchObject({
        period_start: isoDaysAgo(6),
        period_end: isoDaysAgo(0),
        // La page revient à 1 : la page 3 d'une plage plus courte n'existe pas.
        page: 1,
      });
    });
  });

  it('stops sending the header range to the windowed endpoints', async () => {
    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    // Ces trois endpoints ne font que renvoyer les bornes reçues. La page en envoie
    // donc une plage large et fixe, calculée ici, et non les 30 jours par défaut de
    // l'en-tête : un défaut court masquerait le dernier instantané en retard.
    await waitFor(() => {
      expect(apiMocks.getComputeWarehousesOverview).toHaveBeenCalledWith(
        expect.objectContaining({ period_start: isoDaysAgo(364), period_end: isoDaysAgo(0) })
      );
    });
  });

  it('keeps the selected range when switching tabs', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    await user.click(await screen.findByRole('button', { name: 'Last 90d' }));
    await user.click(screen.getByRole('tab', { name: 'Cost' }));

    expect(screen.getByRole('button', { name: 'Last 90d' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await waitFor(() => {
      expect(apiMocks.listComputeWarehousesCost).toHaveBeenCalledWith(
        expect.objectContaining({ window_days: 90 })
      );
    });
  });

  it('displays the covered period read from the API window, not from the chip', async () => {
    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    // `Daily` is selected, the fixture reports a 7-day window: the label follows the
    // data, so a late pipeline run stays visible instead of being masked by a range
    // computed from `today`.
    expect(await screen.findByText('2026-08-07 → 2026-08-13')).toBeInTheDocument();
  });

  it('says so plainly when the window carries no bounds', async () => {
    apiMocks.getComputeWarehousesOverview.mockResolvedValue({
      ...computeWarehousesOverviewFixture,
      window: { window_days: 90, from_date: null, to_date: null },
    });

    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    // No `Date` is built from a null bound, so no `Invalid Date` can surface.
    expect(await screen.findByText('no data over this range')).toBeInTheDocument();
    expect(screen.queryByText(/Invalid Date/)).not.toBeInTheDocument();
  });

  it('reads Workspace then Warehouse on the overview, workspace_name first', async () => {
    apiMocks.getComputeWarehousesOverview.mockResolvedValue({
      ...computeWarehousesOverviewFixture,
      items: [
        { ...computeWarehousesOverviewFixture.items[0]!, workspace_name: 'gold-joined-name' },
      ],
    });

    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    const table = await screen.findByRole('table');
    const headers = within(table).getAllByRole('columnheader');
    // A warehouse name is only unique inside its workspace: container, then object.
    expect(headers[0]).toHaveTextContent('Workspace');
    expect(headers[1]).toHaveTextContent('Warehouse');
    // The name joined in gold wins over the id-to-label resolver.
    expect(within(table).getByText('gold-joined-name')).toBeInTheDocument();
  });

  it('shows the compute type next to the size, and a dash when gold cannot say', async () => {
    const base = computeWarehousesOverviewFixture.items[0]!;
    apiMocks.getComputeWarehousesOverview.mockResolvedValue({
      ...computeWarehousesOverviewFixture,
      items: [
        { ...base, warehouse_id: 'wh-pro', warehouse_type: 'PRO', is_serverless: false },
        {
          ...base,
          warehouse_id: 'wh-serverless',
          warehouse_type: 'SERVERLESS',
          is_serverless: true,
        },
        { ...base, warehouse_id: 'wh-classic', warehouse_type: 'CLASSIC', is_serverless: false },
        // Billed over the window but absent from the utilization snapshot: the type is
        // genuinely unknown, and a `CLASSIC` default would state something gold does not.
        { ...base, warehouse_id: 'wh-unknown', warehouse_type: null, is_serverless: null },
      ],
    });

    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    const table = await screen.findByRole('table');
    const headers = within(table).getAllByRole('columnheader');
    // Size then Type: how big, then what kind — the two halves of the configuration.
    expect(headers[2]).toHaveTextContent('Size');
    expect(headers[3]).toHaveTextContent('Type');

    // Three values and not a boolean: "not serverless" is not something a user can act on.
    expect(within(table).getByText('PRO')).toBeInTheDocument();
    expect(within(table).getByText('SERVERLESS')).toBeInTheDocument();
    expect(within(table).getByText('CLASSIC')).toBeInTheDocument();

    const typeCells = within(table)
      .getAllByRole('row')
      .slice(1)
      .map((row) => within(row).getAllByRole('cell')[3]);
    expect(typeCells.map((cell) => cell?.textContent)).toEqual([
      'PRO',
      'SERVERLESS',
      'CLASSIC',
      '—',
    ]);
  });

  it('names the warehouse on the Query performance tab', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    await user.click(await screen.findByRole('tab', { name: 'Query performance' }));

    // Before the gold column existed this cell could only repeat the id.
    const table = await screen.findByRole('table');
    expect(await within(table).findByText('Analytics WH')).toBeInTheDocument();
  });

  it('keeps the size toolbar and the Size column combo on one value', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    // La combo de colonne écrit dans le même état que le sélecteur : le serveur
    // refuse un `warehouse_size` qui contredit son `column_filter` (422), et deux
    // contrôles indépendants pour un prédicat finissent toujours par diverger.
    await user.click(await screen.findByTestId('column-filter-Size'));
    // Le sélecteur de la barre d'outils expose lui aussi des `option` « Medium » :
    // on cible celle du panneau, sinon la requête est ambiguë.
    const panel = await screen.findByTestId('column-filter-panel-Size');
    await user.click(within(panel).getByRole('option', { name: /Medium/ }));

    await waitFor(() => {
      expect(apiMocks.getComputeWarehousesOverview).toHaveBeenCalledWith(
        expect.objectContaining({ warehouse_size: 'medium', column_filter: ['size:medium'] })
      );
    });
    expect(screen.getByLabelText('Filter by warehouse size')).toHaveValue('medium');

    // Et dans l'autre sens : le sélecteur écrit dans le même état, donc l'entonnoir
    // de la colonne suit, et les deux paramètres repartent toujours d'accord.
    await user.selectOptions(screen.getByLabelText('Filter by warehouse size'), 'large');
    await waitFor(() => {
      expect(apiMocks.getComputeWarehousesOverview).toHaveBeenLastCalledWith(
        expect.objectContaining({ warehouse_size: 'large', column_filter: ['size:large'] })
      );
    });
    expect(screen.getByTestId('column-filter-Size')).toHaveAttribute('data-active', 'true');

    // Remettre « All sizes » désarme l'entonnoir : un seul état, donc pas de filtre
    // fantôme sur la colonne. Aucune requête à attendre ici — React Query a déjà
    // le résultat sans filtre en cache.
    await user.selectOptions(screen.getByLabelText('Filter by warehouse size'), '');
    await waitFor(() => {
      expect(screen.getByTestId('column-filter-Size')).toHaveAttribute('data-active', 'false');
    });
  });

  it('renders a dash, not $0, when a warehouse has no previous window', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeSqlWarehouses />, { route: '/databricks/sql-warehouse' });

    await user.click(await screen.findByRole('tab', { name: 'Cost' }));
    const table = await screen.findByRole('table');
    const newcomerRow = (await within(table).findByText('Newcomer WH')).closest('tr')!;

    // Nothing to compare is not a 0 % variation over a $0 predecessor.
    expect(within(newcomerRow).getByText('—')).toBeInTheDocument();
    expect(within(newcomerRow).queryByText('$0')).not.toBeInTheDocument();
  });
});
