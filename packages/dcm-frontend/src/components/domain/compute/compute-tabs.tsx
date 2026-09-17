import { Tabs, TabsList, TabsTrigger } from '../../ui/tabs';

export type ComputeClustersTabKey = 'overview' | 'cost' | 'efficiency' | 'governance';

const TABS: Array<{ key: ComputeClustersTabKey; label: string }> = [
  { key: 'overview', label: 'Overview' },
  { key: 'cost', label: 'Cost' },
  { key: 'efficiency', label: 'Efficiency' },
  { key: 'governance', label: 'Governance' },
];

export function ComputeTabs({
  value,
  onChange,
  ariaLabel = 'Compute clusters sections',
}: {
  value: ComputeClustersTabKey;
  onChange: (value: ComputeClustersTabKey) => void;
  ariaLabel?: string;
}) {
  return (
    <Tabs>
      <TabsList aria-label={ariaLabel}>
        {TABS.map((tab) => (
          <TabsTrigger key={tab.key} active={value === tab.key} onClick={() => onChange(tab.key)}>
            {tab.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
