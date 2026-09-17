import type {
  AlertSeverity,
  NotificationMinSeverity,
  UserNotificationPreferences,
} from '../types/api';

export type NotificationDomain =
  | 'pipeline'
  | 'cluster'
  | 'cost'
  | 'security'
  | 'governance'
  | 'collector';

const SEVERITY_RANK: Record<AlertSeverity, number> = {
  low: 1,
  medium: 2,
  high: 3,
  critical: 4,
};

const MIN_SEVERITY_RANK: Record<NotificationMinSeverity, number> = {
  info: 1,
  warning: 3,
  critical: 4,
};

export function isDomainEnabled(
  preferences: UserNotificationPreferences,
  domain: NotificationDomain,
): boolean {
  switch (domain) {
    case 'pipeline':
      return preferences.show_pipeline;
    case 'cluster':
      return preferences.show_cluster;
    case 'cost':
      return preferences.show_cost;
    case 'security':
      return preferences.show_security;
    case 'governance':
      return preferences.show_governance;
    case 'collector':
      return preferences.show_collector_status;
    default:
      return true;
  }
}

export function passesSeverityFilter(
  preferences: UserNotificationPreferences,
  severity: AlertSeverity,
): boolean {
  if (preferences.hide_info && SEVERITY_RANK[severity] <= 2) {
    return false;
  }

  return SEVERITY_RANK[severity] >= MIN_SEVERITY_RANK[preferences.min_severity];
}

/** Security critical alerts stay visible even when the security domain is toggled off. */
export function passesNotificationFilter(
  preferences: UserNotificationPreferences,
  domain: NotificationDomain,
  severity: AlertSeverity,
): boolean {
  if (domain === 'security' && severity === 'critical') {
    return passesSeverityFilter(preferences, severity);
  }

  if (!isDomainEnabled(preferences, domain)) {
    return false;
  }

  return passesSeverityFilter(preferences, severity);
}

/** Empty notification_lz_ids = no extra LZ filter (all allowed zones). */
export function passesLandingZoneFilter(
  preferences: UserNotificationPreferences,
  sourceLzId: string | null | undefined,
): boolean {
  const allowed = preferences.notification_lz_ids ?? [];
  if (allowed.length === 0) {
    return true;
  }
  if (!sourceLzId) {
    return false;
  }
  return allowed.includes(sourceLzId);
}
