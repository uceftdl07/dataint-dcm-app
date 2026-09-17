import type { DatabricksFocusViewData } from '../../../../lib/databricks/view-data';
import { formatDuration } from '../../../../lib/databricks/view-data';
import { useClientPagination } from '../../../../hooks/useClientPagination';
import { ListPagination } from '../../list-pagination';
import { WorkloadAccordion } from '../../workload-accordion';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../ui/card';

const JOBS_PAGE_SIZE = 10;

export function JobsFocusView({ data }: { data: DatabricksFocusViewData }) {
  const { loading, filteredWorkloadRows, avgWorkloadDuration } = data;
  const pagination = useClientPagination(filteredWorkloadRows, JOBS_PAGE_SIZE);

  return (
    <Card className="rounded-[1.5rem] border-border/70 shadow-none">
      <CardHeader>
        <CardTitle className="text-base">
          {filteredWorkloadRows.length.toLocaleString('en-GB')} workload row{filteredWorkloadRows.length === 1 ? '' : 's'}
        </CardTitle>
        <CardDescription>
          Average duration: {formatDuration(avgWorkloadDuration)}. Click a row to expand details.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <WorkloadAccordion
          workloads={pagination.pageItems}
          loading={loading}
          emptyMessage="No Databricks job or notebook activity is returned for this period and scope."
        />
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
      </CardContent>
    </Card>
  );
}
