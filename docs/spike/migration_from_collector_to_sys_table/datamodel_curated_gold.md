# Workflow Observability — Data Model (Curated + Gold) après migration

> Modèle de données du domaine `workflow` (observabilité Jobs/Workflows Databricks, epic 009)
> **après** bascule sur les system tables `system.lakeflow.*`.
> Aligné sur la médaillon DCM : `system.*` → **CURATED** (`curated_dbx_*`, MERGE idempotent) →
> **GOLD** (`gold_dbx_workflow_*`, agrégats prêts API).
> Catalog / schéma : `it.ba_data_connect_monitoring__{env}` (`__d` dev, `__p` prod) — vars bundle,
> jamais codé en dur.
> Cloud : tables mutualisées Azure/AWS → `cloud_provider` fait partie de la clé.

---

## 0. Vue d'ensemble

```text
system.lakeflow.jobs ────────────────────┐
system.lakeflow.job_run_timeline ────────┼─►  CURATED fidèle (socle system_tables)
system.lakeflow.job_task_run_timeline ───┘        curated_dbx_lakeflow_*  (MERGE idempotent, watermark)
                                                        │
                                                        ▼
                                        Vues-pont DLT (reshaping → contrat epic 009)
                                          _wf_runs_bridge / _wf_task_runs_bridge
                                                        │
                                                        ▼
                                     GOLD (inchangé) gold_dbx_workflow_* × 8
```

**Grain :**
- CURATED `job_run_timeline` : 1 ligne = 1 run (`run_id`).
- CURATED `job_task_run_timeline` : 1 ligne = 1 exécution de tâche (`task_run_id`).
- GOLD agrégats : 1 jour × workflow (× workspace × LZ).
- GOLD drill-down : `gold_dbx_workflow_runs` (grain run), `gold_dbx_workflow_tasks` (grain task).

**Colonnes d'enveloppe** ajoutées par le socle à chaque table curated : `cloud_provider`,
`collected_at`, `_ingested_at`, `collection_run_id` (voir `enrich_with_envelope`).

---

## 1. Couche CURATED — nouvelles tables system.lakeflow (fidèle source)

Trois `IngestionSpec` à ajouter au registre `system_tables/specs.py`. **Aucune transformation**
ici (contrat du socle : fidèle source, MERGE idempotent par cloud).

### 1.1 `curated_dbx_lakeflow_jobs` ← `system.lakeflow.jobs`

Définitions de jobs (SCD : 1 ligne par version, `change_time`).

| Colonne | Type | Notes |
|---|---|---|
| `cloud_provider` | STRING | clé (anti-collision Azure/AWS) |
| `account_id` | STRING | clé |
| `workspace_id` | STRING | clé |
| `job_id` | STRING | clé (= `workflow_id` DCM) |
| `name` | STRING | `workflow_name` |
| `description` | STRING | |
| `creator_id` | STRING | id numérique du créateur (nom = lookup identité) |
| `run_as` | STRING | principal d'exécution |
| `tags` | MAP<STRING,STRING> | owner / cost-center / domaine |
| `change_time` | TIMESTAMP | **watermark**, clé SCD |
| `delete_time` | TIMESTAMP | NULL = actif |

Clé merge : `(cloud_provider, account_id, workspace_id, job_id, change_time)`. Watermark : `change_time`.

### 1.2 `curated_dbx_lakeflow_job_run_timeline` ← `system.lakeflow.job_run_timeline`

Historique des runs (1 ligne par run terminal / période).

| Colonne | Type | Notes |
|---|---|---|
| `cloud_provider` | STRING | clé |
| `account_id` | STRING | clé |
| `workspace_id` | STRING | clé |
| `job_id` | STRING | = `workflow_id` |
| `run_id` | STRING | clé |
| `period_start_time` | TIMESTAMP | **watermark** ; `start_time` DCM |
| `period_end_time` | TIMESTAMP | `end_time` DCM |
| `trigger_type` | STRING | à re-mapper vers l'enum DCM |
| `run_type` | STRING | `JOB_RUN` / `SUBMIT_RUN` / `WORKFLOW_RUN` |
| `run_name` | STRING | libellé du run |
| `compute_ids` | ARRAY<STRING> | clusters/warehouses utilisés (FinOps) |
| `result_state` | STRING | `SUCCEEDED`/`FAILED`/`CANCELLED`/`TIMED_OUT`/… |
| `termination_code` | STRING | code de terminaison (diagnostic) |
| `job_parameters` | MAP<STRING,STRING> | paramètres du run |

