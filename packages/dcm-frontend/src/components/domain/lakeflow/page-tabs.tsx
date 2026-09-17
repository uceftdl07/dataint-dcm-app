import { NavLink } from 'react-router-dom';
import { cn } from '../../../lib/utils';
import { LAKEFLOW_PAGE_TABS } from '../../../lib/lakeflow/format';

/** Overview / Jobs secondary tabs (vertical sidebar remains primary nav). */
export function LakeflowPageTabs() {
  return (
    <nav className="mb-4 flex gap-1 border-b border-border" aria-label="Databricks sections">
      {LAKEFLOW_PAGE_TABS.map((tab) => (
        <NavLink
          key={tab.path}
          to={tab.path}
          end={tab.path === '/databricks/overview'}
          className={({ isActive }) =>
            cn(
              '-mb-px border-b-2 px-4 py-2.5 text-sm font-semibold tracking-wide transition-colors',
              isActive
                ? 'border-[var(--tdf-blue)] text-[var(--tdf-blue)]'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            )
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}
