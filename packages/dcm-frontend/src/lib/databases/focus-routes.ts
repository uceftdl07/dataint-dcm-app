import type { DatabaseType } from '../../types/api';
import type { DatabaseFocusView, DatabaseCapacitySort } from './focus-view';

export function buildDatabaseFocusPath(
  view: DatabaseFocusView,
  params?: { avail?: 'true' | 'false'; type?: DatabaseType; sort?: DatabaseCapacitySort },
): string {
  const search = new URLSearchParams();
  if (params?.avail) search.set('avail', params.avail);
  if (params?.type) search.set('type', params.type);
  if (params?.sort) search.set('sort', params.sort);
  const query = search.toString();
  return `/databases/${view}${query ? `?${query}` : ''}`;
}
