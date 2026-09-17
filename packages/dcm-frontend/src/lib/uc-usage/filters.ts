/**
 * Périmètre saisi dans la barre de filtres, avant application. Isolé des
 * composants pour que le module de filtres n'exporte que des composants — un
 * export de valeur y casserait le fast refresh.
 */
export interface UcUsageFilterDraft {
  catalog: string;
  schema: string;
  /** Noms qualifiés cochés dans le sélecteur, jamais une saisie libre. */
  tables: string[];
  /**
   * Tables supprimées de Unity Catalog gardées dans l'analyse (spec 027).
   * Décoché par défaut : une table supprimée n'est plus le parc à surveiller,
   * elle est le passé qu'on va chercher explicitement.
   */
  includeDeleted: boolean;
}

export const UC_USAGE_EMPTY_DRAFT: UcUsageFilterDraft = {
  catalog: '',
  schema: '',
  tables: [],
  includeDeleted: false,
};

/**
 * Un catalogue ou un schéma choisi constitue déjà un périmètre explicite. La
 * case « tables supprimées » n'en est pas un : cochée seule, elle ne dit pas
 * quel périmètre analyser.
 */
export function hasUcUsageScope(draft: UcUsageFilterDraft): boolean {
  return Boolean(
    draft.catalog.trim() || draft.schema.trim() || draft.tables.some((table) => table.trim())
  );
}
