import { useId, useState, type ReactNode, type Ref } from 'react';
import { Search } from 'lucide-react';
import { Button } from '../../ui/button';
import { useUcUsageFilterOptions } from '../../../hooks/useUcUsageQueries';
import { hasUcUsageScope, type UcUsageFilterDraft } from '../../../lib/uc-usage/filters';
import {
  UcUsageChips,
  UcUsageMultiSelect,
  UcUsageSelect,
  type UcUsageMultiSelectOption,
} from './uc-usage-multi-select';

/**
 * Filtres communs aux trois vues de la page et aux deux onglets de la page
 * Gouvernance. Le bouton **Appliquer** est ce qui autorise le premier appel
 * daté : rien ne part au chargement (FR-017).
 */
export function UcUsageFilters({
  draft,
  onDraftChange,
  onApply,
  periodLabel,
  periodPrefix = 'Period',
  applyLabel = 'Apply',
  searchSlot,
  requireScope = false,
  catalogTriggerRef,
}: {
  draft: UcUsageFilterDraft;
  onDraftChange: (next: UcUsageFilterDraft) => void;
  onApply: () => void;
  periodLabel: string;
  periodPrefix?: string;
  applyLabel?: string;
  searchSlot?: ReactNode;
  requireScope?: boolean;
  catalogTriggerRef?: Ref<HTMLButtonElement>;
}) {
  const [tableSearch, setTableSearch] = useState('');
  const scopeHintId = useId();
  const canApply = !requireScope || hasUcUsageScope(draft);
  const options = useUcUsageFilterOptions({
    catalog: draft.catalog,
    schema: draft.schema,
    search: tableSearch,
    includeDeleted: draft.includeDeleted,
  });

  const tableOptions: UcUsageMultiSelectOption[] = (options.data?.tables ?? []).map((entry) => ({
    value: entry.table_full_name,
    label: entry.table_full_name,
    // Une table supprimée n'apparaît ici que si la case est cochée : le dire
    // dans l'option évite de l'ajouter au périmètre sans le savoir.
    hint:
      [entry.catalog, entry.schema, entry.is_deleted ? 'deleted' : null]
        .filter(Boolean)
        .join(' · ') || undefined,
  }));

  return (
    <form
      className="flex flex-col gap-2 rounded-[var(--card-radius)] border border-border bg-[var(--card-background)] p-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (canApply) onApply();
      }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <UcUsageSelect
          triggerRef={catalogTriggerRef}
          label="Catalog"
          value={draft.catalog}
          options={options.data?.catalogs ?? []}
          loading={options.loading}
          allLabel="All catalogs"
          placeholder={requireScope && !hasUcUsageScope(draft) ? 'Choose a catalog' : undefined}
          // Changer de catalogue invalide les tables cochées ailleurs : elles
          // sortiraient du périmètre sans que rien ne le dise.
          onChange={(catalog) => onDraftChange({ ...draft, catalog, schema: '', tables: [] })}
        />
        <UcUsageSelect
          label="Schema"
          value={draft.schema}
          options={options.data?.schemas ?? []}
          loading={options.loading}
          allLabel="All schemas"
          placeholder={requireScope && !hasUcUsageScope(draft) ? 'Choose a schema' : undefined}
          onChange={(schema) => onDraftChange({ ...draft, schema, tables: [] })}
        />
        <UcUsageMultiSelect
          label="Tables"
          values={draft.tables}
          options={tableOptions}
          loading={options.loading}
          truncated={options.data?.truncated}
          search={tableSearch}
          onSearchChange={setTableSearch}
          onChange={(tables) => onDraftChange({ ...draft, tables })}
        />

        {/*
          Le drapeau fait partie du périmètre : il part avec Appliquer, comme le
          catalogue et le schéma, et non au clic sur la case (spec 027).
        */}
        <label className="flex cursor-pointer items-center gap-2 whitespace-nowrap text-xs text-foreground">
          <input
            type="checkbox"
            className="h-3.5 w-3.5 rounded border-input"
            checked={draft.includeDeleted}
            onChange={(event) => onDraftChange({ ...draft, includeDeleted: event.target.checked })}
          />
          Include deleted tables
        </label>

        {searchSlot ? (
          <div className="relative w-[220px]">
            <Search
              size={13}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            {searchSlot}
          </div>
        ) : null}

        <Button
          type="submit"
          size="sm"
          className="h-8"
          disabled={!canApply}
          aria-describedby={!canApply ? scopeHintId : undefined}
        >
          {applyLabel}
        </Button>

        <p className="ml-auto text-xs text-muted-foreground">
          {periodPrefix} : {periodLabel}
        </p>
      </div>

      {!canApply ? (
        <p id={scopeHintId} className="text-xs text-muted-foreground">
          Select a catalog, a schema or at least one table to start the analysis.
        </p>
      ) : null}

      {options.error ? (
        <div role="alert" className="flex flex-wrap items-center gap-2 text-xs text-danger">
          <p>Unable to load catalogs, schemas and tables.</p>
          <Button variant="outline" size="sm" onClick={() => options.refetch()}>
            Retry filters
          </Button>
        </div>
      ) : null}

      <UcUsageChips
        values={draft.tables}
        onRemove={(value) =>
          onDraftChange({ ...draft, tables: draft.tables.filter((entry) => entry !== value) })
        }
      />
    </form>
  );
}
