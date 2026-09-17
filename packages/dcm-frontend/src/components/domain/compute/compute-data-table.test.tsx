import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ComputeDataTable, type ComputeDataTableColumn } from './compute-data-table';
import { COLUMN_WIDTH } from './compute-column-widths';
import { columnWidthsStorageKey, MIN_COLUMN_WIDTH } from '../../../hooks/useColumnWidths';

type Row = { id: string; name: string; count: number };

const rows: Row[] = [
  { id: 'a', name: 'un nom de warehouse particulièrement long', count: 12 },
  { id: 'b', name: 'court', count: 3 },
];

const columns: ComputeDataTableColumn<Row>[] = [
  { id: 'name', header: 'Name', width: COLUMN_WIDTH.name, sortable: true, cell: (r) => r.name },
  {
    id: 'count',
    header: 'Count',
    width: COLUMN_WIDTH.number,
    align: 'right',
    sortable: true,
    cell: (r) => r.count,
  },
  { id: 'open', header: '', width: COLUMN_WIDTH.action, resizable: false, cell: () => <a>↗</a> },
];

function renderTable(overrides: Partial<Parameters<typeof ComputeDataTable<Row>>[0]> = {}) {
  return render(
    <ComputeDataTable
      tableId="test-table"
      columns={columns}
      rows={rows}
      rowKey={(r) => r.id}
      emptyTitle="Rien"
      emptyDescription="Aucune ligne"
      {...overrides}
    />
  );
}

function colWidths(container: HTMLElement): Record<string, string> {
  const out: Record<string, string> = {};
  container.querySelectorAll('col[data-column-id]').forEach((col) => {
    out[col.getAttribute('data-column-id')!] = (col as HTMLElement).style.width;
  });
  return out;
}

