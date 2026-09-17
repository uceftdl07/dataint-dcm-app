import { describe, expect, it } from 'vitest';
import type { StandardCheck } from '../../types/api';
import { filterStandardChecks } from './governance';

const baseCheck: StandardCheck = {
  check_id: 'check-1',
  check_name: 'Databricks UC owner',
  cloud_provider: 'azure',
  source_lz_id: 'lz-dbx',
  subscription_or_account_id: 'sub-1',
  check_state: 'no_compliant',
  resource_id: 'adb-123',
  resource_name: 'catalog.schema.table',
  resource_type: 'databricks_table',
  check_effect: 'critical',
  no_check_reasons: ['Missing owner'],
  evaluated_at: '2026-05-25T08:00:00Z',
};

describe('filterStandardChecks search', () => {
  it('filters checks by search term across name and resource fields', () => {
    const checks = [
      baseCheck,
      { ...baseCheck, check_id: 'check-2', check_name: 'SQL backup enabled', resource_name: 'sql-db', resource_type: 'sql_database' },
    ];

    const filtered = filterStandardChecks(checks, { search: 'databricks' });

    expect(filtered).toHaveLength(1);
    expect(filtered[0]?.check_name).toBe('Databricks UC owner');
  });
});
