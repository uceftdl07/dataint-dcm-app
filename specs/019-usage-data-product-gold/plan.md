# Implementation Plan: Usage Data Product — couche curated + gold

**Branch**: `dataeng/019-usage-data-product-gold` (branches filles par ticket : `dataeng/019-usage-data-product-gold-t001` … `-t004`) | **Date**: 2026-09-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/019-usage-data-product-gold/spec.md`

**Réf. spike** : [`docs/spike/usage-data-product-definition/`](../../docs/spike/usage-data-product-definition/) — `usage_page.md` (fonctionnel), `usage_datamodel.md` (schémas curated/gold), `usage_datamapping.md` (mapping colonne à colonne) : source de vérité data-model, déjà très détaillée.

**Réf. précédents** :
- [`specs/010-databricks-usage-finops-curated/`](../010-databricks-usage-finops-curated/) — a posé le socle d'ingestion `pipelines/system_tables/` réutilisé ici tel quel (curated déjà ingérées : `curated_dbx_access_table_lineage`, `curated_dbx_access_audit`, `curated_dbx_query_history`, `curated_dbx_billing_usage`, `curated_dbx_billing_list_prices`).
- [`specs/012-compute-metrics-ingestion/`](../012-compute-metrics-ingestion/) et [`specs/015-compute-metrics-exposition/`](../015-compute-metrics-exposition/) — établissent le pattern de module gold `pipelines/gold_dbx_compute/` (builders par table + `specs.py` registre + `entrypoint.py` wheel + `recommendations.py`) : **réutilisé à l'identique** pour `pipelines/gold_dbx_usage/`.
- [`specs/013-workflow-sys-tables-migration/`](../013-workflow-sys-tables-migration/) — précédent le plus récent utilisant le même socle `system_tables/` pour étendre le registre curated (3 `IngestionSpec` ajoutées) ; pattern directement transposable pour T001.

## Summary

Construire la couche d'observabilité **Usage Data Product** (adoption, consommateurs, fraîcheur, coût FinOps, gouvernance/cycle de vie) à partir des system tables Databricks Unity Catalog, en remplacement fonctionnel de l'ancienne table `gold_data_product_usage`. Découpage en **4 tickets séquencés par couche** (cf. spec §Prerequisites, dépendance d'ordre **T001 → {T002, T003} → T004**) :

1. **T001 — Curated : registre UC**. 3 nouvelles `IngestionSpec` dans `pipelines/system_tables/specs.py` : `curated_dbx_uc_tables` (← `information_schema.tables`, full load), `curated_dbx_uc_table_tags` (← `information_schema.table_tags`, full load), `curated_dbx_uc_table_operations` (← `access.audit` actions d'écriture, extension du filtre `ACCESS_AUDIT_TABLE_ACTIONS` existant, watermark `event_time`). Aucune modification du socle générique (`ingest.py`/`entrypoint.py`/`azure_reader.py`) : uniquement configuration déclarative, comme le pattern 013.
2. **T002 — Gold fait usage**. Nouveau module `pipelines/gold_dbx_usage/` : `gold_dbx_usage_table_daily` (fait de consommation, UNION `table_lineage` + `access_audit` getTable, enrichi `query_history`/`billing_usage`) puis 3 agrégats dérivés : `gold_dbx_usage_table_popularity_daily`, `gold_dbx_usage_consumer_daily`, `gold_dbx_usage_table_query_performance_daily`.
3. **T003 — Gold registre/état**. Dans le même module : `gold_dbx_usage_table_catalog` (registre/fraîcheur/opération qualifiée, dépend de T001), `gold_dbx_usage_dim_workspace` (pont `workspace_id → LZ`, fallback documenté, **non joint** par les autres tables gold usage — FR-008), `gold_dbx_usage_table_governance` (snapshot cycle de vie, seuils clarifiés : `is_unused` > 90j, `is_critical` fan-out ≥ 5, `is_stale_but_consumed` SLA 24h).
4. **T004 — Gold transverse**. `gold_dbx_usage_recommendations` (règles actionnables, clé stable `sha2(...)`, dépend de T002+T003) et `gold_dbx_usage_forecast_daily` (`ai_forecast` sur historique `*_daily`, rétention illimitée par clarification).

Toutes les tables gold respectent : `cloud_provider` dans la clé (mutualisation Azure/AWS), **aucune colonne `source_lz_id`/`subscription_or_account_id`** dans les tables `*_daily`/`*_catalog`/`*_governance`/`recommendations`/`forecast_daily` (FR-008, seule `dim_workspace` conserve cette résolution à part), attribution de coût multi-DP **pondérée par `read_bytes`** (clarification, écart assumé vs défaut spike "parts égales").

## Technical Context

**Language/Version**: Python 3.12 (`>=3.12,<3.13`), PySpark ; aucune autre stack concernée (dataeng seul, cf. domain scope).

**Primary Dependencies**: `pyspark>=3.5`, `delta-spark>=3.1`, `databricks-sql-connector==4.2.6` (lecture Azure `information_schema.*` — même voie que les tables déjà ingérées), `azure-identity==1.20.0`. **Aucune nouvelle dépendance** : réutilisation intégrale de `pipelines/common/` (readers, `merge_into_table`, `IngestionSpec`, `azure_reader`) et du socle `pipelines/system_tables/` pour T001 ; réutilisation du pattern `pipelines/gold_dbx_compute/` pour la structure du nouveau module `pipelines/gold_dbx_usage/` (T002-T004). `ai_forecast` : fonction SQL native Databricks (pas de dépendance Python supplémentaire), invoquée via `spark.sql(...)`.

**Storage**: Databricks Unity Catalog Delta, `it.ba_data_connect_monitoring__{env}` (dev `__d`, prod `__p`, vars bundle `catalog`/`schema` — jamais codé en dur). Sources : `system.information_schema.tables`, `system.information_schema.table_tags`, `system.access.audit` (extension filtre), et les curated déjà ingérées (`access_table_lineage`, `query_history`, `billing_usage`, `billing_list_prices`).

**Testing**: pytest + chispa (assertions DataFrame Spark) pour les 4 tickets ; ruff + mypy zéro nouvelle violation (gate, comparaison baseline comme pratiqué en 013). Tests miroir : `tests/system_tables/test_specs.py` (T001, +3 specs) ; `tests/gold_dbx_usage/` nouveau (T002-T004, miroir `tests/gold_dbx_compute/`).

**Target Platform**: Databricks Jobs — job wheel `dcm_system_tables` (curated, T001 : +3 clés `for_each.inputs`) ; nouveau job wheel (ou extension d'un job existant à trancher en Phase 0/research, cf. pattern `dcm_gold_dbx_compute`) pour le calcul gold `gold_dbx_usage_*` (T002-T004).

**Performance Goals**: Rafraîchissement quotidien best-effort (pas de SLA horaire), cohérent avec le reste du socle usage/FinOps. `information_schema.tables`/`table_tags` = full load léger (référentiel, faible volumétrie). `access.audit` (T001, opérations d'écriture) : même garde-fou `initial_lookback_days`/`azure_fetch_batch_size` que les tables `access.audit` déjà ingérées (anti-OOM driver Azure).

**Constraints**: MERGE idempotent 0 doublon (`merge_into_table`, socle réutilisé) ; `cloud_provider` obligatoire dans toute clé de merge/grain (mutualisation Azure/AWS) ; **jamais de donnée fictive** — mapping `action_name → operation` calé sur valeurs réellement observées au gate (pas de liste théorique), NULL si non résolu (FR-009) ; **pas de `source_lz_id`/`subscription_or_account_id`** dans les tables gold usage hors `dim_workspace` (FR-008) ; attribution coût pondérée `read_bytes` avec repli parts égales documenté si lineage colonne absent pour une requête donnée (clarification + FR-010) ; agrégations strictement en couche Gold (curated = fidèle source, no transform — P12).

**Scale/Scope**: 3 tables curated + 9 objets gold (4 fait/agrégats + 3 registre/état + 2 transverse), 4 tickets séquencés, 1 seul package (`packages/dcm-databricks-pipeline`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principe | Statut | Justification |
|---|---|---|
| P1 Test-First & Code Quality (NON-NEGOTIABLE) | ✅ PASS | Tests pytest/chispa par ticket (specs T001 ; builders T002-T004, miroir `tests/gold_dbx_compute/`) ; ruff/mypy zéro nouvelle violation (comparaison baseline). |
| P2 Simplicité, Explicitness & Versioning | ✅ PASS | Réutilisation intégrale du socle `IngestionSpec`/`merge_into_table` (T001) et du pattern module `gold_dbx_compute` (T002-T004) plutôt qu'un nouveau framework. Découpage additif en 4 tickets, aucune modification breaking d'un contrat existant. |
| P4 Fail Fast, Fail Loud | ✅ PASS | Gate de validation mapping `action_name → operation` avant merge T001 (Prerequisites) ; échec de résolution `(catalog, schema, table_name)` dans le registre ⇒ flag `unknown_data_product` explicite (pas de silent drop, cf. spike §5 Data Quality). |
| P5 Architecture explicite & modularité | ✅ PASS | Nouveau module `pipelines/gold_dbx_usage/` isolé (symétrique à `gold_dbx_compute/`), aucune dépendance croisée nouvelle, aucun appel cross-LZ (system tables lues via le SP Azure existant, niveau compte). |
| P6 Idempotency by Design | ✅ PASS | Curated (T001) via `merge_into_table` (MERGE sur clés + watermark, full load référentiel pour `uc_tables`/`uc_table_tags`) ; gold (T002-T004) via agrégats déterministes + clé de grain unique (`recommendation_id` = hash stable pour éviter les doublons). |
| P7/P8 Secrets Management (NON-NEGOTIABLE) | ✅ PASS | Aucun nouveau secret : réutilise le secret scope Databricks existant (SP Azure OAuth M2M) déjà câblé dans `system_tables/entrypoint.py`. Nouveau `GRANT SELECT` sur `information_schema`/`access.audit` = prérequis infra (moindre privilège), pas de secret en code. |
| P9 No Fake Data in Production (NON-NEGOTIABLE) | ✅ PASS | FR-009 : mapping non résolu = NULL, jamais 0/inventé. Data product hors registre = `unknown_data_product` (exclu du fait usage), pas une valeur bidon. |
| P10 Observability & Traceability | ⚠️ NOTE | Package utilise `logging` stdlib (pas `structlog` JSON) — écart pré-existant uniforme sur `dcm-databricks-pipeline`, non introduit ici (cohérent avec `system_tables/` et `gold_dbx_compute/` déjà en place). |
| P11 Naming Conventions | ✅ PASS | `curated_dbx_uc_*` (préfixe `dbx`, aligné existant) ; gold `gold_dbx_usage_<objet>_<grain>` (convention spike §5 guideline 5, alignée `gold_dbx_compute_*`). Aucun nom legacy `Cluster`/`Compliance`. |
| P12 Medallion — Aggregations on Gold Only | ✅ PASS | T001 (curated) reste fidèle source, no transform, no join (juste projection/filtre documentés, comme `access_audit` existant). Tout le reshaping/agrégation (UNION lineage+audit, jointures registre, `RANK()`, `ai_forecast`) vit dans `pipelines/gold_dbx_usage/` (couche Gold). |
| P13 Immutable Raw Layer | ✅ PASS | Le flux usage **bypasse la couche Raw** (system tables directement en curated, comme 010/012/013) — aucune mutation d'historique raw. |
| P14 Schema Versioning | ✅ PASS | Nouvelles tables (pas de breaking sur un schéma existant). `gold_dbx_usage_table_daily` **remplace** `gold_data_product_usage` avec un schéma différent assumé (renommage documenté en Dependency Analysis, adaptation backend hors scope epic). |
| P15 API Contract Stability | N/A | Aucune route API dans le scope de cette epic (dataeng seul, backend explicitement hors scope — cf. Dependency Analysis). |
| P16 Frontend Quality | N/A | Frontend hors scope de cette epic. |

Aucune violation nécessitant une entrée en Complexity Tracking.

### Post-Design Re-check (après Phase 1)

`research.md`, `data-model.md` et `contracts/` n'introduisent aucune nouvelle dépendance, aucun nouveau secret, aucune agrégation hors couche Gold, et respectent les 5 décisions de clarification (seuils gouvernance, attribution coût pondérée, rétention illimitée). **Constitution Check reconfirmé : PASS**.

## Project Structure

### Documentation (this feature)

```text
specs/019-usage-data-product-gold/
├── plan.md              # This file (/speckit.plan)
├── research.md          # Phase 0 output — décisions techniques (job wheel gold, extension filtre audit, attribution coût pondérée)
├── data-model.md         # Phase 1 output — 3 curated + 9 gold (repris/formalisés depuis le spike)
├── quickstart.md         # Phase 1 output — exécution & validation dev par ticket
├── contracts/             # Phase 1 output
│   └── gold-usage-contract.md   # schémas gold figés (colonnes, grain, clés) — référence pour T002-T004
├── spec.md                # Feature spec (clarifiée)
├── intake.json / domain-scope.json
├── checklists/requirements.md
└── tasks.md               # Phase 2 (/speckit.tasks — NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
packages/dcm-databricks-pipeline/
├── pipelines/
│   ├── system_tables/
│   │   ├── specs.py                     # EXTENDED (T001) — +3 IngestionSpec (uc_tables, uc_table_tags, uc_table_operations) + entrées SPECS/SPEC_KEYS
│   │   ├── ingest.py / entrypoint.py / azure_reader.py   # REUSED as-is (génériques)
│   ├── gold_dbx_usage/                  # NOUVEAU module (T002-T004), pattern symétrique à gold_dbx_compute/
│   │   ├── __init__.py
│   │   ├── specs.py                     # T002-T004 — registre GOLD_SPECS (nom table, grain, clé, colonnes)
│   │   ├── entrypoint.py                # T002 — point d'entrée wheel, symétrique gold_dbx_compute/entrypoint.py
│   │   ├── table_daily.py               # T002 — gold_dbx_usage_table_daily (fait de consommation)
│   │   ├── table_popularity_daily.py    # T002 — agrégat popularité
│   │   ├── consumer_daily.py            # T002 — agrégat consommateur
│   │   ├── table_query_performance_daily.py  # T002 — performance d'accès
│   │   ├── table_catalog.py             # T003 — registre/état/fraîcheur/opération qualifiée
│   │   ├── dim_workspace.py             # T003 — pont workspace → LZ (fallback documenté)
│   │   ├── table_governance.py          # T003 — snapshot gouvernance/cycle de vie
│   │   ├── recommendations.py           # T004 — règles actionnables (sha2 recommendation_id)
│   │   ├── forecast_daily.py            # T004 — ai_forecast sur historique *_daily
│   │   └── sql_helpers.py               # partagé (percentiles, attribution coût pondérée read_bytes)
│   ├── dlt_01_raw_layer.py / dlt_02_curated_layer.py / dlt_03_gold_layer.py   # NON MODIFIÉS (usage hors DLT, socle wheel job comme gold_dbx_compute)
│   └── common/                          # REUSED as-is
├── resources/
│   ├── job_dcm_system_tables.yml        # EXTENDED (T001) — +3 clés for_each.inputs
│   └── job_dcm_gold_dbx_usage.yml       # NOUVEAU (T002) — job wheel gold usage, pattern job_dcm_gold_dbx_compute.yml
└── tests/
    ├── system_tables/test_specs.py      # EXTENDED (T001) — +3 specs, idempotence merge
    └── gold_dbx_usage/                  # NOUVEAU (T002-T004), miroir tests/gold_dbx_compute/
        ├── test_specs.py
        ├── test_table_daily.py
        ├── test_table_popularity_daily.py
        ├── test_consumer_daily.py
        ├── test_table_query_performance_daily.py
        ├── test_table_catalog.py
        ├── test_dim_workspace.py
        ├── test_table_governance.py
        ├── test_recommendations.py
        └── test_forecast_daily.py
```

**Structure Decision**: Single package (`packages/dcm-databricks-pipeline`), aucune extension multi-package. T001 étend le registre curated existant (`system_tables/specs.py`, aucune nouvelle mécanique). T002-T004 introduisent un **nouveau module gold** `pipelines/gold_dbx_usage/`, strictement symétrique en structure à `pipelines/gold_dbx_compute/` (déjà en production) — choix qui minimise le risque et la charge de revue (pattern connu de l'équipe) plutôt que d'inventer une nouvelle convention de module gold.

## Complexity Tracking

Aucune violation de la constitution à justifier (cf. Constitution Check — tout PASS, N/A, ou NOTE pré-existante non introduite par cet Epic).
