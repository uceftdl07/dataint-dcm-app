import { Database } from 'lucide-react';
import { StandardChecksPage } from '../components/domain';
import { isDatabaseCheck } from '../lib/domain/database-classification';

const DatabaseGovernance: React.FC = () => {
  return (
    <StandardChecksPage
      title="Database Governance"
      description={(startDate, endDate) => `Database compliance checks from ${startDate} to ${endDate}`}
      icon={<Database size={20} />}
      emptyTitle="No check Database to display"
      resourceFallback="Database"
      showSource
      scopeChecks={(checks) => checks.filter(isDatabaseCheck)}
    />
  );
};

export default DatabaseGovernance;
