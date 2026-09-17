import { useEffect, useRef, Fragment, type ReactNode } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown, Columns3, FilterX } from 'lucide-react';
import { ListPagination } from '../list-pagination';
import { ComputeColumnFilter } from './compute-column-filter';
import { ComputeColumnResizer } from './compute-column-resizer';
import { ComputeEmptyState } from './compute-empty-state';
import { ComputeInfoTip } from './compute-info-tip';
import { Skeleton } from '../../ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../../ui/table';
import { useColumnWidths } from '../../../hooks/useColumnWidths';
import { countActiveColumnFilters, withColumnFilter } from '../../../lib/compute/column-filters';
import { cn } from '../../../lib/utils';
import type { ComputeColumnFilterValues, ComputeFilterView } from '../../../types/api';

export type SortDirection = 'asc' | 'desc';

export type ComputeDataTableColumn<T> = {
  id: string;
  header: ReactNode;
  description?: string;
  align?: 'left' | 'right';
  className?: string;
  sortable?: boolean;
  /** Largeur de départ en pixels. Toutes les colonnes compute la déclarent. */
  width?: number;
  minWidth?: number;
  maxWidth?: number;
  /** `false` pour une colonne d'action ou d'icône : rien à y élargir. */
  resizable?: boolean;
  /**
   * Nom lisible de la colonne pour l'annonce de la poignée, quand `header` n'est
   * pas un simple texte (badge, icône, libellé composé).
   */
  headerLabel?: string;
  /**
   * Clé allowlistée côté serveur, à déclarer explicitement pour rendre la combo de
   * filtre. **Jamais dérivée de l'`id`** : les deux coïncident souvent, mais une
   * colonne d'affichage (`cost_prev`, `history`, `actions`) porte un `id` qui
   * n'existe pas dans l'allowlist, et une clé inventée part en 422.
   */
  filterKey?: string;
  cell: (row: T) => ReactNode;
};

/**
 * Périmètre supplémentaire dont l'endpoint de valeurs distinctes a besoin pour
 * répondre dans le **même** périmètre que le tableau. Sans lui, une combo ouverte
 * au-dessus d'un tableau réglé sur 90 jours listerait les valeurs de la veille.
 */
export type ComputeDataTableFilterScope = {
  windowDays?: number;
  workflowId?: string;
};

/**
 * Nom annoncé par la poignée de redimensionnement. `header` étant un `ReactNode`,
 * il n'est exploitable que lorsqu'il s'agit déjà d'un texte ; sinon `headerLabel`
 * puis l'`id` prennent le relais — jamais une chaîne vide, qui rendrait la
 * poignée muette.
 */
function columnLabelOf<T>(column: ComputeDataTableColumn<T>): string {
  if (column.headerLabel) {
    return column.headerLabel;
  }
  if (typeof column.header === 'string' || typeof column.header === 'number') {
    // `header: ''` existe dans le code (colonne d'action de LakeflowJobDetail) :
    // un en-tête vide est un `ReactNode` valide mais un nom inutilisable.
    const text = String(column.header).trim();
    if (text) {
      return text;
    }
  }
  return column.id;
}

/**
 * Contenu d'une cellule, coupé à la largeur de sa colonne et lisible en entier au
 * survol.
 *
 * Le texte de l'infobulle est lu **après le rendu**, sur le DOM, et non déduit de
 * l'arbre React : la plupart des cellules rendent un composant
 * (`<ClusterCell/>`, `<StatusBadge/>`, `<WaitStack/>`) dont le texte n'est pas
 * dans `props.children` et n'est donc pas extractible avant rendu. `textContent`
 * ne provoque aucun calcul de mise en page, contrairement à une mesure de
 * débordement — et une largeur ajustée à la main par l'utilisateur peut couper
 * n'importe quelle cellule, donc l'infobulle n'a pas à être conditionnelle.
 *
 * L'attribut est posé directement sur le nœud plutôt que par un état : un état par
 * cellule ferait un second rendu de tout le tableau à chaque page.
 */
