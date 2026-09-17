# T003 — Gold SQL Warehouses: cost, utilization/rightsizing, query performance

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: dataeng/012-gold-warehouses
**Jira**: pending
**Depends on**: T001, T002
**Work type**: feature

## Description

Extend `pipelines/gold_dbx_compute/` (scaffolding created in T002) with the 3 warehouse gold tables: `gold_dbx_compute_warehouse_cost_daily`, `gold_dbx_compute_warehouse_utilization_daily`, `gold_dbx_compute_warehouse_query_performance_daily` (FR-008 to FR-010), sourced from the new curated warehouse tables (T001) + existing `curated_dbx_query_history`/`curated_dbx_billing_usage`.

## Files to create/modify

- UPDATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py` — add 3 warehouse gold specs to the registry (grain `(cloud_provider, source_lz_id, workspace_id, warehouse_id, period_start)`, same `watermark_column="period_start"` / `initial_mode="full"` / `incremental_lookback_days=3` convention as T002 — FR-018, research.md R9).
- CREATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/warehouse_metrics.py` — aggregation logic per [compute_datamapping.md §3](../../../docs/spike/compute-metrics-definition/compute_datamapping.md):
  - `gold_dbx_compute_warehouse_cost_daily`: DBU/cost sum, `query_count`, `cost_per_query_usd`.
  - `gold_dbx_compute_warehouse_utilization_daily`: `running_hours` vs `active_query_hours` (from `curated_dbx_compute_warehouse_events`), `idle_pct`, `active_to_running_ratio`, scale up/down event counts, `utilization_status` + `rightsizing_reco` + `estimated_savings_usd`.
  - `gold_dbx_compute_warehouse_query_performance_daily`: `latency_p50/p95/p99_ms`, `queue_time_avg/p95_ms`, `failure_rate_pct`, `spill_query_count`, `cache_hit_pct`, `bytes_scanned`/`rows_scanned` from `curated_dbx_query_history`.
- UPDATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/entrypoint.py` — register dispatch for the 3 new table keys.
- UPDATE `packages/dcm-databricks-pipeline/resources/job_dcm_gold_dbx_compute.yml` — append the 3 warehouse keys to `for_each_task.inputs`.
- CREATE `packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_warehouse_metrics.py` — chispa-based assertions (`idle_pct`, `failure_rate_pct`, `utilization_status`).

## Acceptance Criteria

- [x] `gold_dbx_compute_warehouse_cost_daily`: `query_count`, `cost_usd`, `cost_per_query_usd` consistent with `curated_dbx_query_history`/`curated_dbx_billing_usage` (spec.md US3 scenario 1).
- [x] `gold_dbx_compute_warehouse_utilization_daily`: warehouse RUNNING without active queries for a large share of the day → `idle_pct` high, `utilization_status = 'OVER'`, `estimated_savings_usd` reflects idle % applied to daily cost (US3 scenario 2).
- [x] `gold_dbx_compute_warehouse_query_performance_daily`: failed/spilled queries correctly reflected in `failure_rate_pct`/`spill_query_count`; percentile latencies computed (US3 scenario 3).
- [x] Re-running the job for the same day is idempotent (SC-003, FR-014) — via `pipelines.common.writers.merge_into_table`, meme socle deja teste sur `system_tables`/T002.
- [x] Naming follows `gold_dbx_compute_warehouse_*` convention (FR-015).
- [x] **First run** on a target table that doesn't exist yet processes the entire available curated history (full mode, e.g. 30 seeded days → 30 gold rows) — FR-018, SC-007. Verifie via `_resolve_lower_bound` (deja generique, reutilise tel quel depuis T002).
- [x] **Subsequent run** only recomputes/upserts `period_start >= today - 3 days` — FR-018. Verifie via assertions sur le predicat SQL genere (memes tests que T002).

## Tests

- [x] `uv run pytest -q tests/gold_dbx_compute/` — 88 passed (3 nouveaux fichiers de test warehouse + extensions `test_specs.py`/`test_entrypoint.py`).
- [x] `uv run ruff check pipelines/gold_dbx_compute/ tests/gold_dbx_compute/` — all checks passed.
- [x] Suite complete du package (`uv run pytest -q`) — 198 passed, 0 regression.
- [x] `databricks bundle validate -t dev` — Validation OK.
- `uv run mypy pipelines/gold_dbx_compute/` — echec connu pre-existant ("Source file found twice under different module names"), non introduit par T003, deja documente par T002 (CI a mypy commente pour ce package).

## Out of scope

- Cluster gold tables (T002, already delivered).
- Recommendations/forecast transverse socle (T004).

## Before PR

- [x] Rebased/merged latest develop before PR (**must** rebase onto T002's merged `specs.py`/`entrypoint.py`/`job_dcm_gold_dbx_compute.yml` — see `merge-strategy.md`)
- [x] Tests pass
- [x] No files outside `packages/dcm-databricks-pipeline`
- [x] Sub-spec checkboxes reviewed

## Notes

- Do not touch the cluster-related entries in `specs.py`/`entrypoint.py` added by T002 — append only.
- See [research.md R8](../research.md) for the merge-key strategy.

### Deviations vs plan initial du sub-spec (implementation reelle T003)

- **Structure fichiers alignee sur T002 reel, pas sur la description litterale de ce sub-spec.** T002 a livre un fichier par table gold (`cluster_cost_daily.py`, `cluster_efficiency_daily.py`, `cluster_reliability_daily.py`, `cluster_governance.py` + `sql_helpers.py` partage), pas un `cluster_metrics.py` monolithique comme decrit initialement. T003 suit ce pattern reel : `warehouse_cost_daily.py`, `warehouse_utilization_daily.py`, `warehouse_query_performance_daily.py` (pas de `warehouse_metrics.py`), reutilisant `sql_helpers.lower_bound_predicate`/`sql_string_list` (aucune duplication). Tests correspondants un fichier par builder (pas de `test_warehouse_metrics.py` unique).
- **Grain sans `source_lz_id`** (contrairement au grain `(cloud_provider, source_lz_id, workspace_id, warehouse_id, period_start)` decrit initialement dans ce sub-spec) : meme limitation structurelle deja identifiee et actee par T002 (`account_id` de `curated_dbx_compute_warehouses`/`curated_dbx_compute_warehouse_events` n'est pas mappable vers `dim_landing_zone.subscription_or_account_id`). `data-model.md` (Couche GOLD — SQL Warehouses) a deja ete mis a jour en consequence avant le demarrage de T003 — grain retenu : `(cloud_provider, workspace_id, warehouse_id, period_start)`. Pas de `cost_rank`/`is_top_cost` sur les tables warehouses (non demande, a la difference des clusters).
- **Job YAML : 3 taches independantes, sans `depends_on`** (et non un `for_each_task` comme decrit initialement) : aucune des 3 agregations warehouses ne lit le resultat gold d'une autre (contrairement aux clusters ou `efficiency_daily` lit `cost_daily` et `governance` lit `efficiency_daily`) — chacune lit uniquement des tables curated (+ `cost_daily` pour `estimated_savings_usd` dans `utilization_daily`, lu en INPUT, pas en dependance de tache puisque toutes les tables `*_daily` warehouses sont rafraichies independamment chaque jour). Coherent avec la deviation deja actee par T002 (job reel a taches explicites chainees, pas de `for_each_task`, malgre ce que dit `merge-strategy.md`).
- **`curated_dbx_compute_warehouse_events` n'a pas de colonne `event_date`** (contrairement a ce que suggere `compute_datamapping.md` §1.2, document spike non mis a jour) : seule `event_time` existe cote curated (fidelite stricte a la source, cf. commentaire `WAREHOUSE_EVENTS_SPEC` dans `system_tables/specs.py`). `to_date(event_time)` est derive directement dans les requetes gold quand un grain jour est necessaire (meme pattern que `to_date(start_time)` dans `cluster_efficiency_daily.py`).
- **`WAREHOUSE_SCALE_DOWN_EVENTS` limite a `('SCALED_DOWN',)`** (asymetrique avec `WAREHOUSE_SCALE_UP_EVENTS = ('SCALING_UP', 'SCALED_UP')`) : fidele au mapping autoritatif `compute_datamapping.md` §3.2, qui ne liste que `SCALED_DOWN` cote scale down. Ecart volontaire documente dans le code (`warehouse_utilization_daily.py`), pas une omission.
- **`running_hours`** : pairing `STARTING → STOPPED` (pas `RUNNING`, non journalise de facon fiable sur les warehouses serverless) via `LEAD` sur la sous-sequence filtree, avec dedup des `STARTING` consecutifs (`LAG`) et decoupage de chaque session par jour calendaire traverse (`LATERAL VIEW explode(sequence(...))` + `GREATEST`/`LEAST`) — cf. section "Fix cible post-livraison T003" ci-dessous pour l'historique du fix (le decoupage jour n'etait pas present a la livraison initiale).
- **`top_consumer`** (`warehouse_cost_daily`) conserve du mapping spike malgre son absence de la description initiale de ce sub-spec : ne depend pas de `dim_landing_zone`, calcule uniquement depuis `curated_dbx_query_history.executed_by`/`total_duration_ms` — aucun risque de la meme limitation LZ que `source_lz_id`/`ba_name`.
- **Nom du job renomme** : `job_dcm_gold_dbx_compute.yml` `name: "[${bundle.target}] DCM Gold Compute (Clusters)"` (cree par T002) renomme en `"[${bundle.target}] DCM Gold Compute"` — le job couvre desormais clusters + warehouses, plus de mention `(Clusters)` trompeuse. Changement cosmetique (nom d'affichage du job), aucun impact sur les `task_key`/dependances/logique.

### Fix cible post-livraison T003 : `running_hours` / `active_query_hours` / `peak_concurrency` de `gold_dbx_compute_warehouse_utilization_daily`

- **Probleme confirme (pas une hypothese)** : en run reel sur `dev_local`, `idle_pct` tombait jusqu'a **-22 537 %** sur des warehouses serverless a cycles courts, et le calcul de `peak_concurrency` (self-join par chevauchement d'intervalle) **timeout** sur un full-refresh de 3 ans d'historique `curated_dbx_query_history`. Trois causes racines identifiees :
  1. `running_hours` attribuait la totalite d'une session `STARTING → STOPPED` au seul jour de son `STARTING`, meme quand la session durait ~22h a cheval sur 2 jours calendaires : le 2e jour recevait 0h de `running_hours` alors que le warehouse y tournait reellement.
  2. `active_query_hours` etait calcule via `COUNT(DISTINCT date_trunc('HOUR', start_time))` (heures calendaires pleines des qu'une seule requete y passe) — incompatible en unite avec `running_hours` (mesure fine, a la seconde), ce qui pouvait le faire depasser `running_hours` et rendre `idle_pct` negatif.
  3. `peak_concurrency` etait calcule par self-join `q1 JOIN q2 ON chevauchement d'intervalle` — `O(n²)` par groupe, ne passe pas a l'echelle sur plusieurs mois/annees d'historique.
