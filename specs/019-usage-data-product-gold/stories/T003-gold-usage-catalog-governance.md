# T003 — Gold registre/état : table_catalog, table_governance

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: dataeng/019-usage-gold-catalog-governance
**Jira**: pending
**Depends on**: T001, T002
**Work type**: feature

> **Branch** = git **branch name** only (e.g. `dataeng/019-usage-gold-catalog-governance`). Never a commit SHA.

## Description

Étendre le module `pipelines/gold_dbx_usage/` (scaffolding créé en T002) avec les tables d'**état courant** : registre/fraîcheur/opération qualifiée par data product, et snapshot de gouvernance/cycle de vie (inutilisé, orphelin, critique).

> **`gold_dbx_usage_dim_workspace` (pont `workspace_id → LZ`) a été livrée puis retirée du périmètre** (2026-09-04) — voir « Décision : suppression de `dim_workspace` » ci-dessous.

## Files to create/modify

- CREATE `pipelines/gold_dbx_usage/table_catalog.py` — `gold_dbx_usage_table_catalog` (base `curated_dbx_uc_tables` + `curated_dbx_uc_table_tags` pivot + `curated_dbx_uc_table_operations` dernière opération + `gold_dbx_usage_table_daily` pour `last_read_at`)
- CREATE `pipelines/gold_dbx_usage/table_governance.py` — `gold_dbx_usage_table_governance` (base `table_catalog` + `table_popularity_daily` fenêtre N jours + fan-out lineage)
- UPDATE `pipelines/gold_dbx_usage/specs.py` — ajouter les 2 nouvelles entrées `GOLD_SPECS`
- UPDATE `resources/job_dcm_gold_dbx_usage.yml` — ajouter les tâches avec `depends_on: [table_daily]` où pertinent (table_catalog pour last_read_at)
- CREATE `tests/gold_dbx_usage/test_table_catalog.py`, `test_table_governance.py`
- ~~CREATE `pipelines/gold_dbx_usage/dim_workspace.py`~~ / ~~`test_dim_workspace.py`~~ — livrées puis **supprimées** (cf. Décision ci-dessous)

## Acceptance Criteria

- [x] `gold_dbx_usage_table_catalog` : `last_operation` = `MAX_BY(action_name, event_time)` par table (valeur brute `createTable`/`deleteTable`/`updateTables`), `freshness_lag_hours` = `now - last_write_at`
- [x] `gold_dbx_usage_table_governance` : `is_unused` = `days_since_last_read IS NULL OR days_since_last_read > 90` (NULL-safe : jamais lu = inutilisé) ; `is_critical` = `downstream_fanout >= 5` ; `is_stale_but_consumed` = `freshness_lag_hours > 24 AND days_since_last_read < 7` ; `is_orphan` = aucun tag owner/domain/cost_center (seuils clarifiés, cf. spec.md Clarifications)
- [x] Aucune colonne `source_lz_id`/`subscription_or_account_id` sur `table_catalog`/`table_governance` — vérifié (`grep -rn "source_lz_id\|subscription_or_account_id" pipelines/gold_dbx_usage/` vide, plus aucune exception)
- [x] `table_full_name` dérivé présent sur `table_catalog` (`concat_ws('.', ...)`) et propagé sur `table_governance`
- [x] Job `dcm_gold_dbx_usage` étendu déployé/exécuté avec succès en dev, tâches T003 correctement chaînées après T002 — vérifié sur donnée réelle (`DESCRIBE HISTORY`) : `gold_dbx_usage_table_catalog` (`CREATE TABLE AS SELECT`, 88 502 lignes) et `gold_dbx_usage_table_governance` (idem, 88 502 lignes), run manuel du 2026-09-07 sur `dev_local`
- [x] Tests pytest/chispa verts, ruff/mypy sans nouvelle violation vs baseline — 90 tests passent (`pytest tests/gold_dbx_usage/ -q`), `ruff check pipelines/gold_dbx_usage/ tests/gold_dbx_usage/` et `mypy -p pipelines.gold_dbx_usage` clean

## Tests