function ComputeDataTableCellContent({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const text = element.textContent?.trim();
    // Un `title` vide serait une infobulle vide au survol, pas l'absence d'infobulle.
    if (text) element.setAttribute('title', text);
    else element.removeAttribute('title');
  });

  return (
    <span ref={ref} className="block min-w-0 truncate">
      {children}
    </span>
  );
}

function sortIconOf(sortable: boolean | undefined, direction: SortDirection | null) {
  if (!sortable) {
    return null;
  }
  if (direction === null) {
    return ArrowUpDown;
  }
  return direction === 'asc' ? ArrowUp : ArrowDown;
}

function ariaSortOf(sortable: boolean | undefined, direction: SortDirection | null) {
  if (!sortable) {
    return undefined;
  }
  if (direction === null) {
    return 'none' as const;
  }
  return direction === 'asc' ? ('ascending' as const) : ('descending' as const);
}

/**
 * Cellule d'en-tête : libellé, infobulle, indicateur de tri et poignée de
 * redimensionnement. Extraite du tableau parce que c'est la cellule la plus
 * chargée du composant — et celle sur laquelle viendra se greffer le filtre.
 */
function ComputeDataTableHeaderCell<T>({
  column,
  width,
  bounds,
  resizable,
  sortDirection,
  onSortChange,
  onResize,
  onResetWidth,
  filterView,
  filterScope,
  filterValue,
  onFilterChange,
  filterControl,
  locale = 'fr',
}: {
  column: ComputeDataTableColumn<T>;
  width: number;
  bounds: { min: number; max: number };
  /**
   * Décidé par le tableau, pas seulement par la colonne : `resizable: false` en
   * déclaration, mais aussi la colonne élastique, dont la largeur est celle qui
   * reste et non une valeur qu'on règle.
   */
  resizable: boolean;
  /** `null` = colonne triable mais non triée ; `undefined` traité comme non triable. */
  sortDirection: SortDirection | null;
  onSortChange?: (key: string) => void;
  onResize: (width: number) => void;
  onResetWidth: () => void;
  filterView?: ComputeFilterView;
  filterScope?: ComputeDataTableFilterScope;
  filterValue?: string;
  filterControl?: ReactNode;
  locale?: 'fr' | 'en';
  onFilterChange?: (key: string, next: string | null) => void;
}) {
  const SortIcon = sortIconOf(column.sortable, sortDirection);
  const alignRight = column.align === 'right';
  const label = columnLabelOf(column);
  const content = (
    <>
      {/* Un en-tête coupé rend la colonne muette : c'est lui qui porte son sens,
          donc son nom complet doit rester lisible au survol. */}
      <span className="min-w-0 truncate" title={label}>
        {column.header}
      </span>
      {column.description ? (
        <ComputeInfoTip description={column.description} label={`${column.id} description`} />
      ) : null}
      {SortIcon ? <SortIcon className="size-3.5 shrink-0 opacity-70" /> : null}
    </>
  );

  // L'entonnoir est un **frère** du bouton de tri, pas un enfant : un bouton
  // imbriqué dans un bouton est du HTML invalide, et le clic serait ambigu.
  const filter =
    column.filterKey && filterView && onFilterChange ? (
      <ComputeColumnFilter
        view={filterView}
        filterKey={column.filterKey}
        columnLabel={label}
        windowDays={filterScope?.windowDays}
        workflowId={filterScope?.workflowId}
        value={filterValue}
        onChange={(next) => onFilterChange(column.filterKey!, next)}
      />
    ) : null;

  return (
    <TableHead
      className={cn(
        'relative px-4 py-2.5 text-[10px] font-black uppercase tracking-[1.2px]',
        alignRight ? 'text-right' : 'text-left',
        column.className
      )}
      aria-sort={ariaSortOf(column.sortable, sortDirection)}
    >
      <span className={cn('flex w-full items-center gap-1', alignRight && 'justify-end')}>
        {column.sortable && onSortChange ? (
          <button
            type="button"
            onClick={() => onSortChange(column.id)}
            className={cn(
              'flex min-w-0 items-center gap-1.5 rounded-md pr-1 transition-colors hover:text-foreground',
              alignRight ? 'justify-end' : 'flex-1'
            )}
          >
            {content}
          </button>
        ) : (
          <span
            className={cn(
              'flex min-w-0 items-center gap-1.5 pr-1',
              alignRight ? 'justify-end' : 'flex-1'
            )}
          >
            {content}
          </span>
        )}
        {filterControl ?? filter}
      </span>
      {resizable ? (
        <ComputeColumnResizer
          locale={locale}
          columnLabel={label}
          width={width}
          min={bounds.min}
          max={bounds.max}
          onResize={onResize}
          onReset={onResetWidth}
        />
      ) : null}
    </TableHead>
  );
}