- **Fix** :
  1. `running_hours` : chaque session `STARTING → STOPPED` est decoupee par jour calendaire traverse (`LATERAL VIEW explode(sequence(to_date(session_start), to_date(session_end)))`, bornee par `GREATEST`/`LEAST` aux limites `[jour 00:00:00, jour+1 00:00:00)`), plus une deduplication des `STARTING` consecutifs sans `STOPPED` entre eux (`LAG` sur la sous-sequence STARTING/STOPPED, ne garde que le premier de la serie).
  2. `active_query_hours`/`peak_concurrency` partagent desormais un unique balayage (sweep-line) : chaque requete emet +1 a `start_time` et -1 a `end_time` (`concurrency_events`), somme cumulee triee par instant (`concurrency_running`) — `active_query_hours` somme les segments `[ts, next_ts)` ou `concurrency > 0` (union d'intervalles reelle, memes unites que `running_hours`), `peak_concurrency` en prend le `MAX`. Remplace le self-join `O(n²)`.
  3. **Garde-fou supplementaire** : une ligne `curated_dbx_query_history` avec `end_time IS NULL` n'est coalescee a `current_timestamp()` que si son `start_time` est recent (`WAREHOUSE_QUERY_STILL_RUNNING_MAX_HOURS = 24h`) ; au-dela, la ligne est **exclue** du balayage plutot que coalescee — sans cette exclusion, une requete orpheline vieille de plusieurs semaines aurait gonfle `active_query_hours` de semaines entieres et aggrave `idle_pct` negatif au lieu de le corriger.
- **Tests** : 9 tests non-regression ajoutes/etendus dans `test_warehouse_utilization_daily.py` (dedup `STARTING` consecutifs, decoupage jour calendaire, sweep-line `active_query_hours`/`peak_concurrency` a la place des self-join/`date_trunc`, coalesce garde-fou 24h). Suite complete apres fix — 205 passed (0 regression, vs 198 avant ce fix). `ruff check pipelines/gold_dbx_compute/ tests/gold_dbx_compute/` clean. `databricks bundle validate -t dev` → Validation OK. `mypy` echoue toujours avec la meme erreur pre-existante du repo (non traitee comme regression).

### Tests

Suite complete apres T003 (avec le fix ci-dessus) : 205 passed (vs 120 apres T002), 0 regression. `ruff check` clean sur les fichiers modifies/crees. `databricks bundle validate -t dev` → Validation OK. `mypy` echoue toujours avec la meme erreur pre-existante du repo (non traitee comme regression, cf. Acceptance Criteria/Tests ci-dessus).
