import { describe, expect, it } from 'vitest';
import { passesLandingZoneFilter, passesNotificationFilter } from './notificationFilters';
import type { UserNotificationPreferences } from '../types/api';

const basePreferences: UserNotificationPreferences = {
  show_pipeline: true,
  show_cluster: true,
  show_cost: true,
  show_security: false,
  show_governance: true,
  show_collector_status: true,
  min_severity: 'warning',
  hide_info: false,
  email_enabled: false,
  teams_digest_enabled: false,
  notification_lz_ids: [],
  updated_at: null,
  is_default: true,
};

describe('passesNotificationFilter', () => {
  it('keeps critical security alerts when the security domain is disabled', () => {
    expect(passesNotificationFilter(basePreferences, 'security', 'critical')).toBe(true);
  });

  it('drops non-critical security alerts when the security domain is disabled', () => {
    expect(passesNotificationFilter(basePreferences, 'security', 'high')).toBe(false);
  });

  it('respects the minimum severity threshold', () => {
    const preferences = { ...basePreferences, show_security: true, min_severity: 'critical' as const };

    expect(passesNotificationFilter(preferences, 'security', 'high')).toBe(false);
    expect(passesNotificationFilter(preferences, 'security', 'critical')).toBe(true);
  });

  it('allows any landing zone when notification_lz_ids is empty', () => {
    expect(passesLandingZoneFilter(basePreferences, 'lz-001')).toBe(true);
    expect(passesLandingZoneFilter(basePreferences, null)).toBe(true);
  });

  it('filters alerts to selected landing zones', () => {
    const preferences = { ...basePreferences, notification_lz_ids: ['lz-001'] };

    expect(passesLandingZoneFilter(preferences, 'lz-001')).toBe(true);
    expect(passesLandingZoneFilter(preferences, 'lz-002')).toBe(false);
    expect(passesLandingZoneFilter(preferences, null)).toBe(false);
  });

  it('hides info-level alerts when hide_info is enabled', () => {
    const preferences = {
      ...basePreferences,
      show_security: true,
      min_severity: 'info' as const,
      hide_info: true,
    };

    expect(passesNotificationFilter(preferences, 'security', 'low')).toBe(false);
    expect(passesNotificationFilter(preferences, 'security', 'high')).toBe(true);
  });
});
