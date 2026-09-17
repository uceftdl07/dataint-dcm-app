import { describe, expect, it } from 'vitest';
import {
  dedupeWorkspacesById,
  formatWorkspaceLabel,
  resolveWorkspaceDisplayLabel,
} from './workspace-label';

describe('formatWorkspaceLabel', () => {
  it('returns short ids unchanged', () => {
    expect(formatWorkspaceLabel('adb-123')).toBe('adb-123');
  });

  it('truncates long workspace ids', () => {
    const workspaceId = 'adb-3059738143761234567890123';
    expect(formatWorkspaceLabel(workspaceId)).toBe('adb-305973814376123456789012…');
  });
});

describe('resolveWorkspaceDisplayLabel', () => {
  it('prefers display_name over workspace_id', () => {
    expect(
      resolveWorkspaceDisplayLabel({
        workspace_id: 'adb-305973814376',
        display_name: 'dbw-dsde-d-03',
      })
    ).toBe('dbw-dsde-d-03');
  });

  it('falls back to workspace_id when display_name is empty', () => {
    expect(
      resolveWorkspaceDisplayLabel({
        workspace_id: 'adb-305973814376',
        display_name: '',
      })
    ).toBe('adb-305973814376');
  });
});

describe('dedupeWorkspacesById', () => {
  it('keeps one row per workspace_id', () => {
    const items = dedupeWorkspacesById([
      { workspace_id: 'adb-1', display_name: 'a', source_lz_id: 'lz-1', cluster_count: 1 },
      { workspace_id: 'adb-1', display_name: 'b', source_lz_id: 'lz-2', cluster_count: 2 },
      { workspace_id: 'adb-2', display_name: 'c', source_lz_id: 'lz-1', cluster_count: 1 },
    ]);

    expect(items).toHaveLength(2);
    expect(items.map((item) => item.workspace_id)).toEqual(['adb-1', 'adb-2']);
  });
});
