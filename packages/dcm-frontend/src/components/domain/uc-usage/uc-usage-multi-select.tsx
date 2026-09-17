/**
 * Sélecteurs des filtres de scope : un choix unique pour le catalogue et le
 * schéma, un choix multiple pour les tables — la maquette 024.
 *
 * Les valeurs viennent du registre (`/uc-usage/filters/options`), jamais des
 * lignes affichées : les vues paginent côté serveur, une liste bâtie sur la page
 * courante ne proposerait que 25 tables sur plusieurs milliers.
 */
import { useEffect, useId, useMemo, useRef, useState, type Ref } from 'react';
import { Check, ChevronDown, Search, X } from 'lucide-react';
import { cn } from '../../../lib/utils';

const PANEL =
  'absolute left-0 top-[calc(100%+4px)] z-30 w-[300px] rounded-md border border-border bg-[var(--card-background)] p-2 shadow-[var(--card-shadow)]';
const TRIGGER =
  'flex h-8 items-center gap-1.5 rounded-md border border-border bg-card px-2.5 text-xs font-medium text-foreground transition-colors hover:bg-accent/40';

function useCloseOnOutside(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) onClose();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open, onClose]);

  return ref;
}

function SearchBox({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (next: string) => void;
  placeholder: string;
}) {
  return (
    <div className="flex items-center gap-1.5 rounded-md border border-border px-2 py-1">
      <Search size={13} className="shrink-0 text-muted-foreground" aria-hidden />
      <input
        className="w-full border-0 bg-transparent p-0 text-xs text-foreground outline-none placeholder:text-muted-foreground"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
      />
    </div>
  );
}

