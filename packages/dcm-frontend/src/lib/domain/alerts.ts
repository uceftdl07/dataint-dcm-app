import type { AlertSeverity, AlertStatus, SecurityAlert } from '../../types/api';

export type AlertStatusFilter = AlertStatus | 'open' | '';
export type BadgeVariant = 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning' | 'info';

export const alertSeverityLabels: Record<AlertSeverity, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

export const alertStatusLabels: Record<AlertStatus, string> = {
  active: 'Active',
  resolved: 'Resolved',
  dismissed: 'Dismissed',
};

export const alertSeverityOrder: AlertSeverity[] = ['critical', 'high', 'medium', 'low'];
export const alertStatusOrder: AlertStatus[] = ['active', 'resolved', 'dismissed'];

export function getAlertSeverityVariant(severity: AlertSeverity): BadgeVariant {
  if (severity === 'critical') return 'destructive';
  if (severity === 'high' || severity === 'medium') return 'warning';
  return 'info';
}

export function getAlertStatusVariant(status: AlertStatus): BadgeVariant {
  if (status === 'resolved') return 'success';
  if (status === 'dismissed') return 'secondary';
  return 'destructive';
}

export function getAlertSeverityPillClass(severity: AlertSeverity) {
  if (severity === 'critical') return 'border-red-200 bg-red-50 text-red-700';
  if (severity === 'high') return 'border-orange-200 bg-orange-50 text-orange-700';
  if (severity === 'medium') return 'border-amber-200 bg-amber-50 text-amber-700';
  return 'border-sky-200 bg-sky-50 text-sky-700';
}

export function getAlertStatusPillClass(status: AlertStatus) {
  if (status === 'resolved') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (status === 'dismissed') return 'border-slate-200 bg-slate-100 text-slate-600';
  return 'border-red-200 bg-red-50 text-red-700';
}

export function getAlertSeverityBarClass(severity: AlertSeverity) {
  if (severity === 'critical') return 'bg-red-500 shadow-red-500/30';
  if (severity === 'high') return 'bg-orange-500 shadow-orange-500/30';
  if (severity === 'medium') return 'bg-amber-400 shadow-amber-400/30';
  return 'bg-sky-500 shadow-sky-500/30';
}

export interface SecurityAlertFilters {
  severity?: AlertSeverity | '';
  status?: AlertStatusFilter;
  resourceType?: string;
  resourceId?: string;
  title?: string;
  search?: string;
}

export function filterSecurityAlerts(alerts: SecurityAlert[], filters: SecurityAlertFilters) {
  const term = filters.search?.trim().toLowerCase();

  return alerts.filter((alert) => {
    if (filters.severity && alert.severity !== filters.severity) return false;
    if (filters.resourceType && alert.resource_type !== filters.resourceType) return false;
    if (filters.resourceId && alert.resource_id !== filters.resourceId) return false;
    if (filters.title && alert.title !== filters.title) return false;
    if (filters.status === 'open' && alert.status === 'resolved') return false;
    if (filters.status && filters.status !== 'open' && alert.status !== filters.status) return false;
    if (!term) return true;

    return [alert.title, alert.description, alert.resource_id, alert.resource_type, alert.source_lz_id]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(term));
  });
}

export function getSecurityAlertCounts(alerts: SecurityAlert[], resourceTypeCount: number) {
  return {
    critical: alerts.filter((alert) => alert.severity === 'critical').length,
    high: alerts.filter((alert) => alert.severity === 'high').length,
    active: alerts.filter((alert) => alert.status === 'active').length,
    resolved: alerts.filter((alert) => alert.status === 'resolved').length,
    resourceTypes: resourceTypeCount,
  };
}
