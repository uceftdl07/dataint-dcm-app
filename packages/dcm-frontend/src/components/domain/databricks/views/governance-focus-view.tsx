import type { DatabricksFocusViewData } from '../../../../lib/databricks/view-data';
import { Skeleton } from '../../../ui/skeleton';
import { StatusBadge } from '../../../ui/status';

export function GovernanceFocusView({ data }: { data: DatabricksFocusViewData }) {
  const { loading, databricksChecks } = data;

  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-14" />
        ))}
      </div>
    );
  }

  if (databricksChecks.length === 0) {
    return (
      <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
        No Databricks governance check is currently identifiable in `/api/v1/standard-checks`.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {databricksChecks.map((check) => (
        <div key={check.check_id} className="rounded-2xl border border-border/70 bg-background/70 p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate font-medium">{check.check_name}</p>
              <p className="mt-1 truncate text-xs text-muted-foreground">
                {check.resource_name ?? check.resource_id ?? check.resource_type ?? 'Databricks resource'}
              </p>
              {check.check_effect && <p className="mt-1 text-xs text-muted-foreground">Effect: {check.check_effect}</p>}
            </div>
            <StatusBadge value={check.check_state} />
          </div>
        </div>
      ))}
    </div>
  );
}