/** Choix unique — « Tous » reste toujours proposé, c'est l'absence de filtre. */
export function UcUsageSelect({
  label,
  value,
  options,
  onChange,
  loading,
  allLabel = 'All',
  placeholder,
  triggerRef,
}: {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (next: string) => void;
  loading?: boolean;
  allLabel?: string;
  placeholder?: string;
  triggerRef?: Ref<HTMLButtonElement>;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const listId = useId();
  const ref = useCloseOnOutside(open, () => setOpen(false));

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return term ? options.filter((entry) => entry.toLowerCase().includes(term)) : options;
  }, [options, search]);

  const select = (next: string) => {
    onChange(next);
    setOpen(false);
    setSearch('');
  };

  return (
    <div className="relative" ref={ref}>
      <button
        ref={triggerRef}
        type="button"
        className={TRIGGER}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={label}
        onClick={() => setOpen((previous) => !previous)}
      >
        <span className="max-w-[160px] truncate">{value || placeholder || allLabel}</span>
        <ChevronDown size={13} className="shrink-0 text-muted-foreground" aria-hidden />
      </button>

      {open ? (
        <div className={PANEL}>
          <SearchBox value={search} onChange={setSearch} placeholder={`Filter ${label}…`} />
          <ul
            id={listId}
            role="listbox"
            aria-label={label}
            className="mt-1 max-h-52 overflow-y-auto"
          >
            <li>
              <button
                type="button"
                role="option"
                aria-selected={value === ''}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs text-muted-foreground hover:bg-accent/40"
                onClick={() => select('')}
              >
                <span className="flex-1 truncate">{allLabel}</span>
                {value === '' ? <Check size={13} className="text-primary" aria-hidden /> : null}
              </button>
            </li>
            {loading && options.length === 0 ? (
              <li className="px-2 py-2 text-xs text-muted-foreground">Loading…</li>
            ) : null}
            {!loading && filtered.length === 0 ? (
              <li className="px-2 py-2 text-xs text-muted-foreground">No values.</li>
            ) : null}
            {filtered.map((entry) => (
              <li key={entry}>
                <button
                  type="button"
                  role="option"
                  aria-selected={entry === value}
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-accent/40"
                  onClick={() => select(entry)}
                >
                  <span className="flex-1 truncate" title={entry}>
                    {entry}
                  </span>
                  {entry === value ? (
                    <Check size={13} className="text-primary" aria-hidden />
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export interface UcUsageMultiSelectOption {
  value: string;
  label: string;
  hint?: string;
}

/**
 * Choix multiple. La sélection est appliquée à chaque case cochée : le bouton
 * du panneau ne fait que le refermer, il ne valide rien — deux gestes de
 * validation (ici puis « Appliquer » du bandeau) seraient un piège.
 */
export function UcUsageMultiSelect({
  label,
  values,
  options,
  onChange,
  loading,
  truncated,
  search,
  onSearchChange,
}: {
  label: string;
  values: string[];
  options: readonly UcUsageMultiSelectOption[];
  onChange: (next: string[]) => void;
  loading?: boolean;
  truncated?: boolean;
  search: string;
  onSearchChange: (next: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useCloseOnOutside(open, () => setOpen(false));
  const selected = useMemo(() => new Set(values), [values]);

  const toggle = (value: string) => {
    onChange(selected.has(value) ? values.filter((entry) => entry !== value) : [...values, value]);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        className={TRIGGER}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={label}
        onClick={() => setOpen((previous) => !previous)}
      >
        <span>{label}</span>
        {values.length > 0 ? (
          <span className="rounded-full bg-primary px-1.5 text-[10px] font-bold leading-4 text-primary-foreground">
            {values.length}
          </span>
        ) : null}
        <ChevronDown size={13} className="shrink-0 text-muted-foreground" aria-hidden />
      </button>

      {open ? (
        <div className={PANEL}>
          <SearchBox
            value={search}
            onChange={onSearchChange}
            placeholder={`Filter ${label.toLowerCase()}…`}
          />
          <ul
            role="listbox"
            aria-label={label}
            aria-multiselectable
            className="mt-1 max-h-52 overflow-y-auto"
          >
            {loading && options.length === 0 ? (
              <li className="px-2 py-2 text-xs text-muted-foreground">Loading…</li>
            ) : null}
            {!loading && options.length === 0 ? (
              <li className="px-2 py-2 text-xs text-muted-foreground">No values.</li>
            ) : null}
            {options.map((option) => (
              <li key={option.value}>
                <label className="flex cursor-pointer items-start gap-2 rounded px-2 py-1.5 text-xs hover:bg-accent/40">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={selected.has(option.value)}
                    onChange={() => toggle(option.value)}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate" title={option.value}>
                      {option.label}
                    </span>
                    {option.hint ? (
                      <span className="block truncate text-[10px] text-muted-foreground">
                        {option.hint}
                      </span>
                    ) : null}
                  </span>
                </label>
              </li>
            ))}
          </ul>

          {truncated ? (
            <p className="px-2 pt-1 text-[10px] leading-snug text-muted-foreground">
              List capped: refine your search to see more tables.
            </p>
          ) : null}

          <div className="mt-1 flex items-center justify-between border-t border-border pt-1">
            <button
              type="button"
              className="rounded px-1 py-0.5 text-[11px] font-semibold text-primary disabled:opacity-50"
              onClick={() => onChange([])}
              disabled={values.length === 0}
            >
              Clear all
            </button>
            <button
              type="button"
              className="rounded px-1 py-0.5 text-[11px] font-semibold text-primary"
              onClick={() => setOpen(false)}
            >
              Close
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** Rappel des tables retenues, chacune retirable sans rouvrir le panneau. */
export function UcUsageChips({
  values,
  onRemove,
  className,
}: {
  values: string[];
  onRemove: (value: string) => void;
  className?: string;
}) {
  if (values.length === 0) return null;
  return (
    <div className={cn('flex flex-wrap gap-1.5', className)}>
      {values.map((value) => (
        <span
          key={value}
          className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-[11px] font-semibold text-secondary-foreground"
        >
          <span className="max-w-[260px] truncate" title={value}>
            {value}
          </span>
          <button
            type="button"
            onClick={() => onRemove(value)}
            aria-label={`Remove ${value}`}
            className="text-muted-foreground hover:text-danger"
          >
            <X size={11} />
          </button>
        </span>
      ))}
    </div>
  );
}
