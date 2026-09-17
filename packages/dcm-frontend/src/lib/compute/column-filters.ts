/**
 * Per-column filters, client side (023 T006).
 *
 * The server owns the allowlist: which columns are filterable, what kind each one
 * is, and which historical parameter it doubles. This module only carries the
 * values between a table header and a query — it declares no column and invents no
 * threshold.
 */
import type { ComputeColumnFilterValues } from '../../types/api';

/**
 * Serializes the active filters into the repeatable `column_filter` parameter.
 *
 * Returns `undefined` rather than `[]` when nothing is active: `apiRequest`
 * serializes an empty array as `column_filter=`, which the server does read as
 * "no filter", but sending it would put an empty parameter on every request and
 * make the query strings harder to read in a network log.
 *
 * Sorted by key so that two identical selections produce one cache key, whatever
 * order the user clicked the headers in.
 */
export function toColumnFilterParam(
  filters: ComputeColumnFilterValues | undefined
): string[] | undefined {
  const items = activeColumnFilterEntries(filters).map(([key, value]) => `${key}:${value}`);
  return items.length > 0 ? items : undefined;
}

/** The entries that actually narrow something — a blank value is not a filter. */
export function activeColumnFilterEntries(
  filters: ComputeColumnFilterValues | undefined
): [string, string][] {
  if (!filters) return [];
  return Object.entries(filters)
    .filter(([key, value]) => Boolean(key) && typeof value === 'string' && value.trim() !== '')
    .map(([key, value]): [string, string] => [key, value.trim()])
    .sort((a, b) => a[0].localeCompare(b[0]));
}

export function countActiveColumnFilters(filters: ComputeColumnFilterValues | undefined): number {
  return activeColumnFilterEntries(filters).length;
}

/**
 * Sets or clears one column, without mutating the object the caller holds.
 *
 * An empty value **removes** the key instead of storing `''`: a leftover
 * `{ size: '' }` would keep the funnel looking active and would send `size:` on
 * every request for nothing.
 */
export function withColumnFilter(
  filters: ComputeColumnFilterValues | undefined,
  key: string,
  value: string | null | undefined
): ComputeColumnFilterValues {
  const next: ComputeColumnFilterValues = { ...(filters ?? {}) };
  if (value == null || value.trim() === '') delete next[key];
  else next[key] = value.trim();
  return next;
}
