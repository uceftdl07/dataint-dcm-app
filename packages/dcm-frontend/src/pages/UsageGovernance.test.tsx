import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ucUsageDeletedLifecycle,
  ucUsageFilterOptionsFixture,
  ucUsageGovernanceKpisFixture,
  ucUsageRecommendationsFixture,
  ucUsageRegistryFixture,
} from '../test/fixtures/uc-usage';
import { fireEvent, renderWithProviders, screen, userEvent, waitFor, within } from '../test/render';
import UsageGovernance from './UsageGovernance';
import {
  ucGovernanceChartsFixture,
  ucRecommendationChartsFixture,
} from '../test/fixtures/uc-governance-charts';

vi.mock('../api/dcmApiClient', () => ({
  getUcUsageGovernanceKpis: vi.fn(),
  getUcUsageGovernanceCharts: vi.fn(),
  getUcUsageRecommendationCharts: vi.fn(),
  listUcUsageGovernanceRegistry: vi.fn(),
  listUcUsageRecommendations: vi.fn(),
  getUcUsageOverview: vi.fn(),
  getUcUsageFinopsTrends: vi.fn(),
  getUcUsageFilterOptions: vi.fn(),
  listUcUsageTables: vi.fn(),
  listUcUsageConsumers: vi.fn(),
  getUcUsageFinopsKpis: vi.fn(),
  listUcUsageCostByTable: vi.fn(),
  getUcUsageTableTopConsumers: vi.fn(),
}));

import {
  getUcUsageFilterOptions,
  getUcUsageGovernanceKpis,
  getUcUsageGovernanceCharts,
  getUcUsageRecommendationCharts,
  listUcUsageGovernanceRegistry,
  listUcUsageRecommendations,
} from '../api/dcmApiClient';

const api = {
  kpis: vi.mocked(getUcUsageGovernanceKpis),
  governanceCharts: vi.mocked(getUcUsageGovernanceCharts),
  recommendationCharts: vi.mocked(getUcUsageRecommendationCharts),
  registry: vi.mocked(listUcUsageGovernanceRegistry),
  recommendations: vi.mocked(listUcUsageRecommendations),
  filterOptions: vi.mocked(getUcUsageFilterOptions),
};

async function openRecommendationsTab() {
  await userEvent.click(screen.getByRole('tab', { name: 'Recommendations' }));
  await waitFor(() => expect(api.recommendations).toHaveBeenCalled());
}

/** Le catalogue est un menu alimenté par le registre, plus une saisie libre. */
async function selectCatalog(value: string) {
  await userEvent.click(screen.getByRole('button', { name: 'Catalog' }));
  await userEvent.click(await screen.findByRole('option', { name: value }));
}

/** Le périmètre est obligatoire : chaque analyse part d'un choix explicite, comme
 * sur la page d'usage. Sans ce geste la page reste sur son accueil. */
async function renderApplied() {
  renderWithProviders(<UsageGovernance />, { route: '/databricks/usage-governance' });
  await selectCatalog('main');
  await userEvent.click(screen.getByRole('button', { name: 'Apply' }));
  await waitFor(() => expect(api.registry).toHaveBeenCalled());
}

