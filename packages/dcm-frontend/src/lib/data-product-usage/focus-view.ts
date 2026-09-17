export const DATA_PRODUCT_FOCUS_VIEWS = ['usage', 'consumers'] as const;
export type DataProductFocusView = (typeof DATA_PRODUCT_FOCUS_VIEWS)[number];

export const DATA_PRODUCT_FOCUS_VIEW_LABELS: Record<DataProductFocusView, string> = {
  usage: 'Usage details',
  consumers: 'Top consumers',
};

export const DATA_PRODUCT_FOCUS_VIEW_DESCRIPTIONS: Record<DataProductFocusView, string> = {
  usage: 'Unity Catalog data product usage rows. Click to expand details.',
  consumers: 'Most active consumers ranked by selected metric.',
};

export function parseDataProductFocusView(value: string | null): DataProductFocusView | null {
  if (!value) return null;
  return DATA_PRODUCT_FOCUS_VIEWS.includes(value as DataProductFocusView) ? (value as DataProductFocusView) : null;
}

export type DataProductTopMetric = 'data_read_bytes' | 'request_count' | 'rows_read' | 'cost_usd';

export function parseTopMetricFromUrl(value: string | null): DataProductTopMetric {
  const valid: DataProductTopMetric[] = ['data_read_bytes', 'request_count', 'rows_read', 'cost_usd'];
  return valid.includes(value as DataProductTopMetric) ? (value as DataProductTopMetric) : 'data_read_bytes';
}
