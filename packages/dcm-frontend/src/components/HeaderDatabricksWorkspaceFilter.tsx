import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Search, Workflow } from 'lucide-react';
import type { DatabricksWorkspace } from '../api/dcmApiClient';
import { resolveWorkspaceDisplayLabel } from '../lib/databricks/workspace-label';
import { cn } from '../lib/utils';

interface HeaderDatabricksWorkspaceFilterProps {
  workspaces: DatabricksWorkspace[];
  loading: boolean;
  error: boolean;
  workspaceIds: string[] | null;
  setWorkspaceIds: (workspaceIds: string[] | null) => void;
  buttonClassName: string;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** True when LZ multi-select is empty — workspaces are intentionally hidden. */
  lzSelectionEmpty?: boolean;
  /** Open the landing-zone filter (used when LZ selection is empty). */
  onRequestOpenLandingZones?: () => void;
}

const EMPTY_WORKSPACE_SCOPE: string[] = [];

function hasFriendlyName(workspace: DatabricksWorkspace): boolean {
  const name = workspace.display_name?.trim();
  return Boolean(name && name !== workspace.workspace_id);
}

function workspaceSummaryLabel(
  workspaceIds: string[] | null,
  workspaces: DatabricksWorkspace[],
  loading: boolean,
  error: boolean,
  lzSelectionEmpty = false
) {
  if (loading) {
    return 'Loading workspaces...';
  }
  if (error) {
    return 'Workspaces unavailable';
  }
  if (lzSelectionEmpty) {
    return 'Select landing zones first';
  }
  if (workspaces.length === 0) {
    return 'No workspaces';
  }
  if (workspaceIds === null) {
    return 'All workspaces';
  }
  if (workspaceIds.length === 0) {
    return 'Select workspaces';
  }
  if (workspaceIds.length === 1) {
    const workspace = workspaces.find((item) => item.workspace_id === workspaceIds[0]);
    return resolveWorkspaceDisplayLabel(workspace, workspaceIds[0], 36);
  }
  return `${workspaceIds.length} workspaces`;
}

function sortWorkspacesForDisplay(workspaces: DatabricksWorkspace[]): DatabricksWorkspace[] {
  return [...workspaces].sort((a, b) => {
    const aNamed = hasFriendlyName(a) ? 0 : 1;
    const bNamed = hasFriendlyName(b) ? 0 : 1;
    if (aNamed !== bNamed) {
      return aNamed - bNamed;
    }
    const aLabel = (a.display_name || a.workspace_id).toLowerCase();
    const bLabel = (b.display_name || b.workspace_id).toLowerCase();
    const byLabel = aLabel.localeCompare(bLabel);
    if (byLabel !== 0) {
      return byLabel;
    }
    return a.workspace_id.localeCompare(b.workspace_id);
  });
}