describe('UsageGovernance', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.kpis.mockResolvedValue(ucUsageGovernanceKpisFixture);
    api.governanceCharts.mockResolvedValue(ucGovernanceChartsFixture);
    api.recommendationCharts.mockResolvedValue(ucRecommendationChartsFixture);
    api.registry.mockResolvedValue(ucUsageRegistryFixture);
    api.recommendations.mockResolvedValue(ucUsageRecommendationsFixture);
    api.filterOptions.mockResolvedValue(ucUsageFilterOptionsFixture);
  });

  it('accueille l’utilisateur sans état global avant sa sélection', async () => {
    renderWithProviders(<UsageGovernance />, { route: '/databricks/usage-governance' });

    await waitFor(() => expect(api.filterOptions).toHaveBeenCalled());
    for (const [name, endpoint] of Object.entries(api)) {
      if (name !== 'filterOptions') expect(endpoint).not.toHaveBeenCalled();
    }
    expect(
      screen.getByRole('region', { name: 'Which tables would you like to analyse?' })
    ).toBeInTheDocument();
    // Variante gouvernance : l'état courant ignore la période du header.
    expect(
      screen.queryByText('Adjust the dates in the application header.')
    ).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Catalog' })).toHaveTextContent('Choose a catalog');
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.queryByText(/Applied scope/)).not.toBeInTheDocument();
    expect(screen.queryByText('No tables in this scope')).not.toBeInTheDocument();
  });

  it('guide vers le sélecteur et n’interroge le snapshot qu’après Appliquer', async () => {
    renderWithProviders(<UsageGovernance />, { route: '/databricks/usage-governance' });
    await userEvent.click(screen.getByRole('button', { name: 'Choose my scope' }));
    expect(screen.getByRole('button', { name: 'Catalog' })).toHaveFocus();
    await userEvent.click(await screen.findByRole('option', { name: 'main' }));
    expect(
      screen.getByText('Your selection is ready. Click Apply to display the analysis.')
    ).toBeInTheDocument();
    expect(api.kpis).not.toHaveBeenCalled();
    expect(api.governanceCharts).not.toHaveBeenCalled();
    expect(api.registry).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: 'Apply' }));

    await waitFor(() => expect(api.registry).toHaveBeenCalled());
    expect(api.kpis.mock.lastCall?.[0]).toMatchObject({ catalog: 'main' });
    expect(
      screen.queryByRole('region', { name: 'Which tables would you like to analyse?' })
    ).not.toBeInTheDocument();
    expect(screen.getAllByRole('tab')).toHaveLength(2);
    expect(screen.getByText(/Applied scope/)).toHaveTextContent('main');
  });

  it('refuse une soumission sans périmètre, y compris depuis le formulaire', async () => {
    renderWithProviders(<UsageGovernance />, { route: '/databricks/usage-governance' });
    await waitFor(() => expect(api.filterOptions).toHaveBeenCalled());
    fireEvent.submit(screen.getByRole('button', { name: 'Apply' }).closest('form')!);
    expect(api.registry).not.toHaveBeenCalled();
    expect(api.governanceCharts).not.toHaveBeenCalled();
    expect(
      screen.getByRole('region', { name: 'Which tables would you like to analyse?' })
    ).toBeInTheDocument();
  });

  it('signale un périmètre modifié tant que Appliquer n’a pas été cliqué', async () => {
    await renderApplied();
    await selectCatalog('lake');
    expect(
      screen.getByText(
        'Selection changed: results still reflect the last applied scope. Click Apply to update the analysis.'
      )
    ).toBeInTheDocument();
    expect(api.registry.mock.lastCall?.[0]).toMatchObject({ catalog: 'main' });
  });

  it('charge les endpoints snapshot sans période', async () => {
    await renderApplied();

    const params = api.registry.mock.calls[0][0] ?? {};
    expect(params).not.toHaveProperty('period_start');
    expect(params).not.toHaveProperty('period_end');
  });

  it('affiche « Non renseigné » plutôt qu’une cellule vide quand owner est absent', async () => {
    await renderApplied();

    expect(await screen.findByText('Unknown')).toBeInTheDocument();
  });

  it('dérive le statut du registre du mot-clé recommended_action', async () => {
    await renderApplied();

    expect(await screen.findByText('Orphaned')).toBeInTheDocument();
    expect(screen.getAllByText('Unused').length).toBeGreaterThan(0);
  });

  it('rend HIGH et high avec le même libellé de sévérité', async () => {
    await renderApplied();

    // Registre : `high` en minuscules.
    expect(await screen.findByText('High')).toBeInTheDocument();

    await openRecommendationsTab();

    // Recommandations : `HIGH` en majuscules, même pastille après normalisation.
    const badges = await screen.findAllByText('High');
    expect(badges.length).toBeGreaterThan(0);
    expect(screen.queryByText('HIGH')).not.toBeInTheDocument();
    expect(screen.queryByText('high')).not.toBeInTheDocument();
  });

  it('limite le filtre de catégorie à la liste fermée de 5 valeurs', async () => {
    await renderApplied();

    await openRecommendationsTab();

    const select = screen.getByLabelText('Category');
    // 5 catégories + l'entrée « Toutes les catégories ».
    expect(within(select).getAllByRole('option')).toHaveLength(6);

    await userEvent.selectOptions(select, 'FINOPS');
    await waitFor(() =>
      expect(api.recommendations.mock.calls.some((call) => call[0]?.category === 'FINOPS')).toBe(
        true
      )
    );
  });

  it('n’offre aucun bouton d’acquittement', async () => {
    await renderApplied();

    await openRecommendationsTab();

    expect(screen.queryByRole('button', { name: /acquitter/i })).not.toBeInTheDocument();
  });

  it('présente le coût comme une référence journalière LIFECYCLE, sans inventer un gain mensuel', async () => {
    await renderApplied();

    await openRecommendationsTab();

    expect(await screen.findByText('Daily reference cost')).toBeInTheDocument();
    expect(screen.getByText('0 / 0 costed LIFECYCLE candidates')).toBeInTheDocument();
    expect(screen.queryByText('Gain estimé')).not.toBeInTheDocument();
  });

  it('n’affiche pas de gain chiffré pour une recommandation sans économie', async () => {
    await renderApplied();

    await openRecommendationsTab();

    const card = (await screen.findByText('Fraîcheur dégradée')).closest('article');
    expect(card).not.toBeNull();
    expect(card?.textContent).not.toContain('Gain estimé');
  });

  it('charge les graphiques snapshot et conserve leur périmètre lors d’un focus du registre', async () => {
    await renderApplied();
    await waitFor(() => expect(api.governanceCharts).toHaveBeenCalledTimes(1));
    expect(api.governanceCharts.mock.calls[0][0]).not.toHaveProperty('period_start');
    await userEvent.click(await screen.findByRole('button', { name: 'Review these tables' }));
    await waitFor(() =>
      expect(api.registry.mock.lastCall?.[0]).toMatchObject({ signal: 'unused_critical', page: 1 })
    );
    expect(api.governanceCharts).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole('button', { name: 'Clear registry focus' }));
    expect(screen.queryByText(/Focus du registre/)).not.toBeInTheDocument();
  });

  it('envoie le schéma et le signal choisis dans la matrice au registre', async () => {
    await renderApplied();
    await userEvent.click(
      await screen.findByRole('button', { name: /main.sales · Missing ownership tags/ })
    );
    await waitFor(() =>
      expect(api.registry.mock.lastCall?.[0]).toMatchObject({
        catalog: 'main',
        schema: 'sales',
        signal: 'orphan',
      })
    );
    expect(api.governanceCharts).toHaveBeenCalledTimes(1);
  });

  it('permet le drill-down du nuage de points au clavier', async () => {
    await renderApplied();
    await userEvent.selectOptions(
      await screen.findByLabelText('Inspect a table in the chart'),
      JSON.stringify(['azure', 'main.sales.orders'])
    );
    await userEvent.click(screen.getByRole('button', { name: 'View in registry' }));
    await waitFor(() =>
      expect(api.registry.mock.lastCall?.[0]?.tables).toEqual(['main.sales.orders'])
    );
    expect(api.governanceCharts.mock.lastCall?.[0]?.tables).toBeUndefined();
  });

  it('applique catalogue, schéma et table aux graphiques des deux onglets seulement après Appliquer', async () => {
    await renderApplied();
    await waitFor(() => expect(api.governanceCharts).toHaveBeenCalledTimes(1));
    await userEvent.click(screen.getByRole('button', { name: 'Catalog' }));
    await userEvent.click(await screen.findByRole('option', { name: 'main' }));
    await userEvent.click(screen.getByRole('button', { name: 'Schema' }));
    await userEvent.click(await screen.findByRole('option', { name: 'sales' }));
    await userEvent.click(screen.getByRole('button', { name: 'Tables' }));
    await userEvent.click(await screen.findByRole('checkbox', { name: /main.sales.orders/ }));
    expect(api.governanceCharts).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole('button', { name: 'Apply' }));
    const scope = { catalog: 'main', schema: 'sales', tables: ['main.sales.orders'] };
    await waitFor(() => expect(api.governanceCharts.mock.lastCall?.[0]).toEqual(scope));
    await openRecommendationsTab();
    expect(api.recommendationCharts.mock.lastCall?.[0]).toEqual(scope);
    expect(api.recommendations.mock.lastCall?.[0]).toMatchObject({
      ...scope,
      object_type: 'DATA_PRODUCT',
    });
  });

  it('combine ancienneté et sévérité sur les cartes sans recalculer les graphiques', async () => {
    await renderApplied();
    await openRecommendationsTab();
    await userEvent.click(
      await screen.findByRole('button', { name: /31–90 days.*Filter recommendations/ })
    );
    await userEvent.selectOptions(screen.getByLabelText('Severity'), 'HIGH');
    await waitFor(() =>
      expect(api.recommendations.mock.lastCall?.[0]).toMatchObject({
        age_bucket: '31_90',
        severity: 'HIGH',
        object_type: 'DATA_PRODUCT',
        sort: 'age',
        page: 1,
      })
    );
    expect(api.recommendationCharts).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole('button', { name: 'Clear card filters' }));
    expect(screen.getByLabelText('Severity')).toHaveValue('');
  });

  it('relie le classement aux cartes puis au registre de la même table', async () => {
    await renderApplied();
    await openRecommendationsTab();
    await userEvent.click(
      await screen.findByRole('button', { name: /main.sales.orders.*View recommendations/ })
    );
    await waitFor(() =>
      expect(api.recommendations.mock.lastCall?.[0]?.tables).toEqual(['main.sales.orders'])
    );
    const buttons = await screen.findAllByRole('button', { name: 'View in registry' });
    await userEvent.click(buttons[0]);
    await waitFor(() =>
      expect(api.registry.mock.lastCall?.[0]?.tables).toEqual(['main.sales.orders'])
    );
    expect(screen.getByRole('tab', { name: 'Governance' })).toHaveAttribute(
      'aria-selected',
      'true'
    );
  });

  it('ne charge les consommateurs globaux qu’à l’ouverture de leur section dédiée', async () => {
    await renderApplied();
    await openRecommendationsTab();
    expect(
      api.recommendations.mock.calls.every((call) => call[0]?.object_type === 'DATA_PRODUCT')
    ).toBe(true);
    await userEvent.click(screen.getByText('Consumer FinOps · outside the selected table scope'));
    await waitFor(() =>
      expect(
        api.recommendations.mock.calls.some((call) => call[0]?.object_type === 'CONSUMER')
      ).toBe(true)
    );
    const params = api.recommendations.mock.calls.find(
      (call) => call[0]?.object_type === 'CONSUMER'
    )?.[0];
    expect(params?.catalog).toBeUndefined();
    expect(params?.tables).toBeUndefined();
    expect(api.recommendationCharts).toHaveBeenCalledTimes(1);
  });

  it('n’inclut les tables supprimées qu’après Appliquer et les marque dans le registre', async () => {
    api.registry.mockResolvedValue({
      ...ucUsageRegistryFixture,
      items: [
        ucUsageRegistryFixture.items[0],
        { ...ucUsageRegistryFixture.items[1], ...ucUsageDeletedLifecycle },
      ],
    });
    await renderApplied();
    expect(api.registry.mock.lastCall?.[0]).not.toHaveProperty('include_deleted', true);
    const callsBeforeChecking = api.registry.mock.calls.length;

    await userEvent.click(screen.getByRole('checkbox', { name: 'Include deleted tables' }));
    expect(api.registry.mock.calls.length).toBe(callsBeforeChecking);

    await userEvent.click(screen.getByRole('button', { name: 'Apply' }));
    // Un seul dénominateur : les cartes et le registre partagent le drapeau.
    await waitFor(() => expect(api.registry.mock.lastCall?.[0]?.include_deleted).toBe(true));
    expect(api.kpis.mock.lastCall?.[0]?.include_deleted).toBe(true);
    expect(api.governanceCharts.mock.lastCall?.[0]?.include_deleted).toBe(true);

    const deletedRow = (await screen.findByText('main.legacy.snapshot_2019')).closest('tr')!;
    expect(within(deletedRow).getByText('Deleted 2026-09-05')).toBeInTheDocument();
    const liveRow = screen.getByText('main.sales.orders').closest('tr')!;
    expect(within(liveRow).queryByText(/^Deleted /)).not.toBeInTheDocument();
  });

  it('permet de relancer les graphiques en erreur et garde le registre disponible', async () => {
    api.governanceCharts.mockRejectedValueOnce(new Error('missing gold'));
    await renderApplied();
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load charts');
    expect(screen.getByText('Table registry — current state')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry charts' }));
    expect(
      await screen.findByRole('table', { name: 'Governance signal matrix' })
    ).toBeInTheDocument();
  });
});
