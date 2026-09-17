import { categoricalFill } from '../compute/compute-chart-colors';

/** Entity identity, never its rank, determines its Compute palette colour. */
export function ucUsageSeriesColor(key: string): string {
  if (key === 'other-tables') return 'var(--tdf-grey)';
  let hash = 0;
  for (const char of key) hash = (Math.imul(hash, 31) + char.charCodeAt(0)) | 0;
  return categoricalFill(hash >>> 0);
}

/** Half the row, minus a sliver, is available on each side of the zero line. */
const COST_CHANGE_HALF_PCT = 49;

/**
 * Width of one signed bar in "Largest cost changes", as a percentage of the row.
 * Linear from the zero line, so length stays proportional to the change in dollars;
 * scaled against the period peak rather than an arbitrary dollar floor. Only an
 * exactly flat cost yields 0 — the caller keeps tiny deltas visible with a pixel
 * minimum, since a sub-pixel bar would read as "no change".
 */
export function ucUsageCostChangeBarWidth(delta: number, maximum: number): number {
  if (delta === 0 || maximum <= 0) return 0;
  return Math.min(1, Math.abs(delta) / maximum) * COST_CHANGE_HALF_PCT;
}

export function ucUsageShortDate(value: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    timeZone: 'UTC',
  }).format(new Date(`${value}T00:00:00Z`));
}
