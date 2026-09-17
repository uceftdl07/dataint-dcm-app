import { act } from '@testing-library/react';
import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  columnWidthsStorageKey,
  DEFAULT_COLUMN_WIDTH,
  MAX_COLUMN_WIDTH,
  MIN_COLUMN_WIDTH,
  readStoredWidths,
  useColumnWidths,
  type ColumnWidthSpec,
} from './useColumnWidths';

const COLUMNS: ColumnWidthSpec[] = [
  { id: 'workspace', width: 200, minWidth: 120, maxWidth: 400 },
  { id: 'warehouse', width: 240, minWidth: 160, maxWidth: 480 },
  { id: 'cost', width: 120 },
];

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

/**
 * Remplace `localStorage` par un stockage qui lève, pour simuler la navigation
 * privée ou un quota dépassé.
 *
 * `vi.spyOn(window.localStorage, …)` **n'intercepte pas** les appels du code sous
 * test dans cet environnement (vérifié : l'espion reste à zéro appel alors que
 * l'écriture a bien eu lieu). Un test bâti dessus passerait à vide. `stubGlobal`
 * remplace la liaison globale, celle que le hook référence réellement.
 */
function stubThrowingStorage() {
  const setItem = vi.fn(() => {
    throw new Error('QuotaExceededError');
  });
  vi.stubGlobal('localStorage', {
    getItem: () => {
      throw new Error('SecurityError');
    },
    setItem,
    removeItem: () => undefined,
    clear: () => undefined,
    key: () => null,
    length: 0,
  });
  return { setItem };
}

describe('readStoredWidths', () => {
  it('rend un objet vide quand rien n est stocke', () => {
    expect(readStoredWidths('warehouses-overview')).toEqual({});
  });

  it('rend un objet vide sur un JSON illisible', () => {
    localStorage.setItem(columnWidthsStorageKey('warehouses-overview'), '{nope');
    expect(readStoredWidths('warehouses-overview')).toEqual({});
  });

  it('rend un objet vide quand le contenu n est pas un objet plat', () => {
    localStorage.setItem(columnWidthsStorageKey('warehouses-overview'), '[200,240]');
    expect(readStoredWidths('warehouses-overview')).toEqual({});
  });

  it('ecarte les valeurs non numeriques mais garde les autres', () => {
    localStorage.setItem(
      columnWidthsStorageKey('warehouses-overview'),
      JSON.stringify({ workspace: '200px', warehouse: 300 })
    );
    expect(readStoredWidths('warehouses-overview')).toEqual({ warehouse: 300 });
  });

  it('ne fait pas echouer la lecture quand localStorage est indisponible', () => {
    stubThrowingStorage();
    expect(readStoredWidths('warehouses-overview')).toEqual({});
  });
});

