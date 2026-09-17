# Implementation Plan — Métriques Usage & FinOps Databricks (Azure + AWS) → curated

**Feature**: `010-databricks-usage-finops-curated`
**Spec**: [`spec.md`](./spec.md)
**Work type**: feature · **Priority**: P2 · **Domain**: DataEng
**Package**: `packages/dcm-databricks-pipeline`
**Created**: 2026-07-27 · **Revised**: 2026-07-30 (intégration spike Delta Sharing)

**Réf. spike (décisif)** : [`docs/spike/delta-sharing-azure-to-aws-billing.md`](../../docs/spike/delta-sharing-azure-to-aws-billing.md) — mécanisme de lecture Azure cross-tenant tranché (E3).

---

## 1. Objectif technique

Ajouter, dans `packages/dcm-databricks-pipeline`, un **Job Databricks PySpark** (planifié, exécuté par un Service Principal) qui :

1. lit les **system tables** Databricks **AWS locales** (accès natif) + **Azure cross-tenant** (via SP OAuth M2M → Azure SQL Warehouse, cf. spike) ;
2. écrit fidèlement (médaillon, no transform) dans la couche **curated** de `it.ba_data_connect_monitoring__d` ;
3. produit des tables **mutualisées** Azure+AWS `curated_databricks_<domain>_<metric>` (union par `cloud_provider`), idempotentes (MERGE — aucun doublon à la réexécution).