describe('ComputeDataTable — largeurs de colonne', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('porte les largeurs sur <colgroup> et non sur les cellules', () => {
    const { container } = renderTable();

    // C'est le point technique de T005 : `table-fixed` seul ne fixe rien, la
    // largeur doit venir du colgroup pour ne pas dépendre du contenu de la page.
    expect(colWidths(container)).toEqual({
      name: `${COLUMN_WIDTH.name}px`,
      count: `${COLUMN_WIDTH.number}px`,
      open: `${COLUMN_WIDTH.action}px`,
    });
    expect(container.querySelector('table')).toHaveClass('table-fixed');
  });

  it('donne au <table> la somme des largeurs, sinon le navigateur les redistribue', () => {
    const { container } = renderTable();
    const total = COLUMN_WIDTH.name + COLUMN_WIDTH.number + COLUMN_WIDTH.action;

    expect((container.querySelector('table') as HTMLElement).style.width).toBe(`${total}px`);
  });

  it('rend une poignée par colonne redimensionnable, aucune sur les autres', () => {
    renderTable();

    expect(screen.getByTestId('column-resizer-Name')).toBeInTheDocument();
    expect(screen.getByTestId('column-resizer-Count')).toBeInTheDocument();
    // `open` est `resizable: false` : pas de poignée à afficher.
    expect(screen.queryByTestId('column-resizer-open')).not.toBeInTheDocument();
  });

  it("annonce la poignée par l'id quand l'en-tête est une chaîne vide", () => {
    const withEmptyHeader: ComputeDataTableColumn<Row>[] = [
      { id: 'actions', header: '', width: COLUMN_WIDTH.action, cell: () => <a>↗</a> },
    ];
    renderTable({ columns: withEmptyHeader });

    // Sans repli sur l'id, la poignée serait annoncée « Redimensionner la colonne ».
    expect(screen.getByTestId('column-resizer-actions')).toHaveAttribute(
      'aria-label',
      'Redimensionner la colonne actions'
    );
  });

  it('élargit la colonne au clavier sans déclencher le tri', () => {
    const onSortChange = vi.fn();
    const { container } = renderTable({ onSortChange });

    fireEvent.keyDown(screen.getByTestId('column-resizer-Name'), { key: 'ArrowRight' });

    expect(colWidths(container).name).toBe(`${COLUMN_WIDTH.name + 16}px`);
    expect(onSortChange).not.toHaveBeenCalled();
  });

  it('ne déclenche pas le tri quand on saisit la poignée', () => {
    const onSortChange = vi.fn();
    renderTable({ onSortChange });
    const handle = screen.getByTestId('column-resizer-Count');

    fireEvent.pointerDown(handle, { button: 0, clientX: 100, pointerId: 1 });
    fireEvent.pointerUp(handle, { clientX: 140, pointerId: 1 });
    fireEvent.click(handle);

    expect(onSortChange).not.toHaveBeenCalled();
  });

  it('trie toujours au clic sur l’en-tête lui-même', () => {
    const onSortChange = vi.fn();
    renderTable({ onSortChange });

    fireEvent.click(screen.getByRole('button', { name: /Name/ }));

    expect(onSortChange).toHaveBeenCalledWith('name');
  });

  it('borne le rétrécissement au minimum global', () => {
    const { container } = renderTable();
    const handle = screen.getByTestId('column-resizer-Count');

    fireEvent.pointerDown(handle, { button: 0, clientX: 500, pointerId: 1 });
    fireEvent.pointerMove(handle, { clientX: 0, pointerId: 1 });

    expect(colWidths(container).count).toBe(`${MIN_COLUMN_WIDTH}px`);
  });

  it('persiste la largeur sous le tableId et la relit au remontage', () => {
    const first = renderTable();
    fireEvent.keyDown(screen.getByTestId('column-resizer-Name'), { key: 'ArrowRight' });
    first.unmount();

    const { container } = renderTable();

    expect(colWidths(container).name).toBe(`${COLUMN_WIDTH.name + 16}px`);
    expect(localStorage.getItem(columnWidthsStorageKey('test-table'))).toContain('name');
  });

  it('ne partage pas les largeurs entre deux tableId — le grief que tableId requis évite', () => {
    const first = renderTable();
    fireEvent.keyDown(screen.getByTestId('column-resizer-Name'), { key: 'ArrowRight' });
    first.unmount();

    const { container } = renderTable({ tableId: 'autre-table' });

    expect(colWidths(container).name).toBe(`${COLUMN_WIDTH.name}px`);
  });

  it("n'affiche le bouton de réinitialisation qu'une fois une largeur modifiée", () => {
    const { container } = renderTable();
    const label = /Réinitialiser les largeurs/;

    expect(screen.queryByRole('button', { name: label })).not.toBeInTheDocument();

    fireEvent.keyDown(screen.getByTestId('column-resizer-Name'), { key: 'ArrowRight' });
    fireEvent.click(screen.getByRole('button', { name: label }));

    expect(colWidths(container).name).toBe(`${COLUMN_WIDTH.name}px`);
    expect(screen.queryByRole('button', { name: label })).not.toBeInTheDocument();
  });

  it('réinitialise une seule colonne par Home', () => {
    const { container } = renderTable();
    fireEvent.keyDown(screen.getByTestId('column-resizer-Name'), { key: 'ArrowRight' });
    fireEvent.keyDown(screen.getByTestId('column-resizer-Count'), { key: 'ArrowRight' });

    fireEvent.keyDown(screen.getByTestId('column-resizer-Name'), { key: 'Home' });

    expect(colWidths(container).name).toBe(`${COLUMN_WIDTH.name}px`);
    expect(colWidths(container).count).toBe(`${COLUMN_WIDTH.number + 16}px`);
  });
});

