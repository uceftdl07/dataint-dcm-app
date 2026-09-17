import type { PipelineStatus } from '../../types/api';
import type { PipelinesFocusView } from './focus-view';

export function buildPipelinesFocusPath(view: PipelinesFocusView, params?: { status?: PipelineStatus; type?: string }): string {
  const search = new URLSearchParams();
  if (params?.status) search.set('status', params.status);
  if (params?.type) search.set('type', params.type);
  const query = search.toString();
  return `/pipelines/${view}${query ? `?${query}` : ''}`;
}
