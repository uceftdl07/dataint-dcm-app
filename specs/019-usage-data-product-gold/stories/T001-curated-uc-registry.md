# T001 — Curated : registre UC (uc_tables, uc_table_tags, uc_table_operations)

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: dataeng/019-usage-curated-uc-registry
**Jira**: pending
**Depends on**: none
**Work type**: feature

> **Branch** = git **branch name** only (e.g. `dataeng/019-usage-curated-uc-registry`). Never a commit SHA.

## Description

Ajouter 3 nouvelles `IngestionSpec` au registre existant `pipelines/system_tables/specs.py` pour ingérer le **registre Unity Catalog** (métadonnées de table, tags de gouvernance, historique des opérations d'écriture), fondation nécessaire à toutes les tables gold usage (T002-T004). Aucune modification du socle générique (`ingest.py`, `entrypoint.py`, `azure_reader.py`) : uniquement de la configuration déclarative, comme le pattern déjà appliqué en 012/013.

## Files to create/modify

- UPDATE `pipelines/system_tables/specs.py` — ajouter :
  - `curated_dbx_uc_tables` ← `system.information_schema.tables` (full load, clé `cloud_provider, table_catalog, table_schema, table_name`)
  - `curated_dbx_uc_table_tags` ← `system.information_schema.table_tags` (full load, clé `cloud_provider, catalog_name, schema_name, table_name, tag_name`)
  - `curated_dbx_uc_table_operations` ← `system.access.audit` filtré actions d'écriture (nouvelle constante `ACCESS_AUDIT_WRITE_ACTIONS`, watermark `event_time`, clé `cloud_provider, event_id`)
- UPDATE `resources/job_dcm_system_tables.yml` — ajouter les 3 clés dans `for_each.inputs` (aligné `SPEC_KEYS`)
- CREATE `tests/system_tables/test_uc_registry_specs.py` (ou extension `test_specs.py` existant) — tests des 3 nouvelles specs

## Acceptance Criteria

- [ ] `curated_dbx_uc_tables` peuplée en dev, 0 doublon sur `(cloud_provider, table_catalog, table_schema, table_name)`
- [ ] `curated_dbx_uc_table_tags` peuplée en dev, 0 doublon sur `(cloud_provider, catalog_name, schema_name, table_name, tag_name)`
- [ ] `curated_dbx_uc_table_operations` peuplée en dev, watermark `event_time` fonctionnel (re-run incrémental sans re-scan complet), 0 doublon sur `(cloud_provider, event_id)`
- [ ] **Gate de validation obligatoire avant merge** : mapping réel `action_name → operation` observé en dev comparé à `ACCESS_AUDIT_WRITE_ACTIONS` (cf. `quickstart.md` T001 étape 4) ; toute action non mappée reste `NULL` (jamais une valeur inventée, P9)
- [ ] Aucune modification du comportement de `curated_dbx_access_audit` existante (nouvelle constante `ACCESS_AUDIT_WRITE_ACTIONS` distincte de `ACCESS_AUDIT_TABLE_ACTIONS`)
- [x] ~~`table_full_name` dérivé (`concat_ws('.', ...)`) présent sur `curated_dbx_uc_tables`~~ **DEVIATION ASSUMÉE (voir Notes)** : non implémenté en curated, reporté en gold (T003 `table_catalog`)
- [ ] Tests pytest/chispa verts, ruff/mypy sans nouvelle violation vs baseline

## Tests

- `uv run pytest tests/system_tables/ -q`
- `uv run ruff check pipelines/system_tables/`

## Out of scope

- Toute table gold (T002-T004)
- `system.access.column_lineage`, `information_schema.table_privileges` (hors MVP, cf. spec Out of scope)
- Modification de `curated_dbx_access_audit` existante ou de son filtre `ACCESS_AUDIT_TABLE_ACTIONS`

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside package scope
- [ ] Diff stays reviewable (prefer fewer changed files / one concern)
- [ ] Sub-spec checkboxes reviewed
- [ ] Jira Story lists **Git branch** name (not a commit SHA)

## Notes

- Cf. `research.md` R3 pour la justification de la nouvelle constante `ACCESS_AUDIT_WRITE_ACTIONS` (ne pas réutiliser/étendre `ACCESS_AUDIT_TABLE_ACTIONS`).
- Cf. `data-model.md` §"Registre IngestionSpec — T001" pour les noms de constantes exacts attendus.
- Colonnes détaillées : spike `docs/spike/usage-data-product-definition/usage_datamodel.md` §1.2/§1.2bis (reprises sans modification).
- Bloque T002 et T003 — merger en premier.
- **DÉVIATION documentée** : `table_full_name` n'est **pas** ajouté sur `curated_dbx_uc_tables`.
  `IngestionSpec.select_columns` ne supporte que des noms de colonnes bruts sur le
  chemin de lecture natif (`df.select(*select_columns)` — Spark ne parse pas
  d'expression SQL, ex. `concat_ws(...)`, via ce mécanisme) ; l'ajouter exigerait de
  modifier le socle générique (`pipelines/common/readers.py`), explicitement hors
  scope de ce ticket. Cohérent avec la règle curated = fidèle source (P12, no
  transform) : `table_full_name` est déjà qualifié d'« informatif » dans le spike
  (`usage_datamodel.md` §1.2 : "les tables gold usage utilisent catalog/schema/table_name
  séparés"). Reporté à T003 (`gold_dbx_usage_table_catalog`), qui calcule déjà cette
  colonne dérivée. Cf. `review-report-T001.md` pour l'analyse complète.
