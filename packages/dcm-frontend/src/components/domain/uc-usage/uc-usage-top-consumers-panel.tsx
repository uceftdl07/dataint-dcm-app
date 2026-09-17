import { Badge } from '../../ui/badge';
import { Skeleton } from '../../ui/skeleton';
import { formatNumber, formatUsd } from '../../../lib/compute/format';
import { formatIsoDate, ucUsageConsumerTypeBadgeClass } from '../../../lib/uc-usage/labels';
import type { UcUsageTopConsumersResponse } from '../../../types/api';

/**
 * Drill-down d'une table, déplié **sous** sa ligne : les cinq premiers
 * consommateurs par coût, tels que l'API les renvoie. Pas de pagination — c'est
 * un `LIMIT 5` serveur (FR-004).
 */
export function UcUsageTopConsumersPanel({
  tableFullName,
  data,
  loading,
  error,
}: {
  tableFullName: string;
  data: UcUsageTopConsumersResponse | null;
  loading: boolean;
  error: unknown;
}) {
  const items = data?.items ?? [];

  return (
    <section className="px-6 py-3" aria-label={`Top consumers of ${tableFullName}`}>
      <p className="mb-2 text-[10px] font-black uppercase tracking-[1.2px] text-muted-foreground">
        Top consumers — {tableFullName}
      </p>

      {error ? (
        <p className="text-xs text-danger">Unable to load consumers.</p>
      ) : loading ? (
        <div className="space-y-1.5">
          <Skeleton className="h-5" />
          <Skeleton className="h-5" />
          <Skeleton className="h-5" />
        </div>
      ) : items.length === 0 ? (
        <p className="text-xs text-muted-foreground">No consumers in the applied period.</p>
      ) : (
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="text-left text-[10px] font-black uppercase tracking-[1.2px] text-muted-foreground">
              <th className="py-1 pr-3 font-black">Rank</th>
              <th className="py-1 pr-3 font-black">Consumer</th>
              <th className="py-1 pr-3 font-black">Type</th>
              <th className="py-1 pr-3 text-right font-black">Read accesses</th>
              <th className="py-1 pr-3 text-right font-black">Estimated cost</th>
              <th className="py-1 font-black">Last access</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.consumer_id} className="border-t border-border/70">
                <td className="py-1.5 pr-3">
                  <Badge>{row.rank}</Badge>
                </td>
                <td className="max-w-[320px] truncate py-1.5 pr-3 font-medium">
                  <span title={row.consumer_id}>
                    {row.consumer_name?.trim() || row.consumer_id}
                  </span>
                </td>
                {/* Vocabulaire ouvert : une valeur inconnue s'affiche telle quelle. */}
                <td className="py-1.5 pr-3">
                  {row.consumer_type?.trim() ? (
                    <Badge
                      variant="outline"
                      className={ucUsageConsumerTypeBadgeClass(row.consumer_type)}
                    >
                      {row.consumer_type.trim()}
                    </Badge>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums">
                  {formatNumber(row.request_count)}
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums">
                  {formatUsd(row.estimated_cost_usd)}
                </td>
                <td className="py-1.5 text-muted-foreground">{formatIsoDate(row.last_used_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
