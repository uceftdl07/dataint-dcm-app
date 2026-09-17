import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../../../test/render';
import { ComputeDataTable, type ComputeDataTableColumn } from './compute-data-table';
import { COLUMN_WIDTH } from './compute-column-widths';
import type { ComputeColumnFilterOptions, ComputeColumnFilterValues } from '../../../types/api';

vi.mock('../../../api/dcmApiClient', () => ({
  getComputeFilterOptions: vi.fn(),
  getLakeflowFilterOptions: vi.fn(),
}));

import { getComputeFilterOptions, getLakeflowFilterOptions } from '../../../api/dcmApiClient';

const apiMocks = {
  compute: vi.mocked(getComputeFilterOptions),
  lakeflow: vi.mocked(getLakeflowFilterOptions),
};

type Row = { id: string; warehouse: string; size: string; cost: number };

const rows: Row[] = [{ id: 'a', warehouse: 'wh-analytics', size: 'MEDIUM', cost: 12 }];

const columns: ComputeDataTableColumn<Row>[] = [
  {
    id: 'warehouse',
    header: 'Warehouse',
    width: COLUMN_WIDTH.name,
    sortable: true,
    filterKey: 'warehouse',
    cell: (r) => r.warehouse,
  },
  {
    id: 'size',
    header: 'Size',
    width: COLUMN_WIDTH.badge,
    sortable: true,
    filterKey: 'size',
    cell: (r) => r.size,
  },
  {
    id: 'cost',
    header: 'Cost',
    width: COLUMN_WIDTH.number,
    align: 'right',
    sortable: true,
    filterKey: 'cost',
    cell: (r) => r.cost,
  },
  // Colonne d'affichage : son `id` n'existe pas dans l'allowlist serveur, donc
  // aucun `filterKey` — et aucun entonnoir.
  { id: 'delta', header: 'Delta', width: COLUMN_WIDTH.number, cell: () => '+2 %' },
];

function optionsResponse(
  overrides: Partial<ComputeColumnFilterOptions> = {}
): ComputeColumnFilterOptions {
  return {
    view: 'warehouses-overview',
    column: 'size',
    kind: 'enum',
    label: 'Size',
    options: [
      { value: 'SMALL', label: 'Small', count: 4 },
      { value: 'MEDIUM', label: 'Medium', count: 12 },
      { value: 'LARGE', label: 'Large', count: 1 },
    ],
    truncated: false,
    ...overrides,
  };
}

type HarnessProps = Partial<Parameters<typeof ComputeDataTable<Row>>[0]> & {
  initialFilters?: ComputeColumnFilterValues;
  onPageReset?: () => void;
};

/**
 * Tient l'état des filtres comme le fait une page : le tableau ne le stocke pas,
 * et un test qui garderait `filters` figé ne verrait jamais l'entonnoir devenir actif.
 */
function FilterHarness({ initialFilters, onPageReset, ...overrides }: HarnessProps) {
  const [filters, setFilters] = useState<ComputeColumnFilterValues>(initialFilters ?? {});
  return (
    <ComputeDataTable
      tableId="test-filters"
      columns={columns}
      rows={rows}
      rowKey={(r) => r.id}
      emptyTitle="Rien"
      emptyDescription="Aucune ligne"
      filterView="warehouses-overview"
      filters={filters}
      onFiltersChange={(next) => {
        setFilters(next);
        onPageReset?.();
      }}
      {...overrides}
    />
  );
}

function renderTable(props: HarnessProps = {}) {
  return renderWithProviders(<FilterHarness {...props} />);
}

async function openFilter(label: string) {
  fireEvent.click(screen.getByTestId(`column-filter-${label}`));
  return waitFor(() => expect(screen.getByRole('listbox')).toBeInTheDocument());
}

