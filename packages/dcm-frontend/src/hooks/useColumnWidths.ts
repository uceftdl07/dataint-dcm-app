import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Largeurs de colonne des tableaux compute : déclarées par la colonne, ajustables
 * par l'utilisateur, persistées par tableau.
 *
 * Ce qui est stocké est une préférence d'affichage — des pixels, rien d'autre :
 * aucun identifiant, aucune donnée métier.
 */

const STORAGE_PREFIX = 'dcm:table-widths';

/**
 * Garde-fou uniquement : les colonnes des tableaux compute déclarent toutes leur
 * largeur. Une colonne qui retomberait ici est une colonne oubliée.
 */
export const DEFAULT_COLUMN_WIDTH = 140;
export const MIN_COLUMN_WIDTH = 64;
export const MAX_COLUMN_WIDTH = 640;

/** Pas du redimensionnement au clavier. */
export const KEYBOARD_RESIZE_STEP = 16;

export type ColumnWidthSpec = {
  id: string;
  width?: number;
  minWidth?: number;
  maxWidth?: number;
  resizable?: boolean;
};

export type ColumnBounds = { min: number; max: number };

export type ColumnWidthsState = {
  /** Largeur effective de chaque colonne passée, en pixels. */
  widths: Record<string, number>;
  /** Somme des largeurs effectives — largeur imposée au `<table>`. */
  totalWidth: number;
  bounds: (columnId: string) => ColumnBounds;
  /** Largeur déclarée par la colonne, cible du « réinitialiser ». */
  declaredWidth: (columnId: string) => number;
  setWidth: (columnId: string, width: number) => void;
  resetColumn: (columnId: string) => void;
  resetAll: () => void;
  /** Vrai dès qu'une largeur diverge de sa déclaration. */
  isCustomized: boolean;
};

export function columnWidthsStorageKey(tableId: string): string {
  return `${STORAGE_PREFIX}:${tableId}`;
}

function boundsOf(column: ColumnWidthSpec): ColumnBounds {
  const min = column.minWidth ?? MIN_COLUMN_WIDTH;
  const max = column.maxWidth ?? MAX_COLUMN_WIDTH;
  // Une déclaration incohérente (`minWidth` > `maxWidth`) ne doit pas produire un
  // intervalle vide dans lequel aucune largeur ne serait acceptable.
  return { min, max: Math.max(min, max) };
}

function declaredWidthOf(column: ColumnWidthSpec): number {
  const bounds = boundsOf(column);
  const declared = column.width ?? DEFAULT_COLUMN_WIDTH;
  return Math.min(Math.max(Math.round(declared), bounds.min), bounds.max);
}

/**
 * Lit les largeurs persistées. Toute anomalie rend un objet vide plutôt que de
 * propager une valeur douteuse : `localStorage` indisponible (navigation privée,
 * quota), JSON illisible, ou contenu qui n'est pas un objet plat.
 */
export function readStoredWidths(tableId: string): Record<string, number> {
  let raw: string | null;
  try {
    raw = localStorage.getItem(columnWidthsStorageKey(tableId));
  } catch {
    return {};
  }
  if (!raw) {
    return {};
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return {};
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return {};
  }

  const result: Record<string, number> = {};
  Object.entries(parsed as Record<string, unknown>).forEach(([columnId, value]) => {
    if (typeof value === 'number' && Number.isFinite(value)) {
      result[columnId] = value;
    }
  });
  return result;
}

function writeStoredWidths(tableId: string, widths: Record<string, number>): void {
  try {
    if (Object.keys(widths).length === 0) {
      localStorage.removeItem(columnWidthsStorageKey(tableId));
      return;
    }
    localStorage.setItem(columnWidthsStorageKey(tableId), JSON.stringify(widths));
  } catch {
    // Quota dépassé ou navigation privée : la largeur reste effective pour la
    // session, elle ne survivra simplement pas au rechargement.
  }
}

