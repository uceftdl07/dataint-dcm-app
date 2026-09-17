import { Factory } from 'lucide-react';
import { StandardChecksPage } from '../components/domain';

const DataFactoryGovernance: React.FC = () => {
  return (
    <StandardChecksPage
      title="Data Factory Governance"
      description={(startDate, endDate) => `Data Factory compliance checks from ${startDate} to ${endDate}`}
      icon={<Factory size={20} />}
      emptyTitle="No Data Factory check to display"
      resourceFallback="Data Factory"
    />
  );
};

export default DataFactoryGovernance;
