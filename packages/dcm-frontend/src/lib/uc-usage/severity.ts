/**
 * Normalisation de la sévérité entre les deux onglets (FR-015).
 *
 * `gold_dbx_usage_recommendations` écrit `HIGH`/`MEDIUM`/`LOW`,
 * `gold_dbx_usage_table_governance` écrit `high`/`medium`/`low`. La comparaison
 * se fait ici, en amont du rendu : passer les deux casses au même composant de
 * badge sans normaliser afficherait deux pastilles différentes pour une même
 * criticité.
 */

export type UcUsageSeverity = 'high' | 'medium' | 'low';

const KNOWN: readonly UcUsageSeverity[] = ['high', 'medium', 'low'];

const LABELS: Record<UcUsageSeverity, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

/** Rang de tri décroissant : `high` d'abord. */
const RANKS: Record<UcUsageSeverity, number> = { high: 0, medium: 1, low: 2 };

export function normalizeUcUsageSeverity(value: string | null | undefined): UcUsageSeverity | null {
  const normalized = (value ?? '').trim().toLowerCase();
  return KNOWN.includes(normalized as UcUsageSeverity) ? (normalized as UcUsageSeverity) : null;
}

/**
 * Libellé affiché. Une valeur hors vocabulaire est rendue telle quelle plutôt
 * que masquée : elle signale une dérive du pipeline, pas une absence de donnée.
 */
export function ucUsageSeverityLabel(value: string | null | undefined): string {
  const normalized = normalizeUcUsageSeverity(value);
  if (normalized) return LABELS[normalized];
  return (value ?? '').trim() || '—';
}

export function ucUsageSeverityBadgeVariant(
  value: string | null | undefined
): 'destructive' | 'warning' | 'secondary' | 'outline' {
  switch (normalizeUcUsageSeverity(value)) {
    case 'high':
      return 'destructive';
    case 'medium':
      return 'warning';
    case 'low':
      return 'secondary';
    default:
      return 'outline';
  }
}

export function ucUsageSeverityRank(value: string | null | undefined): number {
  const normalized = normalizeUcUsageSeverity(value);
  return normalized ? RANKS[normalized] : RANKS.low + 1;
}
