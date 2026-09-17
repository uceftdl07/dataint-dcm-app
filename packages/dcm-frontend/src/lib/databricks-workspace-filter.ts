export function getSelectedWorkspaceIds(workspaceIds: string[] | null): string[] | null {
  if (workspaceIds === null) {
    return null;
  }
  return workspaceIds;
}

export function getApiWorkspaceParams(workspaceIds: string[] | null): {
  workspace_id?: string;
  workspace_ids?: string[];
} {
  const selected = getSelectedWorkspaceIds(workspaceIds);
  if (selected === null) {
    return {};
  }
  if (selected.length === 0) {
    return { workspace_ids: [] };
  }
  if (selected.length === 1) {
    return { workspace_id: selected[0] };
  }
  return { workspace_ids: selected };
}

export function matchesWorkspaceScope(
  workspaceId: string | null | undefined,
  selectedWorkspaceIds: string[] | null,
): boolean {
  const selected = getSelectedWorkspaceIds(selectedWorkspaceIds);
  if (selected === null) {
    return true;
  }
  if (!workspaceId) {
    return selected.length === 0;
  }
  return selected.includes(workspaceId);
}

export function filterBySelectedWorkspaceIds<T extends { workspace_id?: string | null }>(
  items: T[],
  selectedWorkspaceIds: string[] | null | undefined,
): T[] {
  if (selectedWorkspaceIds === null || selectedWorkspaceIds === undefined) {
    return items;
  }
  if (selectedWorkspaceIds.length === 0) {
    return [];
  }
  return items.filter(
    (item) => item.workspace_id != null && selectedWorkspaceIds.includes(item.workspace_id),
  );
}
