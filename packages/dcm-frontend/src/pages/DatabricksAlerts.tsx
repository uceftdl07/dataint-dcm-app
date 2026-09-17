import { Server } from 'lucide-react';
import { SecurityAlertsPage } from '../components/domain';
import { isDatabricksSecurityAlert } from '../lib/databricks/databricks-utils';

const DatabricksAlerts: React.FC = () => {
  return (
    <SecurityAlertsPage
      title="Databricks Alerts"
      description={(startDate, endDate) => `Azure Databricks alerts from ${startDate} to ${endDate}`}
      headerTags={(startDate, endDate) => [
        { value: 'Azure Databricks', icon: <Server size={14} />, tone: 'danger' },
        { label: 'Type', value: 'Alerts' },
        { label: 'From', value: startDate },
        { label: 'To', value: endDate },
      ]}
      icon={<Server size={20} />}
      emptyTitle="No Databricks alerts"
      resourceFallback="Databricks"
      resourceFilterLabel="Workspace"
      scopeAlerts={(alerts) => alerts.filter(isDatabricksSecurityAlert)}
    />
  );
};

export default DatabricksAlerts;
