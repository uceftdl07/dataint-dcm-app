# T001 — Usage Databricks (compute, access.audit, table_lineage, query.history) Azure+AWS → curated

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: feature/010_metrics_system
**Jira**: DCINT-192
**Depends on**: none
**Work type**: feature

## Description

Créer un **Job Databricks PySpark** qui ingère les métriques **d'usage** Databricks depuis les system tables — AWS locales (natif) + **Azure cross-tenant via SP OAuth M2M → Azure SQL Warehouse (JDBC, cf. spike)** — et les écrit **fidèlement** (médaillon, no transform) dans la couche curated de `it.ba_data_connect_monitoring__d`. Couvre compute (clusters + node_timeline), **usage utilisateurs via `system.access.audit`**, **lignage des Data Products via `system.access.table_lineage`** et **historique des requêtes via `system.query.history`**. **Tables mutualisées** Azure ⊎ AWS via colonne `cloud_provider`. Écritures **idempotentes** (MERGE — anti-doublon).

> **Pas de DLT** (E5) : sources = system tables batch (dont JDBC cross-cloud), pas un flux de fichiers volume. On utilise `spark.read` + `MERGE INTO` Delta, disjoint du pipeline DLT collecteur.
>
> **Accès Azure (E3, spike)** : Delta Sharing UC→UC **bloqué** (firewall ADLS Gen2). Lecture Azure = **JDBC** vers Azure SQL Warehouse, auth SP OAuth M2M (`AuthMech=11`, `Auth_Flow=1`), secrets via secret scope. AWS ne touche jamais au storage Azure. Réf : [`docs/spike/delta-sharing-azure-to-aws-billing.md`](../../../docs/spike/delta-sharing-azure-to-aws-billing.md).

## Sources system tables

- `system.compute.clusters`, `system.compute.node_timeline`
- `system.access.audit` (usage utilisateurs — incrémental, watermark `event_time`)
- `system.access.table_lineage` (lignage Data Products — full scan idempotent, partition `event_date`)
- `system.query.history` (historique requêtes — incrémental, watermark `start_time`)

## Files to create/modify

- CREATE `pipelines/system_tables_usage.py` — Job PySpark : ingestion + MERGE curated (no DLT)
- CREATE `pipelines/azure_jdbc.py` (socle commun) — helper connexion **SP OAuth M2M → Azure SQL Warehouse** (JDBC), réutilisé par T002
- CREATE `resources/job_dcm_system_tables.yml` — Job bundle (planifié, run_as SP)
- UPDATE `databricks.yml` — variable schéma `__d` + target dev AWS `dbc-16a9ad66-c301` + **host/warehouse Azure + secret scope SP** (E1/E2/E3)
- CREATE `tests/test_system_tables_usage.py` — mapping fidèle + idempotence (mock `spark.read`)

## Sub-tasks

- [x] Resource bundle Job `job_dcm_system_tables.yml` — _tâche `system_tables_usage` ajoutée au Job (créé en T002), même env serverless + named_parameters_
- [x] Variables target : schéma `__d`, hôtes AWS dev/prod, **host Azure SQL Warehouse + secret scope SP** — _déjà présents dans `databricks.yml` (socle T002), réutilisés_
- [x] **Socle Azure JDBC** : helper OAuth M2M via `dbutils.secrets` — _vit dans `pipelines/common` (readers/azure_auth), réutilisé ; `pipelines/azure_jdbc.py` du plan original superseded par le socle T002_
- [x] Ingestion `system.compute.clusters` + `node_timeline` → **2 tables curated fidèles** `curated_dbx_compute_clusters` + `curated_dbx_compute_node_timeline` — _médaillon fidèle-source (pas de jointure) ; décision validée avec l'utilisateur_
- [x] Ingestion `system.access.audit` → `curated_dbx_access_audit` (incrémental, watermark `event_time`, partition `event_date`)
- [x] Ingestion `system.access.table_lineage` → `curated_dbx_access_table_lineage` (full scan idempotent ; `event_date` est DATE, incompatible avec `compute_lower_bound` datetime → pas de watermark ; partition `event_date`) — merge keys : `cloud_provider, account_id, workspace_id, source_table_full_name, target_table_full_name, event_date`
- [x] Ingestion `system.query.history` → `curated_dbx_query_history` (incrémental, watermark `start_time`, lookback 30j) — merge key : `cloud_provider, statement_id`
- [ ] Ingestion usage tables → `curated_databricks_table_usage` (si dispo) — _skippé : source ambiguë, hors scope confirmé_
- [x] Enrichir chaque ligne : `cloud_provider`, `workspace_id`, `account_id`, `collection_run_id`, `collected_at` — _via `enrich_with_envelope` (socle)_
- [x] **Table mutualisée** : Azure ⊎ AWS via `cloud_provider` (MERGE séparé par cloud, autoMerge schéma Delta)
- [x] MERGE idempotent sur clé métier (anti-doublon)
- [x] Tests transformations + idempotence (2 runs ⇒ 0 doublon) — _12 tests `tests/usage`_
- [x] ruff + mypy zéro warning

