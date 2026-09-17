import { waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LandingZonesResponse, UserNotificationPreferences } from '../types/api';
import {
  QUERY_GC_DEFAULT_MS,
  QUERY_STALE_DEFAULT_MS,
  QUERY_STALE_NOTIFICATIONS_MS,
} from './query-config';
import { createTestQueryClient, renderHookWithQueryClient } from '../test/query-client';
import { useDatabricksWorkspacesList } from './useDatabricksWorkspacesList';
import { useLandingZonesList } from './useLandingZonesList';
import { useNotificationPreferences } from './useNotificationPreferences';

const mockListLandingZones = vi.fn();
const mockListDatabricksWorkspaces = vi.fn();
const mockGetNotificationPreferences = vi.fn();
const mockUpdateNotificationPreferences = vi.fn();

vi.mock('../api/dcmApiClient', () => ({
  getNotificationPreferences: (...args: unknown[]) => mockGetNotificationPreferences(...args),
  listDatabricksWorkspaces: (...args: unknown[]) => mockListDatabricksWorkspaces(...args),
  listLandingZones: (...args: unknown[]) => mockListLandingZones(...args),
  updateNotificationPreferences: (...args: unknown[]) => mockUpdateNotificationPreferences(...args),
}));

const landingZonesFixture = {
  items: [
    {
      lz_id: 'lz-001',
      lz_name: 'analytics-prod',
      cloud_provider: 'azure',
      subscription_or_account_id: 'sub-001',
      environment: 'prod',
      ba_name: 'Analytics',
      valid_from: '2026-01-01',
    },
  ],
  total: 1,
} satisfies LandingZonesResponse;

const preferencesFixture: UserNotificationPreferences = {
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
  notification_lz_ids: [],
  updated_at: null,
  is_default: true,
};

describe('data fetching performance', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListLandingZones.mockResolvedValue(landingZonesFixture);
    mockListDatabricksWorkspaces.mockResolvedValue({ items: [], total: 0 });
    mockGetNotificationPreferences.mockResolvedValue(preferencesFixture);
    mockUpdateNotificationPreferences.mockImplementation(async (payload) => ({
      ...preferencesFixture,
      ...payload,
      is_default: false,
    }));
  });

  it('deduplicates landing zone requests across concurrent subscribers', async () => {
    const queryClient = createTestQueryClient();
    const wrapper = renderHookWithQueryClient(() => useLandingZonesList(), { queryClient });
    const second = renderHookWithQueryClient(() => useLandingZonesList(), { queryClient });

    await waitFor(() => {
      expect(wrapper.result.current.isSuccess).toBe(true);
      expect(second.result.current.isSuccess).toBe(true);
    });

    expect(mockListLandingZones).toHaveBeenCalledTimes(1);
  });

  it('reuses cached landing zones when remounting within staleTime', async () => {
    const queryClient = createTestQueryClient();
    const first = renderHookWithQueryClient(() => useLandingZonesList(), { queryClient });

    await waitFor(() => expect(first.result.current.isSuccess).toBe(true));
    expect(mockListLandingZones).toHaveBeenCalledTimes(1);

    first.unmount();

    const second = renderHookWithQueryClient(() => useLandingZonesList(), { queryClient });
    await waitFor(() => expect(second.result.current.isSuccess).toBe(true));

    expect(mockListLandingZones).toHaveBeenCalledTimes(1);
  });

  it('shares landing zone cache between Header and Settings consumers', async () => {
    const queryClient = createTestQueryClient();
    const header = renderHookWithQueryClient(() => useLandingZonesList(true), { queryClient });
    const settings = renderHookWithQueryClient(() => useLandingZonesList(true), { queryClient });

    await waitFor(() => {
      expect(header.result.current.data?.items).toHaveLength(1);
      expect(settings.result.current.data?.items).toHaveLength(1);
    });

    expect(mockListLandingZones).toHaveBeenCalledTimes(1);
  });

  it('deduplicates notification preference reads across subscribers', async () => {
    const queryClient = createTestQueryClient();
    const bell = renderHookWithQueryClient(() => useNotificationPreferences(), { queryClient });
    const settings = renderHookWithQueryClient(() => useNotificationPreferences(), { queryClient });

    await waitFor(() => {
      expect(bell.result.current.preferences).not.toBeNull();
      expect(settings.result.current.preferences).not.toBeNull();
    });

    expect(mockGetNotificationPreferences).toHaveBeenCalledTimes(1);
  });

  it('does not refetch workspaces when query is disabled', async () => {
    renderHookWithQueryClient(() => useDatabricksWorkspacesList(false));

    await waitFor(() => {
      expect(mockListDatabricksWorkspaces).not.toHaveBeenCalled();
    });
  });

  it('uses performance-oriented cache timings', () => {
    expect(QUERY_STALE_DEFAULT_MS).toBeGreaterThanOrEqual(5 * 60 * 1000);
    expect(QUERY_GC_DEFAULT_MS).toBeGreaterThan(QUERY_STALE_DEFAULT_MS);
    expect(QUERY_STALE_NOTIFICATIONS_MS).toBeLessThanOrEqual(QUERY_STALE_DEFAULT_MS);
  });
});