describe('ComputeColumnFilter — ouverture et navigation', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    apiMocks.compute.mockResolvedValue(optionsResponse());
    apiMocks.lakeflow.mockResolvedValue(optionsResponse({ view: 'lakeflow-jobs' }));
  });

  it("n'affiche l'entonnoir que sur les colonnes portant un filterKey", () => {
    renderTable();

    expect(screen.getByTestId('column-filter-Size')).toBeInTheDocument();
    expect(screen.getByTestId('column-filter-Warehouse')).toBeInTheDocument();
    // `delta` est une colonne d'affichage : une clé inventée partirait en 422.
    expect(screen.queryByTestId('column-filter-Delta')).not.toBeInTheDocument();
  });

  it("n'affiche aucun entonnoir quand la page ne détient pas les filtres", () => {
    renderWithProviders(
      <ComputeDataTable
        tableId="test-sans-filtres"
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        emptyTitle="Rien"
        emptyDescription="Aucune ligne"
      />
    );

    expect(screen.queryByTestId('column-filter-Size')).not.toBeInTheDocument();
  });

  it("n'interroge le serveur qu'à l'ouverture", async () => {
    renderTable();

    // Onze tableaux, 88 colonnes filtrables : un préchargement à l'affichage
    // lancerait 88 `GROUP BY` pour des listes que personne n'a ouvertes.
    expect(apiMocks.compute).not.toHaveBeenCalled();

    await openFilter('Size');

    expect(apiMocks.compute).toHaveBeenCalledTimes(1);
    expect(apiMocks.compute).toHaveBeenCalledWith(
      expect.objectContaining({ view: 'warehouses-overview', column: 'size' })
    );
  });

  it('interroge le périmètre du tableau, fenêtre glissante comprise', async () => {
    renderTable({ filterScope: { windowDays: 90 } });

    await openFilter('Size');

    // Sans `window_days`, la combo listerait les valeurs de la veille au-dessus
    // d'un tableau réglé sur 90 jours.
    expect(apiMocks.compute).toHaveBeenCalledWith(
      expect.objectContaining({ window_days: 90, period_start: expect.any(String) })
    );
  });

  it('passe par l’endpoint Lakeflow pour les vues Lakeflow', async () => {
    renderTable({ filterView: 'lakeflow-jobs', filterScope: { workflowId: 'job-7' } });

    await openFilter('Size');

    expect(apiMocks.compute).not.toHaveBeenCalled();
    expect(apiMocks.lakeflow).toHaveBeenCalledWith(
      expect.objectContaining({ view: 'lakeflow-jobs', workflow_id: 'job-7' })
    );
  });

  it('ouvre au clavier, comme tout combobox', async () => {
    renderTable();
    const trigger = screen.getByTestId('column-filter-Size');

    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    // `fireEvent.click` est ce que produit Enter sur un `<button>` natif.
    fireEvent.keyDown(trigger, { key: 'Enter' });
    fireEvent.click(trigger);

    await waitFor(() => expect(trigger).toHaveAttribute('aria-expanded', 'true'));
  });

  it('se ferme par Escape et rend le focus à l’entonnoir', async () => {
    renderTable();
    await openFilter('Size');

    fireEvent.keyDown(screen.getByTestId('column-filter-panel-Size'), { key: 'Escape' });

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(screen.getByTestId('column-filter-Size')).toHaveFocus();
  });

  it('se ferme au clic extérieur', async () => {
    renderTable();
    await openFilter('Size');

    fireEvent.mouseDown(document.body);

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('reste ouverte au clic dans le panneau', async () => {
    renderTable();
    await openFilter('Size');
    const panel = screen.getByTestId('column-filter-panel-Size');

    fireEvent.mouseDown(panel);

    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });

  it('parcourt la liste aux flèches et sélectionne par Enter', async () => {
    renderTable();
    await openFilter('Size');
    const panel = screen.getByTestId('column-filter-panel-Size');

    fireEvent.keyDown(panel, { key: 'ArrowDown' });
    fireEvent.keyDown(panel, { key: 'ArrowDown' });
    fireEvent.keyDown(panel, { key: 'ArrowUp' });
    fireEvent.keyDown(panel, { key: 'Enter' });

    // 0 → 1 → 2 → 1 : « Medium », la deuxième valeur.
    await waitFor(() =>
      expect(screen.getByTestId('column-filter-Size')).toHaveAttribute('data-active', 'true')
    );
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('ne trie ni ne redimensionne quand on ouvre l’entonnoir', async () => {
    const onSortChange = vi.fn();
    const { container } = renderTable({ onSortChange });
    const widthBefore = (container.querySelector('col[data-column-id="size"]') as HTMLElement).style
      .width;

    await openFilter('Size');

    // L'entonnoir est un frère du bouton de tri dans la même cellule d'en-tête :
    // sans `stopPropagation`, l'ouvrir trierait la colonne au passage.
    expect(onSortChange).not.toHaveBeenCalled();
    expect((container.querySelector('col[data-column-id="size"]') as HTMLElement).style.width).toBe(
      widthBefore
    );
  });

  it('trie toujours au clic sur le libellé de la colonne', () => {
    const onSortChange = vi.fn();
    renderTable({ onSortChange });

    fireEvent.click(screen.getByRole('button', { name: /Size/ }));

    expect(onSortChange).toHaveBeenCalledWith('size');
  });
});

describe('ComputeColumnFilter — recherche', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    apiMocks.compute.mockResolvedValue(optionsResponse());
  });

  it('débonce la saisie avant d’interroger le serveur', async () => {
    renderTable();
    await openFilter('Warehouse');
    expect(apiMocks.compute).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByLabelText('Rechercher une valeur de Warehouse'), {
      target: { value: 'ana' },
    });

    // Immédiatement après la frappe, rien n'est parti : c'est tout l'objet du debounce.
    expect(apiMocks.compute).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(apiMocks.compute).toHaveBeenCalledWith(expect.objectContaining({ q: 'ana' }))
    );
  });

  it('oublie la recherche à la fermeture', async () => {
    apiMocks.compute.mockImplementation(async (params) =>
      optionsResponse(
        params.q
          ? { options: [{ value: 'MEDIUM', label: 'Medium', count: 12 }], truncated: true }
          : {}
      )
    );
    renderTable();
    await openFilter('Warehouse');
    fireEvent.change(screen.getByLabelText('Rechercher une valeur de Warehouse'), {
      target: { value: 'med' },
    });
    await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(1));

    fireEvent.keyDown(screen.getByTestId('column-filter-panel-Warehouse'), { key: 'Escape' });
    await openFilter('Warehouse');

    // Une liste rétrécie à côté d'un champ de recherche vide serait incompréhensible.
    expect(screen.getByLabelText('Rechercher une valeur de Warehouse')).toHaveValue('');
    expect(screen.getAllByRole('option')).toHaveLength(3);
  });

  it('remplace la recherche par les seuils serveur sur une colonne numérique', async () => {
    apiMocks.compute.mockResolvedValue(
      optionsResponse({
        column: 'cost',
        kind: 'numeric',
        label: 'Cost',
        options: [
          { value: '100', label: '≥ 100' },
          { value: '1000', label: '≥ 1 000' },
        ],
      })
    );
    renderTable();

    await openFilter('Cost');

    expect(screen.getByText('Seuils proposés par le serveur')).toBeInTheDocument();
    expect(screen.queryByLabelText('Rechercher une valeur de Cost')).not.toBeInTheDocument();
    expect(screen.getByRole('option', { name: /≥ 100/ })).toBeInTheDocument();
  });
});

