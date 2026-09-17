import {
  ucWriteChartsFixture,
  ucEntityDetailFixture,
  ucCostChangesFixture,
} from '../test/fixtures/uc-usage-exploration';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ucUsageAttentionFixture,
  ucUsageConsumersFixture,
  ucUsageCostByTableFixture,
  ucUsageDeletedLifecycle,
  ucUsageFilterOptionsFixture,
  ucUsageFinopsKpisFixture,
  ucUsageOverviewFixture,
  ucUsageTablesFixture,
  ucUsageTopConsumersFixture,
  ucUsageTrendsFixture,
} from '../test/fixtures/uc-usage';
import { fireEvent, renderWithProviders, screen, userEvent, waitFor, within } from '../test/render';
import UsageTablesUc from './UsageTablesUc';
import {
  ucTableChartsFixture,
  ucConsumerChartsFixture,
  ucFinopsChartsFixture,
} from '../test/fixtures/uc-usage-charts';

vi.mock('../api/dcmApiClient', () => ({
  getUcUsageOverview: vi.fn(),
  getUcUsageWriteCharts: vi.fn(),
  getUcUsageCostChanges: vi.fn(),
  getUcUsageEntityDetail: vi.fn(),
  getUcUsageTableCharts: vi.fn(),
  getUcUsageConsumerCharts: vi.fn(),
  getUcUsageFinopsCharts: vi.fn(),
  getUcUsageFinopsTrends: vi.fn(),
  getUcUsageFilterOptions: vi.fn(),
  getUcUsageAttention: vi.fn(),
  listUcUsageTables: vi.fn(),
  listUcUsageConsumers: vi.fn(),
  getUcUsageFinopsKpis: vi.fn(),
  listUcUsageCostByTable: vi.fn(),
  getUcUsageTableTopConsumers: vi.fn(),
  getUcUsageGovernanceKpis: vi.fn(),
  listUcUsageGovernanceRegistry: vi.fn(),
  listUcUsageRecommendations: vi.fn(),
}));

import {
  getUcUsageAttention,
  getUcUsageFilterOptions,
  getUcUsageFinopsKpis,
  getUcUsageFinopsTrends,
  getUcUsageOverview,
  getUcUsageWriteCharts,
  getUcUsageCostChanges,
  getUcUsageEntityDetail,
  getUcUsageTableCharts,
  getUcUsageConsumerCharts,
  getUcUsageFinopsCharts,
  getUcUsageTableTopConsumers,
  listUcUsageConsumers,
  listUcUsageCostByTable,
  listUcUsageTables,
} from '../api/dcmApiClient';

const api = {
  overview: vi.mocked(getUcUsageOverview),
  writes: vi.mocked(getUcUsageWriteCharts),
  costChanges: vi.mocked(getUcUsageCostChanges),
  details: vi.mocked(getUcUsageEntityDetail),
  tableCharts: vi.mocked(getUcUsageTableCharts),
  consumerCharts: vi.mocked(getUcUsageConsumerCharts),
  finopsCharts: vi.mocked(getUcUsageFinopsCharts),
  trends: vi.mocked(getUcUsageFinopsTrends),
  attention: vi.mocked(getUcUsageAttention),
  filterOptions: vi.mocked(getUcUsageFilterOptions),
  tables: vi.mocked(listUcUsageTables),
  consumers: vi.mocked(listUcUsageConsumers),
  finopsKpis: vi.mocked(getUcUsageFinopsKpis),
  costByTable: vi.mocked(listUcUsageCostByTable),
  topConsumers: vi.mocked(getUcUsageTableTopConsumers),
};

async function applyPeriod() {
  // Chaque analyse de test choisit explicitement un périmètre, comme l’utilisateur.
  if (screen.getByRole('button', { name: 'Apply' }).hasAttribute('disabled')) {
    await selectCatalog('main');
  }
  await userEvent.click(screen.getByRole('button', { name: 'Apply' }));
}

