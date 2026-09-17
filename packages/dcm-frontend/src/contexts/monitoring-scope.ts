import { createContext, useContext } from 'react';
import type { CloudProvider } from '../types/api';

export type MonitoringScopeKind =
  | 'all'
  | 'cloud'
  | 'workspace'
  | 'subscription'
  | 'account'
  | 'landing-zone'
  | 'landing-zones'
  | 'environment';

export interface MonitoringScope {
  kind: MonitoringScopeKind;
  label: string;
  cloudProvider?: CloudProvider;
  workspaceId?: string;
  subscriptionOrAccountId?: string;
  sourceLzId?: string;
  sourceLzIds?: string[];
  environment?: string;
}

interface ScopedParamSupport {
  cloudProvider?: boolean;
  workspaceId?: boolean;
  subscriptionOrAccountId?: boolean;
  sourceLzId?: boolean;
  environment?: boolean;
}

export interface MonitoringScopeContextType {
  scope: MonitoringScope;
  setScope: (scope: MonitoringScope) => void;
  resetScope: () => void;
  databricksWorkspaceIds: string[] | null;
  setDatabricksWorkspaceIds: (workspaceIds: string[] | null) => void;
  /**
   * Project the header filters are narrowed to, or `null` for everything the
   * account may see. It carries no API parameter of its own: a project is a pair
   * of scope lists, so selecting one simply drives the landing-zone and
   * Databricks workspace selections that already reach the backend.
   */
  projectId: string | null;
  setProjectId: (projectId: string | null) => void;
  getScopedParams: (support?: ScopedParamSupport) => {
    cloud_provider?: CloudProvider;
    workspace_id?: string;
    workspace_ids?: string[];
    subscription_or_account_id?: string;
    source_lz_id?: string;
    source_lz_ids?: string[];
    environment?: string;
  };
}

const ALL_SCOPE: MonitoringScope = {
  kind: 'all',
  label: 'All landing zones',
};

export const monitoringScopeDefaults = {
  all: ALL_SCOPE,
};

export const MonitoringScopeContext = createContext<MonitoringScopeContextType | undefined>(undefined);

export function useMonitoringScope() {
  const context = useContext(MonitoringScopeContext);
  if (context === undefined) {
    throw new Error('useMonitoringScope must be used within MonitoringScopeProvider');
  }
  return context;
}
