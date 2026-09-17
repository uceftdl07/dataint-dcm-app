# DCM Review Report — T004 hotfix (forecast_daily : ecriture directe sur SQL Warehouse)

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/019-usage-gold-transverse` (base: `develop`)
**Stack**: python (module `pipelines`)
**Scope**: `pipelines/gold_dbx_usage/forecast_daily.py`, `entrypoint.py`, `tests/gold_dbx_usage/test_forecast_daily.py`.

**Verdict**: **PASS**

## Contexte

Run dev complet du job `dcm_gold_dbx_usage` : la tâche `gold_usage_forecast_daily`
(`ai_forecast`) a échoué 3 fois de suite en environnement réel, sur 2 tailles
de SQL Warehouse différentes (2X-Small puis Medium) :

1. `Execution ran out of memory` (2X-Small, ~64 min avant échec).
2. `InvalidProtocolBufferException` (Medium, ~14 min).
3. `InvalidProtocolBufferException$InvalidWireTypeException` (Medium, ~11 min,
   même classe d'erreur, chemin de deserialisation identique).

**Cause racine** : `build_usage_forecast` rapatriait les résultats
`ai_forecast` (API Statement Execution) vers le driver Python
(`_execute_statement` → `list[list[Any]]`) puis les réinjectait en DataFrame
Spark via `spark.createDataFrame(rows, schema=...)`. Au grain réel constaté
en dev (~528k data products actifs sur la fenêtre de 14j × 4 métriques × 7j
d'horizon ≈ 14,8M lignes), cette reconstruction sérialise l'intégralité des
lignes en un unique message protobuf `LocalRelation` côté client Spark
Connect — qui dépasse la limite de taille gRPC et se corrompt en transit.
Le changement de taille de warehouse n'avait aucun effet (le goulot est
côté driver/protocole, pas compute), ce qui a confirmé le diagnostic.

## Correctif

Le calcul **et** l'écriture Delta s'exécutent désormais entièrement côté
SQL Warehouse, sans jamais faire transiter les lignes par le driver Python :

- `render_forecast_write_sql` (nouvelle fonction pure) : construit le texte
  SQL complet — `CREATE TABLE ... USING DELTA AS SELECT` (première
  exécution) ou `MERGE INTO ... WHEN MATCHED THEN UPDATE SET *
  WHEN NOT MATCHED THEN INSERT *` (exécutions suivantes) — en réutilisant
  `render_forecast_query` (inchangée) pour le calcul `ai_forecast`, avec
  déduplication `ROW_NUMBER() OVER (PARTITION BY <merge_keys>)` (équivalent
  SQL de `DataFrame.dropDuplicates` utilisé par
  `pipelines.common.writers.merge_into_table` sur les autres tables gold).
- `write_usage_forecast` (remplace `build_usage_forecast`) : orchestration —
  `spark.catalog.tableExists` (métadonnée légère) pour choisir CREATE/MERGE,
  exécution du texte SQL via `_execute_statement` (inchangée) contre
  `warehouse_id`, puis attache des commentaires de table/colonnes via
  `pipelines.common.writers._apply_table_comments` (réutilisée telle quelle).
- `entrypoint.py` : `forecast_daily` court-circuite désormais le chemin
  générique `builders[table]() → merge_into_table(...)` (retiré du dict
  `builders`) — appel direct à `write_usage_forecast`, seule table du
  domaine dont le calcul ET l'écriture doivent s'exécuter hors du job
  cluster générique.
- Suppression de code mort : `_coerce_forecast_row`, `_FORECAST_RESULT_SCHEMA`
  (plus nécessaires, aucune ligne ne transite plus en Python).

## Gates

| Gate | Status | Detail |
|------|--------|--------|
| ruff (module + tests) | PASS | `ruff check pipelines/gold_dbx_usage/forecast_daily.py pipelines/gold_dbx_usage/entrypoint.py tests/gold_dbx_usage/test_forecast_daily.py` → 0 violation |
| ruff (paquet complet) | PASS (baseline identique) | 269 violations pré-existantes, toutes dans `pipelines/dlt_0{1,2,3}_*.py`/`tests/test_dlt_*.py` (fichiers DLT non touchés par cette branche, confirmés pré-existants sur `develop`) |
| pytest (suite complète) | PASS | `pytest -q` → 623 passed (133 dans `tests/gold_dbx_usage/`) |
| mypy | PASS (baseline identique) | Même erreur pré-existante (`sqs_to_volume_drain.py`, conflit de nom de module `common.models`/`pipelines.common.models`), non liée à cette branche |

## Validation dev (re-run x2)

Redéployé (`databricks bundle deploy -t dev_local`) puis job complet relancé
2 fois :

1. **1er run (CREATE TABLE, table absente)** : `gold_usage_forecast_daily` →
   **SUCCESS** en 10,9 min (vs échec après ~64 min/14 min/11 min avant le
   correctif).
2. **2e run (MERGE INTO, idempotence)** : `gold_usage_forecast_daily` →
   **SUCCESS** en 41,8 min (MERGE plus lent que CREATE — scan complet de la
   table cible sans pruning, piste d'optimisation future via
   `partition_predicate`, non bloquant).

Idempotence vérifiée après chaque run (requête SQL directe, hors ORM) :
`SELECT merge_keys, COUNT(*) FROM gold_dbx_usage_forecast_daily GROUP BY 1..5
HAVING COUNT(*) > 1` → **0 ligne** dans les deux cas.

## Deviation documentee

Le domaine `gold_dbx_usage` diverge maintenant de `gold_dbx_compute/forecast.py`
(qui garde le pattern `createDataFrame`) sur ce point précis : cardinalité
bien plus élevée côté usage (~528k data products actifs vs le parc
clusters/jobs/warehouses du compute), le bug ne s'étant jamais manifesté côté
compute. Pattern à ré-évaluer pour `gold_dbx_compute` si sa cardinalité
augmente un jour (hors scope de ce ticket).

## Next

- T004 complet et validé en dev (2 runs, idempotence confirmée) — prêt pour
  mise à jour `tasks.md` et PR vers `develop`.
- Optimisation `MERGE INTO` (pruning) : amélioration future possible, non
  bloquante.
