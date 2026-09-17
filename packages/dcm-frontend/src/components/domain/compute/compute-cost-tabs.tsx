import { Tabs, TabsList, TabsTrigger } from '../../ui/tabs';

/**
 * Sub-tabs for the stable-grain compute pages (jobs, DLT pipelines).
 *
 * Overview, Cost and Efficiency: since 024 T004 the utilization signal is rolled up
 * at these grains too (`*_efficiency_rolling`), so the Efficiency tab reads real
 * data — a population smaller than Cost, measurement coming from `node_timeline`
 * and cost from billing.
 *
 * Still no Governance: tags, DBR version and oversizing are cluster-level snapshots
 * and stay on the all-purpose grain (024 C2).
 */
export type ComputeCostGrainTabKey = 'overview' | 'cost' | 'efficiency';

const TABS: Array<{ key: ComputeCostGrainTabKey; label: string }> = [
  { key: 'overview', label: 'Overview' },
  { key: 'cost', label: 'Cost' },
  { key: 'efficiency', label: 'Efficiency' },
];

export function ComputeCostGrainTabs({
  value,
  onChange,
  ariaLabel = 'Compute sections',
}: {
  value: ComputeCostGrainTabKey;
  onChange: (value: ComputeCostGrainTabKey) => void;
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
