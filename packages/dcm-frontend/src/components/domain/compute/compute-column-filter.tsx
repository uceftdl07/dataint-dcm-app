/**
 * Combo de filtre greffée sur l'en-tête d'une colonne (023 T006).
 *
 * Les valeurs proposées viennent du serveur, jamais des lignes affichées : les onze
 * tableaux paginent côté serveur, donc une liste construite depuis `rows` ne
 * proposerait que les valeurs des 25 lignes de la page courante — la faute déjà
 * corrigée par 022 T004, déplacée dans la liste déroulante.
 *
 * Le panneau part dans un **portail**, comme `ComputeInfoTip` : le conteneur du
 * tableau est en `overflow-x-auto`, ce qui rogne tout élément positionné à
 * l'intérieur d'une cellule d'en-tête.
 */
import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { createPortal } from 'react-dom';
import { Check, Filter, Search, X } from 'lucide-react';
import { cn } from '../../../lib/utils';
import { useColumnFilterOptions } from '../../../hooks/useColumnFilterOptions';
import { Skeleton } from '../../ui/skeleton';
import type { ComputeFilterOption, ComputeFilterView } from '../../../types/api';

const PANEL_WIDTH = 248;
const VIEWPORT_MARGIN = 8;

export function ComputeColumnFilter({
  view,
  filterKey,
  columnLabel,
  windowDays,
  workflowId,
  value,
  onChange,
}: {
  view: ComputeFilterView;
  /** Clé allowlistée côté serveur. Jamais devinée depuis l'`id` de la colonne. */
  filterKey: string;
  /** Nom lisible de la colonne, pour l'annonce et les `data-testid`. */
  columnLabel: string;
  windowDays?: number;
  workflowId?: string;
  /** Valeur active, `undefined` si la colonne n'est pas filtrée. */
  value?: string;
  onChange: (next: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  const { data, loading, fetching, searchSettled } = useColumnFilterOptions({
    view,
    column: filterKey,
    open,
    search,
    windowDays,
    workflowId,
  });

  // Mémoïsé : c'est une dépendance du `useMemo` du corps du panneau, et une
  // nouvelle liste vide à chaque rendu le reconstruirait pour rien.
  const options = useMemo<ComputeFilterOption[]>(() => data?.options ?? [], [data?.options]);
  const kind = data?.kind;
  // `enabled: false` n'arrive que lorsque la source n'a pas pu être lue du tout.
  // À distinguer d'une liste vide : « on n'a pas pu construire cette liste » n'est
  // pas « aucune valeur dans votre périmètre ».
  const unavailable = data?.enabled === false;
  const isActive = Boolean(value);

  const updatePosition = useCallback(() => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const maxLeft = Math.max(
      VIEWPORT_MARGIN,
      (window.innerWidth || PANEL_WIDTH) - PANEL_WIDTH - VIEWPORT_MARGIN
    );
    setPosition({
      top: rect.bottom + 4,
      left: Math.min(Math.max(VIEWPORT_MARGIN, rect.right - PANEL_WIDTH), maxLeft),
    });
  }, []);

  useEffect(() => {
    if (!open) {
      setSearch('');
      setActiveIndex(0);
      return undefined;
    }
    updatePosition();
    const focus = requestAnimationFrame(() => {
      // Pas de champ de recherche sur une colonne numérique : les seuils sont
      // déclarés par le serveur, il n'y a rien à y chercher.
      (searchRef.current ?? panelRef.current)?.focus();
    });
    // Le tableau défile horizontalement sous un panneau en position fixe : sans
    // repositionnement, il resterait accroché au pixel où il s'est ouvert.
    const reposition = () => updatePosition();
    window.addEventListener('resize', reposition);
    document.addEventListener('scroll', reposition, true);
    return () => {
      cancelAnimationFrame(focus);
      window.removeEventListener('resize', reposition);
      document.removeEventListener('scroll', reposition, true);
    };
  }, [open, updatePosition]);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDownOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (panelRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDownOutside);
    return () => document.removeEventListener('mousedown', onPointerDownOutside);
  }, [open]);

  const close = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  const select = useCallback(
    (option: ComputeFilterOption) => {
      // Rechoisir la valeur déjà posée l'enlève : c'est le geste attendu d'une
      // liste à choix unique, et il évite d'aller chercher « Effacer ».
      onChange(option.value === value ? null : option.value);
      setOpen(false);
    },
    [onChange, value]
  );

  const onPanelKeyDown = (event: ReactKeyboardEvent) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      close();
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex((index) => Math.min(index + 1, Math.max(0, options.length - 1)));
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((index) => Math.max(index - 1, 0));
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      const option = options[activeIndex];
      if (option) select(option);
    }
  };

  const body = useMemo(() => {
    if (loading && options.length === 0) {
      return (
        <div className="space-y-1.5 px-3 py-2.5">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-4/5" />
        </div>
      );
    }
    if (unavailable) {
      return (
        <p className="px-3 py-3 text-[11px] leading-snug text-muted-foreground">
          Liste indisponible : cette source n’a pas pu être lue. Le filtre reste saisissable
          ailleurs, mais aucune valeur ne peut être proposée ici.
        </p>
      );
    }
    if (options.length === 0) {
      return (
        <p className="px-3 py-3 text-[11px] leading-snug text-muted-foreground">
          {data?.truncated
            ? 'Trop de valeurs distinctes pour les lister : affinez la recherche.'
            : 'Aucune valeur dans votre périmètre.'}
        </p>
      );
    }
    return (
      <ul id={listId} role="listbox" aria-label={`Valeurs de ${columnLabel}`} className="max-h-56 overflow-y-auto py-1">
        {options.map((option, index) => {
          const selected = option.value === value;
          return (
            <li
              key={option.value}
              role="option"
              aria-selected={selected}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => select(option)}
              className={cn(
                'flex cursor-pointer items-center gap-2 px-3 py-1.5 text-[11px] font-normal normal-case tracking-normal',
                index === activeIndex ? 'bg-accent/60 text-foreground' : 'text-muted-foreground'
              )}
            >
              <span className="min-w-0 flex-1 truncate" title={option.label}>
                {option.label}
              </span>
              {option.count == null ? null : (
                <span className="shrink-0 tabular-nums opacity-70">
                  {option.count.toLocaleString('fr-FR')}
                </span>
              )}
              {selected ? <Check className="size-3.5 shrink-0 text-primary" aria-hidden /> : null}
            </li>
          );
        })}
      </ul>
    );
  }, [
    loading,
    unavailable,
    options,
    data?.truncated,
    listId,
    columnLabel,
    value,
    activeIndex,
    select,
  ]);

  const panel =
    open && typeof document !== 'undefined'
      ? createPortal(
          <div
            ref={panelRef}
            tabIndex={-1}
            data-testid={`column-filter-panel-${columnLabel}`}
            className="fixed z-[9998] overflow-hidden rounded-lg border border-border bg-popover text-popover-foreground shadow-lg focus:outline-none"
            style={{ top: position.top, left: position.left, width: PANEL_WIDTH }}
            onKeyDown={onPanelKeyDown}
            onClick={(event) => event.stopPropagation()}
          >
            {kind === 'numeric' ? (
              <p className="border-b border-border/70 px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Seuils proposés par le serveur
              </p>
            ) : (
              <div className="flex items-center gap-2 border-b border-border/70 px-3 py-2">
                <Search className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                <input
                  ref={searchRef}
                  type="text"
                  value={search}
                  onChange={(event) => {
                    setSearch(event.target.value);
                    setActiveIndex(0);
                  }}
                  placeholder="Rechercher…"
                  aria-label={`Rechercher une valeur de ${columnLabel}`}
                  aria-controls={listId}
                  className="w-full border-0 bg-transparent p-0 text-[11px] font-normal normal-case tracking-normal text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-0"
                />
                {fetching || !searchSettled ? (
                  <span
                    className="size-1.5 shrink-0 animate-pulse rounded-full bg-primary"
                    aria-hidden
                  />
                ) : null}
              </div>
            )}

            {body}

            {data?.truncated && options.length > 0 ? (
              <p className="border-t border-border/70 px-3 py-1.5 text-[10px] font-normal normal-case leading-snug tracking-normal text-muted-foreground">
                Liste tronquée : affinez la recherche pour voir le reste.
              </p>
            ) : null}

            {isActive ? (
              <button
                type="button"
                onClick={() => {
                  onChange(null);
                  setOpen(false);
                }}
                className="flex w-full items-center gap-1.5 border-t border-border/70 px-3 py-2 text-[10.5px] font-bold normal-case tracking-normal text-muted-foreground transition-colors hover:text-foreground"
              >
                <X className="size-3" aria-hidden />
                Effacer ce filtre
              </button>
            ) : null}
          </div>,
          document.body
        )
      : null;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={listId}
        aria-label={
          isActive ? `Filtrer la colonne ${columnLabel} (actif)` : `Filtrer la colonne ${columnLabel}`
        }
        data-testid={`column-filter-${columnLabel}`}
        data-active={isActive ? 'true' : 'false'}
        // Le bouton de tri est un frère dans la même cellule d'en-tête : ouvrir le
        // filtre ne doit ni trier ni démarrer un redimensionnement.
        onPointerDown={(event) => event.stopPropagation()}
        onClick={(event) => {
          event.stopPropagation();
          event.preventDefault();
          setOpen((current) => !current);
        }}
        onKeyDown={(event) => event.stopPropagation()}
        className={cn(
          'inline-flex size-4 shrink-0 items-center justify-center rounded transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tdf-blue/40',
          isActive ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
        )}
      >
        <Filter className={cn('size-3', isActive && 'fill-current')} aria-hidden />
      </button>
      {panel}
    </>
  );
}
