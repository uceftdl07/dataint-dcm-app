import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '../../test/render';
import { DatabaseAccordion } from './database-accordion';
import type { DatabaseMetric } from '../../types/api';

const sampleDb: DatabaseMetric = {
  active_connections: 42,
  availability_zone: '1',
  cloud_provider: 'azure',
  collected_at: '2026-06-04T12:00:00Z',
  cpu_percent: 67,
  db_id: 'db-prod-001',
  db_name: 'prod-sql',
  db_type: 'sqlserver',
  dtus_used: null,
  is_available: true,
  memory_percent: 54,
  region: 'westeurope',
  resource_group: 'rg-prod',
  server_name: 'prod-sql-server',
  source_lz_id: 'lz-azure-prod',
  storage_cost_impact_usd: 120.5,
  storage_limit_gb: 500,
  storage_used_gb: 210,
  storage_used_pct: 42,
  subscription_or_account_id: 'sub-prod',
  tags: { env: 'prod' },
};

describe('DatabaseAccordion', () => {
  it('renders empty state', () => {
    render(<DatabaseAccordion databases={[]} loading={false} emptyMessage="No databases" />);
    expect(screen.getByText('No databases')).toBeInTheDocument();
  });

  it('expands database details inline when clicked', () => {
    render(<DatabaseAccordion databases={[sampleDb]} loading={false} />);

    fireEvent.click(screen.getByRole('button', { name: /prod-sql/i }));

    expect(screen.getByText('prod-sql-server')).toBeInTheDocument();
    expect(screen.getByText('env: prod')).toBeInTheDocument();
  });
});