describe('ComputeDataTable — lisibilité à largeur fixe', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('tronque une cellule texte en exposant la valeur complète en infobulle', () => {
    renderTable();

    // Contrepartie obligatoire de `table-fixed` : sans le `title`, la valeur
    // tronquée serait définitivement perdue pour l'utilisateur.
    const cell = screen.getByTitle(rows[0].name);
    expect(cell).toHaveClass('truncate');
    expect(cell).toHaveTextContent(rows[0].name);
  });

  it('coupe aussi une cellule composite et en expose le texte complet', () => {
    // Le texte est rendu **par un composant** : il n'est pas dans `props.children`,
    // donc il ne peut pas être extrait de l'arbre React avant rendu. C'est le cas
    // de presque toutes les cellules des 11 tableaux (`<ClusterCell/>`,
    // `<StatusBadge/>`, `<WaitStack/>`), et la raison pour laquelle l'infobulle est
    // construite après rendu, sur le DOM.
    function StackedCell({ row }: { row: Row }) {
      return (
        <div>
          <div>{row.name}</div>
          <div>{row.id}</div>
        </div>
      );
    }
    const { container } = renderTable({
      columns: [
        {
          id: 'name',
          header: 'Name',
          width: COLUMN_WIDTH.name,
          cell: (row) => <StackedCell row={row} />,
        },
      ],
    });
    const wrapper = container.querySelector('tbody tr td > span') as HTMLElement;

    expect(wrapper).toHaveClass('truncate');
    expect(wrapper).toHaveAttribute('title', `${rows[0].name}${rows[0].id}`);
  });

  it('coupe le débordement sur la cellule elle-même, dernier rempart de la colonne', () => {
    const { container } = renderTable();

    // Sans ce clip, un contenu plus large que la colonne sort de sa cellule et
    // recouvre la voisine : c'est ce que la largeur fixe rend possible.
    container.querySelectorAll('tbody td').forEach((cell) => {
      expect(cell).toHaveClass('overflow-hidden');
    });
  });

  it("expose le nom complet de l'en-tête, coupé à la même largeur", () => {
    renderTable();

    // Un en-tête coupé rend la colonne muette : c'est lui qui porte son sens.
    expect(screen.getByText('Name')).toHaveAttribute('title', 'Name');
  });

  it('laisse son infobulle à une cellule qui en pose déjà une', () => {
    const { container } = renderTable({
      columns: [
        {
          id: 'name',
          header: 'Name',
          width: COLUMN_WIDTH.name,
          cell: (row) => <span title={`${row.name} · ${row.id}`}>{row.name}</span>,
        },
      ],
    });
    const inner = container.querySelector('tbody tr td span span') as HTMLElement;

    // L'élément le plus intérieur gagne au survol : une cellule qui sait mieux dire
    // sa valeur qu'une concaténation de son texte garde la main.
    expect(inner).toHaveAttribute('title', `${rows[0].name} · ${rows[0].id}`);
  });

  it('conserve le nombre de colonnes du colgroup sur un tableau vide', () => {
    const { container } = renderTable({ rows: [] });

    // Un colgroup désaligné du colSpan décale toute la géométrie.
    expect(container.querySelectorAll('col')).toHaveLength(columns.length);
    expect(container.querySelector('tbody td')).toHaveAttribute('colspan', String(columns.length));
  });
});

/**
 * jsdom ne calcule aucune mise en page : ces tests verrouillent le **mécanisme**
 * qui laisse le navigateur répartir le surplus (largeur du `<table>`, colonne sans
 * largeur, poignée retirée), pas les pixels obtenus — ceux-là se vérifient dans un
 * vrai navigateur.
 */
describe('ComputeDataTable — colonne élastique', () => {
  const total = COLUMN_WIDTH.name + COLUMN_WIDTH.number + COLUMN_WIDTH.action;

  beforeEach(() => {
    localStorage.clear();
  });

  it('fait de la somme un plancher et non une largeur, pour remplir la carte', () => {
    const { container } = renderTable({ stretchColumnId: 'name' });
    const table = container.querySelector('table') as HTMLElement;

    expect(table.style.width).toBe('100%');
    // Le plancher garde `name` au moins à sa largeur déclarée sur un écran étroit,
    // où le tableau redevient défilant comme avant.
    expect(table.style.minWidth).toBe(`${total}px`);
  });

  it('laisse la colonne élastique sans largeur et garde les pixels des autres', () => {
    const { container } = renderTable({ stretchColumnId: 'name' });

    // Sous `table-layout: fixed`, la seule colonne `auto` prend ce qui reste ; les
    // colonnes de chiffres gardent leurs pixels, donc leurs poignées restent justes.
    expect(colWidths(container)).toEqual({
      name: '',
      count: `${COLUMN_WIDTH.number}px`,
      open: `${COLUMN_WIDTH.action}px`,
    });
  });

  it('retire la poignée de la colonne élastique, dont la largeur est celle qui reste', () => {
    renderTable({ stretchColumnId: 'name' });

    expect(screen.queryByTestId('column-resizer-Name')).not.toBeInTheDocument();
    // Les autres poignées ne sont pas emportées avec elle.
    expect(screen.getByTestId('column-resizer-Count')).toBeInTheDocument();
  });

  it('ignore un id qui ne désigne aucune colonne', () => {
    const { container } = renderTable({ stretchColumnId: 'nom' });
    const table = container.querySelector('table') as HTMLElement;

    // Une faute de frappe doit rendre la géométrie d'avant, pas un tableau en
    // largeur 100 % dont toutes les colonnes sont fixes — donc une colonne fantôme.
    expect(table.style.width).toBe(`${total}px`);
    expect(colWidths(container).name).toBe(`${COLUMN_WIDTH.name}px`);
    expect(screen.getByTestId('column-resizer-Name')).toBeInTheDocument();
  });

  it('ne touche à rien quand la prop est absente', () => {
    const { container } = renderTable();
    const table = container.querySelector('table') as HTMLElement;

    expect(table.style.width).toBe(`${total}px`);
    expect(table.style.minWidth).toBe('');
  });
});
