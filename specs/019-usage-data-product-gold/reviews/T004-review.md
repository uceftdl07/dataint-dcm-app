# DCM Review Report — T004 (Gold transverse : recommendations, forecast_daily)

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/019-usage-gold-transverse` (base: `develop`)
**Stack**: python (module `pipelines`)
**Scope**: extension du module `pipelines/gold_dbx_usage/` (CREATE `recommendations.py`, `forecast_daily.py` ; UPDATE `specs.py`, `entrypoint.py`, `resources/job_dcm_gold_dbx_usage.yml`) + `tests/gold_dbx_usage/` (CREATE `test_recommendations.py`, `test_forecast_daily.py` ; UPDATE `test_specs.py`, `test_entrypoint.py`). Aucun fichier hors `gold_dbx_usage`/`tests/gold_dbx_usage` modifié.

**Verdict**: **PASS** (gates locaux) — déploiement dev **non exécuté** à ce stade, cf. section dédiée.

## Gates (scopés au diff de cette task)

| Gate | Status | Detail |
|------|--------|--------|
| ruff (module + tests) | PASS | `ruff check pipelines/gold_dbx_usage/ tests/gold_dbx_usage/` → 0 violation |
| pytest (suite complète) | PASS | `pytest -q` → 464 passed (dont 128 dans `tests/gold_dbx_usage/`, +26 nouveaux pour T004), 0 régression |
| mypy (`-p pipelines.gold_dbx_usage`) | PASS (baseline identique au précédent) | 10 erreurs dans `forecast_daily.py`, **rigoureusement identiques** (mêmes types d'erreurs, mêmes lignes relatives) à celles déjà présentes dans `gold_dbx_compute/forecast.py` (précédent direct, déjà mergé sur `develop`) : `requests` sans stubs, `StatementStatus \| None` non narrowed avant `.state`/`.error`, `statement_id: str \| None` passé où `str` est attendu. Duplication assumée du même pattern Statement Execution API (cf. docstring module, research.md R6) → aucune nouvelle violation vs baseline. |

## Note sur `dcm-review.sh` (générique, non diff-aware pour ruff/mypy)

Le script exécuté tel quel remonte aussi des violations pré-existantes hors
scope T004 (`ANN001` dans `tests/test_dlt_workflow.py`, collision de module
`pipelines/sqs_to_volume_drain.py`) — confirmé identiques sur `develop` avant
toute modification de cette task (`git diff origin/develop --stat` vide sur
ces 2 fichiers). Gates ci-dessus scopés manuellement aux fichiers de T004,
tous verts.

## Acceptance Criteria (cf. stories/T004-gold-usage-transverse.md)

- [x] `gold_dbx_usage_recommendations` : 5 catégories du spike implémentées et testées — LIFECYCLE (×2, mutuellement exclusives), FRESHNESS, GOVERNANCE (×2, dédupliquées par priorité), RELIABILITY, FINOPS (grain CONSUMER) — cf. `test_recommendations.py`.
- [x] `recommendation_id` stable (hash sur `first_seen_date`, pas `generated_date` — écart assumé et documenté vs la formule littérale du spike, cf. docstring module), 0 doublon garanti par construction (2 runs identiques même jour → requête SQL strictement identique, testé), `first_seen_date` préservé / `last_seen_date` mis à jour via `FULL OUTER JOIN existing`.
- [x] `gold_dbx_usage_forecast_daily` : 4 métriques (`request_count`, `distinct_consumers`, `estimated_cost_usd`, `data_read_bytes`) projetées via un seul appel `ai_forecast` multi-métrique, `lower_bound`/`upper_bound` exposés.
- [x] Aucune dépendance Python nouvelle : `requests`/`databricks-sdk` déjà utilisés par le précédent `gold_dbx_compute/forecast.py` (déjà dans `pyproject.toml`), aucun ajout.
- [x] Aucune colonne `source_lz_id`/`subscription_or_account_id` — testé (`test_no_source_lz_id_or_subscription_account_id_column_comments`, étendu aux 2 nouvelles specs).
- [ ] Job `dcm_gold_dbx_usage` complet (T002+T003+T004) déployé et exécuté avec succès en dev — **PAS ENCORE FAIT**, prochaine étape (confirmation utilisateur en attente).
- [x] Tests pytest verts (464 passed), ruff/mypy sans nouvelle violation vs baseline (cf. gates ci-dessus).

## Déviations documentées (assumées, pas des bugs silencieux)

1. **Formule `recommendation_id`** : le spike (`usage_datamapping.md` §4.1) et
   la story T004 littérale utilisent `generated_date` dans le hash — repris
   tel quel, ce hash change de valeur chaque jour où la règle se déclenche
   encore, ce qui romprait l'AC "0 doublon sur re-run, first_seen_date
   préservé" (`generated_date` change chaque jour ≠ `first_seen_date` stable).
   Corrigé en reprenant la formule déjà validée du précédent
   `gold_dbx_compute/recommendations.py` (hash sur `first_seen_date`).
2. **Seuils RELIABILITY (`failure_rate_pct`) et FINOPS (`estimated_cost_usd`)**
   non clarifiés dans `spec.md`. Valeurs choisies par analyse de la
   distribution réelle des données dev (percentiles, via Statement Execution
   API) plutôt qu'inventées : `USAGE_FAILURE_RATE_PCT_THRESHOLD = 5.0` (même
   valeur que le seuil warehouse du compute, ~7.4% des lignes réelles
   au-dessus), `USAGE_HIGH_COST_USD_THRESHOLD = 1.0` (isole le top ~1% des
   coûts consommateur réels).

## Next

- Déployer `dcm_gold_dbx_usage` en `dev_local`, exécuter le job complet,
  vérifier 0 erreur sur les 8 tâches (T002+T003+T004) et l'idempotence
  `recommendation_id` (requête `quickstart.md` T004).
- Après validation dev : commit/push, PR vers `develop`, `/speckit.dcm.sync-status`.
