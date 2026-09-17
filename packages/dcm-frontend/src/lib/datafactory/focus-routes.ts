import type { PipelineStatus } from '../../types/api';
import type { DataFactoryFocusView } from './focus-view';

export function buildDataFactoryFocusPath(
  view: DataFactoryFocusView,
  params?: { status?: PipelineStatus },
): string {
  const search = new URLSearchParams();
  if (params?.status) search.set('status', params.status);
  const query = search.toString();
  return `/datafactory/${view}${query ? `?${query}` : ''}`;
}
