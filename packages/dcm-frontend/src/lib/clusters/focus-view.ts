import type { ComputeState } from '../../types/api';

export const CLUSTERS_FOCUS_VIEWS = ['inventory'] as const;
export type ClustersFocusView = (typeof CLUSTERS_FOCUS_VIEWS)[number];

export const CLUSTERS_FOCUS_VIEW_LABELS: Record<ClustersFocusView, string> = {
  inventory: 'Compute inventory',
};

export const CLUSTERS_FOCUS_VIEW_DESCRIPTIONS: Record<ClustersFocusView, string> = {
  inventory: 'Latest cluster snapshots. Click a row to expand details.',
};

export function parseClustersFocusView(value: string | null): ClustersFocusView | null {
  if (!value) return null;
  return CLUSTERS_FOCUS_VIEWS.includes(value as ClustersFocusView) ? (value as ClustersFocusView) : null;
}

const STATES: ComputeState[] = ['running', 'terminated', 'error', 'unknown'];

export function parseComputeStateFromUrl(value: string | null): ComputeState | '' {
  if (!value) return '';
  return STATES.includes(value as ComputeState) ? (value as ComputeState) : '';
}

export function buildClustersFocusPath(view: ClustersFocusView, params?: { state?: ComputeState }): string {
  const search = new URLSearchParams();
  if (params?.state) search.set('state', params.state);
  const query = search.toString();
  return `/clusters/${view}${query ? `?${query}` : ''}`;
}
