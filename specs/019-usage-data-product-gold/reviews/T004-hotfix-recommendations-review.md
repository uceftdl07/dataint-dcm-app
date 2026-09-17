# DCM Review Report — T004 hotfix (recommendations UNRESOLVED_COLUMN)

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/019-usage-gold-transverse` (base: `develop`)
**Stack**: python (module `pipelines`)
**Scope**: `pipelines/gold_dbx_usage/recommendations.py`, `specs.py`, `entrypoint.py`, `resources/job_dcm_gold_dbx_usage.yml`, `tests/gold_dbx_usage/{test_recommendations,test_specs,test_entrypoint}.py`.

**Verdict**: **PASS**

## Contexte

Run dev complet du job `dcm_gold_dbx_usage` (T002+T003+T004) : la tâche
`gold_usage_recommendations` a échoué avec
`[UNRESOLVED_COLUMN.WITH_SUGGESTION] lp.estimated_cost_usd`. La règle
LIFECYCLE "inutilisé" joignait `latest_query_performance` (grain requête,
sans `estimated_cost_usd`) au lieu de `table_popularity_daily` (grain
table, colonne réelle) pour calculer `estimated_savings_usd`. Non
détectable par les tests unitaires `FakeSpark` (pas de validation de
grammaire SQL réelle contre le vrai schéma).

## Correctif

- `build_usage_recommendations` : nouveau paramètre `popularity_daily_table`,
  CTE `latest_popularity` ajoutée, jointure LIFECYCLE corrigée.
- `RECOMMENDATIONS_SPEC.source_tables` étendu (`GOLD_TABLE_POPULARITY_DAILY`).
- `entrypoint.py`/`resources/job_dcm_gold_dbx_usage.yml` : dispatch + `depends_on` mis à jour.
- Nouveau test de non-régression : `test_lifecycle_estimated_savings_reads_popularity_not_query_performance`.

## Gates

| Gate | Status | Detail |
|------|--------|--------|
| ruff (module + tests) | PASS | `ruff check pipelines/gold_dbx_usage/ tests/gold_dbx_usage/` → 0 violation |
| pytest (suite complète) | PASS | `pytest -q` → 465 passed (129 dans `tests/gold_dbx_usage/`, +1 vs revue précédente) |
| mypy (`-p pipelines.gold_dbx_usage`) | PASS (baseline identique) | 10 erreurs pré-existantes dans `forecast_daily.py`, identiques au précédent mergé `gold_dbx_compute/forecast.py` — aucune nouvelle violation |

## Validation dev (re-run)

Re-déployé (`databricks bundle deploy -t dev_local`) puis relancé
`dcm_gold_dbx_usage` : `gold_usage_recommendations` → **SUCCESS** au run
suivant (confirmé fixé). `gold_usage_forecast_daily` (`ai_forecast`) en
cours d'exécution séparément — suivi hors de ce commit.

## Next

- Suivre la fin de `gold_usage_forecast_daily`, vérifier idempotence
  `recommendation_id` puis clôturer T004.
