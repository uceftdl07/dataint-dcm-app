import { Database } from 'lucide-react';
import { SecurityAlertsPage } from '../components/domain';

const DatabaseAlerts: React.FC = () => {
  return (
    <SecurityAlertsPage
      title="Database Alerts"
      description={(startDate, endDate) => `Azure Database security alerts and configuration from ${startDate} to ${endDate}`}
      icon={<Database size={20} />}
      emptyTitle="No database alerts"
      resourceFallback="Database"
      resourceFilterLabel="Resource"
    />
  );
};

export default DatabaseAlerts;