describe('ComputeColumnFilter — états de liste', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('distingue « liste indisponible » d’une liste vide', async () => {
    apiMocks.compute.mockResolvedValue(
      optionsResponse({ enabled: false, options: [], truncated: false })
    );
    renderTable();

    fireEvent.click(screen.getByTestId('column-filter-Size'));

    // `enabled: false` = la source n'a pas pu être lue. L'afficher comme vide
    // ferait croire que le périmètre ne contient aucune valeur.
    expect(await screen.findByText(/Liste indisponible/)).toBeInTheDocument();
  });

  it('annonce une liste tronquée au lieu d’un vide trompeur', async () => {
    apiMocks.compute.mockResolvedValue(
      optionsResponse({ kind: 'text', options: [], truncated: true })
    );
    renderTable();

    fireEvent.click(screen.getByTestId('column-filter-Size'));

    expect(await screen.findByText(/affinez la recherche/)).toBeInTheDocument();
  });

  it('dit « aucune valeur » quand le périmètre est réellement vide', async () => {
    apiMocks.compute.mockResolvedValue(optionsResponse({ options: [], truncated: false }));
    renderTable();

    fireEvent.click(screen.getByTestId('column-filter-Size'));

    expect(await screen.findByText('Aucune valeur dans votre périmètre.')).toBeInTheDocument();
  });

  it('affiche le compte des valeurs quand le serveur le donne', async () => {
    apiMocks.compute.mockResolvedValue(optionsResponse());
    renderTable();

    await openFilter('Size');

    expect(screen.getByRole('option', { name: /Medium/ })).toHaveTextContent('12');
  });
});

