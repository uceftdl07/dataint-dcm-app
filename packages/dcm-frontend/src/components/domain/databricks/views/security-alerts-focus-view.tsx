import type { DatabricksFocusViewData } from '../../../../lib/databricks/view-data';
import { Skeleton } from '../../../ui/skeleton';
import { StatusBadge } from '../../../ui/status';

export function SecurityAlertsFocusView({ data }: { data: DatabricksFocusViewData }) {
  const { loading, databricksAlerts } = data;

  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-14" />
        ))}
      </div>
    );
  }

  if (databricksAlerts.length === 0) {
    return (
      <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
        No active Databricks security alert is currently returned by `/api/v1/security/alerts`.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {databricksAlerts.map((alert) => (
        <div key={`${alert.alert_id}-${alert.source_lz_id}`} className="rounded-2xl border border-border/70 bg-background/70 p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate font-medium">{alert.title}</p>
              <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{alert.description ?? 'No description'}</p>
              <p className="mt-1 truncate text-xs text-muted-foreground">
                {alert.resource_type ?? 'Resource'} · {alert.resource_id ?? alert.source_lz_id}
              </p>
            </div>
            <StatusBadge value={alert.severity} />
          </div>
        </div>
      ))}
    </div>
  );
}
