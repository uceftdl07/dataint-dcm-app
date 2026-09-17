import type { StandardCheck, StandardCheckState } from '../../types/api';
import type { BadgeVariant } from './alerts';

export type CheckEffectFilter = '' | 'critical' | 'warning' | 'info' | 'other';

export const standardCheckStateLabels: Record<StandardCheckState, string> = {
  compliant: 'Compliant',
  no_compliant: 'Non-compliant',
  non_compliant: 'Non-compliant',
  unknown: 'Unknown',
};

function isNonCompliantState(state: StandardCheckState) {
  return state === 'no_compliant' || state === 'non_compliant';
}

export function normalizeCheckEffect(effect: string | null): CheckEffectFilter {
  const value = effect?.toLowerCase();
  if (value === 'critical' || value === 'warning' || value === 'info') return value;
  return 'other';
}

export function getStandardCheckStateVariant(state: StandardCheckState): BadgeVariant {
  if (state === 'compliant') return 'success';
  if (isNonCompliantState(state)) return 'destructive';
  return 'warning';
}

export function getStandardCheckStatePillClass(state: StandardCheckState) {
  if (state === 'compliant') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (isNonCompliantState(state)) return 'border-red-200 bg-red-50 text-red-700';
  return 'border-orange-200 bg-orange-50 text-orange-700';
}

export function getStandardCheckStateBarClass(state: StandardCheckState) {
  if (state === 'compliant') return 'bg-emerald-500 shadow-emerald-500/30';
  if (isNonCompliantState(state)) return 'bg-red-500 shadow-red-500/30';
  return 'bg-orange-500 shadow-orange-500/30';
}

export function getCheckEffectPillClass(effect: string | null) {
  const normalized = normalizeCheckEffect(effect);
  if (normalized === 'critical') return 'border-red-200 bg-red-50 text-red-700';
  if (normalized === 'warning') return 'border-orange-200 bg-orange-50 text-orange-700';
  if (normalized === 'info') return 'border-sky-200 bg-sky-50 text-sky-700';
  return 'border-slate-200 bg-slate-100 text-slate-600';
}

export interface StandardCheckFilters {
  state?: StandardCheckState | '';
  resourceType?: string;
  effect?: CheckEffectFilter;
  source?: string;
  search?: string;
}

function matchesStandardCheckSearch(check: StandardCheck, search: string) {
  const term = search.trim().toLowerCase();
  if (!term) return true;
  return [
    check.check_name,
    check.resource_name,
    check.resource_id,
    check.resource_type,
    check.source_lz_id,
    check.check_effect,
    ...(Array.isArray(check.no_check_reasons) ? check.no_check_reasons : check.no_check_reasons ? [String(check.no_check_reasons)] : []),
  ]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(term));
}

export function filterStandardChecks(checks: StandardCheck[], filters: StandardCheckFilters) {
  return checks.filter((check) => {
    if (filters.state && filters.state === 'no_compliant' && !isNonCompliantState(check.check_state)) return false;
    if (filters.state && filters.state !== 'no_compliant' && check.check_state !== filters.state) return false;
    if (filters.resourceType && check.resource_type !== filters.resourceType) return false;
    if (filters.effect && normalizeCheckEffect(check.check_effect) !== filters.effect) return false;
    if (filters.source && check.source_lz_id !== filters.source) return false;
    if (filters.search && !matchesStandardCheckSearch(check, filters.search)) return false;
    return true;
  });
}

export function getStandardCheckCounts(checks: StandardCheck[], resourceTypeCount: number) {
  return {
    compliant: checks.filter((check) => check.check_state === 'compliant').length,
    noCompliant: checks.filter((check) => isNonCompliantState(check.check_state)).length,
    unknown: checks.filter((check) => check.check_state === 'unknown').length,
    resources: resourceTypeCount,
  };
}
