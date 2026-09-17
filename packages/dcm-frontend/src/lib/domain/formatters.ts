export function formatDateTime(value: string | null | undefined) {
  if (!value) return '-';

  return new Date(value).toLocaleString('en-GB', {
    dateStyle: 'short',
    timeStyle: 'short',
  });
}

export function formatCurrency(amount: number | null | undefined, currency = 'USD') {
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount ?? 0);
}

export function formatPercentage(value: number | null | undefined, digits = 1) {
  return `${(value ?? 0).toFixed(digits)}%`;
}
