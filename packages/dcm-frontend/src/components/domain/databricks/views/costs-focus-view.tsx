import type { DatabricksFocusViewData } from '../../../../lib/databricks/view-data';
import { formatCurrency } from '../../../../lib/databricks/view-data';
import { Skeleton } from '../../../ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../../../ui/table';

export function CostsFocusView({ data }: { data: DatabricksFocusViewData }) {
  const { loading, costItems } = data;

  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-10" />
        ))}
      </div>
    );
  }

  if (costItems.length === 0) {
    return (
      <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
        No Databricks cost line is currently returned by `/api/v1/costs/by-service`.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Service</TableHead>
            <TableHead>Scope</TableHead>
            <TableHead>Budget</TableHead>
            <TableHead className="text-right">Cost</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {costItems.map((item) => (
            <TableRow key={`${item.service_name}-${item.cloud_provider}-${item.source_lz_id ?? 'all'}`}>
              <TableCell>
                <div>
                  <p className="font-medium">{item.service_name}</p>
                  <p className="text-xs capitalize text-muted-foreground">{item.cloud_provider}</p>
                </div>
              </TableCell>
              <TableCell>
                <div className="max-w-xs">
                  <p className="truncate">{item.source_lz_id ?? '—'}</p>
                  <p className="truncate text-xs text-muted-foreground">{item.subscription_or_account_id ?? '—'}</p>
                </div>
              </TableCell>
              <TableCell>{item.avg_budget_consumed_pct === null ? '—' : `${Math.round(item.avg_budget_consumed_pct)}%`}</TableCell>
              <TableCell className="text-right font-medium">{formatCurrency(item.total_cost_usd)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
