import type { MonitoringScope } from '../contexts/monitoring-scope';
import type { CloudProvider, LandingZoneAccessOverviewItem } from '../types/api';

function landingZoneScopeLabel(item: Pick<LandingZoneAccessOverviewItem, 'lz_id' | 'lz_name' | 'environment' | 'cloud_provider'>): string {
  const environment =
    item.environment && item.environment.toLowerCase() !== 'unknown'
      ? item.environment
      : null;

  return [item.lz_name || item.lz_id, environment, item.cloud_provider.toUpperCase()]
    .filter(Boolean)
    .join(' · ');
}

export function buildLandingZoneMonitoringScope(
  item: Pick<
    LandingZoneAccessOverviewItem,
    'lz_id' | 'lz_name' | 'environment' | 'cloud_provider' | 'subscription_or_account_id'
  >,
): MonitoringScope {
  return {
    kind: 'landing-zone',
    label: `Landing Zone - ${landingZoneScopeLabel(item)}`,
    cloudProvider: item.cloud_provider as CloudProvider,
    sourceLzId: item.lz_id,
    environment: item.environment && item.environment.toLowerCase() !== 'unknown'
      ? item.environment
      : undefined,
    subscriptionOrAccountId: item.subscription_or_account_id ?? undefined,
  };
}