describe('useColumnWidths', () => {
  it('part des largeurs declarees par les colonnes', () => {
    const { result } = renderHook(() => useColumnWidths('warehouses-overview', COLUMNS));

    expect(result.current.widths).toEqual({ workspace: 200, warehouse: 240, cost: 120 });
    expect(result.current.totalWidth).toBe(560);
    expect(result.current.isCustomized).toBe(false);
  });

  it('retombe sur la largeur par defaut pour une colonne sans largeur declaree', () => {
    const { result } = renderHook(() => useColumnWidths('t', [{ id: 'orphan' }]));

    expect(result.current.widths.orphan).toBe(DEFAULT_COLUMN_WIDTH);
  });

  it('borne la largeur ecrite par minWidth et maxWidth', () => {
    const { result } = renderHook(() => useColumnWidths('warehouses-overview', COLUMNS));

    act(() => result.current.setWidth('workspace', 10));
    expect(result.current.widths.workspace).toBe(120);

    act(() => result.current.setWidth('workspace', 9999));
    expect(result.current.widths.workspace).toBe(400);
  });

  it('borne par les constantes globales quand la colonne ne declare rien', () => {
    const { result } = renderHook(() => useColumnWidths('t', [{ id: 'cost' }]));

    act(() => result.current.setWidth('cost', 1));
    expect(result.current.widths.cost).toBe(MIN_COLUMN_WIDTH);

    act(() => result.current.setWidth('cost', 100000));
    expect(result.current.widths.cost).toBe(MAX_COLUMN_WIDTH);
  });

  it('persiste la largeur et la relit au remontage', () => {
    const first = renderHook(() => useColumnWidths('warehouses-overview', COLUMNS));
    act(() => first.result.current.setWidth('warehouse', 300));
    first.unmount();

    const second = renderHook(() => useColumnWidths('warehouses-overview', COLUMNS));
    expect(second.result.current.widths.warehouse).toBe(300);
    expect(second.result.current.isCustomized).toBe(true);
  });

  it('ignore une cle persistee dont la colonne a disparu', () => {
    localStorage.setItem(
      columnWidthsStorageKey('warehouses-overview'),
      JSON.stringify({ workspace: 300, colonne_retiree: 500 })
    );

    const { result } = renderHook(() => useColumnWidths('warehouses-overview', COLUMNS));

    expect(result.current.widths).toEqual({ workspace: 300, warehouse: 240, cost: 120 });
    expect(Object.keys(result.current.widths)).not.toContain('colonne_retiree');
  });

  it('ecarte une largeur persistee hors bornes au profit de la declaration', () => {
    localStorage.setItem(
      columnWidthsStorageKey('warehouses-overview'),
      JSON.stringify({ workspace: 5000 })
    );

    const { result } = renderHook(() => useColumnWidths('warehouses-overview', COLUMNS));

    // Ni 5000, ni 400 (la borne haute) : la largeur declaree.
    expect(result.current.widths.workspace).toBe(200);
    expect(result.current.isCustomized).toBe(false);
  });

  it('ecarte une largeur persistee non numerique', () => {
    localStorage.setItem(
      columnWidthsStorageKey('warehouses-overview'),
      JSON.stringify({ workspace: 'large' })
    );

    const { result } = renderHook(() => useColumnWidths('warehouses-overview', COLUMNS));

    expect(result.current.widths.workspace).toBe(200);
  });

  it('rend les largeurs declarees quand localStorage est indisponible', () => {
    const { setItem } = stubThrowingStorage();

    const { result } = renderHook(() => useColumnWidths('warehouses-overview', COLUMNS));
    expect(result.current.widths.workspace).toBe(200);

    // L'ecriture est tentee, echoue, et la largeur reste effective pour la
    // session : elle ne survivra simplement pas au rechargement.
    act(() => result.current.setWidth('workspace', 300));
    expect(result.current.widths.workspace).toBe(300);
    expect(setItem).toHaveBeenCalled();
  });

  it('ne partage pas les largeurs entre deux tableId', () => {
    const overview = renderHook(() => useColumnWidths('warehouses-overview', COLUMNS));
    act(() => overview.result.current.setWidth('warehouse', 320));
    overview.unmount();

    const cost = renderHook(() => useColumnWidths('warehouses-cost', COLUMNS));
    expect(cost.result.current.widths.warehouse).toBe(240);
  });

  it('relit le stockage quand le tableId change en cours de vie', () => {
    localStorage.setItem(
      columnWidthsStorageKey('warehouses-cost'),
      JSON.stringify({ warehouse: 320 })
    );

    const { result, rerender } = renderHook(
      ({ tableId }: { tableId: string }) => useColumnWidths(tableId, COLUMNS),
      { initialProps: { tableId: 'warehouses-overview' } }
    );
    expect(result.current.widths.warehouse).toBe(240);

    rerender({ tableId: 'warehouses-cost' });
    expect(result.current.widths.warehouse).toBe(320);
  });

  it('resetColumn ramene une seule colonne a sa declaration', () => {
    const { result } = renderHook(() => useColumnWidths('warehouses-overview', COLUMNS));
    act(() => result.current.setWidth('workspace', 300));
    act(() => result.current.setWidth('warehouse', 320));

    act(() => result.current.resetColumn('workspace'));

    expect(result.current.widths.workspace).toBe(200);
    expect(result.current.widths.warehouse).toBe(320);
    expect(result.current.isCustomized).toBe(true);
  });

  it('resetAll ramene tout et vide le stockage', () => {
    const { result } = renderHook(() => useColumnWidths('warehouses-overview', COLUMNS));
    act(() => result.current.setWidth('workspace', 300));
    act(() => result.current.setWidth('warehouse', 320));

    act(() => result.current.resetAll());

    expect(result.current.widths).toEqual({ workspace: 200, warehouse: 240, cost: 120 });
    expect(result.current.isCustomized).toBe(false);
    expect(localStorage.getItem(columnWidthsStorageKey('warehouses-overview'))).toBeNull();
  });

  it('expose les bornes et la largeur declaree de chaque colonne', () => {
    const { result } = renderHook(() => useColumnWidths('warehouses-overview', COLUMNS));

    expect(result.current.bounds('workspace')).toEqual({ min: 120, max: 400 });
    expect(result.current.bounds('cost')).toEqual({
      min: MIN_COLUMN_WIDTH,
      max: MAX_COLUMN_WIDTH,
    });
    expect(result.current.declaredWidth('warehouse')).toBe(240);
    expect(result.current.declaredWidth('inconnue')).toBe(DEFAULT_COLUMN_WIDTH);
  });

  it('ignore une ecriture sur une colonne inconnue', () => {
    const { result } = renderHook(() => useColumnWidths('warehouses-overview', COLUMNS));

    act(() => result.current.setWidth('inconnue', 300));

    expect(result.current.isCustomized).toBe(false);
    expect(localStorage.getItem(columnWidthsStorageKey('warehouses-overview'))).toBeNull();
  });
});
