# Review — T002 corrections suite audit validateur (usage-gold-t002)

**Scope** : `packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/`
(`table_daily.py`, `table_query_performance_daily.py`, `consumer_daily.py`,
`sql_helpers.py`, `specs.py`) + `tests/gold_dbx_usage/`.

**Contexte** : un agent validateur externe (lecture seule, dev, warehouse
`fcc5098720414937`, cible `it.ba_data_connect_monitoring__d`, fenetre
2026-07-06/07 → 2026-09-01/02) a audite les 4 tables gold `T002` sur donnee
reelle post-deploiement et produit 15 findings (F001-F015, hors F009/F012
non retenus). Verdict initial : **NON VALIDÉ** (2 bugs S1 confirmes sur donnee, 11
presumes/detectes).

## Corrections apportees

| Finding | Sévérité | Correction |
|---|---|---|
| F014 | S1 confirmé | `entity_type = 'QUERY'` (0 ligne matchee) → `'DBSQL_QUERY'` (valeur reelle). **+ correction additionnelle decouverte en verifiant sur donnee reelle** : la jointure vers `query_history` utilisait `entity_id` (UUID v4, espace d'ID sans rapport) au lieu de la colonne dediee `statement_id` du lineage (doc UC : *"A foreign key to join with query history"*) — 0 ligne joignait encore apres la seule correction du literal. |
| F015 | S1 confirmé | `entity_type != 'QUERY'` (NULL-unsafe, ecartait 46,5% des lignes) → `IS DISTINCT FROM` (NULL-safe), `consumer_type` `COALESCE(...,'UNKNOWN')`. |
| F013 | S1 présumé | `COUNT(DISTINCT catalog, schema, table_name)` (NULL-unsafe) → `COUNT(DISTINCT source_table_full_name)` / `table_full_name`. |
| F006 | S1 présumé | Jointure prix sans dedup (risque multiplication cout) → `QUALIFY ROW_NUMBER() ... = 1`. |
| F001 | — | Parenthesage du filtre incrementale (precedence `AND`/`OR`). |
| F008 | — | `workspace_id` ajoute aux jointures `query_lineage`/`query_cost`/`query_table_counts`. |
| F005 | — | Retrait des `COALESCE(...,0)` masquants sur le chemin cout (NULL distinguable d'un 0 reel). |
| F004 | — | Identite non qualifiable → `'UNKNOWN'` explicite (jamais `SERVICE_PRINCIPAL` par defaut). |
| F003 | — | `MAX(consumer_type)` alphabetique → encodage/decodage par priorite (`USER` > `SERVICE_PRINCIPAL` > reste). |
| F007 | — | `audit_reads.period_start` : `event_date` brut → `to_date(event_time)`. |
| F011 | — | `last_used_at` alimente par les 3 branches (query/non-query/audit), plus seulement audit. |
| F002 | — | Commentaire colonne `cost_attribution_method` : `weighted_bytes` documente comme non implemente/reserve, pas comme option disponible. |
| F010 | — | Commentaires `rows_written`/`data_written_bytes` : "toujours 0, aucune source ne mesure l'ecriture" au lieu d'impliquer une capacite reelle. |

## Verification sur donnee réelle (post-fix, post full-refresh)

Job redeploye (`databricks bundle deploy -t dev_local`) et relance en
`full_refresh=true` (recalcul complet, l'historique 2026-07-06→09-01 portait
les valeurs erronees). Requetes de fermeture executees via l'API Statement
Execution sur le meme warehouse (`fcc5098720414937`) que l'audit :

- `gold_dbx_usage_table_daily` (8 530 677 lignes) :
  `rows_read>0` : 51 836 ; `data_read_bytes>0` : 52 335 ;
  `duration_seconds>0` : 55 982 ; `estimated_cost_usd>0` : 55 982
  (tous > 0, F014 fermé).
- `gold_dbx_usage_table_query_performance_daily` : 47 142 lignes
  (non vide, F014 fermé).
- `consumer_type` : distribution avec `UNKNOWN` (673 937), `SERVICE_PRINCIPAL`,
  `USER`, `JOB`, `PIPELINE`, `NOTEBOOK`, `DASHBOARD_V3`, `DBSQL_QUERY` —
  **aucune valeur NULL** (F004/F015 fermés).
- Jointure `lineage.statement_id = query_history.statement_id` (entity_type
  `DBSQL_QUERY`) : 349 478 lignes (vs 0 via `entity_id`).

## Tests

- `packages/dcm-databricks-pipeline/tests/gold_dbx_usage/` : 65 tests (16
  nouveaux/reecrits verrouillant chaque finding corrigé) — `uv run pytest` :
  **65 passed**.
- `uv run ruff check pipelines/gold_dbx_usage/ tests/gold_dbx_usage/` :
  **All checks passed**.
- Suite complete du package (`uv run pytest`, hors scope) : 348 passed,
  aucune régression.

## Limites connues (documentées, non-bugs)

- `weighted_bytes` reste non implemente (research.md R4) — `specs.py`
  reformule la doc pour ne plus le presenter comme disponible (F002).
- `rows_written`/`data_written_bytes` restent a 0 (aucune source curated ne
  porte cette donnee) — documente comme limite, pas un defaut (F010).
- Seuls ~509 lignes `DBSQL_QUERY` (vs ~31,8M `JOB`) beneficient de
  l'attribution cout/volume par requete — design assume : `JOB`/`NOTEBOOK`/
  `PIPELINE`/`DASHBOARD_V3` sont des lectures directes sans requete tracee
  individuellement, donc sans cout attribuable par construction (cf. docstring
  `table_daily.py`).

**Verdict** : **PASS** — 13/13 findings retenus (F001-F008, F010, F011,
F013-F015) corrigés et vérifiés sur donnée réelle post full-refresh.
