import { Database } from 'lucide-react';
import type { FinOpsServiceCost } from '../../lib/domain/finops';
import { getBudgetBarClass } from '../../lib/domain/finops';
import { formatCurrency } from '../../lib/domain/formatters';
import { Badge } from '../ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table';
import { BudgetBadge } from './badges';
import { EmptyState, TableSkeleton } from './states';
import { TrendCell } from './trend-cell';

export function FinOpsServiceCostTable({
  items,
  allItemsCount,
  loading,
  title,
  description = 'Azure cost lines for the selected scope.',
  emptyTitle,
  emptyDescription,
  contextHeader,
}: {
  items: FinOpsServiceCost[];
  allItemsCount: number;
  loading: boolean;
  title: string;
  description?: string;
  emptyTitle: string;
  emptyDescription: string;
  contextHeader: string;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <CardTitle>{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
          <Badge variant={items.length === 0 ? 'success' : 'secondary'}>
            {items.length === 0 ? 'No cost data' : `${items.length} services`}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {loading ? (
          <TableSkeleton rows={6} />
        ) : items.length === 0 ? (
          <EmptyState
            icon={<Database size={32} />}
            title={emptyTitle}
            description={allItemsCount === 0 ? 'No cost data for this period. Check FinOps collection or widen the period/scope.' : emptyDescription}
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Service</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead>{contextHeader}</TableHead>
                <TableHead>Budget</TableHead>
                <TableHead>Cost</TableHead>
                <TableHead>Trend</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item, index) => (
                <TableRow key={`${item.serviceName}-${item.cloudProvider}-${item.contextValue}-${item.monthlyCost}-${index}`} className="hover:bg-blue-50/50">
                  <TableCell className="max-w-[360px] whitespace-normal">
                    <div className="flex gap-3">
                      <span className={`mt-1 h-10 w-1.5 shrink-0 rounded-full shadow-lg ${item.budgetPercentage === null ? 'bg-muted' : getBudgetBarClass(item.budgetPercentage)}`} />
                      <div>
                        <p className="font-medium text-foreground">{item.serviceName}</p>
                        <p className="mt-1 text-xs text-muted-foreground">{item.contextLabel}: {item.contextValue}</p>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{item.cloudProvider}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{item.contextValue}</Badge>
                  </TableCell>
                  <TableCell>
                    <BudgetBadge percentage={item.budgetPercentage} />
                  </TableCell>
                  <TableCell className="font-semibold text-foreground">{formatCurrency(item.monthlyCost)}</TableCell>
                  <TableCell>
                    <TrendCell direction={item.trend.direction} percentageChange={item.trend.percentageChange} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
