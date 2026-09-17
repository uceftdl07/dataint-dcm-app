import { Factory } from 'lucide-react';
import { SecurityAlertsPage } from '../components/domain';

const DataFactoryAlerts: React.FC = () => {
  return (
    <SecurityAlertsPage
      title="Data Factory Alerts"
      description={(startDate, endDate) => `Azure Data Factory alerts from ${startDate} to ${endDate}`}
      icon={<Factory size={20} />}
      emptyTitle="No Data Factory alerts"
      resourceFallback="Data Factory"
      resourceFilterLabel="Factory"
    />
  );
};

export default DataFactoryAlerts;
