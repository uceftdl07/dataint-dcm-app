import type { SecurityAlert } from '../../types/api';

/**
 * Bell notification deep link.
 * Phase 3 will add `/alerts/:alertId`; until then list view with query params.
 */
export function buildNotificationAlertHref(
  alert: Pick<SecurityAlert, 'alert_id' | 'source_lz_id'>,
): string {
  const params = new URLSearchParams({ status: 'active' });
  if (alert.source_lz_id) {
    params.set('source_lz_id', alert.source_lz_id);
  }
  params.set('alert', alert.alert_id);
  return `/alerts/list?${params.toString()}`;
}
