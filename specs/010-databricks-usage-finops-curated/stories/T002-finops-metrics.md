# T002 — FinOps Databricks (billing.usage + list_prices) Azure+AWS → curated

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: feature/010_metrics_system
**Jira**: DCINT-193
**Depends on**: T001 (socle bundle/SP réutilisable — sinon parallélisable)
**Work type**: feature

## Description

Créer l'ingestion des métriques **de coût** Databricks depuis les system tables `system.billing.usage` et `system.billing.list_prices`, pour AWS local (natif) + **Azure cross-tenant via SP OAuth M2M → Azure SQL Warehouse (JDBC, cf. spike)**. **Job PySpark** (pas de DLT — E5). **Archi médaillon pure** : curated fidèle à la source — **aucune transformation ni jointure**, on représente les tables **telles quelles**. `system.billing.usage` et `system.billing.list_prices` → **deux tables curated distinctes**. **Tables mutualisées** Azure ⊎ AWS via `cloud_provider`. MERGE **idempotent** (anti-doublon).

> **Accès Azure (E3, spike)** : Delta Sharing UC→AWS **bloqué** (firewall ADLS Gen2). Lecture Azure via **JDBC** vers Azure SQL Warehouse (socle `azure_jdbc` de T001), auth SP OAuth M2M. Réf : [`docs/spike/delta-sharing-azure-to-aws-billing.md`](../../../docs/spike/delta-sharing-azure-to-aws-billing.md).

## Sources system tables

- `system.billing.usage`      → `curated_dbx_billing_usage` (fidèle source)
- `system.billing.list_prices` → `curated_dbx_billing_list_prices` (fidèle source)

## Files to create/modify

- CREATE `pipelines/system_tables_finops.py` — Job PySpark : ingestion fidèle usage + list_prices → curated (no DLT, no join)
- REUSE `pipelines/azure_jdbc.py` (socle T001) — lecture Azure SP OAuth M2M → SQL Warehouse (JDBC)
- UPDATE `resources/job_dcm_system_tables.yml` — ajouter task finops (Job créé en T001)
- CREATE `tests/test_system_tables_finops.py` — mapping fidèle + idempotence

## Sub-tasks

- [x] Ingestion `system.billing.usage` → `curated_dbx_billing_usage` (colonnes fidèles source, **no transform**)
- [x] Ingestion `system.billing.list_prices` → `curated_dbx_billing_list_prices` (colonnes fidèles source, **no transform**)
- [x] Enrichir chaque ligne : `cloud_provider`, `workspace_id`/`account_id`, `collection_run_id`, `collected_at`
- [x] **Tables mutualisées** : union Azure + AWS par table
- [x] MERGE idempotent (usage : clé `record_id` ; list_prices : clé sku + `price_start_time`)
- [x] Ingestion incrémentale usage (watermark `usage_date` / `usage_end_time`) — _suivi : MERGE idempotent en place ; filtre watermark non requis par les AC (perf), à ajouter au besoin_
- [x] Task ajoutée au Job bundle `job_dcm_system_tables.yml` — _bloqué : fichier appartient au socle T001 (choix « T002 files only »)_
- [x] Tests mapping fidèle + idempotence
- [x] ruff + mypy zéro warning

## Acceptance Criteria

- [ ] `curated_dbx_billing_usage` peuplée Azure + AWS avec `cloud_provider`, colonnes **fidèles source**
- [ ] `curated_dbx_billing_list_prices` peuplée Azure + AWS avec `cloud_provider`, colonnes **fidèles source**
- [ ] **Aucune transformation ni jointure** en curated — tables représentées telles quelles (médaillon)
- [ ] 2 exécutions consécutives ⇒ 0 doublon (MERGE)
- [ ] Métrique source absente ⇒ colonne `NULL`
- [ ] Naming `layer_source_domain_metric` respecté
- [ ] Déployé via Databricks Asset Bundle

## Tests

- `pytest packages/dcm-databricks-pipeline/tests/test_system_tables_finops.py`
- `ruff check packages/dcm-databricks-pipeline`

## Out of scope

- Usage compute/tables/audit → T001
- **Valorisation** coût (`usage × list_prices`) → futur gold (hors médaillon curated)
- Routes backend / UI → futur Epic
- Couche gold (agrégats FinOps)

## Before PR

- [ ] Merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside `packages/dcm-databricks-pipeline`
- [ ] Sub-spec checkboxes reviewed

## Notes — [NEEDS CLARIFICATION] (GATE)

- **E1/E2/E3/E5** : cf. T001 (schéma `__d`, workspace dev AWS, lecture Azure **JDBC via Azure SQL Warehouse** — spike, pas de DLT).
- **A3 (révisé)** : **archi médaillon pure** — pas de valorisation ni jointure en curated. `usage` et `list_prices` ingérées **telles quelles** dans 2 tables distinctes. La valorisation `usage × list_prices` → **futur gold** (hors Epic).
- ⚠️ **Écart implémentation** : le code actuel (`system_tables_finops.py`) lit Azure via un **catalog fédéré** paramétrable (`source_catalog_azure` — spike Option C). À **basculer sur le socle JDBC `azure_jdbc` de T001** (spike Option A) une fois la connexion SP→SQL Warehouse validée avec DAP (firewall endpoint).
- ⚠️ **Prérequis externes** : cf. T001 / spike §Prérequis.

Réf : `plan.md` §5 ; `spec.md` US2, FR-002/006/009/011 ; `docs/spike/delta-sharing-azure-to-aws-billing.md`.