- `uv run pytest tests/gold_dbx_usage/test_table_catalog.py tests/gold_dbx_usage/test_table_governance.py -q`
- `grep -rn "source_lz_id\|subscription_or_account_id" pipelines/gold_dbx_usage/` → doit être vide (cf. `quickstart.md` T003 étape 2)

## Out of scope

- `gold_dbx_usage_table_daily`, `popularity_daily`, `consumer_daily`, `query_performance_daily` (T002, déjà livrées)
- `gold_dbx_usage_recommendations`, `forecast_daily` (T004)
- `dim_dbx_workspace` (spec 020) — propriété de cette autre feature, non modifiée ici

## Décision : suppression de `dim_workspace` (2026-09-04)

`gold_dbx_usage_dim_workspace` (pont `workspace_id → LZ`, fallback
`coalesce(tags['dcm_lz_id'], tags['Project'], workspace_id)`) a été livrée dans
une passe précédente de ce ticket, puis **retirée** après revue :

- **Redondance identifiée** : la spec 020 (`020-dbx-workspace-dim`, livrée en
  parallèle) a produit `dim_dbx_workspace` (`pipelines.gold_dbx_workspace`,
  `resources/job_dcm_gold_dbx_workspace.yml`) — une vue gold qui résout
  `workspace_id → LZ` via un **vrai référentiel** géré
  (`dim_reference_landing_zone_dbx_workspace`, filtre `status=RUNNING`), déjà
  consommée par la vue `dim_landing_zone` existante
  (`pipelines/gold_landing_zone/view.py`). Le fallback tags de
  `gold_dbx_usage_dim_workspace` était une solution de repli moins fiable pour
  un besoin déjà couvert.
- **Aucun impact donnée** : la table n'a jamais été déployée en dev (0 ligne,
  `SHOW TABLES ... LIKE 'gold_dbx_usage_dim_workspace'` → 0 ligne) —
  suppression sûre.
- **FR-008 simplifiée** : la règle « aucune table gold usage ne porte
  `source_lz_id`/`subscription_or_account_id` » s'applique désormais **sans
  exception** (`dim_workspace` était la seule exception documentée).
- **`[NEEDS DECISION PO]`** (spike datamapping §2.4bis, spec.md Dependency
  Analysis) : **résolu** par cette suppression — pas de rapprochement à
  faire, `dim_dbx_workspace` (020) est l'unique résolution `workspace_id →
  LZ` du projet.

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside package scope
- [ ] Diff stays reviewable (prefer fewer changed files / one concern)
- [ ] Sub-spec checkboxes reviewed
- [ ] Jira Story lists **Git branch** name (not a commit SHA)

## Notes

- Dépend de T001 (registre UC) et T002 (scaffolding module + `table_daily` pour `last_read_at`).
- Bloque T004 (recommendations lit `table_governance`/`table_catalog`).
- `[NEEDS DECISION PO]` résolu par la suppression de `dim_workspace` (cf. section Décision ci-dessus) — plus rien à documenter avant exposition API, la table n'existe plus.

### Statut (2026-09-04)

`table_catalog.py` et `table_governance.py` livrés (T002 mergé/récupéré en amont).
`dim_workspace.py` (livrée dans une passe précédente) a été **retirée** après
revue (redondante avec `dim_dbx_workspace`, spec 020 — cf. section Décision).
Périmètre T003 final : `table_catalog` + `table_governance`, implémentés,
testés (90 tests, `test_table_catalog.py` + `test_table_governance.py`), et
`ruff`/`mypy` clean sur `pipelines/gold_dbx_usage/`.

**Déploiement/exécution en dev** (2026-09-07) : `bundle deploy -t dev_local` puis
run manuel du job `dcm_gold_dbx_usage` — confirmé sur donnée réelle via
`DESCRIBE HISTORY` : `gold_dbx_usage_table_catalog` (`CREATE TABLE AS SELECT`,
88 502 lignes) et `gold_dbx_usage_table_governance` (idem, 88 502 lignes,
même grain que prévu — la jointure `LEFT JOIN` avec `table_popularity_daily`
ne perd aucune ligne). T003 est désormais complet, tous les critères
d'acceptation cochés.

