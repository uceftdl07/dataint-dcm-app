import { ucRecommendationCopy } from '../../../lib/uc-usage/recommendation-copy';
import { Badge } from '../../ui/badge';
import { Button } from '../../ui/button';
import { formatUsd } from '../../../lib/compute/format';
import { formatIsoDate, ucUsageCategoryLabel } from '../../../lib/uc-usage/labels';
import { ucUsageSeverityBadgeVariant, ucUsageSeverityLabel } from '../../../lib/uc-usage/severity';
import type { UcUsageRecommendation } from '../../../types/api';

/**
 * Carte de recommandation ouverte. Aucune action d'acquittement : le pipeline
 * réécrit `status` à chaque run, un bouton ici mentirait sur son effet.
 */
export function UcUsageRecommendationCard({
  item,
  onViewTable,
}: {
  item: UcUsageRecommendation;
  onViewTable?: () => void;
}) {
  const copy = ucRecommendationCopy(item);
  return (
    <article className="rounded-[var(--card-radius)] border border-border bg-[var(--card-background)] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={ucUsageSeverityBadgeVariant(item.severity)}>
          {ucUsageSeverityLabel(item.severity)}
        </Badge>
        <Badge variant="outline">{ucUsageCategoryLabel(item.category)}</Badge>
        <span className="text-xs text-muted-foreground">
          Since {formatIsoDate(item.first_seen_date)}
          {item.age_days != null && item.age_days >= 0 ? ` · ${item.age_days} days` : ''}
        </span>
      </div>

      <h3 className="mt-2 text-sm font-semibold text-foreground">{copy.title}</h3>
      <p className="truncate text-xs text-muted-foreground" title={item.object_id}>
        {item.object_name?.trim() || item.object_id}
      </p>
      {item.cloud_provider ? (
        <p className="mt-1 text-[11px] text-muted-foreground">{item.cloud_provider}</p>
      ) : null}

      {item.detail ? <p className="mt-2 text-sm text-muted-foreground">{copy.detail}</p> : null}

      {item.recommended_action ? (
        <p className="mt-2 text-sm text-foreground">
          <span className="font-semibold">Action: </span>
          {copy.action}
        </p>
      ) : null}

      {/* `null` hors LIFECYCLE « inutilisée » : ne rien afficher plutôt que $0. */}
      {item.estimated_savings_usd != null ? (
        <p className="mt-2 text-sm font-semibold text-success">
          Daily reference cost: {formatUsd(item.estimated_savings_usd)}
          <span className="mt-1 block text-xs font-normal text-muted-foreground">
            LIFECYCLE · estimate to review
          </span>
        </p>
      ) : null}
      {onViewTable && item.object_type.toUpperCase() === 'DATA_PRODUCT' ? (
        <Button variant="ghost" size="sm" className="mt-3" onClick={onViewTable}>
          View in registry
        </Button>
      ) : null}
    </article>
  );
}
