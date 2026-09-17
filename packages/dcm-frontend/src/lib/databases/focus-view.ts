import type { DatabaseType } from '../../types/api';

export const DATABASE_FOCUS_VIEWS = ['inventory', 'pressure', 'capacity'] as const;

export type DatabaseFocusView = (typeof DATABASE_FOCUS_VIEWS)[number];

export const DATABASE_FOCUS_VIEW_LABELS: Record<DatabaseFocusView, string> = {
  inventory: 'Database inventory',
  pressure: 'Pressure watchlist',
  capacity: 'Capacity & connections',
};

export const DATABASE_FOCUS_VIEW_DESCRIPTIONS: Record<DatabaseFocusView, string> = {
  inventory: 'Latest snapshot per database. Click a row to expand full details.',
  pressure: 'Databases ranked by CPU, memory, storage, and DTU pressure.',
  capacity: 'Databases ranked by storage usage and active connections.',
};

export function parseDatabaseFocusView(value: string | null): DatabaseFocusView | null {
  if (!value) return null;
  return DATABASE_FOCUS_VIEWS.includes(value as DatabaseFocusView) ? (value as DatabaseFocusView) : null;
}

export function parseAvailabilityFromUrl(value: string | null): '' | 'true' | 'false' {
  if (value === 'true' || value === 'false') return value;
  return '';
}

export function parseDatabaseTypeFromUrl(value: string | null): DatabaseType | '' {
  if (!value) return '';
  const valid = ['sqlserver', 'postgresql', 'mysql', 'cosmosdb', 'redshift', 'rds_mysql', 'rds_postgres', 'rds_oracle', 'aurora'];
  return valid.includes(value) ? (value as DatabaseType) : '';
}

export type DatabaseCapacitySort = 'storage' | 'connections';

export function parseCapacitySortFromUrl(value: string | null): DatabaseCapacitySort {
  return value === 'connections' ? 'connections' : 'storage';
}
