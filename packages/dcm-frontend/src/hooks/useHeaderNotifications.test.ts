import { act, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { UserNotificationPreferences } from '../types/api';
import { createTestQueryClient, renderHookWithQueryClient } from '../test/query-client';
import { buildHeaderNotifications, useHeaderNotifications } from './useHeaderNotifications';

const mockListSecurityAlerts = vi.fn();
const mockGetNotificationPreferences = vi.fn();

const mockPreferences: UserNotificationPreferences = {
  show_pipeline: true,
  show_cluster: true,
  show_cost: true,
  show_security: true,
  show_governance: true,
  show_collector_status: true,
  min_severity: 'warning',
  hide_info: false,
  email_enabled: false,
  teams_digest_enabled: false,
  notification_lz_ids: ['lz-prod'],
  updated_at: null,
  is_default: false,
};

vi.mock('@azure/msal-react', () => ({
  useMsal: () => ({
    accounts: [{ homeAccountId: 'user-1', localAccountId: 'user-1' }],
  }),
}));

vi.mock('../api/dcmApiClient', () => ({
  getNotificationPreferences: (...args: unknown[]) => mockGetNotificationPreferences(...args),
  listSecurityAlerts: (...args: unknown[]) => mockListSecurityAlerts(...args),
  updateNotificationPreferences: vi.fn(),
}));

describe('useHeaderNotifications', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    mockGetNotificationPreferences.mockResolvedValue(mockPreferences);
    mockListSecurityAlerts.mockResolvedValue({
      items: [
        {
          alert_id: 'a1',
          source_lz_id: 'lz-prod',
          severity: 'high',
          title: 'Prod alert',
          description: 'desc',
          detected_at: '2026-06-04T10:00:00Z',
          status: 'active',
        },
        {
          alert_id: 'a2',
          source_lz_id: 'lz-dev',
          severity: 'critical',
          title: 'Dev alert',
          description: null,
          detected_at: '2026-06-03T10:00:00Z',
          status: 'active',
        },
      ],
    });
  });

  it('uses a 90-day window without header scope params', async () => {
    const { result } = renderHookWithQueryClient(() => useHeaderNotifications());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(mockListSecurityAlerts).toHaveBeenCalledWith(
      expect.objectContaining({
        status: 'active',
        start_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
        end_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      }),
    );
    expect(mockListSecurityAlerts.mock.calls[0][0]).not.toHaveProperty('cloud_provider');
    expect(mockListSecurityAlerts.mock.calls[0][0]).not.toHaveProperty('source_lz_id');
  });

  it('filters by notification preferences and tracks unread count', async () => {
    const { result } = renderHookWithQueryClient(() => useHeaderNotifications());

    await waitFor(() => {
      expect(result.current.items).toHaveLength(1);
    });

    expect(result.current.items[0].id).toBe('a1');
    expect(result.current.items[0].href).toContain('/alerts/list?');
    expect(result.current.unreadCount).toBe(1);

    act(() => {
      result.current.markAsRead('a1', 'lz-prod');
    });

    expect(result.current.unreadCount).toBe(0);
    expect(result.current.items[0].read).toBe(true);
  });

  it('reuses cached security alerts when hook remounts within staleTime', async () => {
    const queryClient = createTestQueryClient();
    const first = renderHookWithQueryClient(() => useHeaderNotifications(), { queryClient });

    await waitFor(() => expect(first.result.current.items).toHaveLength(1));
    expect(mockListSecurityAlerts).toHaveBeenCalledTimes(1);

    first.unmount();

    const second = renderHookWithQueryClient(() => useHeaderNotifications(), { queryClient });
    await waitFor(() => expect(second.result.current.items).toHaveLength(1));

    expect(mockListSecurityAlerts).toHaveBeenCalledTimes(1);
    expect(mockGetNotificationPreferences).toHaveBeenCalledTimes(1);
  });
});

describe('buildHeaderNotifications', () => {
  it('filters alerts by landing zone and severity preferences', () => {
    const items = buildHeaderNotifications(
      [
        {
          alert_id: 'a1',
          source_lz_id: 'lz-prod',
          severity: 'high',
          title: 'Prod alert',
          description: null,
          detected_at: '2026-06-04T10:00:00Z',
          status: 'active',
        },
        {
          alert_id: 'a2',
          source_lz_id: 'lz-dev',
          severity: 'critical',
          title: 'Dev alert',
          description: null,
          detected_at: '2026-06-03T10:00:00Z',
          status: 'active',
        },
      ],
      mockPreferences,
      'user-1',
    );

    expect(items).toHaveLength(1);
    expect(items[0].id).toBe('a1');
  });
});
