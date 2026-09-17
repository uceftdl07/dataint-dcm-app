/**
 * Pure Combobox list shaping — kept out of the React component file so
 * react-refresh/only-export-components stays clean.
 */

import type { ComboboxOption } from './combobox-types';

/** Above this size, an empty query shows a "type to search" hint instead of all rows. */
export const COMBOBOX_LARGE_CATALOG_THRESHOLD = 40;
/** Hard cap on DOM rows rendered for any query (keeps open/filter cheap). */
export const COMBOBOX_MAX_VISIBLE = 50;

export interface ComboboxVisibleResult {
  visible: ComboboxOption[];
  totalMatched: number;
  requiresSearch: boolean;
  truncated: boolean;
}

/** Pure list shaping used by the panel (and unit-tested). */
export function getComboboxVisibleOptions(
  options: readonly ComboboxOption[],
  search: string,
  selectedValue: string,
  {
    largeThreshold = COMBOBOX_LARGE_CATALOG_THRESHOLD,
    maxVisible = COMBOBOX_MAX_VISIBLE,
  }: { largeThreshold?: number; maxVisible?: number } = {}
): ComboboxVisibleResult {
  const query = search.trim().toLowerCase();
  const isLarge = options.length > largeThreshold;

  if (isLarge && !query) {
    // Keep the current selection visible so the open panel is not empty after pick.
    const selected = options.find((o) => o.value === selectedValue);
    return {
      visible: selected ? [selected] : [],
      totalMatched: options.length,
      requiresSearch: true,
      truncated: false,
    };
  }

  const matched = !query
    ? [...options]
    : options.filter((o) => o.label.toLowerCase().includes(query));

  return {
    visible: matched.slice(0, maxVisible),
    totalMatched: matched.length,
    requiresSearch: false,
    truncated: matched.length > maxVisible,
  };
}
