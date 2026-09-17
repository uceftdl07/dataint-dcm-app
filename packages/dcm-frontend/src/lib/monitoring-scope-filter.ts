import type { MonitoringScope } from '../contexts/monitoring-scope';

export function getSelectedLzIds(scope: MonitoringScope): string[] | null {
  if (scope.kind === 'all') {
    return null;
  }
  if (scope.kind === 'landing-zone' && scope.sourceLzId) {
    return [scope.sourceLzId];
  }
  if (scope.kind === 'landing-zones' && scope.sourceLzIds?.length) {
    return scope.sourceLzIds;
  }
  return [];
}

export function getApiSourceLzId(scope: MonitoringScope): string | undefined {
  const selected = getSelectedLzIds(scope);
  if (selected?.length === 1) {
    return selected[0];
  }
  return undefined;
}

export function getApiLzParams(scope: MonitoringScope): {
  source_lz_id?: string;
  source_lz_ids?: string[];
} {
  const selected = getSelectedLzIds(scope);
  if (selected === null) {
    return {};
  }
  if (selected.length === 0) {
    return { source_lz_ids: [] };
  }
  if (selected.length === 1) {
    return { source_lz_id: selected[0] };
  }
  return { source_lz_ids: selected };
}

export function matchesSourceLzScope(
  sourceLzId: string | null | undefined,
  scope: MonitoringScope,
): boolean {
  const selected = getSelectedLzIds(scope);
  if (selected === null) {
    return true;
  }
  if (!sourceLzId) {
    return selected.length === 0;
  }
  return selected.includes(sourceLzId);
}

export function filterBySelectedLzIds<T extends { source_lz_id?: string | null }>(
  items: T[],
  selectedLzIds: string[] | null | undefined,
): T[] {
  if (selectedLzIds === null || selectedLzIds === undefined) {
    return items;
  }
  if (selectedLzIds.length === 0) {
    return [];
  }
  return items.filter(
    (item) => item.source_lz_id != null && selectedLzIds.includes(item.source_lz_id),
  );
}
