import { Factory } from 'lucide-react';
import { FinOpsServicesPage } from '../components/domain';

function isDataFactoryService(serviceName: string) {
  const normalized = serviceName.toLowerCase();
  return normalized.includes('datafactory') || normalized.includes('data factory');
}

const DataFactoryFinOps: React.FC = () => {
  return (
    <FinOpsServicesPage
      title="Data Factory FinOps"
      description={(startDate, endDate) => `Azure Data Factory costs from ${startDate} to ${endDate}`}
      icon={<Factory size={20} />}
      serviceMetricLabel="Data Factory"
      serviceMetricDescription="Data Factory cost lines"
      contextHeader="Factories"
      contextLabel="Factory"
      emptyTitle="No Data Factory cost data"
      synthesisDescription="Consolidated cost breakdown for Data Factory."
      recommendationsDescription="Cost optimization opportunities for Data Factory."
      isInScope={isDataFactoryService}
      getContextValue={(serviceName) => isDataFactoryService(serviceName) ? 'Azure Data Factory' : 'Not provided'}
    />
  );
};

export default DataFactoryFinOps;