## Acceptance Criteria

- [x] `curated_dbx_compute_clusters` + `curated_dbx_compute_node_timeline` alimentées Azure + AWS, colonnes fidèles source (no transform) — _2 tables fidèles au lieu d'une (médaillon, pas de jointure)_
- [x] `curated_dbx_access_audit` peuplée avec `cloud_provider` + identifiants workspace
- [x] `curated_dbx_access_table_lineage` peuplée Azure + AWS, partition `event_date`, MERGE idempotent (full scan — contrainte DATE watermark)
- [x] `curated_dbx_query_history` peuplée Azure + AWS, incrémental watermark `start_time`, MERGE idempotent sur `statement_id`
- [x] Chaque ligne porte `cloud_provider` (`azure`|`aws`) + identifiants Databricks natifs
- [x] 2 exécutions consécutives ⇒ 0 doublon (MERGE idempotent, clé incluant `cloud_provider`)
- [x] Métrique source absente ⇒ colonne `NULL` (jamais valeur fictive — no transform)
- [x] Naming `layer_source_domain_metric` respecté
- [x] Job YAML `inputs` mis à jour de 5 → 7 tables (`access_table_lineage`, `query_history` ajoutés)
- [x] Déployé via Databricks Asset Bundle (tâche `system_tables_usage`)

## Tests

- `pytest packages/dcm-databricks-pipeline/tests/test_system_tables_usage.py`
- `ruff check packages/dcm-databricks-pipeline`

## Out of scope

- Coûts / FinOps → T002
- Routes backend / UI → futur Epic
- Couche gold (agrégats)

## Before PR

- [ ] Merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside `packages/dcm-databricks-pipeline`
- [ ] Sub-spec checkboxes reviewed

## Notes — [NEEDS CLARIFICATION] (GATE)

- **E1 (résolu)** : schéma mappé par target — dev `__d`, prod `__p`. Bundle mis à jour.
- **E2 (résolu)** : dev AWS host = `dbc-16a9ad66-c301` (bundle mis à jour) ; prod `dbc-af3acef9-c998` inchangé.
- **E3 (résolu — spike)** : Delta Sharing UC→UC **bloqué** (firewall ADLS Gen2). Lecture Azure = **SP OAuth M2M → Azure SQL Warehouse** via **JDBC** (spike Option A) ; alt. `databricks-sql-connector` (B) ; Lakehouse Federation (C) = industrialisation, hors POC. Réf : `docs/spike/delta-sharing-azure-to-aws-billing.md`.
- **E5 (résolu)** : **pas de DLT** — Job PySpark `spark.read` + `MERGE INTO`.
- **A4** : fréquence Job + fenêtre lookback incrémentale (à confirmer).
- ⚠️ **Prérequis externes DAP/IAM/Network** (spike §Prérequis / §Points ouverts) : SP Entra ID + secret, Azure SQL Warehouse dédié + `CAN USE`, **firewall endpoint warehouse joignable depuis AWS**, vue matérialisée Azure, choix stockage secret (secret scope vs Secrets Manager).

Réf : `plan.md` §3, §5 ; `spec.md` US1, FR-001/006/008/009/011 ; `docs/spike/delta-sharing-azure-to-aws-billing.md`.
