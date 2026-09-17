import { useMemo, useState, type ReactNode } from 'react';
import { getApiWorkspaceParams } from '../lib/databricks-workspace-filter';
import { getApiLzParams } from '../lib/monitoring-scope-filter';
import {
  MonitoringScopeContext,
  monitoringScopeDefaults,
  type MonitoringScope,
  type MonitoringScopeContextType,
} from './monitoring-scope';

export function MonitoringScopeProvider({ children }: { children: ReactNode }) {
  const [scope, setScope] = useState<MonitoringScope>(monitoringScopeDefaults.all);
  const [databricksWorkspaceIds, setDatabricksWorkspaceIds] = useState<string[] | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);

  const value = useMemo<MonitoringScopeContextType>(() => ({
    scope,
    setScope,
    resetScope: () => {
      setScope(monitoringScopeDefaults.all);
      setDatabricksWorkspaceIds(null);
      setProjectId(null);
    },
    databricksWorkspaceIds,
    setDatabricksWorkspaceIds,
    projectId,
    setProjectId,
    getScopedParams: (support = {}) => ({
      ...(support.cloudProvider && scope.cloudProvider ? { cloud_provider: scope.cloudProvider } : {}),
      ...(support.workspaceId ? getApiWorkspaceParams(databricksWorkspaceIds) : {}),
      ...(support.subscriptionOrAccountId && scope.subscriptionOrAccountId
        ? { subscription_or_account_id: scope.subscriptionOrAccountId }
        : {}),
      ...(support.sourceLzId ? getApiLzParams(scope) : {}),
      ...(support.environment && scope.environment ? { environment: scope.environment } : {}),
    }),
  }), [databricksWorkspaceIds, projectId, scope]);

  return (
    <MonitoringScopeContext.Provider value={value}>
      {children}
    </MonitoringScopeContext.Provider>
  );
}