**Décision technique — pas de DLT.** Delta Live Tables (streaming depuis un volume d'ingestion) est **inadapté** à ce besoin : les sources sont des **system tables** lues en batch (dont une source **JDBC cross-cloud** Azure), pas des fichiers déposés dans un volume. On utilise un **Job Databricks à tâches PySpark** (`spark.read` + `MERGE INTO` Delta), **disjoint** du pipeline DLT collecteur existant (schémas `__a`/`__p`). Aucune modification du DLT ni du contrat backend/frontend.

---

## 2. Contexte codebase (scope: dcm-databricks-pipeline)

| Élément existant | Détail |
|---|---|
| Bundle | `databricks.yml` — targets `dev_local`, `dev` (`dbc-89e8d3b6-20ad`), `prod` (`dbc-af3acef9-c998`) |
| Resources | `resources/job_dcm_metric_full.yml` (orchestrator SQS→DLT), `resources/pipeline_dcm_dlt.yml` |
| Pipeline DLT | `pipelines/dlt_01_raw` → `dlt_02_curated` → `dlt_03_gold` (schéma `__a`) |
| Schéma cible actuel | dev `ba_data_connect_monitoring__d`, prod `__p` |

**Réutilise** : structure bundle, pattern `run_as` SP, notif email, tags, style notebooks.

---

## 3. Écarts / décisions (✅ tranchées)

| # | Écart constaté | Résolution |
|---|---|---|
| **E1** ✅ | Spec cible schéma **`__d`** ; bundle actuel = `__a` (dev) / `__p` (prod). | Schéma mappé par target : dev `__d`, prod `__p` (variable `schema` dans `databricks.yml`). |
| **E2** ✅ | Spec dev AWS = `dbc-16a9ad66-c301` ; bundle dev = `dbc-89e8d3b6-20ad`. | Targets dev/dev_local pointent `dbc-16a9ad66-c301` ; prod `dbc-af3acef9-c998`. |
| **E3** ✅ **(spike)** | Accès Azure cross-tenant : **comment le Job lit Azure** depuis AWS ? | **Delta Sharing UC→UC bloqué** (firewall ADLS Gen2 rejette l'accès storage depuis le réseau AWS). **Solution retenue : SP OAuth M2M → Azure SQL Warehouse** (lecture 100 % intra-Azure), AWS reçoit **uniquement les lignes résultats**. Impl. **Option A — JDBC/Spark connector** (`spark.read.format("jdbc")`, `AuthMech=11`, `Auth_Flow=1`) pour le POC ; alt. **Option B** `databricks-sql-connector`. **Option C** (Lakehouse Federation `CONNECTION`+`FOREIGN CATALOG`) = cible industrialisation, **à valider DAP** (auth SP + firewall endpoint warehouse). Réf : spike §Solution retenue / §Options A-C. |
| **E4** ✅ | `system.access.audit` + `billing.usage` volumineux. | Ingestion **incrémentale** (filtre watermark `event_time` / `usage_date`), MERGE sur clé métier. |
| **E5** ✅ | DLT adapté ? | **Non** — sources = system tables batch (dont JDBC cross-cloud), pas un flux de fichiers volume. **Job PySpark** (`spark.read` + `MERGE INTO`), disjoint du DLT collecteur. |

### Prérequis externes (spike §Prérequis — à confirmer DAP/IAM/Network)

| Élément | Owner | Statut |
|---|---|---|
| Service Principal Entra ID + secret (OAuth M2M) | DAP / IAM | à confirmer |
| Azure SQL Warehouse dédié + `CAN USE` pour le SP | DAP | à confirmer |
| Endpoint warehouse HTTPS 443 joignable **depuis AWS** (firewall) | Network / DAP | ⚠️ point ouvert spike |
| Vue matérialisée Azure `system.billing.usage` (schéma partageable) + refresh | DAP | à confirmer |
| Secret SP côté AWS : **Databricks secret scope** vs Secrets Manager (standard DCM) | Data Eng | à trancher |
| Grants UC : `USE CATALOG`/`USE SCHEMA`/`SELECT` sur les schémas system Azure | Admin metastore Azure | partiellement validé (A1) |

> **Point ouvert bloquant** (spike) : le SP peut-il s'authentifier sur le SQL Warehouse Azure **depuis un réseau AWS** (firewall endpoint) ? À valider avant industrialisation.

---

## 4. Architecture cible

```
┌ SOURCES SYSTEM TABLES ────────────────────────────────────────┐
│ AWS (local, workspace exécution)                              │
│   lecture native UC : system.billing.usage / list_prices,    │
│   system.compute.clusters / node_timeline, system.access.audit│
│                                                               │
│ AZURE (cross-tenant — SP OAuth M2M, cf. spike E3)            │
│   AWS Job ──JDBC (HTTPS 443, OAuth M2M)──▶ Azure SQL Warehouse│
│                          Azure SQL Warehouse ──intra-Azure──▶ │
│                                              ADLS Gen2 (system)│
│   (AWS ne touche jamais au storage Azure — lignes résultats)  │
└───────────────────────────────────────────────────────────────┘
                     │  Job Databricks PySpark (run_as SP dcm-databricks-sp)
                     │  spark.read (natif AWS + JDBC Azure) → union cloud_provider
                     │  → MERGE INTO Delta (idempotent, anti-doublon)
                     ▼
┌ CURATED — it.ba_data_connect_monitoring__d (tables MUTUALISÉES)┐
│ USAGE (US1)                                                   │
│   curated_dbx_compute_clusters   (system.compute.*)   │
│   curated_dbx_compute_node_timeline                    │
│   curated_dbx_access_audit       (usage utilisateurs) │
│   curated_dbx_access_table_lineage (lignage DP)       │
│   curated_dbx_query_history      (histo requêtes)     │
│ FINOPS (US2)                                                  │
│   curated_dbx_billing_usage       (billing.usage)     │
│   curated_dbx_billing_list_prices (billing.list_prices)│
│                                                               │
│ 1 seule table par métrique = Azure ⊎ AWS (colonne cloud_provider)│
│ chaque ligne : + cloud_provider, + workspace_id/url,         │
│                + account_id, + collection_run_id, collected_at│
└───────────────────────────────────────────────────────────────┘
                     ▼  (futur Epic) Backend SQL Warehouse → Frontend
```

**Invariants** :
- Tables **mutualisées** : une table par métrique, Azure et AWS unifiés par `cloud_provider` (pas de tables séparées par cloud).
- Tables **disjointes du DLT collecteur** ; **Job PySpark** dédié (pas de DLT — E5).
- Curated **fidèle à la source** (médaillon) : **aucune transformation ni jointure** ; on représente les system tables **telles quelles** (la valorisation `usage × list_prices` = **futur gold**, hors Epic).
- **Idempotence** : `MERGE INTO` sur clé métier ⇒ 0 doublon en réexécution (SC-004).

---

## 5. Découpage par Story

### T001 — Usage (US1)
- **Socle commun** (créé ici, réutilisé par T002) : helper de **connexion Azure JDBC** (SP OAuth M2M → Azure SQL Warehouse, secrets via secret scope), resource bundle `job_dcm_system_tables.yml` (Job PySpark, run_as SP), variables target (schéma `__d`, host warehouse Azure), planification (A4).
- Job PySpark : ingestion `system.compute.clusters` + `node_timeline` → `curated_dbx_compute_clusters` + `curated_dbx_compute_node_timeline`
- Ingestion `system.access.audit` → `curated_dbx_access_audit` (incrémental, watermark `event_time`)
- Ingestion `system.access.table_lineage` → `curated_dbx_access_table_lineage` (full scan idempotent ; `event_date` est DATE — pas de watermark ; partition `event_date` ; merge keys : `cloud_provider, account_id, workspace_id, source_table_full_name, target_table_full_name, event_date`)
- Ingestion `system.query.history` → `curated_dbx_query_history` (incrémental, watermark `start_time`, lookback 30j ; merge key : `cloud_provider, statement_id`)
- **Lecture AWS native + Azure via JDBC** (spike Option A), union par `cloud_provider` (table mutualisée)
- MERGE idempotent + colonnes traçabilité
- Tests transformations + idempotence (mock `spark.read`, no DLT)

### T002 — FinOps (US2)
- Job PySpark : `system.billing.usage` → `curated_dbx_billing_usage` et `system.billing.list_prices` → `curated_dbx_billing_list_prices` (**fidèles source, no transform, no join**)
- **Lecture AWS native + Azure via JDBC** (socle T001), union par `cloud_provider` (tables mutualisées)
- MERGE idempotent (anti-doublon)
- Tests mapping fidèle + idempotence

**Note dépendance** : T002 réutilise le socle connexion Azure JDBC + Job bundle créé en T001 (sinon parallélisable avec un socle temporaire).

---

## 6. Constraints & conformité DCM

- Python **3.12**, PySpark ; ruff + mypy zéro warning ; pytest.
- **Pas de DLT** — Job Databricks à tâches PySpark (`spark.read` + `MERGE INTO`), disjoint du DLT collecteur (E5).
- **Aucune donnée fictive** — métrique absente ⇒ `NULL` (FR-011).
- **Médaillon** : curated = fidèle source, **aucune transformation ni jointure** (valorisation `usage × list_prices` = futur gold).
- **Tables mutualisées** : 1 table par métrique, Azure ⊎ AWS via `cloud_provider`.
- Idempotence MERGE (FR-009) — anti-doublon garanti. Traçabilité `collection_run_id`/`collected_at` (FR-010).
- **Accès Azure** : SP OAuth M2M → Azure SQL Warehouse (spike E3) ; **jamais** d'accès direct au storage Azure depuis AWS.
- Déploiement via Databricks Asset Bundle (`resources/`).
- Secrets : jamais en dur — secret SP via **Databricks secret scope** (ou Secrets Manager, à trancher — spike).
- Imports absolus.

---

## 7. Testing

- Tests unitaires transformations (mapping colonnes fidèle source, dérivation `cloud_provider`).
- Test idempotence : 2 runs MERGE ⇒ 0 doublon (SC-004).
- Test mapping fidèle des colonnes `billing.usage` / `billing.list_prices` (no transform, no join — US2).
- Validation ruff/mypy (SC-006).

---

## 8. Risques

| Risque | Mitigation |
|---|---|
| Mécanisme lecture Azure cross-tenant flou (E3) | GATE — trancher avant tasks |
| Schéma/target `__d` non provisionné (E1/E2) | GATE — confirmer bundle target |
| Volume `system.access.audit` | Ingestion incrémentale + partition/watermark |
| Divergence schéma system.* Azure vs AWS | Union avec cast explicite + colonnes nullable |

---

## 9. Prochaine étape

Trancher **E1, E2, E3** (bundle + accès Azure), puis :
`/speckit.tasks` → `tasks.md` + `stories/T001-usage-metrics.md` + `stories/T002-finops-metrics.md`.
