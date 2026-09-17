import { describe, expect, it } from 'vitest';
import { dashboardQueryKeys, landingZonesQueryKeys } from './query-keys';

describe('dashboardQueryKeys', () => {
  it('includes date range and cloud provider in the dashboard data key', () => {
    expect(dashboardQueryKeys.data({
      start_date: '2026-04-25',
      end_date: '2026-05-25',
      cloud_provider: 'azure',
    })).toEqual([
      'dashboard',
      'full',
      {
        start_date: '2026-04-25',
        end_date: '2026-05-25',
        cloud_provider: 'azure',
        source_lz_id: 'all',
        source_lz_ids: 'all',
        workspace_id: 'all',
        workspace_ids: 'all',
      },
    ]);
  });

  it('normalizes an omitted cloud provider to all', () => {
    expect(dashboardQueryKeys.data({
      start_date: '2026-04-25',
      end_date: '2026-05-25',
    })[2]).toMatchObject({ cloud_provider: 'all' });
  });
});

describe('shared query keys', () => {
  it('uses stable landing zone list keys for cache sharing', () => {
    expect(landingZonesQueryKeys.list()).toEqual(['landing-zones', 'list']);
  });
});
