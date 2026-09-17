import { describe, expect, it } from 'vitest';
import {
  filterBySelectedWorkspaceIds,
  getApiWorkspaceParams,
  matchesWorkspaceScope,
} from './databricks-workspace-filter';

describe('databricks-workspace-filter', () => {
  it('returns no API params when all workspaces are selected', () => {
    expect(getApiWorkspaceParams(null)).toEqual({});
    expect(matchesWorkspaceScope('adb-1', null)).toBe(true);
  });

  it('builds single workspace API param', () => {
    expect(getApiWorkspaceParams(['adb-1'])).toEqual({ workspace_id: 'adb-1' });
    expect(matchesWorkspaceScope('adb-1', ['adb-1'])).toBe(true);
    expect(matchesWorkspaceScope('adb-2', ['adb-1'])).toBe(false);
  });

  it('builds multi workspace API params', () => {
    expect(getApiWorkspaceParams(['adb-1', 'adb-2'])).toEqual({
      workspace_ids: ['adb-1', 'adb-2'],
    });
  });

  it('returns empty scope when nothing is selected', () => {
    expect(getApiWorkspaceParams([])).toEqual({ workspace_ids: [] });
    expect(
      filterBySelectedWorkspaceIds(
        [{ workspace_id: 'adb-1' }, { workspace_id: 'adb-2' }],
        [],
      ),
    ).toEqual([]);
  });
});
