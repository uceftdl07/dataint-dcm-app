# T002 — Gold fait usage : table_daily, popularity_daily, consumer_daily, query_performance_daily

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: dataeng/019-usage-gold-fact
**Jira**: pending
**Depends on**: T001
**Work type**: feature

> **Branch** = git **branch name** only (e.g. `dataeng/019-usage-gold-fact`). Never a commit SHA.

## Description

Créer le nouveau module `pipelines/gold_dbx_usage/` (scaffolding + fait de consommation) et calculer `gold_dbx_usage_table_daily` — le fait central qui **remplace fonctionnellement** `gold_data_product_usage` — puis ses 3 agrégats dérivés : popularité par data product, agrégat par consommateur, performance d'accès. C'est la première tranche livrant une valeur métier autonome (popularité, coût par consommateur).

## Files to create/modify

- CREATE `pipelines/gold_dbx_usage/__init__.py`
- CREATE `pipelines/gold_dbx_usage/specs.py` — registre `GOLD_SPECS` (pattern dataclass identique à `gold_dbx_compute/specs.py`, cf. research.md R6)
- CREATE `pipelines/gold_dbx_usage/entrypoint.py` — point d'entrée wheel (symétrique `gold_dbx_compute/entrypoint.py`)
- CREATE `pipelines/gold_dbx_usage/table_daily.py` — `gold_dbx_usage_table_daily` (UNION `curated_dbx_access_table_lineage` + `curated_dbx_access_audit` getTable, enrichi `curated_dbx_query_history` + `curated_dbx_billing_usage`/`billing_list_prices`)
- CREATE `pipelines/gold_dbx_usage/table_popularity_daily.py`
- CREATE `pipelines/gold_dbx_usage/consumer_daily.py`
- CREATE `pipelines/gold_dbx_usage/table_query_performance_daily.py`
- CREATE `pipelines/gold_dbx_usage/sql_helpers.py` — percentiles (`percentile_approx`), attribution coût pondérée `read_bytes` (cf. research.md R4)
- CREATE `resources/job_dcm_gold_dbx_usage.yml` — nouveau job wheel, tâches chaînées `depends_on` (cf. research.md R2)
- CREATE `tests/gold_dbx_usage/` (miroir `tests/gold_dbx_compute/`) : `test_specs.py`, `test_table_daily.py`, `test_table_popularity_daily.py`, `test_consumer_daily.py`, `test_table_query_performance_daily.py`

## Acceptance Criteria

- [x] `gold_dbx_usage_table_daily` peuplée au grain `(cloud_provider, catalog, schema, table_name, consumer_id, period_start)`, `usage_date` = alias de `period_start`
- [x] `unknown_data_product` flaggé (pas droppé silencieusement) pour toute lecture d'une table absente du registre `curated_dbx_uc_tables` (T001)
- [x] Attribution du coût — `weighted_bytes` non resolvable (ni lineage ni query.history ne portent de volume par table source, cf. research.md R4) : repli `equal_parts_fallback` documenté et appliqué (flag `cost_attribution_method`)
- [x] **Contrôle de réconciliation testé** : `SUM(parts) = coût requête` sur un cas pytest synthétique multi-DP (research.md R4)
- [x] `gold_dbx_usage_table_popularity_daily` : `popularity_rank` via `RANK() OVER (PARTITION BY period_start ORDER BY request_count DESC)`, `request_delta_pct` vs J-1
- [x] `gold_dbx_usage_consumer_daily` : `distinct_data_products` = `COUNT(DISTINCT (catalog, schema, table_name))`, `consumer_rank` par `estimated_cost_usd` décroissant
- [x] `gold_dbx_usage_table_query_performance_daily` : `failure_rate_pct`, `latency_p50_ms`/`latency_p95_ms` via `percentile_approx`
- [x] Aucune colonne `source_lz_id`/`subscription_or_account_id` sur ces 4 tables (FR-008, cf. `contracts/gold-usage-contract.md` règle 1)
- [x] `cloud_provider` dans la clé/grain des 4 tables (règle 2)
- [x] Rétention illimitée — aucun mécanisme de purge introduit (clarification)
- [x] Job `dcm_gold_dbx_usage` déployé et exécuté avec succès en dev (`databricks bundle run dcm_gold_dbx_usage`) — TERMINATED SUCCESS, target `dev_local` (2 bugs SQL réels corrigés pendant la validation : `user_identity` STRUCT et `WHERE` manquant dans `query_history_filtered`)
- [x] Tests pytest/chispa verts, ruff/mypy sans nouvelle violation vs baseline (mypy : erreur pré-existante hors scope, cf. `sqs_to_volume_drain.py`, confirmée par stash avant/après)

## Tests

- `uv run pytest tests/gold_dbx_usage/ -q`
- `uv run ruff check pipelines/gold_dbx_usage/`
- Requête de vérification fraîcheur : cf. `quickstart.md` T002 étape 3

## Out of scope

- `gold_dbx_usage_table_catalog`, `table_governance` (T003)
- `gold_dbx_usage_recommendations`, `forecast_daily` (T004)
- Adaptation de la route backend `data_product_usage.py` (epic future, hors scope — cf. spec Dependency Analysis)

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside package scope
- [ ] Diff stays reviewable (prefer fewer changed files / one concern)
- [ ] Sub-spec checkboxes reviewed
- [ ] Jira Story lists **Git branch** name (not a commit SHA)

## Notes

- Dépend de T001 (curated_dbx_uc_tables pour résoudre le périmètre "data product").
- Crée le scaffolding réutilisé par T003 (`specs.py`, `entrypoint.py`, job resource) — T003 étend, ne recrée pas.
- Cf. `contracts/gold-usage-contract.md` pour le schéma figé des 4 tables (colonnes exactes).
- Cf. `research.md` R1/R2 pour le choix du job dédié et le chaînage `depends_on`.
