import { Hexagon } from 'lucide-react';
import { FinOpsServicesPage } from '../components/domain';

function isDatabricksService(serviceName: string) {
  return serviceName.toLowerCase().includes('databricks');
}

const DatabricksFinOps: React.FC = () => {
  return (
    <FinOpsServicesPage
      title="Databricks FinOps"
      description={(startDate, endDate) => `Azure Databricks costs from ${startDate} to ${endDate}`}
      icon={<Hexagon size={20} />}
      serviceMetricLabel="Databricks"
      serviceMetricDescription="Databricks cost lines"
      contextHeader="Workspaces"
      contextLabel="Workspace"
      emptyTitle="No Databricks cost data"
      synthesisDescription="Consolidated cost breakdown for Databricks."
      recommendationsDescription="Cost optimization opportunities for Databricks."
      isInScope={isDatabricksService}
      getContextValue={(serviceName) => isDatabricksService(serviceName) ? 'Azure Databricks' : 'Not provided'}
    />
  );
};

export default DatabricksFinOps;
