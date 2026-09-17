import type { DatabricksWorkspace } from '../../api/dcmApiClient';

/**
 * One key per workspace, whatever spelling a source used.
 *
 * Azure sources report `adb-<id>` while the Databricks system tables report the
 * bare numeric id. `/databricks/workspaces` returns the canonical form, but a
 * project's `dbxScope` stores whatever the reference dimension held — comparing
 * the two raw made a granted workspace look absent, so the header filter read
 * "No workspaces" for a project that had some. Mirror of the backend
 * `_canonical_workspace_id`.
 */
export function canonicalWorkspaceId(workspaceId: string | null | undefined): string {
  const id = (workspaceId ?? '').trim();
  return id.toLowerCase().startsWith('adb-') ? id.slice(4) : id;
}

export function formatWorkspaceLabel(workspaceId: string, maxLength = 28): string {
  if (workspaceId.length <= maxLength) {
    return workspaceId;
  }
  return `${workspaceId.slice(0, maxLength)}…`;
}

export function resolveWorkspaceDisplayLabel(
  workspace: Pick<DatabricksWorkspace, 'workspace_id' | 'display_name'> | undefined,
  workspaceId?: string,
  maxLength = 28,
): string {
  const id = workspace?.workspace_id ?? workspaceId ?? '';
  const displayName = workspace?.display_name?.trim();
  if (displayName) {
    return displayName.length <= maxLength ? displayName : `${displayName.slice(0, maxLength)}…`;
  }
  return formatWorkspaceLabel(id, maxLength);
}

export function dedupeWorkspacesById<T extends { workspace_id: string }>(workspaces: T[]): T[] {
  const byId = new Map<string, T>();
  for (const workspace of workspaces) {
    if (!workspace.workspace_id || byId.has(workspace.workspace_id)) {
      continue;
    }
    byId.set(workspace.workspace_id, workspace);
  }
  return [...byId.values()].sort((a, b) => a.workspace_id.localeCompare(b.workspace_id));
}
