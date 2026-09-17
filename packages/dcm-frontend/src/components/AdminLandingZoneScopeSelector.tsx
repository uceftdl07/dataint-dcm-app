import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Cloud, Loader2, X } from 'lucide-react';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { cn } from '../lib/utils';
import type { LandingZoneDetail } from '../types/api';

export type LzScopeSelection =
  | { mode: 'all' }
  | { mode: 'specific'; lzIds: string[] };

interface AdminLandingZoneScopeSelectorProps {
  landingZones: LandingZoneDetail[];
  value: LzScopeSelection;
  onChange: (value: LzScopeSelection) => void;
  className?: string;
  disabled?: boolean;
  loading?: boolean;
  'aria-label'?: string;
}

export function lzScopeFromApiIds(lzIds: string[]): LzScopeSelection {
  return lzIds.length === 0 ? { mode: 'all' } : { mode: 'specific', lzIds: [...lzIds] };
}

export function lzScopeToApiIds(value: LzScopeSelection): string[] {
  return value.mode === 'all' ? [] : value.lzIds;
}

export function filterAssignableLandingZones(landingZones: LandingZoneDetail[]): LandingZoneDetail[] {
  return landingZones.filter(
    (landingZone) =>
      Boolean(landingZone.environment)
      && landingZone.environment !== 'unknown'
      && Boolean(landingZone.ba_name)
      && landingZone.ba_name !== 'unassigned',
  );
}

function landingZoneLabel(landingZone: LandingZoneDetail): string {
  return landingZone.lz_name || landingZone.lz_id;
}

