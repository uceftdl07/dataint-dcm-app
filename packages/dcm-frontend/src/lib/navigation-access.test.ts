import { describe, expect, it } from 'vitest';
import type { ModuleMenuItem } from '../config/navigation';
import { MAIN_MENU } from '../config/navigation';
import { filterModuleMenu } from './navigation-access';
import { LayoutDashboard, Workflow } from 'lucide-react';

describe('filterModuleMenu', () => {
  it('hides requiresSuperAdmin children for non-super-admin users', () => {
    const menu: ModuleMenuItem[] = [
      {
        name: 'Demo',
        icon: Workflow,
        children: [
          { label: 'Open', path: '/open' },
          { label: 'Secrets', path: '/secrets', requiresSuperAdmin: true },
        ],
      },
    ];
    const filtered = filterModuleMenu(menu, 'admin');
    const demo = filtered.find((item) => item.name === 'Demo');

    expect(demo?.children?.some((child) => child.path === '/secrets')).toBe(false);
    expect(demo?.children?.some((child) => child.path === '/open')).toBe(true);
  });

  it('keeps requiresSuperAdmin children for super_admin users', () => {
    const menu: ModuleMenuItem[] = [
      {
        name: 'Demo',
        icon: LayoutDashboard,
        children: [
          { label: 'Open', path: '/open' },
          { label: 'Secrets', path: '/secrets', requiresSuperAdmin: true },
        ],
      },
    ];
    const filtered = filterModuleMenu(menu, 'super_admin');
    const demo = filtered.find((item) => item.name === 'Demo');

    expect(demo?.children?.some((child) => child.path === '/secrets')).toBe(true);
  });

  it('exposes Databricks hub leaf routes in MAIN_MENU', () => {
    const databricks = MAIN_MENU.find((item) => item.name === 'Databricks');
    const leafPaths =
      databricks?.children?.flatMap((c) =>
        c.collapsibleGroup && c.children
          ? c.children.map((leaf) => leaf.path)
          : c.path
            ? [c.path]
            : []
      ) ?? [];

    expect(leafPaths).toEqual([
      '/databricks/overview',
      '/databricks/workflows',
      // Serverless is transversal and not a grain — one page for the twelve surfaces
      // (025) — and it opens the compute group: it carries the larger share of the spend.
      '/databricks/serverless',
      '/databricks/cluster',
      '/databricks/sql-warehouse',
      // Then the group splits by grain: all-purpose, job, DLT pipeline (024).
      '/databricks/job-compute',
      '/databricks/pipeline-compute',
      '/databricks/compute/recommendations',
      '/databricks/finops-v2',
      '/databricks/data-product-usage',
      '/databricks/usage-tables',
      '/databricks/usage-governance',
    ]);
  });
});
