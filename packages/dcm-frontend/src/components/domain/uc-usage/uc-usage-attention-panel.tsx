import { Badge } from '../../ui/badge';
import { Skeleton } from '../../ui/skeleton';
import { formatUsd } from '../../../lib/compute/format';
import { ucUsageCategoryLabel } from '../../../lib/uc-usage/labels';
import { ucUsageSeverityBadgeVariant, ucUsageSeverityLabel } from '../../../lib/uc-usage/severity';
import type { UcUsageRecommendation } from '../../../types/api';

/**
 * Bloc « Points d'attention » de la vue d'ensemble (FR-001) : les recommandations
 * ouvertes les plus sévères, en lecture seule. Instantané — il ne dépend d'aucune
 * période, donc il s'affiche avant tout clic sur Appliquer.
 */
export function UcUsageAttentionPanel({
  items,
  loading,
  error,
}: {
  items: UcUsageRecommendation[];
  loading: boolean;
  error: unknown;
}) {
  return (
    <section
      aria-label="Points to review"
      className="rounded-[var(--card-radius)] border border-border bg-[var(--card-background)] p-4"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-foreground">Points to review</h2>
        <p className="text-xs text-muted-foreground">
          Highest-severity open recommendations · current snapshot
        </p>
      </div>

      {loading ? (
        <Skeleton className="mt-3 h-[96px]" />
      ) : error ? (
        <p className="mt-3 text-sm text-danger">Unable to load recommendations.</p>
      ) : items.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">No open recommendations in this scope.</p>
      ) : (
        <ul className="mt-3 divide-y divide-border">
          {items.map((item) => (
            <li
              key={item.recommendation_id}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2"
            >
              <Badge variant={ucUsageSeverityBadgeVariant(item.severity)}>
                {ucUsageSeverityLabel(item.severity)}
              </Badge>
              <Badge variant="outline">{ucUsageCategoryLabel(item.category)}</Badge>
              <span className="min-w-0 flex-1 truncate text-sm text-foreground" title={item.title}>
                {item.title}
              </span>
              <span
                className="min-w-0 max-w-[280px] truncate text-xs text-muted-foreground"
                title={item.object_id}
              >
                {item.object_name?.trim() || item.object_id}
              </span>
              {/* `null` hors LIFECYCLE « inutilisée » : ne rien afficher plutôt que $0. */}
              {item.estimated_savings_usd != null ? (
                <span className="text-xs font-semibold text-success">
                  {formatUsd(item.estimated_savings_usd)}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
