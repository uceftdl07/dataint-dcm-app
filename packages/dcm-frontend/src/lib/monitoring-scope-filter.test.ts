import { describe, expect, it } from 'vitest';
import { monitoringScopeDefaults } from '../contexts/monitoring-scope';
import {
  filterBySelectedLzIds,
  getApiLzParams,
  getApiSourceLzId,
  getSelectedLzIds,
  matchesSourceLzScope,
} from './monitoring-scope-filter';

describe('monitoring-scope-filter', () => {
  it('returns null for all scope', () => {
    expect(getSelectedLzIds(monitoringScopeDefaults.all)).toBeNull();
    expect(getApiSourceLzId(monitoringScopeDefaults.all)).toBeUndefined();
    expect(matchesSourceLzScope('lz-aws-prod', monitoringScopeDefaults.all)).toBe(true);
  });

  it('returns single API filter for one landing zone', () => {
    const scope = {
      kind: 'landing-zones' as const,
      label: 'lz-aws-prod',
      sourceLzIds: ['lz-aws-prod'],
    };

    expect(getApiSourceLzId(scope)).toBe('lz-aws-prod');
    expect(matchesSourceLzScope('lz-aws-prod', scope)).toBe(true);
    expect(matchesSourceLzScope('lz-azure-prod', scope)).toBe(false);
  });

  it('builds API params for multiple landing zones', () => {
    const scope = {
      kind: 'landing-zones' as const,
      label: '2 landing zones',
      sourceLzIds: ['lz-aws-prod', 'lz-azure-prod'],
    };

    expect(getApiLzParams(scope)).toEqual({
      source_lz_ids: ['lz-aws-prod', 'lz-azure-prod'],
    });
  });

  it('filters lists by multiple landing zones', () => {
    const scope = {
      kind: 'landing-zones' as const,
      label: '2 landing zones',
      sourceLzIds: ['lz-aws-prod', 'lz-azure-prod'],
    };

    expect(getApiSourceLzId(scope)).toBeUndefined();
    expect(
      filterBySelectedLzIds(
        [
          { source_lz_id: 'lz-aws-prod' },
          { source_lz_id: 'lz-azure-prod' },
          { source_lz_id: 'lz-other' },
        ],
        getSelectedLzIds(scope),
      ),
    ).toEqual([{ source_lz_id: 'lz-aws-prod' }, { source_lz_id: 'lz-azure-prod' }]);
  });
});
