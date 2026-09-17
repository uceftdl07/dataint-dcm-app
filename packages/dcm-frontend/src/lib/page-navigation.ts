import {
  Bell,
  Database,
  DollarSign,
  Factory,
  LayoutDashboard,
  Server,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { ALERTS_FOCUS_VIEW_LABELS, parseAlertsFocusView } from './alerts/focus-view';
import { CLUSTERS_FOCUS_VIEW_LABELS, parseClustersFocusView } from './clusters/focus-view';
import { COSTS_FOCUS_VIEW_LABELS, parseCostsFocusView } from './costs/focus-view';
import {
  DATA_PRODUCT_FOCUS_VIEW_LABELS,
  parseDataProductFocusView,
} from './data-product-usage/focus-view';
import {
  DATA_FACTORY_FOCUS_VIEW_LABELS,
  parseDataFactoryFocusView,
} from './datafactory/focus-view';
import { DATABRICKS_FOCUS_VIEW_LABELS, parseDatabricksFocusView } from './databricks/focus-view';
import { DATABASE_FOCUS_VIEW_LABELS, parseDatabaseFocusView } from './databases/focus-view';
import { PIPELINES_FOCUS_VIEW_LABELS, parsePipelinesFocusView } from './pipelines/focus-view';

const DATABRICKS_MODULE_ROUTES = new Set([
  'alerts',
  'finops',
  'governance',
  'insights',
  'overview',
]);

const FOCUS_MODULES = new Set([
  'pipelines',
  'datafactory',
  'clusters',
  'costs',
  'alerts',
  'databases',
  'data-product-usage',
]);

const FOCUS_MODULE_ICONS: Record<string, LucideIcon> = {
  pipelines: Factory,
  datafactory: Factory,
  clusters: Server,
  costs: DollarSign,
  alerts: Bell,
  databases: Database,
  'data-product-usage': Workflow,
  databricks: Workflow,
};

const PAGES_WITH_IN_CONTENT_BACK = new Set(['/guide/lz-onboarding']);

export function getFocusRouteParts(pathname: string): { module: string; view: string } | null {
  const parts = pathname.split('/').filter(Boolean);
  if (parts.length !== 2) return null;
  return { module: parts[0], view: parts[1] };
}

/** Drill-down pages that render their own "Back to … overview" link. */
export function isFocusDetailRoute(pathname: string): boolean {
  const parts = getFocusRouteParts(pathname);
  if (!parts) return false;

  if (parts.module === 'databricks') {
    return !DATABRICKS_MODULE_ROUTES.has(parts.view);
  }

  return FOCUS_MODULES.has(parts.module);
}

export function showsHeaderBackButton(pathname: string): boolean {
  if (pathname === '/dashboard') return false;
  if (PAGES_WITH_IN_CONTENT_BACK.has(pathname)) return false;
  if (isFocusDetailRoute(pathname)) return false;
  return true;
}

export function getFocusPageTitle(pathname: string): string | null {
  const parts = getFocusRouteParts(pathname);
  if (!parts || !isFocusDetailRoute(pathname)) return null;

  switch (parts.module) {
    case 'databricks': {
      const view = parseDatabricksFocusView(parts.view);
      return view ? DATABRICKS_FOCUS_VIEW_LABELS[view] : null;
    }
    case 'pipelines': {
      const view = parsePipelinesFocusView(parts.view);
      return view ? PIPELINES_FOCUS_VIEW_LABELS[view] : null;
    }
    case 'datafactory': {
      const view = parseDataFactoryFocusView(parts.view);
      return view ? DATA_FACTORY_FOCUS_VIEW_LABELS[view] : null;
    }
    case 'clusters': {
      const view = parseClustersFocusView(parts.view);
      return view ? CLUSTERS_FOCUS_VIEW_LABELS[view] : null;
    }
    case 'costs': {
      const view = parseCostsFocusView(parts.view);
      return view ? COSTS_FOCUS_VIEW_LABELS[view] : null;
    }
    case 'alerts': {
      const view = parseAlertsFocusView(parts.view);
      return view ? ALERTS_FOCUS_VIEW_LABELS[view] : null;
    }
    case 'databases': {
      const view = parseDatabaseFocusView(parts.view);
      return view ? DATABASE_FOCUS_VIEW_LABELS[view] : null;
    }
    case 'data-product-usage': {
      const view = parseDataProductFocusView(parts.view);
      return view ? DATA_PRODUCT_FOCUS_VIEW_LABELS[view] : null;
    }
    default:
      return null;
  }
}

export function getFocusPageIcon(pathname: string): LucideIcon {
  const parts = getFocusRouteParts(pathname);
  if (!parts) return LayoutDashboard;
  return FOCUS_MODULE_ICONS[parts.module] ?? LayoutDashboard;
}