export function ComputeDataTable<T>({
  tableId,
  columns,
  rows,
  rowKey,
  loading,
  emptyTitle,
  emptyDescription,
  onRowClick,
  toolbar,
  pagination,
  sort,
  onSortChange,
  filterView,
  filterScope,
  filters,
  onFiltersChange,
  expandedRowKey,
  renderExpandedRow,
  renderColumnFilter,
  locale = 'fr',
  minWidthClassName = 'min-w-[980px]',
  stretchColumnId,
}: {
  /**
   * Identifiant de persistance des largeurs. **Requis** : une valeur par défaut
   * ferait silencieusement partager les largeurs entre deux tableaux d'une même
   * page (vue d'ensemble et onglet Coût). Le dériver de la route ou de la liste
   * des ids de colonnes casserait dès l'ajout d'une colonne.
   */
  tableId: string;
  columns: ComputeDataTableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  emptyTitle: string;
  emptyDescription: string;
  onRowClick?: (row: T) => void;
  toolbar?: ReactNode;
  sort?: { key: string; direction: SortDirection };
  onSortChange?: (key: string) => void;
  pagination?: {
    currentPage: number;
    totalPages: number;
    totalItems: number;
    startIndex: number;
    endIndex: number;
    hasPreviousPage: boolean;
    hasNextPage: boolean;
    onPrevious: () => void;
    onNext: () => void;
  };
  /**
   * Vue de l'allowlist serveur. Sa présence — avec `onFiltersChange` — est ce qui
   * fait apparaître les entonnoirs sur les colonnes portant un `filterKey`.
   */
  filterView?: ComputeFilterView;
  filterScope?: ComputeDataTableFilterScope;
  /**
   * Filtres actifs, **détenus par la page**. Le tableau ne les stocke pas : c'est la
   * page qui les envoie dans sa requête et qui doit revenir à la page 1 quand ils
   * changent, et un état dupliqué ici finirait par contredire ce qui est affiché.
   */
  filters?: ComputeColumnFilterValues;
  onFiltersChange?: (next: ComputeColumnFilterValues) => void;
  /**
   * Ligne dépliée, détenue par la page : le détail vit sous la ligne plutôt que
   * dans un tiroir quand il se lit en colonnes alignées sur le tableau.
   */
  expandedRowKey?: string | null;
  renderExpandedRow?: (row: T) => ReactNode;
  renderColumnFilter?: (column: ComputeDataTableColumn<T>) => ReactNode;
  locale?: 'fr' | 'en';
  minWidthClassName?: string;
  /**
   * Colonne qui absorbe la largeur restante quand le conteneur est plus large que
   * la somme des colonnes — sans elle, le `<table>` s'arrête à cette somme et
   * laisse un vide à droite de sa carte sur un grand écran.
   *
   * **Opt-in, et une seule colonne.** Les autres gardent leurs pixels exacts, donc
   * leurs poignées restent justes : laisser le navigateur répartir le surplus sur
   * toutes les colonnes ferait sauter la première poignée saisie, la largeur de
   * départ du glissement étant la valeur déclarée et non la valeur rendue.
   *
   * À réserver à la colonne large et tronquée d'un tableau (un nom, un chemin) : la
   * donner à une colonne de chiffres alignés à droite éloignerait les valeurs de
   * leur en-tête.
   */
  stretchColumnId?: string;
}) {
  const { widths, totalWidth, bounds, setWidth, resetColumn, resetAll, isCustomized } =
    useColumnWidths(tableId, columns);

  // Un id qui ne désigne aucune colonne est ignoré : sans ce garde-fou, une faute
  // de frappe laisserait le `<table>` en largeur 100 % avec toutes ses colonnes
  // fixes, donc une colonne fantôme à droite.
  const stretchedColumnId =
    stretchColumnId && columns.some((column) => column.id === stretchColumnId)
      ? stretchColumnId
      : null;

  const activeFilterCount = countActiveColumnFilters(filters);
  const onFilterChange = onFiltersChange
    ? (key: string, next: string | null) => onFiltersChange(withColumnFilter(filters, key, next))
    : undefined;

  return (
    <div className="overflow-hidden rounded-[var(--card-radius)] border border-border bg-[var(--card-background)] shadow-[var(--card-shadow)]">
      {toolbar || isCustomized || activeFilterCount > 0 ? (
        <div className="flex flex-wrap items-center gap-2 border-b border-border/70 px-3 py-2.5">
          {toolbar ? <div className="min-w-0 flex-1">{toolbar}</div> : <div className="flex-1" />}
          {/* Un filtre posé sur une colonne au milieu d'un tableau large est
              invisible : ce bouton est le seul endroit qui dit combien sont actifs
              et le seul geste qui les enlève tous d'un coup. */}
          {activeFilterCount > 0 && onFiltersChange ? (
            <button
              type="button"
              onClick={() => onFiltersChange({})}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border px-2 py-1 text-[11px] font-semibold text-muted-foreground transition-colors hover:bg-accent/40 hover:text-foreground"
            >
              <FilterX className="size-3.5" />
              {locale === 'en' ? 'Clear all filters' : 'Effacer tous les filtres'} (
              {activeFilterCount})
            </button>
          ) : null}
          {/* Affiché seulement quand une largeur diverge de sa déclaration : un
              bouton toujours visible qui ne fait rien la plupart du temps est du bruit. */}
          {isCustomized ? (
            <button
              type="button"
              onClick={resetAll}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border px-2 py-1 text-[11px] font-semibold text-muted-foreground transition-colors hover:bg-accent/40 hover:text-foreground"
            >
              <Columns3 className="size-3.5" />
              {locale === 'en' ? 'Reset column widths' : 'Réinitialiser les largeurs'}
            </button>
          ) : null}
        </div>
      ) : null}

      <div className="overflow-x-auto">
        <Table
          className={cn('table-fixed border-collapse text-left text-xs', minWidthClassName)}
          // Avec une colonne élastique, `totalWidth` devient un **plancher** : le
          // tableau remplit sa carte quand elle est plus large, et redevient
          // défilant en dessous, exactement comme sans la prop.
          style={
            stretchedColumnId ? { width: '100%', minWidth: totalWidth } : { width: totalWidth }
          }
        >
          {/* `table-layout: fixed` ne suffit pas : c'est `<colgroup>` qui porte les
              largeurs, et la largeur explicite du `<table>` qui empêche le
              navigateur de les redistribuer pour remplir le conteneur. */}
          <colgroup>
            {columns.map((column) => (
              // La colonne élastique part sans largeur : sous `table-layout: fixed`
              // une colonne `auto` prend ce qui reste, et elle est seule à le faire.
              // Sa largeur déclarée continue de compter dans le plancher, donc elle
              // ne descend jamais sous ce qu'elle mesure aujourd'hui.
              <col
                key={column.id}
                data-column-id={column.id}
                style={{
                  width: column.id === stretchedColumnId ? undefined : widths[column.id],
                }}
              />
            ))}
          </colgroup>
          <TableHeader>
            <TableRow className="border-b border-border bg-muted/40 hover:bg-muted/40">
              {columns.map((column) => (
                <ComputeDataTableHeaderCell
                  key={column.id}
                  column={column}
                  filterControl={renderColumnFilter?.(column)}
                  locale={locale}
                  width={widths[column.id]}
                  bounds={bounds(column.id)}
                  resizable={column.resizable !== false && column.id !== stretchedColumnId}
                  sortDirection={sort?.key === column.id ? sort.direction : null}
                  onSortChange={onSortChange}
                  onResize={(next) => setWidth(column.id, next)}
                  onResetWidth={() => resetColumn(column.id)}
                  filterView={filterView}
                  filterScope={filterScope}
                  filterValue={column.filterKey ? filters?.[column.filterKey] : undefined}
                  onFilterChange={onFilterChange}
                />
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading && rows.length === 0 ? (
              Array.from({ length: 8 }).map((_, index) => (
                <TableRow key={index} className="border-b border-border/50 hover:bg-transparent">
                  <TableCell colSpan={columns.length} className="px-4 py-3">
                    <Skeleton className="h-8 w-full" />
                  </TableCell>
                </TableRow>
              ))
            ) : rows.length === 0 ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={columns.length} className="px-4 py-14">
                  <ComputeEmptyState
                    title={emptyTitle}
                    description={emptyDescription}
                    className="border-0 bg-transparent p-0 shadow-none"
                  />
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => {
                const key = rowKey(row);
                const expanded = renderExpandedRow != null && expandedRowKey === key;
                return (
                  <Fragment key={key}>
                    <TableRow
                      className={cn(
                        'border-b border-border/70',
                        onRowClick &&
                          'cursor-pointer transition-colors hover:bg-accent/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring',
                        expanded && 'bg-accent/30'
                      )}
                      tabIndex={onRowClick ? 0 : undefined}
                      onClick={
                        onRowClick
                          ? (event) => {
                              event.currentTarget.focus();
                              onRowClick(row);
                            }
                          : undefined
                      }
                      onKeyDown={
                        onRowClick
                          ? (event) => {
                              if (
                                event.target === event.currentTarget &&
                                (event.key === 'Enter' || event.key === ' ')
                              ) {
                                event.preventDefault();
                                onRowClick(row);
                              }
                            }
                          : undefined
                      }
                    >
                      {columns.map((column) => (
                        // `overflow-hidden` sur la cellule est le dernier rempart : la
                        // largeur est fixe, donc sans lui un contenu plus large sort de sa
                        // colonne et recouvre la voisine. L'enveloppe intérieure coupe le
                        // texte proprement (points de suspension) et porte l'infobulle.
                        <TableCell
                          key={column.id}
                          className={cn(
                            'overflow-hidden px-4 py-2.5',
                            column.align === 'right' ? 'text-right' : 'text-left',
                            column.className
                          )}
                        >
                          <ComputeDataTableCellContent>
                            {column.cell(row)}
                          </ComputeDataTableCellContent>
                        </TableCell>
                      ))}
                    </TableRow>
                    {expanded ? (
                      <TableRow className="border-b border-border/70 bg-muted/40 hover:bg-muted/40">
                        <TableCell colSpan={columns.length} className="p-0">
                          {renderExpandedRow(row)}
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </Fragment>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

      {pagination ? (
        <div className="px-4 pb-4">
          <ListPagination
            currentPage={pagination.currentPage}
            totalPages={pagination.totalPages}
            totalItems={pagination.totalItems}
            startIndex={pagination.startIndex}
            endIndex={pagination.endIndex}
            hasPreviousPage={pagination.hasPreviousPage}
            hasNextPage={pagination.hasNextPage}
            onPrevious={pagination.onPrevious}
            onNext={pagination.onNext}
          />
        </div>
      ) : null}
    </div>
  );
}
