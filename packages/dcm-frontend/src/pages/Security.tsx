import { Shield } from 'lucide-react';
import { SecurityAlertsPage } from '../components/domain';

const Security: React.FC = () => {
  return (
    <SecurityAlertsPage
      title="Cloud security"
      description={(startDate, endDate) => `Multi-cloud security alerts from ${startDate} to ${endDate}`}
      icon={<Shield size={20} />}
      emptyTitle="No security alerts"
      resourceFallback="Cloud"
      resourceFilterLabel="Resource"
      cloudProvider="all"
    />
  );
};

export default Security;
