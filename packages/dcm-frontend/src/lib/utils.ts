import clsx, { type ClassValue } from 'clsx';

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatCompactNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return Intl.NumberFormat('en-GB', { notation: 'compact', maximumFractionDigits: 1 }).format(
    value
  );
}

/**
 * Aligné sur les autres formateurs de coût de l'app (`lib/domain/formatters.ts`,
 * `lib/databricks/view-data.ts`, `lib/compute/format.ts`) : deux décimales. Sans
 * consommateur à ce jour, mais l'arrondi à l'entier qu'il portait aurait été
 * réintroduit par le premier appelant.
 */
export function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(value);
}

/**
 * Headline KPI figures (e.g. the home-page FinOps card) use compact notation — $12.5K, not $12,500.50.
 * Built from the plain compact number rather than `style: 'currency'`: the en-GB locale renders USD
 * as "US$" (to disambiguate from GBP), not the bare "$" these headline figures need.
 */
export function formatCompactCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const sign = value < 0 ? '-' : '';
  const compact = Intl.NumberFormat('en-GB', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(Math.abs(value));
  return `${sign}$${compact}`;
}
