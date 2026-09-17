import { useMemo } from 'react';
import { resolveWorkspaceDisplayLabel } from '../lib/databricks/workspace-label';
import { useDatabricksWorkspacesList } from './useDatabricksWorkspacesList';

export function useWorkspaceLabelResolver(enabled = true) {
  const query = useDatabricksWorkspacesList(enabled);

  const byId = useMemo(() => {
    const map = new Map<string, { display_name?: string | null; workspace_id: string }>();
    for (const workspace of query.data?.items ?? []) {
      map.set(workspace.workspace_id, workspace);
    }
    return map;
  }, [query.data?.items]);

  const resolve = (workspaceId: string | null | undefined, maxLength = 36) => {
    if (!workspaceId) return '—';
    return resolveWorkspaceDisplayLabel(byId.get(workspaceId), workspaceId, maxLength);
  };

  const resolveWithId = (workspaceId: string | null | undefined) => {
    if (!workspaceId) {
      return { label: '—', id: null as string | null, hasName: false };
    }
    const workspace = byId.get(workspaceId);
    const label = resolveWorkspaceDisplayLabel(workspace, workspaceId, 48);
    const hasName = Boolean(
      workspace?.display_name?.trim() && workspace.display_name.trim() !== workspaceId
    );
    return { label, id: workspaceId, hasName };
  };

  return {
    resolve,
    resolveWithId,
    loading: query.isLoading,
    workspaces: query.data?.items ?? [],
  };
}