/** Le catalogue est un menu alimenté par le registre, plus une saisie libre. */
async function selectCatalog(value: string) {
  await userEvent.click(screen.getByRole('button', { name: 'Catalog' }));
  await userEvent.click(await screen.findByRole('option', { name: value }));
}

describe('UsageTablesUc', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.overview.mockResolvedValue(ucUsageOverviewFixture);
    api.writes.mockResolvedValue(ucWriteChartsFixture);
    api.costChanges.mockResolvedValue(ucCostChangesFixture);
    api.details.mockResolvedValue(ucEntityDetailFixture);
    api.tableCharts.mockResolvedValue(ucTableChartsFixture);
    api.consumerCharts.mockResolvedValue(ucConsumerChartsFixture);
    api.finopsCharts.mockResolvedValue(ucFinopsChartsFixture);
    api.trends.mockResolvedValue(ucUsageTrendsFixture);
    api.attention.mockResolvedValue(ucUsageAttentionFixture);
    api.filterOptions.mockResolvedValue(ucUsageFilterOptionsFixture);
    api.tables.mockResolvedValue(ucUsageTablesFixture);
    api.consumers.mockResolvedValue(ucUsageConsumersFixture);
    api.finopsKpis.mockResolvedValue(ucUsageFinopsKpisFixture);
    api.costByTable.mockResolvedValue(ucUsageCostByTableFixture);
    api.topConsumers.mockResolvedValue(ucUsageTopConsumersFixture);
  });

  it('accueille l’utilisateur sans analyse globale ni chiffres avant sa sélection', async () => {
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });

    await waitFor(() => expect(api.filterOptions).toHaveBeenCalled());
    for (const [name, endpoint] of Object.entries(api)) {
      if (name !== 'filterOptions') expect(endpoint).not.toHaveBeenCalled();
    }
    expect(
      screen.getByRole('region', { name: 'Which tables would you like to analyse?' })
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Catalog' })).toHaveTextContent('Choose a catalog');
    expect(screen.queryByRole('region', { name: 'Overview' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Points to review' })).not.toBeInTheDocument();
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.queryByText('No tables in this scope')).not.toBeInTheDocument();
  });

  it('guide vers le sélecteur et attend Appliquer même après un choix de catalogue', async () => {
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });
    await userEvent.click(screen.getByRole('button', { name: 'Choose my scope' }));
    expect(screen.getByRole('button', { name: 'Catalog' })).toHaveFocus();
    expect(screen.getByRole('button', { name: 'Catalog' })).toHaveAttribute(
      'aria-expanded',
      'true'
    );
    await userEvent.click(await screen.findByRole('option', { name: 'main' }));
    expect(
      screen.getByText('Your selection is ready. Click Apply to display the analysis.')
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apply' })).toBeEnabled();
    expect(api.overview).not.toHaveBeenCalled();
    expect(api.trends).not.toHaveBeenCalled();
    expect(api.attention).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Apply' }));

    await waitFor(() => expect(api.overview).toHaveBeenCalled());
    await waitFor(() => expect(api.tables).toHaveBeenCalled());

    const params = api.overview.mock.calls[0][0];
    expect(params.catalog).toBe('main');
    expect(params.period_start).toBeTruthy();
    expect(params.period_end).toBeTruthy();
    expect(
      screen.queryByRole('region', { name: 'Which tables would you like to analyse?' })
    ).not.toBeInTheDocument();
    expect(screen.getAllByRole('tab')).toHaveLength(3);
  });

  it('refuse une soumission sans périmètre, y compris depuis le formulaire', async () => {
    renderWithProviders(<UsageTablesUc />);
    await waitFor(() => expect(api.filterOptions).toHaveBeenCalled());
    const apply = screen.getByRole('button', { name: 'Apply' });
    fireEvent.submit(apply.closest('form')!);
    expect(api.overview).not.toHaveBeenCalled();
    expect(api.trends).not.toHaveBeenCalled();
    expect(api.attention).not.toHaveBeenCalled();
    expect(
      screen.getByRole('region', { name: 'Which tables would you like to analyse?' })
    ).toBeInTheDocument();
  });

  it('autorise une sélection directe de tables sans imposer catalogue et schéma', async () => {
    renderWithProviders(<UsageTablesUc />);
    await userEvent.click(screen.getByRole('button', { name: 'Tables' }));
    await userEvent.click(await screen.findByRole('checkbox', { name: /main.sales.orders/ }));
    expect(api.tables).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Apply' }));
    await waitFor(() => expect(api.tables).toHaveBeenCalled());
    expect(api.tables.mock.calls[0][0]).toMatchObject({
      catalog: undefined,
      schema: undefined,
      tables: ['main.sales.orders'],
    });
  });

  it('signale une erreur des sélecteurs et permet de les recharger sans lancer l’analyse', async () => {
    api.filterOptions.mockRejectedValueOnce(new Error('Options unavailable'));
    renderWithProviders(<UsageTablesUc />);
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Unable to load catalogs, schemas and tables.'
    );
    await userEvent.click(screen.getByRole('button', { name: 'Retry filters' }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    await selectCatalog('main');
    expect(api.overview).not.toHaveBeenCalled();
    expect(api.filterOptions.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('ne transforme pas l’effacement des filtres en analyse globale implicite', async () => {
    renderWithProviders(<UsageTablesUc />);
    await applyPeriod();
    await waitFor(() => expect(api.overview).toHaveBeenCalledTimes(1));
    await selectCatalog('All catalogs');
    const apply = screen.getByRole('button', { name: 'Apply' });
    expect(apply).toBeDisabled();
    fireEvent.submit(apply.closest('form')!);
    expect(api.overview).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('status')).toHaveTextContent(
      'results still reflect the last applied scope'
    );
  });

  it('libelle les horizons sur sept jours et jamais sur quatorze', async () => {
    const { container } = renderWithProviders(<UsageTablesUc />, {
      route: '/databricks/usage-tables',
    });

    await applyPeriod();
    await waitFor(() => expect(api.overview).toHaveBeenCalled());

    expect(screen.getAllByText(/\+7d/).length).toBeGreaterThan(0);
    // Horizon composé, jamais écrit en clair : le grep de SC-004 doit rester vide.
    expect(container.textContent).not.toContain(`+${14}days`);
  });

  it('removes attention from the Usage page and stops its API calls', async () => {
    renderWithProviders(<UsageTablesUc />);
    await applyPeriod();
    await waitFor(() => expect(api.tables).toHaveBeenCalled());
    expect(api.attention).not.toHaveBeenCalled();
    expect(screen.queryByRole('region', { name: 'Points to review' })).not.toBeInTheDocument();
  });

  it('shows observed write volumes from the applied scope', async () => {
    renderWithProviders(<UsageTablesUc />);
    await applyPeriod();
    expect(await screen.findByRole('region', { name: 'Write activity' })).toBeInTheDocument();
    expect(api.writes.mock.lastCall?.[0]).toEqual(api.tableCharts.mock.lastCall?.[0]);
    expect(screen.getByRole('img', { name: 'Daily read and write volumes' })).toBeInTheDocument();
  });

  it('charge réalisé et prévision uniquement après application du périmètre', async () => {
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });

    await applyPeriod();
    await waitFor(() => expect(api.trends).toHaveBeenCalled());
    // Trois tendances en vue d'ensemble ; `data_read_bytes` reste FinOps (FR-001).
    expect(api.trends.mock.calls[0][0]?.metrics).toEqual([
      'request_count',
      'estimated_cost_usd',
      'distinct_consumers',
    ]);
    expect(api.trends.mock.calls[0][0]?.catalog).toBe('main');
    expect(api.trends.mock.calls[0][0]?.period_start).toBeTruthy();
    // La valeur mise en avant est le dernier réalisé, la prévision reste en second.
    expect((await screen.findAllByText(/620/)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/forecast/).length).toBeGreaterThan(0);
  });

  it('rend un tiret, jamais $0, pour un forecast absent', async () => {
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });

    await applyPeriod();
    await userEvent.click(screen.getByRole('tab', { name: 'FinOps' }));

    await waitFor(() => expect(api.costByTable).toHaveBeenCalled());
    expect(
      await within(await screen.findByRole('table', { name: '' })).findByText(
        'main.finance.invoices'
      )
    ).toBeInTheDocument();

    const forecastCells = screen.getAllByText('—');
    expect(forecastCells.length).toBeGreaterThan(0);
  });

  it('filters and sorts Cost by table server-side, like the two usage tables', async () => {
    // Ce tableau n'avait ni en-tête triable ni filtre de colonne : il était le seul
    // des trois à imposer « coût décroissant », sans moyen de chercher dans le reste.
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });
    await applyPeriod();
    await userEvent.click(screen.getByRole('tab', { name: 'FinOps' }));
    await waitFor(() => expect(api.costByTable).toHaveBeenCalled());

    await userEvent.click(await screen.findByRole('button', { name: 'Filter Forecast +7d' }));
    const dialog = screen.getByRole('dialog', { name: 'Filter Forecast +7d' });
    await userEvent.type(within(dialog).getByLabelText('Value (USD)'), '10');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Apply filter' }));
    await waitFor(() =>
      expect(api.costByTable.mock.lastCall?.[0].column_filter).toEqual([
        'forecast_cost_usd_7d:gte:10',
      ])
    );

    // Une colonne dérivée se trie comme les autres : elle est calculée en SQL.
    await userEvent.click(screen.getByRole('button', { name: 'Cost / access' }));
    await userEvent.click(screen.getByRole('button', { name: 'Cost / access' }));
    await waitFor(() =>
      expect(api.costByTable.mock.lastCall?.[0]).toMatchObject({
        sort: 'cost_per_request',
        direction: 'asc',
        page: 1,
      })
    );
  });

  it('applies the shared search box to Cost by table too', async () => {
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });
    await applyPeriod();
    await userEvent.click(screen.getByRole('tab', { name: 'FinOps' }));
    await waitFor(() => expect(api.costByTable).toHaveBeenCalled());
    expect(api.costByTable.mock.lastCall?.[0].search).toBeUndefined();

    // La boîte de recherche est au niveau de la page : la laisser sans effet ici
    // faisait croire à un résultat filtré alors que le tableau ignorait la saisie.
    await userEvent.type(screen.getByLabelText('Search by name'), 'invoices');
    await userEvent.click(screen.getByRole('button', { name: 'Apply' }));
    await waitFor(() => expect(api.costByTable.mock.lastCall?.[0].search).toBe('invoices'));
  });

  it('affiche le nom qualifié complet plutôt que le seul nom de table', async () => {
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });

    await applyPeriod();
    await waitFor(() => expect(api.tables).toHaveBeenCalled());

    const table = await screen.findByRole('table', { name: '' });
    expect(within(table).getAllByText('main.sales.orders').length).toBeGreaterThan(0);
    expect(within(table).queryByText('orders')).not.toBeInTheDocument();
  });

  it('opens table evolution in a drawer and restores row focus on Escape', async () => {
    renderWithProviders(<UsageTablesUc />);
    await applyPeriod();
    const table = await screen.findByRole('table', { name: '' });
    const row = within(table).getByText('main.sales.orders').closest('tr')!;
    await userEvent.click(row);
    const drawer = await screen.findByRole('dialog', { name: 'main.sales.orders' });
    expect(
      await within(drawer).findByRole('img', { name: 'Entity daily read activity' })
    ).toBeInTheDocument();
    expect(api.details.mock.lastCall?.[0]).toMatchObject({
      ...api.tableCharts.mock.lastCall?.[0],
      entity_kind: 'table',
      entity_id: 'main.sales.orders',
    });
    expect(api.topConsumers).not.toHaveBeenCalled();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(row).toHaveFocus();
  });

  it('filters all table rows server-side and reverses the sort direction', async () => {
    renderWithProviders(<UsageTablesUc />);
    await applyPeriod();
    await userEvent.click(await screen.findByRole('button', { name: 'Filter Bytes written' }));
    const dialog = screen.getByRole('dialog', { name: 'Filter Bytes written' });
    await userEvent.type(within(dialog).getByLabelText('Value (GB)'), '2');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Apply filter' }));
    await waitFor(() =>
      expect(api.tables.mock.lastCall?.[0].column_filter).toEqual([
        'data_written_bytes:gte:2147483648',
      ])
    );
    await userEvent.click(screen.getByRole('button', { name: 'Bytes written' }));
    await userEvent.click(screen.getByRole('button', { name: 'Bytes written' }));
    await waitFor(() =>
      expect(api.tables.mock.lastCall?.[0]).toMatchObject({
        sort: 'writes',
        direction: 'asc',
        page: 1,
      })
    );
    expect(api.tableCharts).toHaveBeenCalledTimes(1);
  });

  it('opens consumer evolution using its exact identifier and keeps the table scope', async () => {
    renderWithProviders(<UsageTablesUc />);
    await applyPeriod();
    await userEvent.click(screen.getByRole('tab', { name: 'By consumer' }));
    const table = await screen.findByRole('table', { name: '' });
    const entity = ucUsageConsumersFixture.items[0];
    const row = within(table)
      .getByText(entity.consumer_name || entity.consumer_id)
      .closest('tr')!;
    row.focus();
    await userEvent.keyboard('{Enter}');
    await waitFor(() =>
      expect(api.details.mock.lastCall?.[0]).toMatchObject({
        catalog: 'main',
        entity_kind: 'consumer',
        entity_id: entity.consumer_id,
      })
    );
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('loads cost changes only in FinOps and shows bounded attribution coverage', async () => {
    renderWithProviders(<UsageTablesUc />);
    await applyPeriod();
    expect(api.costChanges).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('tab', { name: 'FinOps' }));
    expect(await screen.findByRole('region', { name: 'Largest cost changes' })).toBeInTheDocument();
    expect(api.costChanges.mock.lastCall?.[0]).toEqual(api.finopsCharts.mock.lastCall?.[0]);
    const chart = screen.getByRole('img', { name: 'Daily cost attribution coverage' });
    expect(within(chart).getByText('100%')).toBeInTheDocument();
  });

  it('trie les tables par le critère de la colonne cliquée', async () => {
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });

    await applyPeriod();
    await waitFor(() => expect(api.tables).toHaveBeenCalled());

    await userEvent.click(screen.getByRole('button', { name: 'P95 latency' }));

    await waitFor(() =>
      expect(api.tables.mock.calls.some((call) => call[0].sort === 'latency')).toBe(true)
    );
  });

  it('ne réinitialise pas les filtres communs au changement de vue', async () => {
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });

    await selectCatalog('main');
    await applyPeriod();
    await waitFor(() => expect(api.tables).toHaveBeenCalled());

    await userEvent.click(screen.getByRole('tab', { name: 'By consumer' }));

    await waitFor(() => expect(api.consumers).toHaveBeenCalled());
    expect(api.consumers.mock.calls[0][0].catalog).toBe('main');
    expect(screen.getByRole('button', { name: 'Catalog' })).toHaveTextContent('main');
  });

  it('affiche le tooltip de coût mentionnant la méthode d’attribution', async () => {
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });

    await applyPeriod();
    await waitFor(() => expect(api.tables).toHaveBeenCalled());

    const costCell = await screen.findByTitle(
      'cost_attribution_method: equal_parts_fallback · cost_basis: warehouse_prorata'
    );
    expect(costCell).toBeInTheDocument();
  });

  it('n’expose aucun champ renommé du mockup', async () => {
    const { container } = renderWithProviders(<UsageTablesUc />, {
      route: '/databricks/usage-tables',
    });

    await applyPeriod();
    await waitFor(() => expect(api.tables).toHaveBeenCalled());

    // Les colonnes `table_catalog`/`table_schema` du mockup n'existent pas (FR-008) ;
    // `gold_dbx_usage_table_catalog` est en revanche le nom réel d'une table source,
    // cité par les footnotes de provenance.
    expect(container.textContent).not.toMatch(/(?<!gold_dbx_usage_)table_catalog/);
    expect(container.textContent).not.toMatch(/(?<!gold_dbx_usage_)table_schema/);
  });

  it('offre un sélecteur de type de consommateur sans option GENIE', async () => {
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });

    await applyPeriod();
    await userEvent.click(screen.getByRole('tab', { name: 'By consumer' }));
    await waitFor(() => expect(api.consumers).toHaveBeenCalled());

    const select = screen.getByLabelText('Consumer type');
    const options = within(select)
      .getAllByRole('option')
      .map((option) => option.getAttribute('value'));

    expect(options).not.toContain('GENIE');
    expect(options).toContain('SERVICE_PRINCIPAL');

    await userEvent.selectOptions(select, 'JOB');
    await waitFor(() =>
      expect(api.consumers.mock.calls.some((call) => call[0].consumer_type === 'JOB')).toBe(true)
    );
  });

  it('rend les quatre états de la vue Par table sans planter', async () => {
    api.tables.mockRejectedValueOnce(new Error('boom'));
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });

    // 1. accueil unique avant de choisir le périmètre.
    expect(
      screen.getByRole('region', { name: 'Which tables would you like to analyse?' })
    ).toBeInTheDocument();

    await applyPeriod();

    // 2. chargement, puis 3. erreur — l'état vide générique ne doit pas la masquer
    expect(await screen.findByText('Unable to load tables')).toBeInTheDocument();

    // 4. vide — nouveau périmètre, donc nouvelle clé de cache : sans quoi
    // React Query resservirait l'erreur mémorisée pour les mêmes paramètres.
    api.tables.mockResolvedValue({ ...ucUsageTablesFixture, items: [], total: 0 });
    await selectCatalog('lake');
    await applyPeriod();
    expect(await screen.findByText('No tables in this scope')).toBeInTheDocument();
  });

  it('applique le même catalogue, schéma, table et période aux trois groupes de graphiques', async () => {
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });
    await selectCatalog('main');
    await userEvent.click(screen.getByRole('button', { name: 'Schema' }));
    await userEvent.click(await screen.findByRole('option', { name: 'sales' }));
    await userEvent.click(screen.getByRole('button', { name: 'Tables' }));
    await userEvent.click(await screen.findByRole('checkbox', { name: /main.sales.orders/ }));
    expect(api.tableCharts).not.toHaveBeenCalled();
    await applyPeriod();
    await waitFor(() => expect(api.tableCharts).toHaveBeenCalledTimes(1));
    const applied = api.tableCharts.mock.calls[0][0];
    expect(applied).toMatchObject({
      catalog: 'main',
      schema: 'sales',
      tables: ['main.sales.orders'],
    });
    expect(applied.period_start).toBeTruthy();
    expect(applied.period_end).toBeTruthy();
    expect(await screen.findByRole('region', { name: 'Usage regularity' })).toBeInTheDocument();

    // A draft change does not alter the figures, even when switching tabs.
    await selectCatalog('lake');
    expect(api.tableCharts).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole('tab', { name: 'By consumer' }));
    await waitFor(() => expect(api.consumerCharts).toHaveBeenCalledTimes(1));
    expect(api.consumerCharts.mock.calls[0][0]).toEqual(applied);
    expect(
      await screen.findByRole('region', { name: 'Daily active consumers' })
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'FinOps' }));
    await waitFor(() => expect(api.finopsCharts).toHaveBeenCalledTimes(1));
    expect(api.finopsCharts.mock.calls[0][0]).toEqual(applied);
    expect(
      await screen.findByRole('region', { name: 'Cost per 1,000 costed accesses' })
    ).toBeInTheDocument();

    await applyPeriod();
    await waitFor(() => expect(api.finopsCharts).toHaveBeenCalledTimes(2));
    expect(api.finopsCharts.mock.calls[1][0]).toMatchObject({
      catalog: 'lake',
      schema: undefined,
      tables: undefined,
    });
  });

  it('garde les agrégats des graphiques indépendants du tri et de la recherche du tableau', async () => {
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });
    await applyPeriod();
    await waitFor(() => expect(api.tableCharts).toHaveBeenCalledTimes(1));
    await userEvent.click(screen.getByRole('button', { name: 'P95 latency' }));
    await waitFor(() =>
      expect(api.tables.mock.calls.some((call) => call[0].sort === 'latency')).toBe(true)
    );
    await userEvent.type(screen.getByRole('textbox', { name: 'Search by name' }), 'orders');
    await applyPeriod();
    await waitFor(() =>
      expect(api.tables.mock.calls.some((call) => call[0].search === 'orders')).toBe(true)
    );
    expect(api.tableCharts).toHaveBeenCalledTimes(1);
    expect(api.tableCharts.mock.calls[0][0]).not.toHaveProperty('page');
    expect(api.tableCharts.mock.calls[0][0]).not.toHaveProperty('search');
    expect(api.tableCharts.mock.calls[0][0]).not.toHaveProperty('sort');
  });

  it('retire les graphiques du périmètre précédent pendant le chargement du nouveau', async () => {
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });
    await applyPeriod();
    expect(await screen.findByRole('region', { name: 'Usage regularity' })).toBeInTheDocument();
    let resolve!: (data: typeof ucTableChartsFixture) => void;
    api.tableCharts.mockReturnValueOnce(
      new Promise((done) => {
        resolve = done;
      })
    );
    await selectCatalog('lake');
    await applyPeriod();
    expect(await screen.findByRole('status', { name: 'Loading charts' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Usage regularity' })).not.toBeInTheDocument();
    resolve(ucTableChartsFixture);
    expect(await screen.findByRole('region', { name: 'Usage regularity' })).toBeInTheDocument();
  });

  it('n’applique la case « Include deleted tables » qu’au clic sur Appliquer', async () => {
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });
    await applyPeriod();
    await waitFor(() => expect(api.tables).toHaveBeenCalled());
    // Périmètre sans la case : la requête est celle d'avant la spec 027.
    expect(api.tables.mock.lastCall?.[0]).not.toHaveProperty('include_deleted', true);
    const callsBeforeChecking = api.tables.mock.calls.length;

    await userEvent.click(screen.getByRole('checkbox', { name: 'Include deleted tables' }));
    expect(api.tables.mock.calls.length).toBe(callsBeforeChecking);

    await userEvent.click(screen.getByRole('button', { name: 'Apply' }));
    await waitFor(() => expect(api.tables.mock.lastCall?.[0].include_deleted).toBe(true));
    expect(api.overview.mock.lastCall?.[0].include_deleted).toBe(true);
    expect(api.tableCharts.mock.lastCall?.[0].include_deleted).toBe(true);
    expect(api.trends.mock.lastCall?.[0]?.include_deleted).toBe(true);
  });

  it('ne fait pas partir le drapeau vers les deux vues de grain consommateur', async () => {
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });
    await applyPeriod();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Include deleted tables' }));
    await userEvent.click(screen.getByRole('button', { name: 'Apply' }));
    await userEvent.click(screen.getByRole('tab', { name: 'By consumer' }));

    // Ces deux endpoints n'ont pas de clé table à filtrer : le contrat les exempte,
    // donc le drapeau ne doit ni partir ni entrer dans leur clé de cache.
    await waitFor(() => expect(api.consumers).toHaveBeenCalled());
    expect(api.consumers.mock.lastCall?.[0]).not.toHaveProperty('include_deleted');
    expect(api.consumerCharts.mock.lastCall?.[0]).not.toHaveProperty('include_deleted');
  });

  it('marque les tables supprimées et leur date dans les tableaux de grain table', async () => {
    api.tables.mockResolvedValue({
      ...ucUsageTablesFixture,
      items: [
        { ...ucUsageTablesFixture.items[0], ...ucUsageDeletedLifecycle },
        ucUsageTablesFixture.items[1],
      ],
    });
    api.costByTable.mockResolvedValue({
      ...ucUsageCostByTableFixture,
      items: [{ ...ucUsageCostByTableFixture.items[0], ...ucUsageDeletedLifecycle }],
    });
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });
    await applyPeriod();

    const table = await screen.findByRole('table', { name: '' });
    // Sans la date, une ligne supprimée se lirait comme une ligne vide.
    expect(await within(table).findByText('Deleted 2026-09-05')).toBeInTheDocument();
    expect(
      within(table).getByTitle('Deleted from Unity Catalog on 2026-09-05')
    ).toBeInTheDocument();
    expect(within(table).getAllByText('Deleted 2026-09-05')).toHaveLength(1);

    await userEvent.click(screen.getByRole('tab', { name: 'FinOps' }));
    await waitFor(() => expect(api.costByTable).toHaveBeenCalled());
    expect((await screen.findAllByText('Deleted 2026-09-05')).length).toBeGreaterThan(0);
  });

  it('rappelle la suppression dans le tiroir d’historique sans changer son titre', async () => {
    api.tables.mockResolvedValue({
      ...ucUsageTablesFixture,
      items: [{ ...ucUsageTablesFixture.items[0], ...ucUsageDeletedLifecycle }],
    });
    api.details.mockResolvedValue({ ...ucEntityDetailFixture, ...ucUsageDeletedLifecycle });
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });
    await applyPeriod();

    const table = await screen.findByRole('table', { name: '' });
    await userEvent.click(within(table).getByText('main.sales.orders').closest('tr')!);

    // Le titre reste le nom de la table : c'est lui qui nomme la boîte de dialogue.
    const drawer = await screen.findByRole('dialog', { name: 'main.sales.orders' });
    expect(await within(drawer).findByText('Deleted 2026-09-05')).toBeInTheDocument();
  });

  it('propose les tables supprimées au sélecteur dès que la case est cochée', async () => {
    api.filterOptions.mockResolvedValue({
      ...ucUsageFilterOptionsFixture,
      tables: [
        { ...ucUsageFilterOptionsFixture.tables[0], ...ucUsageDeletedLifecycle },
        ucUsageFilterOptionsFixture.tables[1],
      ],
    });
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });
    await waitFor(() => expect(api.filterOptions).toHaveBeenCalled());
    expect(api.filterOptions.mock.lastCall?.[0]).not.toHaveProperty('include_deleted', true);

    // Le sélecteur, lui, obéit à la case sans attendre Appliquer : sinon on ne
    // pourrait jamais cocher la table supprimée qu'on veut analyser.
    await userEvent.click(screen.getByRole('checkbox', { name: 'Include deleted tables' }));
    await waitFor(() => expect(api.filterOptions.mock.lastCall?.[0]?.include_deleted).toBe(true));
    await userEvent.click(screen.getByRole('button', { name: 'Tables' }));
    expect(
      await screen.findByRole('checkbox', { name: /main.sales.orders.*deleted/ })
    ).toBeInTheDocument();
  });

  it('permet de réessayer les graphiques sans bloquer le tableau existant', async () => {
    api.tableCharts.mockRejectedValueOnce(new Error('Warehouse unavailable'));
    renderWithProviders(<UsageTablesUc />, { route: '/databricks/usage-tables' });
    await applyPeriod();
    const retry = await screen.findByRole('button', { name: 'Retry charts' });
    expect(
      await within(await screen.findByRole('table', { name: '' })).findByText('main.sales.orders')
    ).toBeInTheDocument();
    await userEvent.click(retry);
    expect(await screen.findByRole('region', { name: 'Usage regularity' })).toBeInTheDocument();
    expect(api.tableCharts).toHaveBeenCalledTimes(2);
  });
});
