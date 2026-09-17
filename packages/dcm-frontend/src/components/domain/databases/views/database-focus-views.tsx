import { DatabaseAccordion } from '../../database-accordion';
import { ListPagination } from '../../list-pagination';
import { useClientPagination } from '../../../../hooks/useClientPagination';
import type { DatabaseMetric } from '../../../../types/api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../ui/card';

const DB_PAGE_SIZE = 10;

function DatabaseListView({
  databases,
  loading,
  title,
  description,
  emptyMessage,
}: {
  databases: DatabaseMetric[];
  loading: boolean;
  title: string;
  description: string;
  emptyMessage?: string;
}) {
  const pagination = useClientPagination(databases, DB_PAGE_SIZE);

  return (
    <Card className="rounded-[1.5rem] border-border/70 shadow-none">
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <DatabaseAccordion
          databases={pagination.pageItems}
          loading={loading}
          emptyMessage={emptyMessage}
          resetKey={`${pagination.currentPage}-${databases.length}`}
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

export function InventoryFocusView({
  databases,
  loading,
}: {
  databases: DatabaseMetric[];
  loading: boolean;
}) {
  return (
    <DatabaseListView
      databases={databases}
      loading={loading}
      title={`${databases.length.toLocaleString('en-GB')} database${databases.length === 1 ? '' : 's'}`}
      description="Click a database to expand its latest snapshot."
      emptyMessage="No database matches the selected filters."
    />
  );
}

export function PressureFocusView({
  databases,
  loading,
}: {
  databases: DatabaseMetric[];
  loading: boolean;
}) {
  return (
    <DatabaseListView
      databases={databases}
      loading={loading}
      title={`${databases.length.toLocaleString('en-GB')} pressured database${databases.length === 1 ? '' : 's'}`}
      description="Ranked by average CPU, memory, storage, and DTU signals."
      emptyMessage="No pressure signal to display for this scope."
    />
  );
}

export function CapacityFocusView({
  databases,
  loading,
  sort,
}: {
  databases: DatabaseMetric[];
  loading: boolean;
  sort: 'storage' | 'connections';
}) {
  return (
    <DatabaseListView
      databases={databases}
      loading={loading}
      title={`${databases.length.toLocaleString('en-GB')} database${databases.length === 1 ? '' : 's'}`}
      description={
        sort === 'connections'
          ? 'Ranked by active connections. Click a row for full capacity details.'
          : 'Ranked by storage usage. Click a row for full capacity details.'
      }
      emptyMessage="No capacity data to display for this scope."
    />
  );
}
