import { Database } from 'lucide-react';
import { FinOpsServicesPage } from '../components/domain';
import { getDatabaseFamily, isDatabaseValue } from '../lib/domain/database-classification';

const DatabaseFinOps: React.FC = () => {
  return (
    <FinOpsServicesPage
      title="Database FinOps"
      description={(startDate, endDate) => `Azure Database costs from ${startDate} to ${endDate}`}
      icon={<Database size={20} />}
      serviceMetricLabel="Database"
      serviceMetricDescription="Database cost lines"
      contextHeader="Families"
      contextLabel="Family"
      emptyTitle="No database cost data"
      synthesisDescription="Consolidated cost breakdown for Database."
      recommendationsDescription="Cost optimization opportunities for Database."
      isInScope={isDatabaseValue}
      getContextValue={getDatabaseFamily}
    />
  );
};

export default DatabaseFinOps;
