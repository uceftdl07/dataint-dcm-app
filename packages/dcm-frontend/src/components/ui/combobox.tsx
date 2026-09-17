/**
 * Combobox — accessible single-select with a built-in search box.
 *
 * Tuned for long catalogues (890+ Business Applications): the panel never mounts
 * the full list in the DOM. Large catalogues require typing to search; results
 * are capped so opening the control stays responsive.
 */

import { Check, ChevronsUpDown, Search } from 'lucide-react';
import * as React from 'react';
import { cn } from '../../lib/utils';
import type { ComboboxOption } from './combobox-types';
import { getComboboxVisibleOptions } from './combobox-utils';

export type { ComboboxOption } from './combobox-types';

interface ComboboxProps {
  options: readonly ComboboxOption[];
  value: string;
  onChange: (value: string) => void;
  id?: string;
  placeholder?: string;
  searchPlaceholder?: string;
  /** Shown when a large catalogue needs typing before listing rows. */
  typeToSearchMessage?: string;
  emptyMessage?: string;
  disabled?: boolean;
  required?: boolean;
  'aria-label'?: string;
}

export const Combobox: React.FC<ComboboxProps> = ({
  options,
  value,
  onChange,
  id,
  placeholder = 'Select…',
  searchPlaceholder = 'Search…',
  typeToSearchMessage = 'Start typing to search',
  emptyMessage = 'No match found.',
  disabled = false,
  required = false,
  'aria-label': ariaLabel,
}) => {
  const [open, setOpen] = React.useState(false);
  const [search, setSearch] = React.useState('');
  const [activeIndex, setActiveIndex] = React.useState(0);
  const containerRef = React.useRef<HTMLDivElement>(null);
  const searchRef = React.useRef<HTMLInputElement>(null);
  const listId = React.useId();

  const selectedOption = React.useMemo(
    () => options.find((o) => o.value === value) ?? null,
    [options, value]
  );

  const { visible, totalMatched, requiresSearch, truncated } = React.useMemo(
    () => getComboboxVisibleOptions(options, search, value),
    [options, search, value]
  );

  React.useEffect(() => {
    if (!open) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  React.useEffect(() => {
    if (open) {
      setActiveIndex(0);
      const raf = requestAnimationFrame(() => searchRef.current?.focus());
      return () => cancelAnimationFrame(raf);
    }
    setSearch('');
    return undefined;
  }, [open]);

  const select = (option: ComboboxOption) => {
    onChange(option.value);
    setOpen(false);
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, Math.max(visible.length - 1, 0)));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const option = visible[activeIndex];
      if (option) select(option);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      setOpen(false);
    }
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        id={id}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-haspopup="listbox"
        aria-label={ariaLabel}
        aria-required={required || undefined}
        onClick={() => !disabled && setOpen((o) => !o)}
        disabled={disabled}
        className={cn(
          'flex w-full items-center justify-between gap-2 rounded-xl border border-slate-300 bg-white px-4 py-3 text-left text-sm',
          'focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20',
          'disabled:cursor-not-allowed disabled:opacity-50'
        )}
      >
        <span className={cn('truncate', selectedOption ? 'text-slate-900' : 'text-slate-400')}>
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <ChevronsUpDown className="h-4 w-4 flex-shrink-0 text-slate-400" />
      </button>

      {open && (
        <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg">
          <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2">
            <Search className="h-4 w-4 flex-shrink-0 text-slate-400" />
            <input
              ref={searchRef}
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setActiveIndex(0);
              }}
              onKeyDown={handleKeyDown}
              placeholder={searchPlaceholder}
              aria-label={searchPlaceholder}
              className="w-full border-0 bg-transparent p-0 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-0"
            />
          </div>
          <ul id={listId} role="listbox" className="max-h-60 overflow-y-auto py-1">
            {requiresSearch ? (
              <li className="px-4 py-3 text-sm text-slate-600">
                <p className="font-medium text-slate-800">{typeToSearchMessage}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {totalMatched.toLocaleString()} options available — type at least one character to
                  see the list.
                </p>
                {visible.length > 0 && (
                  <p className="mt-2 text-xs text-slate-400">
                    Your current selection is shown below.
                  </p>
                )}
              </li>
            ) : null}
            {!requiresSearch && visible.length === 0 ? (
              <li className="px-4 py-3 text-xs text-slate-500">{emptyMessage}</li>
            ) : (
              visible.map((option, index) => {
                const isSelected = option.value === value;
                const isActive = index === activeIndex;
                return (
                  <li
                    key={option.value}
                    role="option"
                    aria-selected={isSelected}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => select(option)}
                    className={cn(
                      'flex cursor-pointer items-center justify-between gap-2 px-4 py-2 text-sm',
                      isActive ? 'bg-blue-50 text-blue-900' : 'text-slate-700'
                    )}
                  >
                    <span className="truncate">{option.label}</span>
                    {isSelected && <Check className="h-4 w-4 flex-shrink-0 text-blue-600" />}
                  </li>
                );
              })
            )}
            {truncated && (
              <li className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
                Showing {visible.length} of {totalMatched.toLocaleString()} — refine your search.
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
};