function landingZoneMatchesQuery(landingZone: LandingZoneDetail, query: string): boolean {
  const haystack = [
    landingZone.lz_id,
    landingZone.lz_name,
    landingZone.environment,
    landingZone.cloud_provider,
    landingZone.ba_name,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  return haystack
    .split(/[\s,.-]+/)
    .some((token) => token.startsWith(query) || haystack.includes(query));
}

function sameLzIds(left: string[], right: string[]): boolean {
  if (left.length !== right.length) {
    return false;
  }
  const sortedLeft = [...left].sort();
  const sortedRight = [...right].sort();
  return sortedLeft.every((lzId, index) => lzId === sortedRight[index]);
}

export function sameLzScope(left: LzScopeSelection, right: LzScopeSelection): boolean {
  if (left.mode === 'all' && right.mode === 'all') {
    return true;
  }
  if (left.mode === 'specific' && right.mode === 'specific') {
    return sameLzIds(left.lzIds, right.lzIds);
  }
  return false;
}

export function AdminLandingZoneScopeSelector({
  landingZones,
  value,
  onChange,
  className,
  disabled = false,
  loading = false,
  'aria-label': ariaLabel = 'Landing zone scope',
}: AdminLandingZoneScopeSelectorProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const selectAllRef = useRef<HTMLInputElement>(null);

  const allLzIds = useMemo(
    () => landingZones.map((landingZone) => landingZone.lz_id),
    [landingZones],
  );
  const specificLzIds = useMemo(() => {
    if (value.mode !== 'specific') {
      return [];
    }
    return value.lzIds.filter((lzId) => allLzIds.includes(lzId));
  }, [allLzIds, value]);
  const isAllScope = value.mode === 'all';
  const allSelected = isAllScope;
  const someSelected = value.mode === 'specific' && specificLzIds.length > 0;

  const searchQuery = query.trim().toLowerCase();
  const filteredLandingZones = useMemo(() => {
    if (!searchQuery) {
      return landingZones;
    }
    return landingZones.filter((landingZone) => landingZoneMatchesQuery(landingZone, searchQuery));
  }, [landingZones, searchQuery]);

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
      selectAllRef.current.indeterminate = someSelected && !allSelected;
    }
  }, [allSelected, someSelected, open]);

  const isLzChecked = (lzId: string) => {
    if (isAllScope) {
      return true;
    }
    return specificLzIds.includes(lzId);
  };

  const toggleSelectAll = () => {
    if (isAllScope) {
      onChange({ mode: 'specific', lzIds: [] });
      return;
    }
    onChange({ mode: 'all' });
  };

  const toggleLandingZone = (lzId: string) => {
    if (isAllScope) {
      onChange({
        mode: 'specific',
        lzIds: allLzIds.filter((id) => id !== lzId),
      });
      return;
    }

    const next = new Set(specificLzIds);
    if (next.has(lzId)) {
      next.delete(lzId);
    } else {
      next.add(lzId);
    }

    const nextIds = allLzIds.filter((id) => next.has(id));
    if (nextIds.length === allLzIds.length) {
      onChange({ mode: 'all' });
      return;
    }

    onChange({ mode: 'specific', lzIds: nextIds });
  };

  const removeSelectedLz = (lzId: string) => {
    if (isAllScope) {
      onChange({
        mode: 'specific',
        lzIds: allLzIds.filter((id) => id !== lzId),
      });
      return;
    }

    onChange({
      mode: 'specific',
      lzIds: specificLzIds.filter((id) => id !== lzId),
    });
  };

  const selectedBadges = isAllScope
    ? [{ id: 'all', label: 'All landing zones' }]
    : specificLzIds.map((lzId) => {
        const landingZone = landingZones.find((item) => item.lz_id === lzId);
        return {
          id: lzId,
          label: landingZone ? landingZoneLabel(landingZone) : lzId,
        };
      });

  return (
    <div ref={containerRef} className={cn('space-y-2', className)}>
      {selectedBadges.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selectedBadges.map((badge) => (
            <Badge
              key={badge.id}
              variant={badge.id === 'all' ? 'info' : 'outline'}
              className="gap-1 bg-background/80 pr-1 font-normal"
            >
              <span className="max-w-[12rem] truncate">{badge.label}</span>
              {badge.id !== 'all' && (
                <button
                  type="button"
                  className="rounded-full p-0.5 hover:bg-muted"
                  aria-label={`Remove ${badge.label}`}
                  onClick={() => removeSelectedLz(badge.id)}
                >
                  <X size={12} />
                </button>
              )}
            </Badge>
          ))}
        </div>
      )}

      <div className="relative">
        <Cloud className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-tdf-blue" />
        <Input
          ref={inputRef}
          type="text"
          value={query}
          disabled={disabled || loading || landingZones.length === 0}
          placeholder={
            loading
              ? 'Loading landing zones...'
              : landingZones.length === 0
                ? 'No assignable landing zones'
                : 'Type to filter landing zones (name, ID, env, cloud)...'
          }
          aria-label={ariaLabel}
          aria-expanded={open}
          aria-haspopup="listbox"
          className="h-11 pr-9 pl-9"
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              setOpen(false);
              setQuery('');
            }
          }}
        />
        <button
          type="button"
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-muted-foreground hover:bg-accent/40"
          aria-label="Toggle landing zone list"
          disabled={disabled || loading || landingZones.length === 0}
          onClick={() => {
            setOpen((current) => !current);
            inputRef.current?.focus();
          }}
        >
          {loading ? <Loader2 className="size-3.5 animate-spin" /> : <ChevronDown className="size-3.5" />}
        </button>

        {open && landingZones.length > 0 && (
          <div
            role="listbox"
            aria-label={ariaLabel}
            className="absolute left-0 top-[calc(100%+0.35rem)] z-50 w-full min-w-[16rem] rounded-xl border border-border/70 bg-card p-2 shadow-lg shadow-slate-950/10"
          >
            <label className="flex cursor-pointer items-center gap-2 rounded-lg px-1.5 py-1.5 hover:bg-accent/50">
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

            <div className="max-h-52 space-y-0 overflow-y-auto pr-0.5">
              {filteredLandingZones.length === 0 ? (
                <p className="px-1.5 py-2 text-xs text-muted-foreground">
                  No landing zone matches &quot;{query.trim()}&quot;.
                </p>
              ) : (
                filteredLandingZones.map((landingZone) => {
                  const checked = isLzChecked(landingZone.lz_id);
                  return (
                    <label
                      key={landingZone.lz_id}
                      className="flex cursor-pointer items-start gap-2 rounded-lg px-1.5 py-1.5 hover:bg-accent/40"
                    >
                      <input
                        type="checkbox"
                        className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border-input"
                        checked={checked}
                        onChange={() => toggleLandingZone(landingZone.lz_id)}
                      />
                      <span className="min-w-0">
                        <span className="block truncate text-xs font-medium text-foreground">
                          {landingZoneLabel(landingZone)}
                        </span>
                        <span className="block truncate font-mono text-[10px] text-muted-foreground">
                          {landingZone.lz_id}
                          {landingZone.environment ? ` · ${landingZone.environment}` : ''}
                          {landingZone.cloud_provider ? ` · ${landingZone.cloud_provider.toUpperCase()}` : ''}
                        </span>
                      </span>
                    </label>
                  );
                })
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
