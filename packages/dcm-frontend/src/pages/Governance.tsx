import { ShieldCheck } from 'lucide-react';
import { StandardChecksPage } from '../components/domain';

const Governance: React.FC = () => {
  return (
    <StandardChecksPage
      title="Standard Checks"
      description={(startDate, endDate) => `Multi-cloud compliance checks from ${startDate} to ${endDate}`}
      icon={<ShieldCheck size={20} />}
      emptyTitle="No compliance evaluation"
      resourceFallback="multi-cloud"
      showSource
      cloudProvider="all"
    />
  );
};

export default Governance;
