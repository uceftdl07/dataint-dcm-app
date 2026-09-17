import { Tabs, TabsList, TabsTrigger } from '../../ui/tabs';

export type ComputeWarehousesTabKey = 'overview' | 'cost' | 'query-performance' | 'slow-queries';

const BASE_TABS: Array<{ key: ComputeWarehousesTabKey; label: string }> = [
  { key: 'overview', label: 'Overview' },
  { key: 'cost', label: 'Cost' },
  { key: 'query-performance', label: 'Query performance' },
  { key: 'slow-queries', label: 'Slow queries' },
];

export function ComputeWarehouseTabs({
  value,
  onChange,
  showSlowQueries,
}: {
  value: ComputeWarehousesTabKey;
  onChange: (value: ComputeWarehousesTabKey) => void;
  showSlowQueries: boolean;
}) {
  const tabs = showSlowQueries ? BASE_TABS : BASE_TABS.filter((tab) => tab.key !== 'slow-queries');

  return (
    <Tabs>
      <TabsList aria-label="SQL Warehouses tabs">
        {tabs.map((tab) => (
          <TabsTrigger key={tab.key} active={value === tab.key} onClick={() => onChange(tab.key)}>
            {tab.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
