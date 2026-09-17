import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Cloud } from 'lucide-react';
import {
  monitoringScopeDefaults,
  type MonitoringScope,
} from '../contexts/monitoring-scope';
import { getSelectedLzIds } from '../lib/monitoring-scope-filter';
import { cn } from '../lib/utils';
import type { LandingZoneDetail } from '../types/api';

interface HeaderLandingZoneFilterProps {
  landingZones: LandingZoneDetail[];
  loading: boolean;
  error: boolean;
  scope: MonitoringScope;
  setScope: (scope: MonitoringScope) => void;
  buttonClassName: string;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

function landingZoneLabel(landingZone: LandingZoneDetail) {
  return landingZone.lz_name || landingZone.lz_id;
}

const EMPTY_LZ_SCOPE: MonitoringScope = {
  kind: 'landing-zones',
  label: 'Select landing zones',
  sourceLzIds: [],
};

function buildLandingZonesScope(
  lzIds: string[],
  landingZones: LandingZoneDetail[],
): MonitoringScope {
  if (lzIds.length === 1) {
    const landingZone = landingZones.find((item) => item.lz_id === lzIds[0]);
    return {
      kind: 'landing-zones',
      label: landingZone ? landingZoneLabel(landingZone) : lzIds[0],
      sourceLzIds: lzIds,
      cloudProvider: landingZone?.cloud_provider,
      environment: landingZone?.environment ?? undefined,
    };
  }

  return {
    kind: 'landing-zones',
    label: `${lzIds.length} landing zones`,
    sourceLzIds: lzIds,
  };
}

function scopeSummaryLabel(scope: MonitoringScope, landingZones: LandingZoneDetail[]) {
  if (scope.kind === 'all') {
    return monitoringScopeDefaults.all.label;
  }

  const selected = getSelectedLzIds(scope) ?? [];
  if (selected.length === 1) {
    const landingZone = landingZones.find((item) => item.lz_id === selected[0]);
    return landingZone ? landingZoneLabel(landingZone) : selected[0];
  }
  if (selected.length > 1) {
    return `${selected.length} landing zones`;
  }

  return 'Select landing zones';
}

export function HeaderLandingZoneFilter({
  landingZones,
  loading,
  error,
  scope,
  setScope,
  buttonClassName,
  open: controlledOpen,
  onOpenChange,
}: HeaderLandingZoneFilterProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen ?? internalOpen;
  const setOpen = onOpenChange ?? setInternalOpen;
  const containerRef = useRef<HTMLDivElement>(null);
  const selectAllRef = useRef<HTMLInputElement>(null);
  const allLzIds = useMemo(() => landingZones.map((landingZone) => landingZone.lz_id), [landingZones]);
  const selectedLzIds = useMemo(() => {
    if (scope.kind === 'all') {
      return new Set(allLzIds);
    }
    return new Set(getSelectedLzIds(scope) ?? []);
  }, [allLzIds, scope]);
  const allSelected = allLzIds.length > 0 && selectedLzIds.size === allLzIds.length;
  const someSelected = selectedLzIds.size > 0 && !allSelected;

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [open]);

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someSelected;
    }
  }, [someSelected, open]);

  const selectAllLandingZones = () => {
    setScope(monitoringScopeDefaults.all);
  };

  const deselectAllLandingZones = () => {
    setScope(EMPTY_LZ_SCOPE);
  };

  const toggleSelectAll = () => {
    if (allSelected) {
      deselectAllLandingZones();
      return;
    }
    selectAllLandingZones();
  };

  const toggleLandingZone = (lzId: string) => {
    const isSelected = selectedLzIds.has(lzId);
    const next = isSelected
      ? [...selectedLzIds].filter((id) => id !== lzId)
      : [...selectedLzIds, lzId];

    if (next.length === 0) {
      setScope(EMPTY_LZ_SCOPE);
      return;
    }

    if (next.length === allLzIds.length) {
      setScope(monitoringScopeDefaults.all);
      return;
    }

    setScope(buildLandingZonesScope(next, landingZones));
  };

  const summary = loading
    ? 'Loading landing zones...'
    : error
      ? 'Landing zones unavailable'
      : landingZones.length === 0
        ? 'No landing zones'
        : scopeSummaryLabel(scope, landingZones);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        id="monitoring-scope"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Landing zone filter"
        disabled={loading || landingZones.length === 0}
        onClick={() => setOpen(!open)}
        className={cn(
          buttonClassName,
          'flex w-full items-center gap-2 py-0 pl-9 pr-8 text-left disabled:opacity-100',
          (error || landingZones.length === 0) && 'border-warning-border bg-warning-subtle/80 text-warning',
        )}
        style={{ minInlineSize: 0, minWidth: 0, width: '100%', maxWidth: '100%' }}
      >
        <span className="min-w-0 truncate">{summary}</span>
      </button>
      <Cloud className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-tdf-blue" />
      <ChevronDown className="pointer-events-none absolute right-2 top-1/2 size-3.5 -translate-y-1/2 text-tdf-blue" />

      {open && landingZones.length > 0 && (
        <div
          role="listbox"
          aria-label="Landing zone selection"
          className="absolute right-0 top-[calc(100%+0.35rem)] z-50 w-[min(17rem,calc(100vw-2rem))] rounded-xl border border-border/70 bg-card p-2 shadow-lg shadow-slate-950/10"
        >
          <label className="flex cursor-pointer items-center gap-2 rounded-lg px-1.5 py-1 hover:bg-accent/50">
            <input
              ref={selectAllRef}
              type="checkbox"
              className="h-3.5 w-3.5 rounded border-input"
              checked={allSelected}
              onChange={toggleSelectAll}
            />
            <span className="text-xs font-semibold text-foreground">All landing zones</span>
          </label>

          <div className="my-1 h-px bg-border/50" />

          <div className="max-h-32 space-y-0 overflow-y-auto pr-0.5">
            {landingZones.map((landingZone) => {
              const checked = selectedLzIds.has(landingZone.lz_id);
              return (
                <label
                  key={landingZone.lz_id}
                  className="flex cursor-pointer items-center gap-2 rounded-lg px-1.5 py-1 hover:bg-accent/40"
                >
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5 shrink-0 rounded border-input"
                    checked={checked}
                    onChange={() => toggleLandingZone(landingZone.lz_id)}
                  />
                  <span className="min-w-0 truncate text-xs text-foreground">
                    {landingZoneLabel(landingZone)}
                  </span>
                </label>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
