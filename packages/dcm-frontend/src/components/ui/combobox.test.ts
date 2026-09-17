import { describe, expect, it } from 'vitest';
import {
  COMBOBOX_LARGE_CATALOG_THRESHOLD,
  COMBOBOX_MAX_VISIBLE,
  getComboboxVisibleOptions,
} from './combobox-utils';

function options(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    value: `id-${i}`,
    label: `Option ${String(i).padStart(3, '0')}`,
  }));
}

describe('getComboboxVisibleOptions', () => {
  it('returns the full small catalogue when search is empty', () => {
    const small = options(COMBOBOX_LARGE_CATALOG_THRESHOLD);
    const result = getComboboxVisibleOptions(small, '', '');
    expect(result.requiresSearch).toBe(false);
    expect(result.visible).toHaveLength(small.length);
    expect(result.truncated).toBe(false);
  });

  it('requires typing for large catalogues instead of mounting every row', () => {
    const large = options(COMBOBOX_LARGE_CATALOG_THRESHOLD + 1);
    const result = getComboboxVisibleOptions(large, '', '');
    expect(result.requiresSearch).toBe(true);
    expect(result.visible).toEqual([]);
    expect(result.totalMatched).toBe(large.length);
  });

  it('keeps the current selection visible while waiting for a search query', () => {
    const large = options(100);
    const result = getComboboxVisibleOptions(large, '', 'id-7');
    expect(result.requiresSearch).toBe(true);
    expect(result.visible).toEqual([{ value: 'id-7', label: 'Option 007' }]);
  });

  it('filters and caps long result sets', () => {
    const large = options(200);
    const result = getComboboxVisibleOptions(large, 'option 1', '');
    expect(result.requiresSearch).toBe(false);
    expect(result.visible.length).toBeLessThanOrEqual(COMBOBOX_MAX_VISIBLE);
    expect(result.truncated).toBe(result.totalMatched > COMBOBOX_MAX_VISIBLE);
    expect(result.visible.every((o) => o.label.toLowerCase().includes('option 1'))).toBe(true);
  });
});
