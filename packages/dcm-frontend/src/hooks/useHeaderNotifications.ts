import { useMsal } from '@azure/msal-react';
import { useQuery } from '@tanstack/react-query';
import { useCallback, useMemo, useState } from 'react';
import { listSecurityAlerts } from '../api/dcmApiClient';
import { buildNotificationAlertHref } from '../lib/notifications/alertDeepLink';
import { getBellWindowApiParams } from '../lib/notifications/bellWindow';
import {
  isNotificationRead,
  markNotificationRead,
  markNotificationsRead,
} from '../lib/notifications/readState';
import { passesLandingZoneFilter, passesNotificationFilter } from '../lib/notificationFilters';
import type { SecurityAlert, UserNotificationPreferences } from '../types/api';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_NOTIFICATIONS_MS } from './query-config';
import { headerNotificationsQueryKeys } from './query-keys';
import { useNotificationPreferences } from './useNotificationPreferences';

export interface HeaderNotificationItem {
  id: string;
  sourceLzId: string | null;
  domain: 'security';
  severity: SecurityAlert['severity'];
  title: string;
  description: string | null;
  detectedAt: string;
  href: string;
  read: boolean;
}

const PREVIEW_LIMIT = 20;

function resolveUserId(homeAccountId?: string, localAccountId?: string) {
  return homeAccountId ?? localAccountId ?? '';
}

function toNotificationItem(alert: SecurityAlert, userId: string): HeaderNotificationItem {
  const sourceLzId = alert.source_lz_id ?? null;
  return {
    id: alert.alert_id,
    sourceLzId,
    domain: 'security',
    severity: alert.severity,
    title: alert.title,
    description: alert.description,
    detectedAt: alert.detected_at,
    href: buildNotificationAlertHref(alert),
    read: isNotificationRead(userId, alert.alert_id, sourceLzId),
  };
}

export function buildHeaderNotifications(
  alerts: SecurityAlert[],
  preferences: UserNotificationPreferences,
  userId: string,
): HeaderNotificationItem[] {
  return alerts
    .filter((alert) => passesLandingZoneFilter(preferences, alert.source_lz_id))
    .filter((alert) => passesNotificationFilter(preferences, 'security', alert.severity))
    .sort((left, right) => right.detected_at.localeCompare(left.detected_at))
    .slice(0, PREVIEW_LIMIT)
    .map((alert) => toNotificationItem(alert, userId));
}

export function useHeaderNotifications() {
  const { accounts } = useMsal();
  const userId = resolveUserId(accounts[0]?.homeAccountId, accounts[0]?.localAccountId);
  const { preferences, loading: preferencesLoading } = useNotificationPreferences();
  const [readTick, setReadTick] = useState(0);
  const bellWindow = useMemo(() => getBellWindowApiParams(), []);

  const alertsQuery = useQuery({
    queryKey: headerNotificationsQueryKeys.alerts(bellWindow),
    queryFn: () =>
      listSecurityAlerts({
        start_date: bellWindow.start_date,
        end_date: bellWindow.end_date,
        status: 'active',
        limit: 100,
      }),
    enabled: Boolean(preferences),
    staleTime: QUERY_STALE_NOTIFICATIONS_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
  });

  const items = useMemo(() => {
    if (!preferences) {
      return [];
    }

    return buildHeaderNotifications(alertsQuery.data?.items ?? [], preferences, userId).map(
      (item) => ({
        ...item,
        read: isNotificationRead(userId, item.id, item.sourceLzId),
      }),
    );
  }, [alertsQuery.data, preferences, readTick, userId]);

  const markAsRead = useCallback(
    (alertId: string, sourceLzId: string | null) => {
      markNotificationRead(userId, alertId, sourceLzId);
      setReadTick((value) => value + 1);
    },
    [userId],
  );

  const markAllAsRead = useCallback(() => {
    markNotificationsRead(
      userId,
      items.map((item) => ({ alertId: item.id, sourceLzId: item.sourceLzId })),
    );
    setReadTick((value) => value + 1);
  }, [items, userId]);

  const unreadCount = useMemo(() => items.filter((item) => !item.read).length, [items]);

  const refresh = useCallback(async () => {
    await alertsQuery.refetch();
  }, [alertsQuery]);

  return {
    bellWindow,
    error: alertsQuery.error instanceof Error ? alertsQuery.error.message : null,
    items,
    loading: preferencesLoading || alertsQuery.isLoading,
    markAllAsRead,
    markAsRead,
    preferences,
    refresh,
    unreadCount,
  };
}
