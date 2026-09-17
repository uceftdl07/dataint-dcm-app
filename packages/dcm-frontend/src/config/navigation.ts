import {
  BookOpen,
  Bot,
  FolderKanban,
  LayoutDashboard,
  ShieldCheck,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { getFocusPageIcon, getFocusPageTitle } from '../lib/page-navigation';

interface MenuChild {
  label: string;
  path: string;
  title?: string;
  requiresSuperAdmin?: boolean;
  /** Static non-clickable group label (legacy). Prefer collapsibleGroup. */
  isGroupHeader?: true;
  /** Collapsible subgroup under Databricks (Lakeflow / Compute). */
  collapsibleGroup?: true;
  children?: MenuChild[];
}

export type MenuIcon = LucideIcon;

export type { MenuChild };

export type ModuleMenuItem =
  | {
      name: string;
      icon: MenuIcon;
      path: string;
      requiresAdmin?: boolean;
      children?: never;
    }
  | {
      name: string;
      icon: MenuIcon;
      children: MenuChild[];
      requiresAdmin?: boolean;
      path?: never;
    };

export interface PageMeta {
  title: string;
  icon: MenuIcon;
}

/** Flatten nested menu children to leaf routes (skip group headers). */
export function flattenMenuLeaves(children: MenuChild[]): MenuChild[] {
  const leaves: MenuChild[] = [];
  for (const child of children) {
    if (child.collapsibleGroup && child.children?.length) {
      leaves.push(...flattenMenuLeaves(child.children));
      continue;
    }
    if (child.isGroupHeader || !child.path) {
      continue;
    }
    leaves.push(child);
  }
  return leaves;
}

/** Main sidebar section — exactly 3 top-level items (nav v2). */
export const MAIN_MENU: ModuleMenuItem[] = [
  {
    name: 'Home',
    icon: LayoutDashboard,
    path: '/dashboard',
  },
  {
    name: 'Databricks',
    icon: Workflow,
    children: [
      { label: 'Overview', path: '/databricks/overview', title: 'Databricks Overview' },
      {
        label: 'Jobs & Pipelines',
        path: '/databricks/workflows',
        title: 'Jobs & Pipelines',
      },
      {
        label: 'Compute',
        path: '',
        collapsibleGroup: true,
        children: [
          // First of the group, and transversal: it reads the twelve serverless surfaces
          // at once, where the four entries below each read one classic compute form.
          // Serverless carries the larger share of the DBU spend, so it frames the others
          // rather than closing the list.
          {
            label: 'Serverless',
            path: '/databricks/serverless',
            title: 'Compute — Serverless',
          },
          {
            label: 'All-purpose clusters',
            path: '/databricks/cluster',
            title: 'Compute — All-purpose clusters',
          },
          {
            label: 'SQL Warehouses',
            path: '/databricks/sql-warehouse',
            title: 'Compute — SQL Warehouses',
          },
          {
            label: 'Job clusters',
            path: '/databricks/job-compute',
            title: 'Compute — Job clusters',
          },
          {
            label: 'DLT pipeline clusters',
            path: '/databricks/pipeline-compute',
            title: 'Compute — DLT pipeline clusters',
          },
          {
            label: 'Recommendations & Forecast',
            path: '/databricks/compute/recommendations',
            title: 'Compute — Recommendations & Forecast',
          },
        ],
      },
      { label: 'FinOps', path: '/databricks/finops-v2', title: 'Databricks FinOps' },
      {
        label: 'Usage Data Product',
        path: '/databricks/data-product-usage',
        title: 'Usage Data Product',
      },
      {
        label: 'Usage',
        path: '',
        collapsibleGroup: true,
        children: [
          { label: 'UC tables', path: '/databricks/usage-tables', title: 'Usage — UC tables' },
          {
            label: 'Governance & Recommendations',
            path: '/databricks/usage-governance',
            title: 'Usage — Governance & Recommendations',
          },
        ],
      },
    ],
  },
  {
    name: 'Talk to your Data',
    icon: Bot,
    path: '/talk-to-data',
  },
];

/** Settings sidebar section — Administration + My Projects. */
export const SETTINGS_MENU: ModuleMenuItem[] = [
  {
    name: 'Administration',
    icon: ShieldCheck,
    path: '/admin',
    requiresAdmin: true,
  },
  {
    name: 'My Projects',
    icon: FolderKanban,
    path: '/projects',
  },
];

/** Merged menu for getPageMeta + backward compat. */
export const MODULE_MENU: ModuleMenuItem[] = [...MAIN_MENU, ...SETTINGS_MENU];

export function getPageMeta(pathname: string): PageMeta {
  if (pathname === '/guide/lz-onboarding') {
    return { title: 'LZ onboarding guide', icon: BookOpen };
  }

  const focusTitle = getFocusPageTitle(pathname);
  if (focusTitle) {
    return { title: focusTitle, icon: getFocusPageIcon(pathname) };
  }

  for (const item of MODULE_MENU) {
    if ('path' in item && item.path === pathname) {
      return { title: item.name, icon: item.icon };
    }

    if (item.children) {
      const child = flattenMenuLeaves(item.children).find((entry) => entry.path === pathname);
      if (child) {
        return { title: child.title ?? child.label, icon: item.icon };
      }
    }
  }

  return { title: 'Data connect', icon: LayoutDashboard };
}
