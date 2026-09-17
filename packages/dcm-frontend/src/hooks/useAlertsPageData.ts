import { useCallback, useMemo, useState } from 'react';
import { listSecurityAlerts } from '../api/dcmApiClient';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { getBellWindowApiParams } from '../lib/notifications/bellWindow';
import { matchesSourceLzScope } from '../lib/monitoring-scope-filter';
import { useGlobalTimeRange } from '../contexts/time-range';
import type { AlertSeverity, AlertStatus, SecurityAlert } from '../types/api';
import { useStagedListFetch } from './useStagedQueries';

export interface UseAlertsPageDataOptions {
  initialSeverity?: AlertSeverity | '';
  initialStatus?: AlertStatus | '';
  focusAlertId?: string;
  deepLinkSourceLzId?: string;
}

export function useAlertsPageData(options: UseAlertsPageDataOptions = {}) {
  const { focusAlertId, deepLinkSourceLzId } = options;
  const { getApiParams } = useGlobalTimeRange();
  const { scope, getScopedParams } = useMonitoringScope();
  const [severity, setSeverity] = useState<AlertSeverity | ''>(options.initialSeverity ?? '');
  const [status, setStatus] = useState<AlertStatus | ''>(options.initialStatus ?? 'active');
  const [search, setSearch] = useState('');

  const { start_date, end_date } = focusAlertId ? getBellWindowApiParams() : getApiParams();
  const scopedParams = getScopedParams({ cloudProvider: true, sourceLzId: true });

  const {
    items: alerts,
    loading,
    loadingDetails,
    error,
    reload: load,
  } = useStagedListFetch<SecurityAlert, { items: SecurityAlert[]; total: number }>(
    (limit) => listSecurityAlerts({
      start_date,
      end_date,
      cloud_provider: scopedParams.cloud_provider,
      ...(deepLinkSourceLzId
        ? { source_lz_id: deepLinkSourceLzId }
        : {
            source_lz_id: scopedParams.source_lz_id,
            source_lz_ids: scopedParams.source_lz_ids,
          }),
      limit,
    }),
    [
      deepLinkSourceLzId,
      end_date,
      focusAlertId,
      scopedParams.cloud_provider,
      scopedParams.source_lz_id,
      scopedParams.source_lz_ids,
      start_date,
    ],
  );

  const scopedAlerts = useMemo(() => {
    if (deepLinkSourceLzId) {
      return alerts.filter((alert) => alert.source_lz_id === deepLinkSourceLzId);
    }
    return alerts.filter((alert) => matchesSourceLzScope(alert.source_lz_id, scope));
  }, [alerts, deepLinkSourceLzId, scope]);

  const filteredAlerts = useMemo(() => {
    if (focusAlertId) {
      const focused = scopedAlerts.filter((alert) => alert.alert_id === focusAlertId);
      if (focused.length > 0) {
        return focused;
      }
    }

    const term = search.trim().toLowerCase();
    return scopedAlerts.filter((alert) => {
      const matchesSeverity = !severity || alert.severity === severity;
      const matchesStatus = !status || alert.status === status;
      const matchesSearch =
        !term
        || [alert.alert_id, alert.title, alert.description, alert.resource_id, alert.resource_type]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(term));
      return matchesSeverity && matchesStatus && matchesSearch;
    });
  }, [focusAlertId, scopedAlerts, search, severity, status]);

  const focusedAlertFound = Boolean(
    focusAlertId && scopedAlerts.some((alert) => alert.alert_id === focusAlertId),
  );

  const criticalCount = scopedAlerts.filter((a) => a.severity === 'critical').length;
  const highCount = scopedAlerts.filter((a) => a.severity === 'high').length;
  const activeCount = scopedAlerts.filter((a) => a.status === 'active').length;

  const resetFilters = useCallback(() => {
    setSeverity('');
    setStatus('');
    setSearch('');
  }, []);

  return {
    activeCount,
    criticalCount,
    error,
    focusedAlertFound,
    filteredAlerts,
    highCount,
    load,
    loading,
    loadingDetails,
    resetFilters,
    scope,
    scopedAlerts,
    search,
    setSearch,
    setSeverity,
    setStatus,
    severity,
    status,
  };
}