Clé merge : `(cloud_provider, account_id, workspace_id, job_id, run_id, period_start_time)`.
Watermark : `period_start_time`. Partition : `date(period_start_time)`.
Backfill initial borné (`initial_lookback_days`, cf. tables d'événements volumineuses).

### 1.3 `curated_dbx_lakeflow_job_task_run_timeline` ← `system.lakeflow.job_task_run_timeline`

Historique des tâches (1 ligne par exécution de tâche).

| Colonne | Type | Notes |
|---|---|---|
| `cloud_provider` | STRING | clé |
| `account_id` | STRING | clé |
| `workspace_id` | STRING | clé |
| `job_id` | STRING | = `workflow_id` |
| `run_id` | STRING | run parent |
| `parent_run_id` | STRING | run parent (multi-task) |
| `task_run_id` | STRING | clé (= `task_id` DCM, unique) |
| `task_key` | STRING | nom stable de la tâche |
| `period_start_time` | TIMESTAMP | **watermark** ; `start_time` DCM |
| `period_end_time` | TIMESTAMP | `end_time` DCM |
| `compute_ids` | ARRAY<STRING> | cluster de la tâche (FinOps) |
| `result_state` | STRING | état de la tâche |
| `termination_code` | STRING | code de terminaison |

Clé merge : `(cloud_provider, account_id, workspace_id, job_id, run_id, task_run_id, period_start_time)`.
Watermark : `period_start_time`. Partition : `date(period_start_time)`.

---

## 2. Vues-pont DLT (reshaping → contrat epic 009)

Deux vues DLT dans `dlt_03_gold_layer.py` qui **reproduisent exactement** le schéma des
anciennes tables curated (pour ne pas toucher les 8 fonctions gold). Elles lisent les
curated system tables (via `spark.read.table`) et appliquent le mapping (cf. [datamapping.md](datamapping.md)).

### 2.1 `_wf_runs_bridge` (schéma = ancien `curated_dbx_workflow_runs`)

Colonnes produites : `source_lz_id`, `cloud_provider`, `workspace_id`, **`workspace_name` (NULL)**,
`workflow_id`, `workflow_name`, `run_id`, `status`, `trigger_type`, `start_time`, `end_time`,
`duration_seconds`, **`queued_duration_seconds` (NULL)**, **`setup_duration_seconds` (NULL)**,
**`execution_duration_seconds` (NULL)**, **`cleanup_duration_seconds` (NULL)**,
**`schedule_lag_seconds` (NULL)**, `retry_count`, `tasks_total`, `tasks_failed`,
`task_failure_rate`, `cluster_instance_id`, `creator_user_name` (= `creator_id`),
`run_page_url` (reconstruit), `run_type`, `error_message` (= `termination_code`), `tags`.

### 2.2 `_wf_task_runs_bridge` (schéma = ancien `curated_dbx_workflow_task_runs`)

Colonnes produites : `source_lz_id`, `cloud_provider`, `workspace_id`, **`workspace_name` (NULL)**,
`workflow_id`, `workflow_name`, `run_id`, `task_id`, `task_key`, `status`, `start_time`,
`end_time`, `duration_seconds`, `attempt_number`, `cluster_instance_id`,
`error_message` (= `termination_code`).

> **En gras** = champs devenus NULL (voir [migration_steps.md](migration_steps.md) §A).

---

## 3. Couche GOLD — inchangée (8 tables)

Le schéma des tables gold **ne change pas**. Seule leur **source** change (vues-pont au lieu
des curated collecteur), et certaines colonnes deviennent NULL (dérivées de champs perdus).

| Table gold | Grain | Colonnes impactées par les champs perdus |
|---|---|---|
| `gold_dbx_workflow_success_rate` | jour × workflow | aucune (status/duration conservés) |
| `gold_dbx_workflow_duration_percentiles` | jour × workflow | `avg_queued_duration_seconds`, `avg_schedule_lag_seconds`, `max_schedule_lag_seconds` → **NULL** |
| `gold_dbx_workflow_duration_drift` | jour × workflow | aucune (basée sur `duration_seconds`) |
| `gold_dbx_workflow_task_failure_rate` | jour × workflow | aucune (tasks dérivés du task timeline) |
| `gold_dbx_workflow_concurrency_1min` | minute × workspace | fraîcheur dégradée (latence system tables) |
| `gold_dbx_workflow_task_health` | jour × workflow × task_key | aucune |
| `gold_dbx_workflow_runs` | run | `queued_duration_seconds`, `execution_duration_seconds`, `schedule_lag_seconds` → **NULL** ; `workspace_name` → **NULL** ; `error_message` réduit ; `run_page_url` reconstruit |
| `gold_dbx_workflow_tasks` | task | `workspace_name` → **NULL** ; `error_message` réduit |

> Les colonnes restent **présentes** dans le schéma gold (pas de rupture de contrat API/DDL) ;
> elles sont simplement `NULL`. Cf. [impact_back_front.md](impact_back_front.md) pour l'affichage.

---

## 4. Positionnement médaillon & rafraîchissement

| Couche | Objet | Type | Rafraîchissement |
|---|---|---|---|
| CURATED | `curated_dbx_lakeflow_*` | Job wheel `dcm_system_tables` (MERGE idempotent, watermark) | quotidien (cron `0 0 3 * * ?`) |
| GOLD `_wf_*_bridge` | vues reshaping | DLT view | à chaque run pipeline gold |
| GOLD `gold_dbx_workflow_*` | agrégats / drill | DLT table (materialized) | à chaque run pipeline gold |

FK commune : toutes les tables gold référencent `dim_landing_zone (lz_id)` (inchangé).
