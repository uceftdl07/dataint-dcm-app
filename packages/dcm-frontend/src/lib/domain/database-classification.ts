import type { StandardCheck } from '../../types/api';

const DATABASE_KEYWORDS = [
  'database',
  'sql',
  'postgres',
  'mysql',
  'maria',
  'cosmos',
  'oracle',
  'rds',
  'aurora',
  'db',
];

export const NO_DATABASE_LABEL = 'Not provided';

export function isDatabaseValue(value: string | null | undefined) {
  if (!value) return false;

  const normalized = value.toLowerCase();

  return DATABASE_KEYWORDS.some((keyword) => {
    if (keyword === 'db') return /(^|[\s-_])db($|[\s-_])/.test(normalized);
    return normalized.includes(keyword);
  });
}

export function getDatabaseFamily(value: string | null | undefined) {
  const normalized = value?.toLowerCase() ?? '';

  if (normalized.includes('cosmos')) return 'Cosmos DB';
  if (normalized.includes('postgres')) return 'PostgreSQL';
  if (normalized.includes('mysql')) return 'MySQL';
  if (normalized.includes('maria')) return 'MariaDB';
  if (normalized.includes('oracle')) return 'Oracle';
  if (normalized.includes('rds')) return 'Amazon RDS';
  if (normalized.includes('aurora')) return 'Amazon Aurora';
  if (normalized.includes('sql')) return 'SQL Database';
  if (normalized.includes('database') || /(^|[\s-_])db($|[\s-_])/.test(normalized)) return 'Database';
  return NO_DATABASE_LABEL;
}

export function isDatabaseCheck(check: StandardCheck) {
  return [
    check.resource_type,
    check.resource_name,
    check.resource_id,
    check.check_name,
  ].some(isDatabaseValue);
}
