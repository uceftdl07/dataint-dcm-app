import type { BadgeProps } from '../../components/ui/badge';
import type { Severity, UtilizationStatus } from './format';

export function utilizationBadgeVariant(
  status: UtilizationStatus | null | undefined,
  isZombie?: boolean | null
): NonNullable<BadgeProps['variant']> {
  const s = (status || '').trim().toUpperCase();
  if (isZombie || s === 'ZOMBIE') return 'destructive';
  if (s === 'OVER') return 'warning';
  if (s === 'UNDER') return 'info';
  if (s === 'OPTIMAL') return 'success';
  return 'outline';
}

export function severityBadgeVariant(
  severity: Severity | null | undefined
): NonNullable<BadgeProps['variant']> {
  const s = (severity || '').trim().toUpperCase();
  if (s === 'HIGH') return 'warning';
  if (s === 'MEDIUM') return 'info';
  if (s === 'LOW') return 'success';
  return 'outline';
}

export function clusterTypeBadgeVariant(
  clusterType: string | null | undefined
): NonNullable<BadgeProps['variant']> {
  const s = (clusterType || '').trim().toUpperCase();
  if (s === 'JOB') return 'info';
  if (s === 'PIPELINE' || s === 'DLT') return 'warning';
  if (s === 'ALL_PURPOSE') return 'success';
  if (s === 'SQL' || s === 'SQL_WAREHOUSE') return 'secondary';
  return 'outline';
}
