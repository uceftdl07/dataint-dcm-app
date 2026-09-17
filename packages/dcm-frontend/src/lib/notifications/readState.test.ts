import { beforeEach, describe, expect, it } from 'vitest';
import { isNotificationRead, markNotificationRead, markNotificationsRead } from './readState';

describe('notification read state', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('marks and reads notification state per user and alert', () => {
    expect(isNotificationRead('user-1', 'alert-1', 'lz-a')).toBe(false);
    markNotificationRead('user-1', 'alert-1', 'lz-a');
    expect(isNotificationRead('user-1', 'alert-1', 'lz-a')).toBe(true);
    expect(isNotificationRead('user-2', 'alert-1', 'lz-a')).toBe(false);
  });

  it('marks multiple notifications at once', () => {
    markNotificationsRead('user-1', [
      { alertId: 'a1', sourceLzId: 'lz-1' },
      { alertId: 'a2', sourceLzId: null },
    ]);
    expect(isNotificationRead('user-1', 'a1', 'lz-1')).toBe(true);
    expect(isNotificationRead('user-1', 'a2', null)).toBe(true);
  });
});
