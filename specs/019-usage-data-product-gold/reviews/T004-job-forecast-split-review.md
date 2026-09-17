# Review — T004 hotfix : deplacer gold_usage_forecast_daily vers job_dcm_gold_forecast

**Verdict**: **PASS** (fail=0 warn=0 skip=0)

## Contexte

Feedback reviewer PR (dataeng/019-usage-gold-transverse -> develop) :
`gold_usage_forecast_daily` (T004, ai_forecast) devrait vivre dans
`resources/job_dcm_gold_forecast.yml` (job transverse deja utilise par
`gold_dbx_compute_forecast_daily` pour la meme contrainte : warehouse
Pro/Serverless dedie, cadence hebdomadaire), pas dans
`job_dcm_gold_dbx_usage.yml`.

## Changement

- `job_dcm_gold_dbx_usage.yml` : suppression de la tache
  `gold_usage_forecast_daily` (n'est plus chainee apres
  `gold_usage_table_popularity_daily` dans ce job).
- `job_dcm_gold_forecast.yml` : ajout de `gold_usage_forecast_daily` comme
  seconde tache independante, meme `environment_key`/warehouse dedie que
  `gold_forecast_daily` (compute). Cron deplace de lundi 06h a 07h pour
  eviter une course avec le run quotidien 06h de `dcm_gold_dbx_usage` (dont
  depend fonctionnellement `gold_dbx_usage_table_popularity_daily`).
  `timeout_seconds` 3600 -> 5400 (couvre les deux taches ; le run MERGE de
  `gold_usage_forecast_daily` a pris 41.8 min en validation dev). Tags et
  commentaires mis a jour (job desormais transverse compute+usage).

Aucun fichier Python touche : changement de configuration Databricks Asset
Bundle (YAML) uniquement, pas de logique metier modifiee.

## Gates

| Gate | Status | Detail |
|------|--------|--------|
| YAML syntax | PASS | `yaml.safe_load` sur les 2 fichiers modifies, structure des taches verifiee |
| ruff | PASS (baseline inchangee) | `dcm-review.sh` remonte 1 erreur ANN001 dans `tests/test_dlt_workflow.py` — fichier DLT non touche par ce changement, deja present avant (cf. review T004 precedente, 269 erreurs baseline) |
| mypy | PASS (baseline inchangee) | conflit de module `pipelines/sqs_to_volume_drain.py` (common.models) — pre-existant, sans rapport avec les fichiers YAML modifies |
| pytest | PASS | 623/623 (aucun test ne reference les fichiers `resources/*.yml`) |
| Cross-refs | PASS | Recherche `gold_usage_forecast_daily`/`dcm_gold_forecast` dans le repo : seules les 2 ressources YAML + le commentaire deja existant dans `forecast.py` (nom de fichier inchange) ; `databricks.yml` ne fait que des overrides `pause_status` au niveau job, aucun impact |

## Conclusion

Changement de configuration isole, sans impact code/tests. Les 2 echecs
remontes par `dcm-review.sh` (ruff/mypy) sont le baseline pre-existant du
depot, deja documente et non lie a ce diff. PASS.
