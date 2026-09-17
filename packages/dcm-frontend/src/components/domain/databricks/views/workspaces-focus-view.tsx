import type { DatabricksFocusViewData } from '../../../../lib/databricks/view-data';
import { formatCurrency } from '../../../../lib/databricks/view-data';
import { Badge } from '../../../ui/badge';
import { Skeleton } from '../../../ui/skeleton';

export function WorkspacesFocusView({ data }: { data: DatabricksFocusViewData }) {
  const { loading, workspaceSummaries } = data;

  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-14" />
        ))}
      </div>
    );
  }

  if (workspaceSummaries.length === 0) {
    return (
      <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
        No workspace is attached to the visible Databricks clusters.
      </div>
    );
  }

  return (
    <div className="grid gap-3 md:grid-cols-2">
      {workspaceSummaries.map((workspace) => (
        <div key={workspace.id} className="rounded-2xl border border-border/70 bg-background/70 p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate font-medium" title={workspace.id}>{workspace.name}</p>
              <p className="text-xs text-muted-foreground">
                {workspace.running} running / {workspace.total} cluster(s)
              </p>
            </div>
            <Badge variant={workspace.costUsd > 0 ? 'warning' : 'outline'}>{formatCurrency(workspace.costUsd)}</Badge>
          </div>
        </div>
      ))}
    </div>
  );
}
