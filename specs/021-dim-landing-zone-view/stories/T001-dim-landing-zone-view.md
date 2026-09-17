# T001 — Rename `dim_landing_zone` → collector, vue union, suppression FK gold

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: dataeng/021-rename-collector-vue-union-dim-landing
**Jira**: [DCINT-302](https://tdf.atlassian.net/browse/DCINT-302) (Epic [DCINT-301](https://tdf.atlassian.net/browse/DCINT-301))
**Depends on**: —
**Work type**: technique

> **Branch** = git **branch name** only (e.g. `dataeng/021-rename-collector-vue-union-dim-landing`). Never a commit SHA.

## Description

Transformer la dimension `dim_landing_zone` (aujourd'hui **table streaming DLT SCD1**) en **vue Unity Catalog** unifiant deux périmètres de LZ (collectées par DCM + workspaces référentiels `dim_dbx_workspace`), enrichie par le référentiel Business Application, avec `lz_id` recalculé et déduplication par `subscription_or_account_id`.

Trois changements indissociables, dans un seul package / une seule PR :

1. **Renommer** la table DLT `dim_landing_zone` → `dim_landing_zone_collector` (mécanique SCD1 / `apply_changes` inchangée) et rediriger les 3 `dlt.read` internes.
2. **Supprimer** les 7 contraintes FK `fk_gold_*_lz … REFERENCES … dim_landing_zone (lz_id)` des tables gold.
3. **Créer** le module `pipelines/gold_landing_zone/` produisant, via une **tâche wheel** (`CREATE OR REPLACE VIEW`), la vue `dim_landing_zone` — SQL généré par une fonction pure `build_dim_landing_zone_view_sql(catalog, schema)` unit-testable.

Pattern mirroir de feature 020 (`pipelines/gold_dbx_workspace/`). Cf. [plan.md](../plan.md), [research.md](../research.md), [data-model.md](../data-model.md).

## Files to create/modify

**Édition `pipelines/dlt_03_gold_layer.py`**
- MODIFY `dlt.create_streaming_table(name="dim_landing_zone", …)` → `name="dim_landing_zone_collector"` + renommer PK `pk_dim_landing_zone` → `pk_dim_landing_zone_collector`
- MODIFY `dlt.apply_changes(target="dim_landing_zone", …)` → `target="dim_landing_zone_collector"` (`keys`, `sequence_by`, `stored_as_scd_type=1` inchangés)
- MODIFY 3× `dlt.read("dim_landing_zone")` → `dlt.read("dim_landing_zone_collector")` dans `gold_cost_summary`, `gold_standard_check_score`, `gold_security_summary` (jointures `source_lz_id == lz_id` inchangées)
- DELETE 7 fragments `+ f", CONSTRAINT fk_gold_*_lz FOREIGN KEY (source_lz_id) REFERENCES {_CATALOG_SCHEMA}.dim_landing_zone (lz_id)"` : `gold_pipeline_summary`, `gold_compute_utilization`, `gold_cost_summary`, `gold_database_capacity_alerts`, `gold_standard_check_score`, `gold_security_summary`, `gold_activity_performance` (PK conservées)

**Nouveau module vue** (mirror `pipelines/gold_dbx_workspace/`)
- CREATE `pipelines/gold_landing_zone/__init__.py`
- CREATE `pipelines/gold_landing_zone/view.py` — `build_dim_landing_zone_view_sql(catalog: str, schema: str) -> str` (fonction pure, aucun I/O) produisant le `CREATE OR REPLACE VIEW` (UNION ALL `dim_dbx_workspace` + `dim_landing_zone_collector`, INNER JOIN BA, QUALIFY dédup, `lz_id` recalculé, colonnes héritées castées)
- CREATE `pipelines/gold_landing_zone/entrypoint.py` — tâche wheel : lit `catalog`/`schema` (params job), exécute `DROP TABLE IF EXISTS {catalog}.{schema}.dim_landing_zone` **puis** `spark.sql(build_dim_landing_zone_view_sql(...))`

**Câblage DAB**
- CREATE `resources/job_dcm_gold_landing_zone.yml` — job wheel serverless, `entry_point: dcm-gold-landing-zone`, named_parameters `catalog`/`schema`, cron en aval des sources
- MODIFY `pyproject.toml` — `[project.scripts]` `dcm-gold-landing-zone = "pipelines.gold_landing_zone.entrypoint:run"`
- MODIFY `databricks.yml` — override `pause_status: PAUSED` du job en `dev`/`dev_local`

**Tests**
- CREATE `tests/gold_landing_zone/test_view.py` — assertions string-based sur `build_dim_landing_zone_view_sql`
- MODIFY `tests/test_dlt_03_gold_layer.py` — `dlt.read` internes → `dim_landing_zone_collector` ; aucune FK vers `dim_landing_zone`

## Acceptance Criteria

- [ ] Table DLT renommée `dim_landing_zone_collector`, `apply_changes` SCD1 (`keys=["lz_id"]`, `sequence_by=_ingested_at`) et colonnes inchangées ; PK renommée `pk_dim_landing_zone_collector`
- [ ] Les 3 agrégats gold (`cost_summary`, `standard_check_score`, `security_summary`) lisent `dim_landing_zone_collector` et produisent les mêmes colonnes `environment`/`owner_team` qu'avant
- [ ] Aucune des 7 tables gold ne déclare de FK vers `dim_landing_zone` ; leurs PK sont inchangées ; le bundle valide et déploie
- [ ] `build_dim_landing_zone_view_sql(catalog, schema)` est une fonction pure paramétrée (aucun `catalog`/`schema` codé en dur), produisant `CREATE OR REPLACE VIEW {catalog}.{schema}.dim_landing_zone`
- [ ] La vue projette 10 colonnes : `lz_id` (recalculé `CONCAT('lz-', cloud_provider, '-', subscription_or_account_id)`), `cloud_provider`, `subscription_or_account_id`, `lz_name`, `environment`, `region`, `owner_team`, `onboarded_at`, `business_application_id`, `business_application_name`
- [ ] UNION ALL `dim_dbx_workspace` (colonnes héritées `CAST(NULL AS STRING/DATE)`) + `dim_landing_zone_collector` (`WHERE subscription_or_account_id IS NOT NULL`)
- [ ] INNER JOIN `dim_reference_landing_zone_business_application` sur `subscription_or_account_id` (LZ sans BA absentes — clarif C1)
- [ ] Dédup `QUALIFY ROW_NUMBER() OVER (PARTITION BY subscription_or_account_id ORDER BY CASE WHEN lz_name IS NOT NULL THEN 0 ELSE 1 END) = 1` (clarif C4)
- [ ] L'entrypoint exécute `DROP TABLE IF EXISTS … dim_landing_zone` avant `CREATE OR REPLACE VIEW` (l'ancienne table DLT physique bloquerait sinon la vue homonyme — cf. research.md R2)
- [ ] Job `dcm_gold_landing_zone` déployé et exécuté avec succès en dev ; `DESCRIBE EXTENDED … dim_landing_zone` renvoie un objet de type VUE
- [ ] Tests pytest verts ; ruff/mypy sans nouvelle violation sur le module `gold_landing_zone` (le module DLT reste jugé sur son baseline existant)

## Tests

- `uv run pytest -q tests/gold_landing_zone/test_view.py tests/test_dlt_03_gold_layer.py`
- `uv run ruff check pipelines/gold_landing_zone tests/gold_landing_zone`
- `uv run mypy -p pipelines.gold_landing_zone`
- Validation dev : `databricks bundle validate -t dev` → `deploy` → `run dcm_gold_landing_zone` (cf. [quickstart.md](../quickstart.md))

## Out of scope

- Adaptation des consommateurs backend de `dim_landing_zone` (`governance.py`, `lz_scope.py`, `projects.py`…) — la vue conserve volontairement les colonnes lues (clarif C2), aucune modification backend nécessaire
- Production de `dim_dbx_workspace` (feature 020) et `dim_reference_landing_zone_business_application` (job `reference_lz`) — déjà existants
- Migration/backfill de données — le rename conserve le contenu de la table

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside package scope (`packages/dcm-databricks-pipeline`)
- [ ] Diff stays reviewable (une seule préoccupation, peu de fichiers)
- [ ] Sub-spec checkboxes reviewed
- [ ] Jira Story lists **Git branch** name (not a commit SHA)

## Notes

- Écart assumé (Complexity Tracking, plan.md) : vue produite par tâche wheel hors DLT (croise tables DLT + non-DLT) + `DROP TABLE` de migration one-off.
- Repo memory : `uv run` exige l'exécution non sandboxée ; mypy en module mode `-p pipelines.gold_landing_zone` ; `dev` a `mode: production` dans `databricks.yml` — nouveau job à créer explicitement PAUSED en dev.
- Rollback : revert du commit + redéploiement (rename inverse, restauration des FK, suppression vue + job). Aucune donnée perdue.
