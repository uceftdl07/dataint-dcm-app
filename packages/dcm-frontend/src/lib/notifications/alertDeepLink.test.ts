import { describe, expect, it } from 'vitest';
import { buildNotificationAlertHref } from './alertDeepLink';

describe('buildNotificationAlertHref', () => {
  it('builds alerts list link with alert id and landing zone', () => {
    expect(
      buildNotificationAlertHref({ alert_id: 'sec-001', source_lz_id: 'lz-prod' }),
    ).toBe('/alerts/list?status=active&source_lz_id=lz-prod&alert=sec-001');
  });

  it('omits source_lz_id when missing', () => {
    expect(buildNotificationAlertHref({ alert_id: 'sec-002', source_lz_id: null })).toBe(
      '/alerts/list?status=active&alert=sec-002',
    );
  });
});
