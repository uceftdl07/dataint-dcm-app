/** Libellés et formats propres au module Usage des tables UC. */

import type { UcUsageRegistryRow } from '../../types/api';

/** Le tag UC `owner` est absent sur la quasi-totalité du parc (FR-012). */
export const OWNER_FALLBACK = 'Unknown';

export function ucUsageOwnerLabel(owner: string | null | undefined): string {
  return owner?.trim() || OWNER_FALLBACK;
}

/**
 * Statut dérivé du **mot-clé** `recommended_action`, vocabulaire fermé à trois
 * valeurs plus `null` — jamais du texte libre d'une recommandation (FR-012).
 */
export function ucUsageRegistryStatus(row: Pick<UcUsageRegistryRow, 'recommended_action'>): {
  label: string;
  variant: 'destructive' | 'warning' | 'info' | 'success';
} {
  switch ((row.recommended_action ?? '').trim().toLowerCase()) {
    case 'archiver':
      return { label: 'Unused', variant: 'destructive' };
    case 'documenter':
      return { label: 'Orphaned', variant: 'warning' };
    case 'surveiller':
      return { label: 'Stale but consumed', variant: 'info' };
    default:
      return { label: 'OK', variant: 'success' };
  }
}

const OPERATION_LABELS: Record<string, string> = {
  createtable: 'Created',
  deletetable: 'Deleted',
  updatetables: 'Updated',
};

/** Vocabulaire fermé côté audit UC ; une valeur inattendue s'affiche brute. */
export function ucUsageOperationLabel(value: string | null | undefined): string {
  const raw = (value ?? '').trim();
  if (!raw) return '—';
  return OPERATION_LABELS[raw.toLowerCase()] ?? raw;
}

const CATEGORY_LABELS: Record<string, string> = {
  LIFECYCLE: 'Lifecycle',
  FRESHNESS: 'Write freshness',
  GOVERNANCE: 'Governance',
  RELIABILITY: 'Reliability',
  FINOPS: 'FinOps',
};

/** Liste fermée à 5 catégories (FR-013). */
export const UC_USAGE_RECOMMENDATION_CATEGORIES = [
  'LIFECYCLE',
  'FRESHNESS',
  'GOVERNANCE',
  'RELIABILITY',
  'FINOPS',
] as const;

export function ucUsageCategoryLabel(value: string | null | undefined): string {
  const raw = (value ?? '').trim();
  if (!raw) return '—';
  return CATEGORY_LABELS[raw.toUpperCase()] ?? raw;
}

const BYTE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'] as const;

/** `null` reste un tiret : une absence de mesure n'est pas un volume nul. */
export function formatBytes(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const bytes = Number(value);
  if (bytes === 0) return '0 B';
  const exponent = Math.max(
    0,
    Math.min(BYTE_UNITS.length - 1, Math.floor(Math.log(Math.abs(bytes)) / Math.log(1024)))
  );
  const scaled = bytes / 1024 ** exponent;
  return `${scaled.toLocaleString('en-US', {
    maximumFractionDigits: exponent === 0 ? 0 : 1,
  })} ${BYTE_UNITS[exponent]}`;
}

export function formatMilliseconds(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const ms = Number(value);
  if (ms < 1000) return `${ms.toLocaleString('en-US', { maximumFractionDigits: 0 })} ms`;
  return `${(ms / 1000).toLocaleString('en-US', { maximumFractionDigits: 2 })} s`;
}

export function formatIsoDate(value: string | null | undefined): string {
  const raw = (value ?? '').trim();
  if (!raw) return '—';
  return raw.slice(0, 10);
}

/** Fraîcheur lue comme dans le mockup : une ancienneté d'écriture, pas un nombre d'heures brut. */
export function ucUsageFreshnessLabel(hours: number | null | undefined): string {
  if (hours == null || Number.isNaN(Number(hours))) return '—';
  const value = Number(hours);
  if (value < 1) return 'Written less than 1 hour ago';
  if (value < 48) return `Written ${Math.round(value)} hours ago`;
  return `Written ${Math.round(value / 24)} days ago`;
}

/**
 * Une couleur par type de consommateur, comme au mockup : la colonne Type se lit
 * d'un coup d'œil. Vocabulaire ouvert — une valeur inconnue reste neutre.
 */
const CONSUMER_TYPE_BADGE_CLASS: Record<string, string> = {
  SERVICE_PRINCIPAL: 'border-info-border bg-info-subtle text-info',
  DASHBOARD: 'border-purple-border bg-purple-subtle text-purple',
  DASHBOARD_V3: 'border-purple-border bg-purple-subtle text-purple',
  JOB: 'border-warning-border bg-warning-subtle text-warning',
  PIPELINE: 'border-success-border bg-success-subtle text-success',
  NOTEBOOK: 'border-border bg-secondary text-secondary-foreground',
  USER: 'border-border bg-secondary text-secondary-foreground',
};

export function ucUsageConsumerTypeBadgeClass(value: string | null | undefined): string {
  const raw = (value ?? '').trim().toUpperCase();
  return CONSUMER_TYPE_BADGE_CLASS[raw] ?? 'border-border bg-card text-muted-foreground';
}

/** Seuil d'alerte du mockup : au-delà, le taux d'échec se lit en rouge. */
export const UC_USAGE_FAILURE_RATE_ALERT_PCT = 1;

/**
 * `freshness_basis = table_altered` n'est pas une preuve d'écriture : la
 * fraîcheur qui en découle est une estimation, et doit se lire comme telle.
 */
export function ucUsageFreshnessIsEstimate(basis: string | null | undefined): boolean {
  return (basis ?? '').trim().toLowerCase() === 'table_altered';
}

/** Horizon réel de `gold_dbx_usage_forecast_daily` : sept jours (SC-004). */
export const UC_USAGE_FORECAST_HORIZON_LABEL = '+7d';

/**
 * Valeurs constatées de `entity_type` dans le lineage. **Pas de `GENIE`** : le
 * chantier DataEng n'a pas démarré, l'offrir filtrerait toujours sur zéro ligne.
 * Le vocabulaire reste ouvert côté données — une valeur hors liste doit être
 * affichée telle quelle, jamais masquée.
 */
export const UC_USAGE_CONSUMER_TYPES = [
  'USER',
  'SERVICE_PRINCIPAL',
  'JOB',
  'NOTEBOOK',
  'PIPELINE',
  'DASHBOARD_V3',
  'UNKNOWN',
] as const;
