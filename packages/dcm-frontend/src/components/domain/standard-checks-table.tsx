import { ListChecks, ShieldCheck } from 'lucide-react';
import type { StandardCheck } from '../../types/api';
import { useClientPagination } from '../../hooks/useClientPagination';
import { getStandardCheckStateBarClass } from '../../lib/domain/governance';
import { formatDateTime } from '../../lib/domain/formatters';
import { Badge } from '../ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table';
import { CheckEffectBadge, StandardCheckStateBadge } from './badges';
import { ListPagination } from './list-pagination';
import { EmptyState, TableSkeleton } from './states';

const DEFAULT_CHECKS_PAGE_SIZE = 15;

export function StandardChecksTable({
  checks,
  allChecksCount,
  loading,
  title = 'Compliance checks',
  description = 'Azure compliance checks for the selected scope.',
  emptyTitle,
  emptyDescription,
  resourceFallback,
  showSource = false,
  pageSize = DEFAULT_CHECKS_PAGE_SIZE,
}: {
  checks: StandardCheck[];
  allChecksCount: number;
  loading: boolean;
  title?: string;
  description?: string;
  emptyTitle: string;
  emptyDescription: string;
  resourceFallback: string;
  showSource?: boolean;
  pageSize?: number;
}) {
  const pagination = useClientPagination(checks, pageSize);

  const getNoCheckReasons = (reasons: StandardCheck['no_check_reasons']) =>
    Array.isArray(reasons) ? reasons : reasons ? [String(reasons)] : [];

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <ListChecks className="size-5 text-primary" />
              {title}
            </CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
          <Badge variant={checks.length === 0 ? 'success' : 'secondary'}>
            {checks.length === 0 ? 'No check' : `${checks.length} checks`}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {loading ? (
          <TableSkeleton rows={6} />
        ) : checks.length === 0 ? (
          <EmptyState
            icon={<ShieldCheck size={32} />}
            title={emptyTitle}
            description={allChecksCount === 0 ? 'No governance check found for this period.' : emptyDescription}
          />
        ) : (
          <div className="space-y-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Check</TableHead>
                  <TableHead>State</TableHead>
                  <TableHead>Effect</TableHead>
                  <TableHead>Resource</TableHead>
                  {showSource && <TableHead>Source</TableHead>}
                  <TableHead>Evaluation</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pagination.pageItems.map((check) => {
                  const noCheckReasons = getNoCheckReasons(check.no_check_reasons);
                  const rowKey = `${check.check_id}-${check.source_lz_id ?? 'all'}-${check.resource_id ?? check.resource_name ?? 'resource'}-${check.evaluated_at}`;

                  return (
                    <TableRow key={rowKey} className="hover:bg-blue-50/50">
                      <TableCell className="max-w-[420px] whitespace-normal">
                        <div className="flex gap-3">
                          <span className={`mt-1 h-10 w-1.5 shrink-0 rounded-full shadow-lg ${getStandardCheckStateBarClass(check.check_state)}`} />
                          <div>
                            <p className="font-medium text-foreground">{check.check_name}</p>
                            {noCheckReasons.length > 0 && (
                              <p className="mt-1 text-xs text-muted-foreground">{noCheckReasons.join(', ')}</p>
                            )}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <StandardCheckStateBadge state={check.check_state} />
                      </TableCell>
                      <TableCell>
                        <CheckEffectBadge effect={check.check_effect} />
                      </TableCell>
                      <TableCell className="max-w-[260px] whitespace-normal">
                        <div className="flex flex-col gap-1">
                          <span className="text-sm font-medium text-foreground">{check.resource_name ?? check.resource_id ?? resourceFallback}</span>
                          {check.resource_type && <span className="text-xs text-muted-foreground">{check.resource_type}</span>}
                        </div>
                      </TableCell>
                      {showSource && (
                        <TableCell>
                          <Badge variant="outline">{check.source_lz_id}</Badge>
                        </TableCell>
                      )}
                      <TableCell>{formatDateTime(check.evaluated_at)}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            <ListPagination
              currentPage={pagination.currentPage}
              endIndex={pagination.endIndex}
              hasNextPage={pagination.hasNextPage}
              hasPreviousPage={pagination.hasPreviousPage}
              onNext={pagination.nextPage}
              onPrevious={pagination.previousPage}
              startIndex={pagination.startIndex}
              totalItems={pagination.totalItems}
              totalPages={pagination.totalPages}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
