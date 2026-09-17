import { NavLink, useLocation } from 'react-router-dom';
import {
  Content,
  ContentDescription,
  ContentHeader,
  ContentMain,
  ContentTitle,
} from '../components/layout/content';
import { Badge } from '../components/ui/badge';
import { cn } from '../lib/utils';

type GroupKey = 'Lakeflow' | 'Compute' | 'Databricks';

const PAGE_META: Record<string, { title: string; group: GroupKey }> = {
  '/databricks/pipelines': { title: 'Pipelines', group: 'Lakeflow' },
  '/databricks/workflows': { title: 'Workflows', group: 'Lakeflow' },
  '/databricks/cluster': { title: 'Clusters', group: 'Compute' },
  '/databricks/sql-warehouse': { title: 'SQL Warehouse', group: 'Compute' },
  '/databricks/compute/recommendations': { title: 'Recommendations & Forecast', group: 'Compute' },
  '/databricks/finops-v2': { title: 'FinOps', group: 'Databricks' },
  '/databricks/data-product-usage': { title: 'Usage Data Product', group: 'Databricks' },
};

const GROUP_TABS: Record<GroupKey, { label: string; path: string }[]> = {
  Lakeflow: [],
  Compute: [
    { label: 'Clusters', path: '/databricks/cluster' },
    { label: 'SQL Warehouse', path: '/databricks/sql-warehouse' },
    { label: 'Recommendations & Forecast', path: '/databricks/compute/recommendations' },
  ],
  Databricks: [],
};

export default function DatabricksComingSoon() {
  const { pathname } = useLocation();
  const meta = PAGE_META[pathname] ?? { title: 'Databricks', group: 'Databricks' as GroupKey };
  const tabs = GROUP_TABS[meta.group] ?? [];

  return (
    <Content className="mx-auto max-w-[1600px] gap-4 p-4 pb-24 lg:p-5 lg:pb-28">
      <ContentHeader>
        <div className="flex flex-wrap items-center gap-2">
          <ContentTitle>{meta.title}</ContentTitle>
          <Badge variant="secondary">{meta.group}</Badge>
        </div>
        <ContentDescription>Coming soon — this section is under construction.</ContentDescription>
        {tabs.length > 0 && (
          <nav
            className="mt-3 flex flex-wrap gap-1 border-b border-border pb-px"
            aria-label={`${meta.group} sections`}
          >
            {tabs.map((tab) => (
              <NavLink
                key={tab.path}
                to={tab.path}
                className={({ isActive }) =>
                  cn(
                    '-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'border-primary text-foreground'
                      : 'border-transparent text-muted-foreground hover:text-foreground'
                  )
                }
              >
                {tab.label}
              </NavLink>
            ))}
          </nav>
        )}
      </ContentHeader>
      <ContentMain>
        <p className="text-sm text-muted-foreground">
          Placeholder page for <span className="font-medium text-foreground">{meta.title}</span> in{' '}
          <span className="font-medium text-foreground">{meta.group}</span>. No data is loaded yet.
        </p>
      </ContentMain>
    </Content>
  );
}
