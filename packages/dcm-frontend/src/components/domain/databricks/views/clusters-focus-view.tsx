import { ClusterAccordion } from '../../cluster-accordion';
import { ListPagination } from '../../list-pagination';
import { useClientPagination } from '../../../../hooks/useClientPagination';
import type { DatabricksFocusViewData } from '../../../../lib/databricks/view-data';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../ui/card';

const CLUSTERS_PAGE_SIZE = 10;

export function ClustersFocusView({ data }: { data: DatabricksFocusViewData }) {
  const { loading, filteredClusters } = data;
  const pagination = useClientPagination(filteredClusters, CLUSTERS_PAGE_SIZE);

  return (
    <Card className="rounded-[1.5rem] border-border/70 shadow-none">
      <CardHeader>
        <CardTitle className="text-base">
          {filteredClusters.length.toLocaleString('en-GB')} cluster{filteredClusters.length === 1 ? '' : 's'}
        </CardTitle>
        <CardDescription>Click a cluster to expand its details. Use pagination when the list is long.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <ClusterAccordion
          clusters={pagination.pageItems}
          loading={loading}
          resetKey={`${pagination.currentPage}-${filteredClusters.length}`}
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
