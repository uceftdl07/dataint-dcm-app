import { describe, expect, it } from 'vitest';
import type { SecurityAlert, StandardCheck } from '../../types/api';
import { isDatabricksGovernanceCheck, isDatabricksSecurityAlert } from './databricks-utils';

describe('Databricks data scoping helpers', () => {
  it('keeps Databricks security alerts', () => {
    const alert = {
      title: 'Public cluster',
      description: 'Azure Databricks workspace adb-123',
      resource_type: 'cluster',
    } as SecurityAlert;
    expect(isDatabricksSecurityAlert(alert)).toBe(true);
  });

  it('excludes non-Databricks security alerts', () => {
    const alert = {
      title: 'SQL injection',
      description: 'Azure SQL database',
      resource_type: 'database',
    } as SecurityAlert;
    expect(isDatabricksSecurityAlert(alert)).toBe(false);
  });

  it('keeps Databricks governance checks', () => {
    const check = {
      check_name: 'UC table owner',
      resource_name: 'catalog.schema.table',
      resource_type: 'databricks_table',
    } as StandardCheck;
    expect(isDatabricksGovernanceCheck(check)).toBe(true);
  });

  it('excludes non-Databricks governance checks', () => {
    const check = {
      check_name: 'Backup enabled',
      resource_name: 'sql-db-prod',
      resource_type: 'database',
    } as StandardCheck;
    expect(isDatabricksGovernanceCheck(check)).toBe(false);
  });
});
