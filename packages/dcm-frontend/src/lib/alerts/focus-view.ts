import type { AlertSeverity, AlertStatus } from '../../types/api';

export const ALERTS_FOCUS_VIEWS = ['list'] as const;
export type AlertsFocusView = (typeof ALERTS_FOCUS_VIEWS)[number];

export const ALERTS_FOCUS_VIEW_LABELS: Record<AlertsFocusView, string> = {
  list: 'Security alerts',
};

export const ALERTS_FOCUS_VIEW_DESCRIPTIONS: Record<AlertsFocusView, string> = {
  list: 'Active and historical alerts. Click a row to expand full details.',
};

export function parseAlertsFocusView(value: string | null): AlertsFocusView | null {
  if (!value) return null;
  return ALERTS_FOCUS_VIEWS.includes(value as AlertsFocusView) ? (value as AlertsFocusView) : null;
}

export function parseAlertSeverityFromUrl(value: string | null): AlertSeverity | '' {
  const valid: AlertSeverity[] = ['critical', 'high', 'medium', 'low'];
  if (!value) return '';
  return valid.includes(value as AlertSeverity) ? (value as AlertSeverity) : '';
}

export function parseAlertStatusFromUrl(value: string | null): AlertStatus | '' {
  const valid: AlertStatus[] = ['active', 'resolved', 'dismissed'];
  if (!value) return '';
  return valid.includes(value as AlertStatus) ? (value as AlertStatus) : '';
}

export function buildAlertsFocusPath(
  view: AlertsFocusView,
  params?: { severity?: AlertSeverity; status?: AlertStatus },
): string {
  const search = new URLSearchParams();
  if (params?.severity) search.set('severity', params.severity);
  if (params?.status) search.set('status', params.status);
  const query = search.toString();
  return `/alerts/${view}${query ? `?${query}` : ''}`;
}