export function useColumnWidths(tableId: string, columns: ColumnWidthSpec[]): ColumnWidthsState {
  const [overrides, setOverrides] = useState<Record<string, number>>(() =>
    readStoredWidths(tableId)
  );

  // L'écriture ne peut pas vivre dans l'updater de `setOverrides` : un updater doit
  // être pur, React se réservant le droit de le réinvoquer. Ce miroir permet de
  // calculer l'état suivant hors de l'updater et de n'écrire qu'une fois.
  const overridesRef = useRef(overrides);
  overridesRef.current = overrides;

  // Deux tableaux de la même page ne partagent pas leurs largeurs : changer de
  // `tableId` relit le stockage au lieu de conserver les valeurs du précédent.
  const loadedTableId = useRef(tableId);
  useEffect(() => {
    if (loadedTableId.current === tableId) {
      return;
    }
    loadedTableId.current = tableId;
    const loaded = readStoredWidths(tableId);
    overridesRef.current = loaded;
    setOverrides(loaded);
  }, [tableId]);

  // `columns` est reconstruit à chaque rendu par certaines pages : le garder dans
  // une ref évite de recréer les rappels et de faire lire des bornes périmées.
  const columnsRef = useRef(columns);
  columnsRef.current = columns;

  const findColumn = useCallback(
    (columnId: string) => columnsRef.current.find((column) => column.id === columnId),
    []
  );

  const widths: Record<string, number> = {};
  let totalWidth = 0;
  let isCustomized = false;
  columns.forEach((column) => {
    const declared = declaredWidthOf(column);
    const { min, max } = boundsOf(column);
    const stored = overrides[column.id];
    // Une valeur hors bornes est écartée au profit de la largeur déclarée, pas
    // rabotée en silence : elle vient d'une déclaration qui a changé depuis, la
    // rogner produirait une géométrie que personne n'a choisie.
    const usable =
      typeof stored === 'number' && Number.isFinite(stored) && stored >= min && stored <= max;
    const effective = usable ? Math.round(stored) : declared;
    widths[column.id] = effective;
    totalWidth += effective;
    if (effective !== declared) {
      isCustomized = true;
    }
  });
  // Une clé persistée dont la colonne n'existe plus est ignorée du seul fait
  // qu'on n'itère que sur `columns`.

  const commit = useCallback(
    (next: Record<string, number>) => {
      overridesRef.current = next;
      writeStoredWidths(tableId, next);
      setOverrides(next);
    },
    [tableId]
  );

  const setWidth = useCallback(
    (columnId: string, width: number) => {
      const column = findColumn(columnId);
      if (!column) {
        return;
      }
      const { min, max } = boundsOf(column);
      const next = Math.min(Math.max(Math.round(width), min), max);
      if (overridesRef.current[columnId] === next) {
        return;
      }
      commit({ ...overridesRef.current, [columnId]: next });
    },
    [commit, findColumn]
  );

  const resetColumn = useCallback(
    (columnId: string) => {
      if (!(columnId in overridesRef.current)) {
        return;
      }
      const updated = { ...overridesRef.current };
      delete updated[columnId];
      commit(updated);
    },
    [commit]
  );

  const resetAll = useCallback(() => {
    if (Object.keys(overridesRef.current).length === 0) {
      return;
    }
    commit({});
  }, [commit]);

  const bounds = useCallback(
    (columnId: string) => {
      const column = findColumn(columnId);
      return column ? boundsOf(column) : { min: MIN_COLUMN_WIDTH, max: MAX_COLUMN_WIDTH };
    },
    [findColumn]
  );

  const declaredWidth = useCallback(
    (columnId: string) => {
      const column = findColumn(columnId);
      return column ? declaredWidthOf(column) : DEFAULT_COLUMN_WIDTH;
    },
    [findColumn]
  );

  return {
    widths,
    totalWidth,
    bounds,
    declaredWidth,
    setWidth,
    resetColumn,
    resetAll,
    isCustomized,
  };
}
