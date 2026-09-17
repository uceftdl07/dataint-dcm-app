import { ShieldCheck } from 'lucide-react';
import { StandardChecksPage } from '../components/domain';
import { isDatabricksGovernanceCheck } from '../lib/databricks/databricks-utils';

const DatabricksGovernance: React.FC = () => {
  return (
    <StandardChecksPage
      title="Databricks Governance"
      description={(startDate, endDate) => `Databricks compliance checks from ${startDate} to ${endDate}`}
      icon={<ShieldCheck size={20} />}
      emptyTitle="No check Databricks to display"
      resourceFallback="Databricks"
      scopeChecks={(checks) => checks.filter(isDatabricksGovernanceCheck)}
    />
  );
};

export default DatabricksGovernance;