export function HeaderDatabricksWorkspaceFilter({
  workspaces,
  loading,
  error,
  workspaceIds,
  setWorkspaceIds,
  buttonClassName,
  open: controlledOpen,
  onOpenChange,
  lzSelectionEmpty = false,
  onRequestOpenLandingZones,
}: HeaderDatabricksWorkspaceFilterProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const [search, setSearch] = useState('');
  const open = controlledOpen ?? internalOpen;
  const setOpen = onOpenChange ?? setInternalOpen;
  const containerRef = useRef<HTMLDivElement>(null);
  const selectAllRef = useRef<HTMLInputElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const sortedWorkspaces = useMemo(() => sortWorkspacesForDisplay(workspaces), [workspaces]);
  const allWorkspaceIds = useMemo(
    () => sortedWorkspaces.map((workspace) => workspace.workspace_id),
    [sortedWorkspaces]
  );
  const selectedWorkspaceIds = useMemo(() => {
    if (workspaceIds === null) {
      return new Set(allWorkspaceIds);
    }
    return new Set(workspaceIds);
  }, [allWorkspaceIds, workspaceIds]);
  const allSelected =
    allWorkspaceIds.length > 0 && selectedWorkspaceIds.size === allWorkspaceIds.length;
  const someSelected = selectedWorkspaceIds.size > 0 && !allSelected;
  const summary = useMemo(
    () => workspaceSummaryLabel(workspaceIds, workspaces, loading, error, lzSelectionEmpty),
    [error, loading, lzSelectionEmpty, workspaceIds, workspaces]
  );
  const filteredWorkspaces = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) {
      return sortedWorkspaces;
    }
    return sortedWorkspaces.filter((workspace) => {
      const id = workspace.workspace_id.toLowerCase();
      const name = (workspace.display_name || '').toLowerCase();
      return id.includes(query) || name.includes(query);
    });
  }, [search, sortedWorkspaces]);
  // Keep clickable when LZ is empty so we can redirect to the LZ filter.
  const disabled = loading || (workspaces.length === 0 && !lzSelectionEmpty && !error);

  useEffect(() => {
    if (!open) {
      setSearch('');
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    const focusTimer = window.setTimeout(() => searchInputRef.current?.focus(), 0);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      window.clearTimeout(focusTimer);
    };
  }, [open, setOpen]);

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someSelected;
    }
  }, [open, someSelected]);

  const selectAllWorkspaces = () => {
    setWorkspaceIds(null);
  };

  const deselectAllWorkspaces = () => {
    setWorkspaceIds(EMPTY_WORKSPACE_SCOPE);
  };

  const toggleSelectAll = () => {
    if (allSelected) {
      deselectAllWorkspaces();
      return;
    }
    selectAllWorkspaces();
  };

  const toggleWorkspace = (workspaceId: string) => {
    const isSelected = selectedWorkspaceIds.has(workspaceId);
    const next = isSelected
      ? [...selectedWorkspaceIds].filter((id) => id !== workspaceId)
      : [...selectedWorkspaceIds, workspaceId];

    if (next.length === 0) {
      setWorkspaceIds(EMPTY_WORKSPACE_SCOPE);
      return;
    }

    if (next.length === allWorkspaceIds.length) {
      setWorkspaceIds(null);
      return;
    }

    setWorkspaceIds(next);
  };

  const handleButtonClick = () => {
    if (lzSelectionEmpty) {
      setOpen(false);
      onRequestOpenLandingZones?.();
      return;
    }
    setOpen(!open);
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        id="databricks-workspace-filter"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={
          lzSelectionEmpty
            ? 'Select landing zones first to filter workspaces'
            : 'Databricks workspace filter'
        }
        disabled={disabled}
        onClick={handleButtonClick}
        className={cn(
          buttonClassName,
          'flex w-full items-center gap-2 py-0 pl-9 pr-8 text-left disabled:opacity-100',
          (error || workspaces.length === 0 || lzSelectionEmpty) &&
            'border-warning-border bg-warning-subtle/80 text-warning'
        )}
        style={{ minInlineSize: 0, minWidth: 0, width: '100%', maxWidth: '100%' }}
      >
        <span className="min-w-0 truncate">{summary}</span>
      </button>
      <Workflow className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-tdf-blue" />
      <ChevronDown className="pointer-events-none absolute right-2 top-1/2 size-3.5 -translate-y-1/2 text-tdf-blue" />

      {open && workspaces.length > 0 && (
        <div
          role="listbox"
          aria-label="Databricks workspace selection"
          className="absolute right-0 top-[calc(100%+0.35rem)] z-50 w-[min(20rem,calc(100vw-2rem))] rounded-xl border border-border/70 bg-card p-2 shadow-lg shadow-slate-950/10"
        >
          <div className="relative mb-1.5">
            <Search
              className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <input
              ref={searchInputRef}
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search name or ID…"
              aria-label="Search workspaces by name or ID"
              className="h-8 w-full rounded-lg border border-border/70 bg-background py-1 pl-7 pr-2 text-xs text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-tdf-blue/40"
              onClick={(event) => event.stopPropagation()}
              onKeyDown={(event) => event.stopPropagation()}
            />
          </div>

          <label className="flex cursor-pointer items-center gap-2 rounded-lg px-1.5 py-1 hover:bg-accent/50">
            <input
              ref={selectAllRef}
              type="checkbox"
              className="h-3.5 w-3.5 rounded border-input"
              checked={allSelected}
              onChange={toggleSelectAll}
            />
            <span className="text-xs font-semibold text-foreground">All workspaces</span>
          </label>

          <div className="my-1 h-px bg-border/50" />

          <div className="max-h-48 space-y-0 overflow-y-auto pr-0.5">
            {filteredWorkspaces.length === 0 ? (
              <p className="px-1.5 py-2 text-xs text-muted-foreground">
                No workspace matches “{search.trim()}”.
              </p>
            ) : (
              filteredWorkspaces.map((workspace) => {
                const checked = selectedWorkspaceIds.has(workspace.workspace_id);
                const named = hasFriendlyName(workspace);
                const displayName = (workspace.display_name || '').trim();
                return (
                  <label
                    key={workspace.workspace_id}
                    title={
                      named ? `${displayName} (${workspace.workspace_id})` : workspace.workspace_id
                    }
                    className="flex cursor-pointer items-center gap-2 rounded-lg px-1.5 py-1 hover:bg-accent/40"
                  >
                    <input
                      type="checkbox"
                      className="h-3.5 w-3.5 shrink-0 rounded border-input"
                      checked={checked}
                      onChange={() => toggleWorkspace(workspace.workspace_id)}
                    />
                    <span
                      className="min-w-0 flex-1 truncate text-xs text-foreground"
                      title={
                        named
                          ? `${displayName} (${workspace.workspace_id})`
                          : workspace.workspace_id
                      }
                    >
                      {named ? (
                        <span className="block truncate font-medium">{displayName}</span>
                      ) : (
                        <span className="font-mono">{workspace.workspace_id}</span>
                      )}
                    </span>
                  </label>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
