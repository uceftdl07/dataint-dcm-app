import { waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { UserNotificationPreferences } from '../types/api';
import { createTestQueryClient, renderHookWithQueryClient } from '../test/query-client';
import { useNotificationPreferences } from './useNotificationPreferences';

const mockGetNotificationPreferences = vi.fn();
const mockUpdateNotificationPreferences = vi.fn();

vi.mock('../api/dcmApiClient', () => ({
  getNotificationPreferences: (...args: unknown[]) => mockGetNotificationPreferences(...args),
  updateNotificationPreferences: (...args: unknown[]) => mockUpdateNotificationPreferences(...args),
}));

const preferencesFixture: UserNotificationPreferences = {
  show_pipeline: true,
  show_cluster: false,
  show_cost: true,
  show_security: true,
  show_governance: false,
  show_collector_status: true,
  min_severity: 'warning',
  hide_info: false,
  email_enabled: false,
  teams_digest_enabled: false,
  notification_lz_ids: ['lz-prod'],
  updated_at: null,
  is_default: false,
};

describe('useNotificationPreferences', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetNotificationPreferences.mockResolvedValue(preferencesFixture);
    mockUpdateNotificationPreferences.mockImplementation(async (payload) => ({
      ...preferencesFixture,
      ...payload,
    }));
  });

  it('loads preferences once and updates cache after save', async () => {
    const queryClient = createTestQueryClient();
    const { result } = renderHookWithQueryClient(() => useNotificationPreferences(), { queryClient });

    await waitFor(() => expect(result.current.preferences?.show_cluster).toBe(false));

    await result.current.save({ ...preferencesFixture, show_cluster: true });

    await waitFor(() => expect(result.current.preferences?.show_cluster).toBe(true));
    expect(mockGetNotificationPreferences).toHaveBeenCalledTimes(1);
    expect(mockUpdateNotificationPreferences).toHaveBeenCalledTimes(1);
  });
});
