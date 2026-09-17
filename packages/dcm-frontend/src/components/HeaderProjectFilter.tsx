import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, FolderKanban } from 'lucide-react';
import { cn } from '../lib/utils';
import type { ProjectSummary } from '../types/api';

interface HeaderProjectFilterProps {
  /** Active projects the caller may look at — a pending one grants nothing yet. */
  projects: ProjectSummary[];
  loading: boolean;
  error: boolean;
  projectId: string | null;
  setProjectId: (projectId: string | null) => void;
  buttonClassName: string;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

/** Widening back to whatever the account itself may see, project aside. */
const ALL_PROJECTS_LABEL = 'All my projects';

function projectSummaryLabel(
  projectId: string | null,
  projects: ProjectSummary[],
  loading: boolean,
  error: boolean
) {
  if (loading) {
    return 'Loading projects...';
  }
  if (error) {
    return 'Projects unavailable';
  }
  if (projects.length === 0) {
    return 'No project';
  }
  const selected = projects.find((project) => project.id === projectId);
  return selected ? selected.name : ALL_PROJECTS_LABEL;
}

/** `2 LZ · 1 workspace` — what picking this project narrows the other filters to. */
function scopeHint(project: ProjectSummary): string {
  const workspaces = project.dbxScope.length;
  return `${project.lzScope.length} LZ · ${workspaces} workspace${workspaces === 1 ? '' : 's'}`;
}

/**
 * Project dimension of the header scope (feature 015).
 *
 * Single-select on purpose: a project *is* a pair of scope lists (landing zones
 * and Databricks workspaces), so unioning several of them would produce a scope
 * that belongs to no project and grants more than any of them. Picking one
 * narrows the landing-zone and workspace filters next to it to exactly what that
 * project was granted.
 */
export function HeaderProjectFilter({
  projects,
  loading,
  error,
  projectId,
  setProjectId,
  buttonClassName,
  open: controlledOpen,
  onOpenChange,
}: HeaderProjectFilterProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen ?? internalOpen;
  const setOpen = onOpenChange ?? setInternalOpen;
  const containerRef = useRef<HTMLDivElement>(null);
  const summary = useMemo(
    () => projectSummaryLabel(projectId, projects, loading, error),
    [error, loading, projectId, projects]
  );
  const sortedProjects = useMemo(
    () => [...projects].sort((a, b) => a.name.localeCompare(b.name)),
    [projects]
  );

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [open, setOpen]);

  const select = (nextProjectId: string | null) => {
    setProjectId(nextProjectId);
    setOpen(false);
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        id="project-scope"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Project filter"
        disabled={loading || projects.length === 0}
        onClick={() => setOpen(!open)}
        className={cn(
          buttonClassName,
          'flex w-full items-center gap-2 py-0 pl-9 pr-8 text-left disabled:opacity-100',
          (error || projects.length === 0) && 'border-warning-border bg-warning-subtle/80 text-warning'
        )}
        style={{ minInlineSize: 0, minWidth: 0, width: '100%', maxWidth: '100%' }}
      >
        <span className="min-w-0 truncate">{summary}</span>
      </button>
      <FolderKanban className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-tdf-blue" />
      <ChevronDown className="pointer-events-none absolute right-2 top-1/2 size-3.5 -translate-y-1/2 text-tdf-blue" />

      {open && projects.length > 0 && (
        <div
          role="listbox"
          aria-label="Project selection"
          className="absolute right-0 top-[calc(100%+0.35rem)] z-50 w-[min(18rem,calc(100vw-2rem))] rounded-xl border border-border/70 bg-card p-2 shadow-lg shadow-slate-950/10"
        >
          <button
            type="button"
            role="option"
            aria-selected={projectId === null}
            onClick={() => select(null)}
            className={cn(
              'flex w-full items-center rounded-lg px-1.5 py-1 text-left text-xs font-semibold text-foreground hover:bg-accent/50',
              projectId === null && 'bg-accent/60'
            )}
          >
            {ALL_PROJECTS_LABEL}
          </button>

          <div className="my-1 h-px bg-border/50" />

          <div className="max-h-40 space-y-0 overflow-y-auto pr-0.5">
            {sortedProjects.map((project) => (
              <button
                key={project.id}
                type="button"
                role="option"
                aria-selected={project.id === projectId}
                title={project.businessAppId}
                onClick={() => select(project.id)}
                className={cn(
                  'flex w-full flex-col items-start rounded-lg px-1.5 py-1 text-left hover:bg-accent/40',
                  project.id === projectId && 'bg-accent/60'
                )}
              >
                <span className="w-full truncate text-xs text-foreground">{project.name}</span>
                <span className="w-full truncate text-[10px] text-muted-foreground">
                  {scopeHint(project)}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
