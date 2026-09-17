import type { UcUsageFilters } from '../../../hooks/useUcUsageQueries';
import type {
  UcUsageGovernanceSignal,
  UcUsageInactivityBucket,
  UcUsageMissingTag,
  UcUsageRecommendationAgeBucket,
} from '../../../types/api';

export interface UcGovernanceFocus {
  label: string;
  scope?: UcUsageFilters;
  signal?: UcUsageGovernanceSignal;
  inactivity?: UcUsageInactivityBucket;
  missingTag?: UcUsageMissingTag;
}

export interface UcRecommendationFocus {
  label: string;
  table?: string;
  category?: string;
  ageBucket?: UcUsageRecommendationAgeBucket;
}

export const GOVERNANCE_SIGNALS = [
  { key: 'unused', label: 'Unused' },
  { key: 'stale', label: 'Stale but read' },
  { key: 'critical', label: 'Critical' },
  { key: 'orphan', label: 'Missing ownership tags' },
] as const;

export const INACTIVITY_LABELS: Record<UcUsageInactivityBucket, string> = {
  '0_7': '0–7 days',
  '8_30': '8–30 days',
  '31_90': '31–90 days',
  over_90: 'Over 90 days',
  unobserved: 'No read observed',
};

export const AGE_LABELS: Record<UcUsageRecommendationAgeBucket, string> = {
  '0_7': '0–7 days',
  '8_30': '8–30 days',
  '31_90': '31–90 days',
  over_90: 'Over 90 days',
  unknown: 'Date unavailable',
};

export const TAG_LABELS: Record<UcUsageMissingTag, string> = {
  owner: 'Owner',
  domain: 'Domain',
  cost_center: 'Cost center',
  classification: 'Classification',
};

export const GOVERNANCE_SEVERITIES = [
  { key: 'HIGH', label: 'High', color: 'var(--danger)' },
  { key: 'MEDIUM', label: 'Medium', color: 'var(--warning)' },
  { key: 'LOW', label: 'Low', color: 'var(--tdf-blue)' },
  { key: 'UNKNOWN', label: 'Unknown', color: 'var(--tdf-grey)' },
] as const;

export function governanceIdentity(cloud: string | null | undefined, name: string): string {
  return JSON.stringify([cloud ?? '', name]);
}

export function governanceSnapshotLabel(value: string | null | undefined): string {
  if (!value) return 'Latest known state';
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return 'Latest known state';
  return `Snapshot as of ${new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'short',
    timeZone: 'UTC',
  }).format(date)}`;
}
