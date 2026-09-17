# T004 — Gold transverse : recommendations, forecast_daily

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: dataeng/019-usage-gold-transverse
**Jira**: pending
**Depends on**: T002, T003
**Work type**: feature

> **Branch** = git **branch name** only (e.g. `dataeng/019-usage-gold-transverse`). Never a commit SHA.

## Description

Étendre le module `pipelines/gold_dbx_usage/` avec les deux tables transverses : le socle **réactif** (`gold_dbx_usage_recommendations`, règles actionnables unifiées) et le socle **prédictif** (`gold_dbx_usage_forecast_daily`, projections `ai_forecast`). Dernier ticket de l'epic — clôture la couverture fonctionnelle du spike.

## Files to create/modify

- CREATE `pipelines/gold_dbx_usage/recommendations.py` — `gold_dbx_usage_recommendations` (règles de génération, cf. spike datamapping §4.1, `recommendation_id = sha2(object_type||object_id||category||generated_date)`)
- CREATE `pipelines/gold_dbx_usage/forecast_daily.py` — `gold_dbx_usage_forecast_daily` (`ai_forecast` SQL natif sur historique `popularity_daily`/`consumer_daily`, cf. research.md R5)
- UPDATE `pipelines/gold_dbx_usage/specs.py` — ajouter les 2 nouvelles entrées `GOLD_SPECS`
- UPDATE `resources/job_dcm_gold_dbx_usage.yml` — ajouter les tâches (`recommendations` chaînée après `table_governance`/`table_catalog`/`table_popularity_daily`/`table_query_performance_daily`/`consumer_daily` ; `forecast_daily` chaînée après `table_popularity_daily`/`consumer_daily`, indépendante de `recommendations`)
- CREATE `tests/gold_dbx_usage/test_recommendations.py`, `test_forecast_daily.py`

## Acceptance Criteria

- [ ] `gold_dbx_usage_recommendations` : au moins une règle de chaque catégorie du spike (`LIFECYCLE`, `FRESHNESS`, `GOVERNANCE`, `RELIABILITY`, `FINOPS`) implémentée et testée (cf. spike datamapping §4.1 tableau de règles)
- [ ] `recommendation_id` stable (hash), 0 doublon sur re-run, `first_seen_date` préservé / `last_seen_date` mis à jour (pas une nouvelle ligne à chaque run)
- [ ] `gold_dbx_usage_forecast_daily` : au moins les 4 métriques du spike projetées (`request_count`, `distinct_consumers`, `estimated_cost_usd`, `data_read_bytes`) via `ai_forecast` SQL natif, avec `lower_bound`/`upper_bound`
- [ ] Aucune dépendance Python nouvelle introduite pour le forecast (invocation SQL uniquement, cf. research.md R5)
- [ ] Aucune colonne `source_lz_id`/`subscription_or_account_id` sur ces 2 tables
- [ ] Job `dcm_gold_dbx_usage` complet (T002+T003+T004) déployé et exécuté avec succès en dev, 0 erreur sur l'ensemble des tâches
- [ ] Tests pytest/chispa verts, ruff/mypy sans nouvelle violation vs baseline

## Tests

- `uv run pytest tests/gold_dbx_usage/test_recommendations.py tests/gold_dbx_usage/test_forecast_daily.py -q`
- Vérification idempotence : cf. `quickstart.md` T004 (requête SQL doublon `recommendation_id`)

## Out of scope

- Toute autre table gold (déjà livrées en T002/T003)
- Frontend/backend consommant ces recommandations (epic future, hors scope — cf. spec Out of scope)
- Ajustement des seuils de règles au-delà des valeurs clarifiées en spec (pas de nouvelle négociation de seuil dans ce ticket)

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside package scope
- [ ] Diff stays reviewable (prefer fewer changed files / one concern)
- [ ] Sub-spec checkboxes reviewed
- [ ] Jira Story lists **Git branch** name (not a commit SHA)

## Notes

- Dépend de T002 (`table_popularity_daily`, `consumer_daily`, `table_query_performance_daily`) et T003 (`table_catalog`, `table_governance`).
- Si `ai_forecast` s'avère incompatible avec le compute serverless générique du job wheel (risque identifié dans l'epic précédente 012 — `ai_forecast` nécessite un SQL Warehouse Pro/Serverless), envisager un `sql_task` séparé plutôt qu'une tâche `python_wheel_task` — précédent : `specs/012-compute-metrics-ingestion/stories/T005-gold-compute-forecast.md`. À vérifier tôt dans ce ticket (spike, avant d'investir dans l'intégration complète).
- Dernier ticket de l'epic — après merge, l'ensemble du spike `docs/spike/usage-data-product-definition/` est couvert côté dataeng.