describe('ComputeDataTable — filtres actifs', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    apiMocks.compute.mockResolvedValue(optionsResponse());
  });

  it('remonte le filtre à la page et revient à la page 1', async () => {
    const onPageReset = vi.fn();
    renderTable({ onPageReset });
    await openFilter('Size');

    fireEvent.click(screen.getByRole('option', { name: /Medium/ }));

    // Les onze tableaux paginent côté serveur : rester page 4 après un filtre
    // afficherait une page vide alors que le résultat tient sur une page.
    expect(onPageReset).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(screen.getByTestId('column-filter-Size')).toHaveAttribute('data-active', 'true')
    );
  });

  it('marque l’entonnoir comme actif et l’annonce', () => {
    renderTable({ initialFilters: { size: 'MEDIUM' } });
    const trigger = screen.getByTestId('column-filter-Size');

    expect(trigger).toHaveAttribute('data-active', 'true');
    expect(trigger).toHaveAccessibleName('Filtrer la colonne Size (actif)');
  });

  it('enlève le filtre en rechoisissant la valeur déjà posée', async () => {
    renderTable({ initialFilters: { size: 'MEDIUM' } });
    await openFilter('Size');

    fireEvent.click(screen.getByRole('option', { name: /Medium/ }));

    await waitFor(() =>
      expect(screen.getByTestId('column-filter-Size')).toHaveAttribute('data-active', 'false')
    );
  });

  it('efface un filtre depuis le panneau', async () => {
    renderTable({ initialFilters: { size: 'MEDIUM' } });
    await openFilter('Size');

    fireEvent.click(screen.getByRole('button', { name: /Effacer ce filtre/ }));

    expect(screen.getByTestId('column-filter-Size')).toHaveAttribute('data-active', 'false');
  });

  it('compte les filtres actifs et les efface tous d’un geste', async () => {
    renderTable({ initialFilters: { size: 'MEDIUM', warehouse: 'ana' } });

    // Un filtre posé sur une colonne au milieu d'un tableau large est invisible :
    // ce bouton est le seul endroit qui dit combien sont actifs.
    const clearAll = screen.getByRole('button', { name: /Effacer tous les filtres \(2\)/ });
    fireEvent.click(clearAll);

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /Effacer tous les filtres/ })).not.toBeInTheDocument()
    );
    expect(screen.getByTestId('column-filter-Size')).toHaveAttribute('data-active', 'false');
  });

  it('n’affiche pas le bouton d’effacement sans filtre actif', () => {
    renderTable();

    expect(
      screen.queryByRole('button', { name: /Effacer tous les filtres/ })
    ).not.toBeInTheDocument();
  });
});
