import { describe, expect, it } from 'vitest';
import { monitoringScopeDefaults } from '../contexts/monitoring-scope';
import { matchesSourceLzScope } from '../lib/monitoring-scope-filter';
import type { SecurityAlert } from '../types/api';

function filterAlertsLikePage(
  alerts: SecurityAlert[],
  options: {
    scope: typeof monitoringScopeDefaults.all;
    focusAlertId?: string;
    deepLinkSourceLzId?: string;
    status?: string;
  },
) {
  const scopedAlerts = options.deepLinkSourceLzId
    ? alerts.filter((alert) => alert.source_lz_id === options.deepLinkSourceLzId)
    : alerts.filter((alert) => matchesSourceLzScope(alert.source_lz_id, options.scope));

  if (options.focusAlertId) {
    const focused = scopedAlerts.filter((alert) => alert.alert_id === options.focusAlertId);
    if (focused.length > 0) {
      return focused;
    }
  }

  return scopedAlerts.filter((alert) => !options.status || alert.status === options.status);
}

const sampleAlerts: SecurityAlert[] = [
  {
    alert_id: 'alert-1',
    title: 'Suspicious login',
    description: 'Detected on workspace',
    severity: 'high',
    status: 'active',
    cloud_provider: 'azure',
    source_lz_id: 'sub-iasp-lz-DataSquad',
    resource_id: 'res-1',
    resource_type: 'workspace',
    detected_at: '2026-06-01T10:00:00Z',
  },
  {
    alert_id: 'alert-2',
    title: 'Public bucket',
    description: 'S3 exposure',
    severity: 'critical',
    status: 'active',
    cloud_provider: 'aws',
    source_lz_id: 'awsp-wl-MTEDSDataEngP',
    resource_id: 'res-2',
    resource_type: 'bucket',
    detected_at: '2026-06-02T10:00:00Z',
  },
];

describe('alert notification deep link filtering', () => {
  it('shows focused alert even when header scope excludes its landing zone', () => {
    const scope = {
      kind: 'landing-zones' as const,
      label: 'awsp-wl-MTEDSDataEngP',
      sourceLzIds: ['awsp-wl-MTEDSDataEngP'],
    };

    const result = filterAlertsLikePage(sampleAlerts, {
      scope,
      focusAlertId: 'alert-1',
      deepLinkSourceLzId: 'sub-iasp-lz-DataSquad',
      status: 'active',
    });

    expect(result).toHaveLength(1);
    expect(result[0]?.alert_id).toBe('alert-1');
  });

  it('does not treat alert id as free-text search', () => {
    const result = filterAlertsLikePage(sampleAlerts, {
      scope: monitoringScopeDefaults.all,
      focusAlertId: 'alert-2',
      status: 'active',
    });

    expect(result).toHaveLength(1);
    expect(result[0]?.title).toBe('Public bucket');
  });
});
