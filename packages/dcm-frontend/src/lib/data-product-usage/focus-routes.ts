import type { DataProductFocusView, DataProductTopMetric } from './focus-view';

export function buildDataProductFocusPath(
  view: DataProductFocusView,
  params?: { metric?: DataProductTopMetric; product?: string; consumer?: string },
): string {
  const search = new URLSearchParams();
  if (params?.metric) search.set('metric', params.metric);
  if (params?.product) search.set('product', params.product);
  if (params?.consumer) search.set('consumer', params.consumer);
  const query = search.toString();
  return `/data-product-usage/${view}${query ? `?${query}` : ''}`;
}
