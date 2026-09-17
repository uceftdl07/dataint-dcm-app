import { describe, expect, it } from 'vitest';
import type { StandardCheck } from '../../types/api';
import { render, screen } from '../../test/render';
import { StandardChecksTable } from './standard-checks-table';

const baseCheck: StandardCheck = {
  check_id: 'check-1',
  check_name: 'Require Data Factory HTTPS',
  cloud_provider: 'azure',
  source_lz_id: 'lz-datafactory',
  subscription_or_account_id: 'sub-1',
  check_state: 'no_compliant',
  resource_id: '/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.DataFactory/factories/adf-1',
  resource_name: 'adf-1',
  resource_type: 'Microsoft.DataFactory/factories',
  check_effect: 'audit',
  no_check_reasons: ['HTTPS traffic is disabled'],
  evaluated_at: '2026-05-25T08:00:00Z',
};

describe('StandardChecksTable', () => {
  it('renders standard checks with list reasons', () => {
    render(
      <StandardChecksTable
        checks={[baseCheck]}
        allChecksCount={1}
        loading={false}
        emptyTitle="No check"
        emptyDescription="No check found."
        resourceFallback="Data Factory"
      />,
    );

    expect(screen.getByText('Require Data Factory HTTPS')).toBeInTheDocument();
    expect(screen.getByText('HTTPS traffic is disabled')).toBeInTheDocument();
  });

  it('does not crash when legacy API data sends a single reason string', () => {
    render(
      <StandardChecksTable
        checks={[{ ...baseCheck, no_check_reasons: 'HTTPS traffic is disabled' as unknown as string[] }]}
        allChecksCount={1}
        loading={false}
        emptyTitle="No check"
        emptyDescription="No check found."
        resourceFallback="Data Factory"
      />,
    );

    expect(screen.getByText('HTTPS traffic is disabled')).toBeInTheDocument();
  });

  it('paginates long check lists', () => {
    const checks = Array.from({ length: 25 }, (_, index) => ({
      ...baseCheck,
      check_id: `check-${index + 1}`,
      check_name: `Check ${index + 1}`,
    }));

    render(
      <StandardChecksTable
        checks={checks}
        allChecksCount={25}
        loading={false}
        emptyTitle="No check"
        emptyDescription="No check found."
        resourceFallback="multi-cloud"
      />,
    );

    expect(screen.getByText('Check 1')).toBeInTheDocument();
    expect(screen.queryByText('Check 16')).not.toBeInTheDocument();
    expect(screen.getByText('1–15 of 25 · Page 1 / 2')).toBeInTheDocument();
  });
});
