import type { CloudProvider, DatabaseMetric, DatabaseType } from '../../types/api';

export const DATABASE_TYPES: DatabaseType[] = [
  'sqlserver',
  'postgresql',
  'mysql',
  'cosmosdb',
  'redshift',
  'rds_mysql',
  'rds_postgres',
  'rds_oracle',
  'aurora',
];

export const DATABASE_TYPE_GROUPS: Array<{
  type: DatabaseType;
  types: DatabaseType[];
  label: string;
  description: string;
  color: string;
}> = [
  { type: 'sqlserver', types: ['sqlserver'], label: 'SQL Database', description: 'Azure SQL / SQL Server', color: 'var(--tdf-blue)' },
  { type: 'cosmosdb', types: ['cosmosdb'], label: 'Cosmos DB', description: 'NoSQL accounts', color: 'var(--tdf-purple)' },
  { type: 'mysql', types: ['mysql', 'rds_mysql'], label: 'MySQL', description: 'Azure / RDS MySQL', color: 'var(--tdf-green)' },
  { type: 'postgresql', types: ['postgresql', 'rds_postgres'], label: 'PostgreSQL', description: 'Azure / RDS PostgreSQL', color: 'var(--tdf-teal)' },
  { type: 'redshift', types: ['redshift'], label: 'Redshift', description: 'AWS analytics database', color: 'var(--chart-5)' },
  { type: 'aurora', types: ['aurora'], label: 'Aurora', description: 'AWS Aurora clusters', color: 'var(--tdf-pink)' },
];

export function formatDatabaseType(type: DatabaseType) {
  const labels: Record<DatabaseType, string> = {
    sqlserver: 'SQL Server',
    postgresql: 'PostgreSQL',
    mysql: 'MySQL',
    cosmosdb: 'Cosmos DB',
    redshift: 'Redshift',
    rds_mysql: 'RDS MySQL',
    rds_postgres: 'RDS PostgreSQL',
    rds_oracle: 'RDS Oracle',
    aurora: 'Aurora',
  };
  return labels[type] ?? type;
}

export function formatPercent(value: number | null | undefined) {
  return value == null || Number.isNaN(value) ? '—' : `${Math.round(value)}%`;
}

export function formatNumber(value: number | null | undefined) {
  return value == null || Number.isNaN(value) ? '—' : Intl.NumberFormat('en-GB').format(value);
}

export function formatStorage(value: number | null | undefined) {
  return value == null || Number.isNaN(value) ? '—' : `${Number(value).toFixed(value >= 100 ? 0 : 1)} GB`;
}

export function formatCurrency(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '—';
  return Intl.NumberFormat('en-GB', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value);
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('en-GB');
}

export function getStoragePercent(db: DatabaseMetric) {
  if (db.storage_used_pct != null) return db.storage_used_pct;
  if (db.storage_used_gb == null || db.storage_limit_gb == null || db.storage_limit_gb <= 0) return null;
  return (db.storage_used_gb / db.storage_limit_gb) * 100;
}

export function average(values: Array<number | null | undefined>) {
  const validValues = values.filter((value): value is number => value != null && !Number.isNaN(value));
  if (validValues.length === 0) return null;
  return validValues.reduce((sum, value) => sum + value, 0) / validValues.length;
}

export function sumOptional(values: Array<number | null | undefined>) {
  const validValues = values.filter((value): value is number => value != null && !Number.isNaN(value));
  if (validValues.length === 0) return null;
  return validValues.reduce((sum, value) => sum + value, 0);
}

export function clampPercent(value: number) {
  return Math.min(Math.max(value, 0), 100);
}

export function getPressureScore(db: DatabaseMetric) {
  const values = [db.cpu_percent, db.memory_percent, getStoragePercent(db), db.dtus_used].filter(
    (value): value is number => value != null && !Number.isNaN(value),
  );
  if (values.length === 0) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export function getPressureColor(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return 'var(--muted-foreground)';
  if (value >= 85) return 'var(--danger)';
  if (value >= 70) return 'var(--warning)';
  return 'var(--tdf-green)';
}

export function getHealthCopy(unavailableCount: number, healthRate: number) {
  if (unavailableCount > 0) return `${unavailableCount} database${unavailableCount > 1 ? 's' : ''} to review first`;
  if (healthRate >= 95) return 'Platform stable, monitoring active';
  return 'Healthy coverage, keep watching';
}

export function computeDatabaseStats(filteredDbs: DatabaseMetric[]) {
  const availableCount = filteredDbs.filter((db) => db.is_available).length;
  const unavailableCount = filteredDbs.length - availableCount;
  const totalStorageUsed = filteredDbs.reduce((sum, db) => sum + (db.storage_used_gb ?? 0), 0);

  return {
    availableCount,
    unavailableCount,
    avgCpu: average(filteredDbs.map((db) => db.cpu_percent)),
    avgMemory: average(filteredDbs.map((db) => db.memory_percent)),
    avgStorage: average(filteredDbs.map(getStoragePercent)),
    totalStorageUsed,
    totalConnections: sumOptional(filteredDbs.map((db) => db.active_connections)),
    totalStorageCost: sumOptional(filteredDbs.map((db) => db.storage_cost_impact_usd)),
    byCloud: filteredDbs.reduce<Record<CloudProvider, number>>((acc, db) => {
      acc[db.cloud_provider] = (acc[db.cloud_provider] ?? 0) + 1;
      return acc;
    }, {} as Record<CloudProvider, number>),
    byType: filteredDbs.reduce<Record<DatabaseType, number>>((acc, db) => {
      acc[db.db_type] = (acc[db.db_type] ?? 0) + 1;
      return acc;
    }, {} as Record<DatabaseType, number>),
  };
}

export function sortDatabasesByPressure(dbs: DatabaseMetric[]) {
  return [...dbs]
    .filter((db) => getPressureScore(db) != null)
    .sort((a, b) => (getPressureScore(b) ?? 0) - (getPressureScore(a) ?? 0));
}

export function sortDatabasesByCapacity(dbs: DatabaseMetric[], sort: 'storage' | 'connections' = 'storage') {
  return [...dbs].sort((a, b) => {
    if (sort === 'connections') {
      return (b.active_connections ?? 0) - (a.active_connections ?? 0);
    }
    return (b.storage_used_gb ?? 0) - (a.storage_used_gb ?? 0);
  });
}
