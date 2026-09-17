# DCM Azure Collector — Flux complet et lineage CURATED/GOLD

## 1) Périmètre

Ce document décrit, de bout en bout, le chemin des données **Azure collector** :

1. collecte (APIs Azure/Databricks) ;
2. construction `MetricPayload` ;
3. envoi Apigee ;
4. ingestion Lambda + SQS ;
5. dépôt JSON sur volume Databricks ;
6. transformation DLT `RAW -> CURATED -> GOLD`.

Il inclut, pour chaque donnée CURATED/GOLD :
- domaine ;
- source ;
- fonction collecteur liée.

---

## 2) Flux technique de bout en bout

## 2.1 Collecte côté agent Azure

Fichiers clés :
- `packages/dcm-azure-collector/azure_collector/main.py`
- `packages/dcm-commons/dcm_commons/collectors/base.py`
- `packages/dcm-azure-collector/azure_collector/collectors/*.py`

Chaîne d’exécution :

1. `run()` charge config (`AzureCollectorConfig.from_env_and_keyvault`) puis démarre boucle.
2. `run_collection_cycle()` instancie chaque collecteur activé (`_COLLECTOR_REGISTRY`).
3. Chaque collecteur appelle `BaseCollector.collect()` :
   - exécute `collector._collect_metrics()`,
   - construit `MetricPayload` (`collection_run_id`, `source_lz_id`, `cloud_provider`, `domain`, `metrics`).
4. `ApigeeClient.send_batch(payloads)` envoie les payloads.

## 2.2 Apigee -> Lambda -> SQS

Fichiers clés :
- `packages/dcm-commons/dcm_commons/clients/apigee.py`
- `packages/dcm-lambda-ingestion/lambda_ingestion/handler.py`
- `packages/dcm-lambda-ingestion/lambda_ingestion/sqs_publisher.py`

Chaîne d’exécution :

1. `ApigeeClient.send()` POST `/v1/metrics/ingest` avec bearer Entra + `x-apif-apikey`.
2. Lambda `handler()` :
   - `_parse_body()` lit JSON,
   - `validate_payload()` valide `MetricPayload`,
   - `_get_publisher().publish(payload)` publie SQS.
3. `SQSPublisher.publish()` envoie :
   - `MessageBody = payload.model_dump_json()`,
   - `MessageAttributes`: `domain`, `cloud_provider`, `source_lz_id`.

## 2.3 SQS -> JSON sur volume Databricks

Fichier clé :
- `packages/dcm-databricks-pipeline/pipelines/sqs_to_volume_drain.py`

Chaîne d’exécution :

1. lit SQS par batch (`receive_message`, max 10) ;
2. parse body JSON ;
3. valide domaine (`VALID_DOMAINS`) ;
4. déduplique par `collection_run_id` (garde plus récent `collected_at`) ;
5. écrit un fichier par run :  
   `INGESTION_VOLUME_PATH/{collection_run_id}.json` ;
6. supprime message SQS **après** écriture réussie.

## 2.4 Volume JSON -> RAW DLT

Fichier clé :
- `packages/dcm-databricks-pipeline/pipelines/dlt_01_raw_layer.py`

Chaîne d’exécution :

1. lecture stream volume (`cloudFiles` text + `wholetext=true`) ;
2. `parse_json(value)` -> `record` VARIANT ;
3. table `raw_metrics` :
   - `body = record`,
   - colonnes techniques (`collection_run_id`, `domain`, `cloud_provider`, `source_lz_id`, `_ingested_at`).

---

## 3) Matrice collecteurs Azure : API + domaine + fonctions

| Domaine payload | Collecteur | Fonctions clés | API/SDK source |
|---|---|---|---|
| `pipeline` | `DataFactoryCollector` | `_collect_metrics`, `_query_pipeline_runs`, `_map_run_to_metric` | `DataFactoryManagementClient.factories.list`, `pipeline_runs.query_by_factory` |
| `activity_run` | `ActivityRunCollector` | `_collect_metrics`, `_collect_factory_activity_metrics`, `_collect_activity_metrics_for_run` | `factories.list`, `pipeline_runs.query_by_factory`, `activity_runs.query_by_pipeline_run` |
| `compute` | `DatabricksCollector` | `_collect_metrics`, `_list_workspaces`, `_list_clusters`, `_map_cluster_to_metric` | `GET management.azure.com/.../Microsoft.Databricks/workspaces`, `GET {workspace}/api/2.0/clusters/list` |
| `pipeline` | `DatabricksPipelineCollector` | `_collect_metrics`, `_list_workspaces`, `_list_job_runs`, `_map_run_to_metric` | `GET management.../workspaces`, `GET {workspace}/api/2.1/jobs/runs/list` |
| `workflow` | `DatabricksWorkflowCollector` | `_collect_metrics`, `_list_workspaces` (import), `_list_job_runs` (2.2), `_map_run_to_metric`, `_map_tasks` | `GET management.../workspaces`, `GET {workspace}/api/2.2/jobs/runs/list?expand_tasks=true`, `GET {workspace}/api/2.2/jobs/list` |
| `user` | `DatabricksUserCollector` | `_collect_metrics`, `_list_workspaces`, `_collect_workspace_users`, `_map_scim_user` | `GET management.../workspaces`, `GET /api/2.0/preview/scim/v2/Users`, `GET /api/2.0/preview/scim/v2/Groups` |
| `cost` | `CostManagementCollector` | `_collect_metrics`, `_query_costs_by_service`, `_query_budgets`, `_build_cost_metrics` | `POST .../Microsoft.CostManagement/query`, `GET .../Microsoft.Consumption/budgets` |
| `database` | `DatabaseCollector` | `_collect_metrics`, `_collect_sql_metrics`, `_collect_postgresql_metrics`, `_collect_mysql_metrics`, `_collect_cosmos_metrics`, `_fetch_monitor_metrics` | `SqlManagementClient`, `PostgreSQL...Client`, `MySQL...Client`, `CosmosDBManagementClient`, `MonitorManagementClient.metrics.list` |
| `security` | `SecurityCenterCollector` | `_collect_metrics`, `_map_alert` | `SecurityCenter.alerts.list()` |
| `standard_check` | `StandardCheckCollector` | `_collect_metrics`, `_query_policy_states`, `_map_policy_state` | `PolicyInsightsClient.policy_states.list_query_results_for_subscription(policy_states_resource='latest')` |

Note importante :
- le domaine `pipeline` alimente `curated_pipeline_metrics` depuis **2 collecteurs** (ADF + Databricks Jobs 2.1) ;
- le domaine `workflow` alimente `curated_dbx_workflow_runs` et `curated_dbx_workflow_task_runs` (via `_map_tasks`).

---

## 4) Structure JSON écrite sur volume

Payload écrit dans `{collection_run_id}.json` :

- `schema_version`
- `collection_run_id`
- `source_lz_id`
- `cloud_provider`
- `domain`
- `collected_at`
- `metrics[]` (objets métriques)
- `metric_count`, `is_empty`

`dlt_01_raw_layer.py` conserve objet complet en `body` (VARIANT), puis CURATED explode `body:metrics`.

---

## 5) Lineage CURATED (champ -> source -> domaine -> fonction collecteur)

## 5.1 Colonnes enveloppe communes (toutes tables CURATED)

Source : `parse_metrics_and_dq()` dans `dlt_02_curated_layer.py`

| Colonne curated | Source |
|---|---|
| `collection_run_id` | colonne RAW `collection_run_id` |
| `source_lz_id` | colonne RAW `source_lz_id` |
| `cloud_provider` | colonne RAW `cloud_provider` |
| `subscription_or_account_id` | `body:subscription_or_account_id::STRING` |
| `collected_at` | `body:collected_at::TIMESTAMP` |
| `_ingested_at` | colonne RAW `_ingested_at` |

## 5.2 Dictionnaire CURATED par table

## `curated_pipeline_metrics` (domaine `pipeline`)
Collecteurs liés :
- `DataFactoryCollector._map_run_to_metric`
- `DatabricksPipelineCollector._map_run_to_metric`

Champs :
- `pipeline_id <= metric:pipeline_id`
- `pipeline_name <= metric:pipeline_name`
- `run_id <= metric:run_id`
- `status <= metric:status`
- `trigger_type <= metric:trigger_type`
- `start_time <= metric:start_time`
- `end_time <= metric:end_time`
- `duration_seconds <= metric:duration_seconds`
- `error_message <= metric:error_message`
- `factory_name <= metric:factory_name`
- `resource_group <= metric:resource_group`
- `glue_job_name <= metric:glue_job_name`
- `tags <= metric:tags`

## `curated_activity_runs` (domaine `activity_run`)
Collecteur lié : `ActivityRunCollector._collect_activity_metrics_for_run`

Champs :
- `activity_run_id <= concat(metric:pipeline_run_id, '|', metric:activity_name)` (clé technique)
- `pipeline_run_id <= metric:pipeline_run_id`
- `pipeline_name <= metric:pipeline_name`
- `activity_name <= metric:activity_name`
- `activity_type <= metric:activity_type`
- `status <= metric:status`
- `start_time <= metric:start_time`
- `end_time <= metric:end_time`
- `duration_seconds <= metric:duration_seconds`
- `rows_read <= metric:rows_read`
- `rows_written <= metric:rows_written`
- `data_read_bytes <= metric:data_read_bytes`
- `data_written_bytes <= metric:data_written_bytes`
- `error_message <= metric:error_message`
- `tags <= metric:tags`

## `curated_compute_metrics` (domaine `compute`)
Collecteur lié : `DatabricksCollector._map_cluster_to_metric`

Champs :
- `compute_resource_id <= metric:compute_resource_id`
- `resource_name <= metric:resource_name`
- `compute_type <= metric:compute_type`
- `node_type <= metric:node_type`
- `num_workers <= metric:num_workers`
- `state <= metric:state`
- `avg_cpu_utilization_pct <= metric:avg_cpu_utilization_pct`
- `avg_mem_utilization_pct <= metric:avg_mem_utilization_pct`
- `autoscale_min <= metric:autoscale_min`
- `autoscale_max <= metric:autoscale_max`
- `spark_version <= metric:spark_version`
- `start_time <= metric:start_time`
- `creator <= metric:creator`
- `estimated_hourly_cost_usd <= metric:estimated_hourly_cost_usd`
- `workspace_id <= metric:workspace_id`
- `tags <= metric:tags`

## `curated_cost_metrics` (domaine `cost`)
Collecteur lié : `CostManagementCollector._build_cost_metrics`

Champs :
- `service_name <= metric:service_name`
- `resource_group <= metric:resource_group`
- `period_start <= metric:period_start`
- `period_end <= metric:period_end`
- `cost_usd <= metric:cost_usd`
- `currency <= metric:currency`
- `budget_name <= metric:budget_name`
- `budget_limit_usd <= metric:budget_limit_usd`
- `budget_consumed_pct <= metric:budget_consumed_pct`
- `tags <= metric:tags`

## `curated_database_metrics` (domaine `database`)
Collecteur lié : `DatabaseCollector` (`_collect_sql_metrics`, `_collect_postgresql_metrics`, `_collect_mysql_metrics`, `_collect_cosmos_metrics`)

Champs :
- `db_id <= metric:db_id`
- `db_name <= metric:db_name`
- `db_type <= metric:db_type`
- `server_name <= metric:server_name`
- `resource_group <= metric:resource_group`
- `region <= metric:region`
- `cpu_percent <= metric:cpu_percent`
- `memory_percent <= metric:memory_percent`
- `storage_used_gb <= metric:storage_used_gb`
- `storage_limit_gb <= metric:storage_limit_gb`
- `active_connections <= metric:active_connections`
- `dtus_used <= metric:dtus_used`
- `is_available <= metric:is_available`
- `tags <= metric:tags`

## `curated_security_alerts` (domaine `security`)
Collecteur lié : `SecurityCenterCollector._map_alert`

Champs :
- `alert_id <= metric:alert_id`
- `title <= metric:title`
- `description <= metric:description`
- `severity <= metric:severity`
- `status <= metric:status`
- `detected_at <= metric:detected_at`
- `resource_id <= metric:resource_id`
- `resource_name <= metric:resource_name`
- `resource_type <= metric:resource_type`
- `remediation <= metric:remediation`
- `compromised_entity <= metric:compromised_entity`
- `tags <= metric:tags`

## `curated_user_metrics` (domaine `user`)
Collecteur lié : `DatabricksUserCollector._map_scim_user`

Champs :
- `user_id <= metric:user_id`
- `user_name <= metric:user_name`
- `user_type <= metric:user_type`
- `is_active <= metric:is_active`
- `display_name <= metric:display_name`
- `workspace_or_account <= metric:workspace_or_account`
- `groups <= metric:groups`
- `roles <= metric:roles`
- `last_activity_at <= metric:last_activity_at`
- `tags <= metric:tags`

## `curated_standard_checks` (domaine `standard_check`)
Collecteur lié : `StandardCheckCollector._map_policy_state`

Champs :
- `check_id <= metric:check_id`
- `check_name <= metric:check_name`
- `check_state <= metric:check_state`
- `resource_id <= metric:resource_id`
- `resource_name <= metric:resource_name`
- `resource_type <= metric:resource_type`
- `check_effect <= metric:check_effect`
- `non_check_reasons <= metric:non_check_reasons`
- `evaluated_at <= metric:evaluated_at`
- `tags <= metric:tags`

## `curated_dbx_workflow_runs` (domaine `workflow`)
Collecteur lié : `DatabricksWorkflowCollector._map_run_to_metric`

Champs :
- `workflow_id <= metric:workflow_id`
- `workflow_name <= metric:workflow_name`
- `run_id <= metric:run_id`
- `workspace_id <= metric:workspace_id`
- `workspace_name <= metric:workspace_name`
- `status <= metric:status`
- `trigger_type <= metric:trigger_type`
- `start_time <= metric:start_time`
- `end_time <= metric:end_time`
- `duration_seconds <= metric:duration_seconds`
- `queued_duration_seconds <= metric:queued_duration_seconds`
- `setup_duration_seconds <= metric:setup_duration_seconds`
- `execution_duration_seconds <= metric:execution_duration_seconds`
- `cleanup_duration_seconds <= metric:cleanup_duration_seconds`
- `schedule_lag_seconds <= metric:schedule_lag_seconds`
- `retry_count <= metric:retry_count`
- `tasks_total <= metric:tasks_total`
- `tasks_failed <= metric:tasks_failed`
- `task_failure_rate <= metric:task_failure_rate`
- `cluster_instance_id <= metric:cluster_instance_id`
- `creator_user_name <= metric:creator_user_name`
- `run_page_url <= metric:run_page_url`
- `run_type <= metric:run_type`
- `error_message <= metric:error_message`
- `tags <= metric:tags`

## `curated_dbx_workflow_task_runs` (domaine `workflow`, grain tâche)
Collecteur lié : `DatabricksWorkflowCollector._map_tasks`

Champs :
- `workflow_id <= metric:workflow_id`
- `workflow_name <= metric:workflow_name`
- `run_id <= metric:run_id` (run parent)
- `workspace_id <= metric:workspace_id`
- `workspace_name <= metric:workspace_name`
- `task_id <= task:task_id` (`tasks[].run_id`)
- `task_key <= task:task_key`
- `status <= task:status`
- `start_time <= task:start_time`
- `end_time <= task:end_time`
- `duration_seconds <= task:duration_seconds`
- `attempt_number <= task:attempt_number`
- `cluster_instance_id <= task:cluster_instance_id`
- `error_message <= task:error_message`

---

## 6) Lineage GOLD (table -> source curated -> logique de calcul -> collecteur amont)

## `gold_pipeline_summary`
- Source : `curated_pipeline_metrics`
- Formules :
  - `total_runs = count(*)`
  - `avg_duration_seconds = avg(duration_seconds)`
  - `max_duration_seconds = max(duration_seconds)`
  - `min_duration_seconds = min(duration_seconds)`
  - `failed_with_error = count(error_message is not null)`
- Collecteurs amont : `DataFactoryCollector`, `DatabricksPipelineCollector`

## `gold_compute_utilization`
- Source : `curated_compute_metrics`
- Formules :
  - flags CPU/MEM (`UNDERUTILIZED` <20, `OPTIMAL` 20-80, `OVERUTILIZED` >80)
  - agrégats `cluster_count`, `avg_cpu_pct`, `avg_mem_pct`, `avg_num_workers`, `total_estimated_cost_usd`
- Collecteur amont : `DatabricksCollector`

## `gold_cost_summary`
- Sources : `curated_cost_metrics` + `dim_landing_zone`
- Formules :
  - `total_cost_usd = sum(cost_usd)`
  - `resource_count = count(*)`
  - `avg_budget_consumed_pct = avg(budget_consumed_pct)`
- Collecteur amont : `CostManagementCollector`

## `gold_database_capacity_alerts`
- Source : `curated_database_metrics`
- Formules :
  - `available_space_gb = storage_limit_gb - storage_used_gb`
  - `storage_utilization_pct = storage_used_gb / storage_limit_gb * 100`
  - `alert_level = CRITICAL (>90) / WARNING (>80) / OK`
  - filtre final `storage_utilization_pct > 80`
- Collecteur amont : `DatabaseCollector`

## `gold_standard_check_score`
- Sources : `curated_standard_checks` + `dim_landing_zone`
- Formules :
  - `total_checks = count(*)`
  - `compliant_count = count(check_state='compliant')`
  - `non_compliant_count = count(check_state='non_compliant')`
  - `compliance_score_pct = compliant_count / total_checks * 100`
- Collecteur amont : `StandardCheckCollector`

## `gold_security_summary`
- Sources : `curated_security_alerts` + `dim_landing_zone`
- Formules :
  - `alert_count = count(*)`
  - group by `severity`, `status`, `detection_date`
- Collecteur amont : `SecurityCenterCollector`

## `gold_activity_performance`
- Source : `curated_activity_runs`
- Formules :
  - `total_runs = count(*)`
  - `avg_duration_seconds`, `max_duration_seconds`
  - `avg_rows_read`, `avg_rows_written`
  - `avg_row_ratio = avg(rows_written/rows_read)` si `rows_read>0`
  - `avg_data_read_bytes`, `avg_data_written_bytes`
- Collecteur amont : `ActivityRunCollector`

## `gold_dbx_workflow_success_rate`
- Source : `curated_dbx_workflow_runs`
- Formules :
  - compteurs terminal/succeeded/failed/cancelled/timed_out
  - `success_rate_24h_pct = succeeded_runs / terminal_runs * 100`
  - `success_rate_7d_pct` via fenêtre glissante 7 jours (`rowsBetween(-6,0)`)
- Collecteur amont : `DatabricksWorkflowCollector._map_run_to_metric`

## `gold_dbx_workflow_duration_percentiles`
- Source : `curated_dbx_workflow_runs`
- Formules :
  - `p50`, `p95`, `p99` via `percentile_approx(duration_seconds, q)`
  - moyennes durée, queue, lag, retry + max durée/lag
- Collecteur amont : `DatabricksWorkflowCollector._map_run_to_metric`

## `gold_dbx_workflow_duration_drift`
- Source : `curated_dbx_workflow_runs`
- Formules :
  - agrégat quotidien `avg_duration_seconds`
  - `baseline_avg_14d` via fenêtre trailing 14 jours excluant jour courant (`rowsBetween(-14,-1)`)
  - `duration_drift_pct = (avg_duration - baseline_14d)/baseline_14d * 100`
- Collecteur amont : `DatabricksWorkflowCollector._map_run_to_metric`

## `gold_dbx_workflow_task_failure_rate`
- Source : `curated_dbx_workflow_runs` (compteurs tâche agrégés run)
- Formules :
  - `runs_with_tasks = count(*)`
  - `tasks_total = sum(tasks_total)`
  - `tasks_failed = sum(tasks_failed)`
  - `task_failure_rate_pct = tasks_failed / tasks_total * 100`
- Collecteur amont : `DatabricksWorkflowCollector._map_run_to_metric`

## `gold_dbx_workflow_concurrency_1min`
- Source : `curated_dbx_workflow_runs`
- Formules :
  - reconstruction intervalle actif `[start_time, end_time or now]`
  - `minute_bucket` via `sequence(date_trunc(...), interval 1 minute)`
  - `concurrent_runs_active = countDistinct(run_id)`
- Collecteur amont : `DatabricksWorkflowCollector._map_run_to_metric`

## `gold_dbx_workflow_task_health` (ajout task_id)
- Source : `curated_dbx_workflow_task_runs`
- Formules :
  - `total_task_runs = countDistinct(task_id)`
  - `failed_task_runs = sum(CASE status IN ('failed','timed_out','cancelled') THEN 1 ELSE 0 END)`
  - `task_failure_rate_pct = failed_task_runs / total_task_runs * 100`
  - `avg_task_duration_seconds = avg(duration_seconds)`
  - `p95_task_duration_seconds = percentile_approx(duration_seconds, 0.95)`
- Collecteur amont : `DatabricksWorkflowCollector._map_tasks`

## `gold_dbx_workflow_runs` (drill-down, grain run)
- Source : `curated_dbx_workflow_runs`
- Logique : projection run-grain (pas d'agrégation), filtre `start_time IS NOT NULL`
- Grain / PK : `(source_lz_id, workspace_id, workflow_id, run_id)`
- Champs exposés : `run_id`, `execution_date = date(start_time)`, `status`, `trigger_type`, `run_type`, `start_time`, `end_time`, `duration_seconds`, `queued_duration_seconds`, `execution_duration_seconds`, `schedule_lag_seconds`, `retry_count`, `tasks_total`, `tasks_failed`, `task_failure_rate`, `creator_user_name`, `cluster_instance_id`, `run_page_url`, `error_message`
- Collecteur amont : `DatabricksWorkflowCollector._map_run_to_metric`

## `gold_dbx_workflow_tasks` (drill-down, grain tâche)
- Source : `curated_dbx_workflow_task_runs`
- Logique : projection task-grain (pas d'agrégation), filtre `start_time IS NOT NULL`
- Grain / PK : `(source_lz_id, workspace_id, workflow_id, run_id, task_id)`
- Champs exposés : `run_id` (parent), `task_id`, `task_key`, `execution_date = date(start_time)`, `status`, `start_time`, `end_time`, `duration_seconds`, `attempt_number`, `cluster_instance_id`, `error_message`
- Collecteur amont : `DatabricksWorkflowCollector._map_tasks`

---

## 7) Traçabilité rapide (où regarder dans le code)

- Orchestration agent : `azure_collector/main.py`
- Contrat payload + retry : `dcm_commons/collectors/base.py`
- Ingestion HTTP Apigee : `dcm_commons/clients/apigee.py`
- Ingestion Lambda : `lambda_ingestion/handler.py`
- Publication SQS : `lambda_ingestion/sqs_publisher.py`
- Drain SQS -> volume : `pipelines/sqs_to_volume_drain.py`
- RAW DLT : `pipelines/dlt_01_raw_layer.py`
- CURATED DLT : `pipelines/dlt_02_curated_layer.py`
- GOLD DLT : `pipelines/dlt_03_gold_layer.py`

---

## 8) Mapping par typologie de métriques (Raw → Curated → Gold)

> Suite au retour sur [DCINT-171](https://tdf.atlassian.net/browse/DCINT-171) : tableau de mapping
> détaillé par typologie (pipeline, workflow, compute, cost, database, security, activity, standard
> check, user). Pour chaque champ : position **RAW** (source), position **CURATED**, position **GOLD**,
> transformation appliquée et commentaire métrique.
>
> Conventions communes : les colonnes d'enveloppe (`collection_run_id`, `subscription_or_account_id`,
> `collected_at`, `_ingested_at`) sont propagées en CURATED pour la gouvernance/lineage et **non
> exploitées** comme KPI en GOLD ; `source_lz_id` et `cloud_provider` sont propagés jusqu'en GOLD comme
> **dimensions** d'agrégation.

### 8.1 Pipeline (`curated_pipeline_metrics` → `gold_pipeline_summary`)

| Raw (source) | Curated | Gold | Transformation | Commentaire métrique |
|---|---|---|---|---|
| `body:metrics[].pipeline_id` | `curated_pipeline_metrics.pipeline_id` | Non utilisé | Cast STRING + DQ `valid_pipeline_id` (NOT NULL) | Identifiant technique pipeline/job. Clé de dédup avec `run_id` + `source_lz_id`. |
| `body:metrics[].pipeline_name` | `curated_pipeline_metrics.pipeline_name` | Non utilisé | Cast STRING | Nom lisible. Analyse opérationnelle, pas agrégé. |
| `body:metrics[].run_id` | `curated_pipeline_metrics.run_id` | Non utilisé | Cast STRING + DQ `valid_run_id` (NOT NULL) | Identifiant exécution. Clé de dédup run-level. |
| `body:metrics[].status` | `curated_pipeline_metrics.status` | `gold_pipeline_summary.status` | Cast STRING + DQ valeurs autorisées | Statut run. Axe de regroupement journalier en gold. |
| `body:metrics[].trigger_type` | `curated_pipeline_metrics.trigger_type` | Non utilisé | Cast STRING | Type de déclenchement (`UNKNOWN` fréquent côté Databricks). |
| `body:metrics[].start_time` | `curated_pipeline_metrics.start_time` | `gold_pipeline_summary.execution_date` | Cast TIMESTAMP puis `date(start_time)` | Début exécution. Devient grain jour en gold. |
| `body:metrics[].end_time` | `curated_pipeline_metrics.end_time` | Non utilisé direct | Cast TIMESTAMP | Fin exécution. NULL si run en cours. |
| `body:metrics[].duration_seconds` | `curated_pipeline_metrics.duration_seconds` | `gold_pipeline_summary.avg_duration_seconds` / `max_duration_seconds` / `min_duration_seconds` | Cast DOUBLE ; dérivée côté collector si absente | Durée run. KPI principal performance. |
| `body:metrics[].error_message` | `curated_pipeline_metrics.error_message` | `gold_pipeline_summary.failed_with_error` | Cast STRING ; `count(isNotNull)` en gold | Message erreur. Proxy échec avec erreur renseignée. |
| `body:metrics[].factory_name` | `curated_pipeline_metrics.factory_name` | Non utilisé | Cast STRING | Spécifique Azure ADF. NULL côté AWS/Databricks. |
| `body:metrics[].resource_group` | `curated_pipeline_metrics.resource_group` | Non utilisé | Cast STRING | Contexte Azure resource group. |
| `body:metrics[].glue_job_name` | `curated_pipeline_metrics.glue_job_name` | Non utilisé | Cast STRING | Spécifique AWS Glue. NULL côté Azure. |
| `body:metrics[].tags` | `curated_pipeline_metrics.tags` | Non utilisé | Cast STRING (pas MAP en curated) | Tags run. Conservés, non exploités en gold. |
| enveloppe `source_lz_id` | `curated_pipeline_metrics.source_lz_id` | `gold_pipeline_summary.source_lz_id` | Propagation directe | Dimension Landing Zone. |
| enveloppe `cloud_provider` | `curated_pipeline_metrics.cloud_provider` | `gold_pipeline_summary.cloud_provider` | Propagation directe | Dimension cloud multi-cloud. |

### 8.2 Workflow — grain run (`curated_dbx_workflow_runs` → agrégats + drill-down)

| Raw (workflow) | Curated | Gold | Transformation | Commentaire |
|---|---|---|---|---|
| `workflow_id` | `curated_dbx_workflow_runs.workflow_id` | `success_rate` / `duration_percentiles` / `duration_drift` / `task_failure_rate` / `gold_dbx_workflow_runs` `.workflow_id` | Cast STRING + DQ NOT NULL + clé MERGE | Identifiant job/workflow Databricks. |
| `workflow_name` | `curated_dbx_workflow_runs.workflow_name` | mêmes tables (col `workflow_name`) | Cast STRING | Nom lisible workflow. |
| `run_id` | `curated_dbx_workflow_runs.run_id` | `concurrency_1min.concurrent_runs_active` (`countDistinct`) ; `gold_dbx_workflow_runs.run_id` (drill-down) | Cast STRING + DQ NOT NULL + clé MERGE | ID unique run. Calcul concurrence minute + drill-down. |
| `workspace_id` | `curated_dbx_workflow_runs.workspace_id` | toutes tables gold workflow (dimension) | Cast STRING | Scope workspace des agrégats. |
| `workspace_name` | `curated_dbx_workflow_runs.workspace_name` | `gold_dbx_workflow_runs.workspace_name` (drill-down) | Cast STRING | Métadonnée descriptive workspace. |
| `status` | `curated_dbx_workflow_runs.status` | `success_rate.terminal_runs`/`succeeded_runs`/`failed_runs`/`cancelled_runs`/`timed_out_runs`/`success_rate_24h_pct`/`success_rate_7d_pct` | Cast STRING + DQ liste statuts | Variable principale fiabilité run. |
| `trigger_type` | `curated_dbx_workflow_runs.trigger_type` | `gold_dbx_workflow_runs.trigger_type` (drill-down) | Cast STRING | Type de déclenchement (periodic/manual/…). |
| `start_time` | `curated_dbx_workflow_runs.start_time` | `execution_date` (success_rate / duration_percentiles / duration_drift / task_failure_rate) ; `concurrency_1min.minute_bucket` | Cast TIMESTAMP + `date_trunc`/`date` | Pivot temporel de tous les KPI workflow. |
| `end_time` | `curated_dbx_workflow_runs.end_time` | `concurrency_1min` (borne fin d'intervalle) | Cast TIMESTAMP + `coalesce(current_timestamp())` si NULL | Reconstruction des chevauchements de runs actifs. |
| `duration_seconds` | `curated_dbx_workflow_runs.duration_seconds` | `duration_percentiles.total_runs`/`avg`/`p50`/`p95`/`p99`/`max_duration_seconds` ; `duration_drift.avg_duration_seconds`/`baseline_avg_14d`/`duration_drift_pct` | Cast DOUBLE + agrégats + `percentile_approx` + fenêtre 14j | KPI performance run. |
| `queued_duration_seconds` | `curated_dbx_workflow_runs.queued_duration_seconds` | `duration_percentiles.avg_queued_duration_seconds` | Cast DOUBLE + moyenne | Temps d'attente avant exécution. |
| `setup_duration_seconds` | `curated_dbx_workflow_runs.setup_duration_seconds` | Non utilisé en gold | Cast DOUBLE | Détail latence setup cluster. |
| `execution_duration_seconds` | `curated_dbx_workflow_runs.execution_duration_seconds` | `gold_dbx_workflow_runs.execution_duration_seconds` (drill-down) | Cast DOUBLE | Détail temps exécution tâches. |
| `cleanup_duration_seconds` | `curated_dbx_workflow_runs.cleanup_duration_seconds` | Non utilisé en gold | Cast DOUBLE | Détail teardown cluster. |
| `schedule_lag_seconds` | `curated_dbx_workflow_runs.schedule_lag_seconds` | `duration_percentiles.avg_schedule_lag_seconds`/`max_schedule_lag_seconds` | Cast DOUBLE + agrégats | Retard planifié vs démarrage réel. |
| `retry_count` | `curated_dbx_workflow_runs.retry_count` | `duration_percentiles.avg_retry_count` | Cast INT + moyenne | Intensité des retries. |
| `tasks_total` | `curated_dbx_workflow_runs.tasks_total` | `task_failure_rate.runs_with_tasks`/`tasks_total`/`task_failure_rate_pct` | Cast INT + somme + ratio | Dénominateur taux d'échec tâches. |
| `tasks_failed` | `curated_dbx_workflow_runs.tasks_failed` | `task_failure_rate.tasks_failed`/`task_failure_rate_pct` | Cast INT + somme + ratio | Numérateur taux d'échec tâches. |
| `task_failure_rate` | `curated_dbx_workflow_runs.task_failure_rate` | Non utilisé (recalculé depuis `tasks_total`/`tasks_failed`) | Cast DOUBLE | Valeur run-level conservée, non retenue pour KPI. |
| `cluster_instance_id` | `curated_dbx_workflow_runs.cluster_instance_id` | `gold_dbx_workflow_runs.cluster_instance_id` (drill-down) | Cast STRING | Clé FinOps join cluster. |
| `creator_user_name` | `curated_dbx_workflow_runs.creator_user_name` | `gold_dbx_workflow_runs.creator_user_name` (drill-down) | Cast STRING | Attribut ownership/audit. |
| `run_page_url` | `curated_dbx_workflow_runs.run_page_url` | `gold_dbx_workflow_runs.run_page_url` (drill-down) | Cast STRING | Lien UI Databricks (troubleshooting). |
| `run_type` | `curated_dbx_workflow_runs.run_type` | `gold_dbx_workflow_runs.run_type` (drill-down) | Cast STRING | Type technique run. |
| `error_message` | `curated_dbx_workflow_runs.error_message` | `gold_dbx_workflow_runs.error_message` (drill-down) | Cast STRING | Détail erreur run (debug). |
| `tags` | `curated_dbx_workflow_runs.tags` | Non utilisé | Cast STRING | Tags libres, enrichissement futur. |
| enveloppe `source_lz_id` | `curated_dbx_workflow_runs.source_lz_id` | toutes tables gold workflow (dimension) | Propagation enveloppe | Dimension Landing Zone. |
| enveloppe `cloud_provider` | `curated_dbx_workflow_runs.cloud_provider` | tables gold workflow (dimension ; sauf `concurrency` sans axe statut) | Propagation enveloppe | Dimension cloud. |
| enveloppe `collected_at` / `_ingested_at` / `collection_run_id` / `subscription_or_account_id` | colonnes homologues curated | Non utilisées en gold | Propagation + traçabilité | Gouvernance/lineage, pas KPI direct. |

### 8.3 Workflow — grain tâche (`curated_dbx_workflow_task_runs` → `gold_dbx_workflow_task_health` + `gold_dbx_workflow_tasks`)

| Raw (task) | Curated | Gold | Transformation | Commentaire |
|---|---|---|---|---|
| `task:task_id` (`tasks[].run_id`) | `curated_dbx_workflow_task_runs.task_id` | `task_health.total_task_runs` (`countDistinct`) ; `gold_dbx_workflow_tasks.task_id` | Cast STRING + DQ NOT NULL + clé MERGE | ID unique exécution tâche. |
| `task:task_key` | `curated_dbx_workflow_task_runs.task_key` | `task_health` (axe `task_key`) ; `gold_dbx_workflow_tasks.task_key` | Cast STRING | Nom stable de la tâche dans le job. |
| `task:status` | `curated_dbx_workflow_task_runs.status` | `task_health.failed_task_runs`/`task_failure_rate_pct` ; `gold_dbx_workflow_tasks.status` | Cast STRING + DQ liste statuts | Fiabilité tâche. |
| `task:start_time` | `curated_dbx_workflow_task_runs.start_time` | `task_health.execution_date = date(start_time)` ; `gold_dbx_workflow_tasks.execution_date` | Cast TIMESTAMP + `date()` | Pivot temporel tâche. |
| `task:end_time` | `curated_dbx_workflow_task_runs.end_time` | `gold_dbx_workflow_tasks.end_time` (drill-down) | Cast TIMESTAMP | Fin tâche. NULL si en cours. |
| `task:duration_seconds` | `curated_dbx_workflow_task_runs.duration_seconds` | `task_health.avg_task_duration_seconds`/`p95_task_duration_seconds` ; `gold_dbx_workflow_tasks.duration_seconds` | Cast DOUBLE + `avg`/`percentile_approx` | Performance tâche. |
| `task:attempt_number` | `curated_dbx_workflow_task_runs.attempt_number` | `gold_dbx_workflow_tasks.attempt_number` (drill-down) | Cast INT | Retries de la tâche. |
| `task:cluster_instance_id` | `curated_dbx_workflow_task_runs.cluster_instance_id` | `gold_dbx_workflow_tasks.cluster_instance_id` (drill-down) | Cast STRING | Clé FinOps join cluster (tâche). |
| `task:error_message` | `curated_dbx_workflow_task_runs.error_message` | `gold_dbx_workflow_tasks.error_message` (drill-down) | Cast STRING | Détail erreur tâche (debug). |

### 8.4 Compute (`curated_compute_metrics` → `gold_compute_utilization`)

| Raw (metric) | Curated | Gold | Transformation | Commentaire |
|---|---|---|---|---|
| `compute_resource_id` | `curated_compute_metrics.compute_resource_id` | Non utilisé | Cast STRING | Identifiant ressource compute (dédup). |
| `resource_name` | `curated_compute_metrics.resource_name` | Non utilisé | Cast STRING | Nom lisible cluster/compute. |
| `compute_type` | `curated_compute_metrics.compute_type` | `gold_compute_utilization.compute_type` | Cast STRING | Dimension type (databricks, emr…). |
| `node_type` | `curated_compute_metrics.node_type` | Non utilisé | Cast STRING | Type d'instance nœud. |
| `num_workers` | `curated_compute_metrics.num_workers` | `gold_compute_utilization.avg_num_workers` | Cast INT + moyenne | Taille moyenne cluster. |
| `state` | `curated_compute_metrics.state` | Non utilisé | Cast STRING | État cluster. |
| `avg_cpu_utilization_pct` | `curated_compute_metrics.avg_cpu_utilization_pct` | `gold_compute_utilization.cpu_utilization_status` (flag) + `avg_cpu_pct` | Cast DOUBLE + flag `<20`/`>80` + moyenne | KPI FinOps CPU. |
| `avg_mem_utilization_pct` | `curated_compute_metrics.avg_mem_utilization_pct` | `gold_compute_utilization.mem_utilization_status` (flag) + `avg_mem_pct` | Cast DOUBLE + flag `<20`/`>80` + moyenne | KPI FinOps mémoire. |
| `autoscale_min` / `autoscale_max` | `curated_compute_metrics.autoscale_min`/`autoscale_max` | Non utilisé | Cast INT | Bornes autoscaling. |
| `spark_version` | `curated_compute_metrics.spark_version` | Non utilisé | Cast STRING | Version runtime. |
| `start_time` | `curated_compute_metrics.start_time` | Non utilisé | Cast TIMESTAMP | Démarrage cluster (pas de grain jour en gold). |
| `creator` | `curated_compute_metrics.creator` | Non utilisé | Cast STRING | Ownership/audit. |
| `estimated_hourly_cost_usd` | `curated_compute_metrics.estimated_hourly_cost_usd` | `gold_compute_utilization.total_estimated_cost_usd` | Cast DOUBLE + somme | Coût FinOps estimé. |
| `workspace_id` | `curated_compute_metrics.workspace_id` | Non utilisé | Cast STRING | Scope workspace. |
| `tags` | `curated_compute_metrics.tags` | Non utilisé | Cast STRING | Tags cluster. |
| enveloppe `source_lz_id` / `cloud_provider` | colonnes homologues curated | `gold_compute_utilization.source_lz_id`/`cloud_provider` | Propagation directe | Dimensions d'agrégation. |

### 8.5 Cost (`curated_cost_metrics` → `gold_cost_summary`)

| Raw (metric) | Curated | Gold | Transformation | Commentaire |
|---|---|---|---|---|
| `service_name` | `curated_cost_metrics.service_name` | `gold_cost_summary.service_name` | Cast STRING | Axe service cloud. |
| `resource_group` | `curated_cost_metrics.resource_group` | Non utilisé | Cast STRING | Contexte Azure resource group. |
| `period_start` | `curated_cost_metrics.period_start` | `gold_cost_summary.period_start` | Cast STRING (YYYY-MM-DD) | Axe période de facturation. |
| `period_end` | `curated_cost_metrics.period_end` | Non utilisé | Cast STRING | Fin de période. |
| `cost_usd` | `curated_cost_metrics.cost_usd` | `gold_cost_summary.total_cost_usd` | Cast DOUBLE + somme | KPI coût principal. |
| `currency` | `curated_cost_metrics.currency` | Non utilisé | Cast STRING | Devise (USD attendu). |
| `budget_name` | `curated_cost_metrics.budget_name` | Non utilisé | Cast STRING | Nom du budget. |
| `budget_limit_usd` | `curated_cost_metrics.budget_limit_usd` | Non utilisé | Cast DOUBLE | Plafond budget. |
| `budget_consumed_pct` | `curated_cost_metrics.budget_consumed_pct` | `gold_cost_summary.avg_budget_consumed_pct` | Cast DOUBLE + moyenne | Consommation budgétaire. |
| `tags` | `curated_cost_metrics.tags` | Non utilisé | Cast STRING | Tags coût. |
| `environment` (via join `dim_landing_zone`) | — | `gold_cost_summary.environment` | Jointure LZ | Dimension environnement. |
| enveloppe `source_lz_id` / `cloud_provider` | colonnes homologues curated | `gold_cost_summary.source_lz_id`/`cloud_provider` | Propagation directe | Dimensions d'agrégation. |

### 8.6 Database (`curated_database_metrics` → `gold_database_capacity_alerts`)

| Raw (metric) | Curated | Gold | Transformation | Commentaire |
|---|---|---|---|---|
| `db_id` | `curated_database_metrics.db_id` | `gold_database_capacity_alerts.db_id` (PK) | Cast STRING | Identifiant base. |
| `db_name` | `curated_database_metrics.db_name` | `gold_database_capacity_alerts.db_name` | Cast STRING | Nom base. |
| `db_type` | `curated_database_metrics.db_type` | `gold_database_capacity_alerts.db_type` | Cast STRING | Moteur (sql, postgresql…). |
| `server_name` | `curated_database_metrics.server_name` | `gold_database_capacity_alerts.server_name` | Cast STRING | Hôte serveur. |
| `region` | `curated_database_metrics.region` | `gold_database_capacity_alerts.region` | Cast STRING | Région cloud. |
| `cpu_percent` | `curated_database_metrics.cpu_percent` | `gold_database_capacity_alerts.cpu_percent` | Cast DOUBLE | Charge CPU instantanée. |
| `memory_percent` | `curated_database_metrics.memory_percent` | `gold_database_capacity_alerts.memory_percent` | Cast DOUBLE | Charge mémoire instantanée. |
| `storage_used_gb` | `curated_database_metrics.storage_used_gb` | `gold_database_capacity_alerts.storage_used_gb` (+ calcul util.) | Cast DOUBLE | Stockage utilisé. |
| `storage_limit_gb` | `curated_database_metrics.storage_limit_gb` | `gold_database_capacity_alerts.storage_limit_gb` (+ calcul) | Cast DOUBLE | Stockage alloué. |
| `active_connections` | `curated_database_metrics.active_connections` | Non utilisé | Cast INT | Connexions actives. |
| `dtus_used` | `curated_database_metrics.dtus_used` | Non utilisé | Cast DOUBLE | DTU Azure SQL. |
| `is_available` | `curated_database_metrics.is_available` | `gold_database_capacity_alerts.is_available` | Cast BOOLEAN | Disponibilité base. |
| `tags` | `curated_database_metrics.tags` | Non utilisé | Cast STRING | Tags base. |
| *(calculé)* | — | `gold_database_capacity_alerts.available_space_gb` = `storage_limit_gb - storage_used_gb` | Calcul gold | Espace restant. |
| *(calculé)* | — | `gold_database_capacity_alerts.storage_utilization_pct` = `used/limit*100` | Calcul gold + filtre `>80` | Taux d'occupation ; seuil d'alerte. |
| *(calculé)* | — | `gold_database_capacity_alerts.alert_level` (`CRITICAL >90` / `WARNING >80` / `OK`) | Calcul gold | Sévérité capacité. |
| `_ingested_at` (enveloppe) | `curated_database_metrics._ingested_at` | `gold_database_capacity_alerts._ingested_at` | Propagation | Fraîcheur donnée. |
| enveloppe `source_lz_id` / `cloud_provider` | colonnes homologues curated | `gold_database_capacity_alerts.source_lz_id`/`cloud_provider` | Propagation directe | Dimensions. |

### 8.7 Security (`curated_security_alerts` → `gold_security_summary`)

| Raw (metric) | Curated | Gold | Transformation | Commentaire |
|---|---|---|---|---|
| `alert_id` | `curated_security_alerts.alert_id` | `gold_security_summary.alert_count` (via `count(*)`) | Cast STRING + comptage | Identité alerte ; agrégée en compteur. |
| `title` / `description` | `curated_security_alerts.title`/`description` | Non utilisé | Cast STRING | Détail alerte. |
| `severity` | `curated_security_alerts.severity` | `gold_security_summary.severity` | Cast STRING | Axe sévérité. |
| `status` | `curated_security_alerts.status` | `gold_security_summary.status` | Cast STRING | Axe cycle de vie (active/resolved…). |
| `detected_at` | `curated_security_alerts.detected_at` | `gold_security_summary.detection_date = date(detected_at)` | Cast TIMESTAMP + `date()` | Axe temporel. |
| `resource_id` / `resource_name` / `resource_type` | colonnes homologues curated | Non utilisé | Cast STRING | Ressource concernée. |
| `remediation` | `curated_security_alerts.remediation` | Non utilisé | Cast STRING | Recommandation. |
| `compromised_entity` | `curated_security_alerts.compromised_entity` | Non utilisé | Cast STRING | Entité compromise. |
| `tags` | `curated_security_alerts.tags` | Non utilisé | Cast STRING | Tags alerte. |
| `environment` (via join `dim_landing_zone`) | — | `gold_security_summary.environment` | Jointure LZ | Dimension environnement. |
| enveloppe `source_lz_id` / `cloud_provider` | colonnes homologues curated | `gold_security_summary.source_lz_id`/`cloud_provider` | Propagation directe | Dimensions. |

### 8.8 Activity run (`curated_activity_runs` → `gold_activity_performance`)

| Raw (metric) | Curated | Gold | Transformation | Commentaire |
|---|---|---|---|---|
| `pipeline_run_id` + `activity_name` | `curated_activity_runs.activity_run_id` (`concat(...,'|',...)`) | Non utilisé | Concat clé technique | Clé unique run d'activité. |
| `pipeline_run_id` | `curated_activity_runs.pipeline_run_id` | Non utilisé | Cast STRING | Run pipeline parent. |
| `pipeline_name` | `curated_activity_runs.pipeline_name` | Non utilisé | Cast STRING | Pipeline parent. |
| `activity_name` | `curated_activity_runs.activity_name` | Non utilisé | Cast STRING | Nom activité. |
| `activity_type` | `curated_activity_runs.activity_type` | `gold_activity_performance.activity_type` | Cast STRING | Axe type d'activité. |
| `status` | `curated_activity_runs.status` | `gold_activity_performance.status` | Cast STRING | Axe statut. |
| `start_time` / `end_time` | colonnes homologues curated | Non utilisé | Cast TIMESTAMP | Bornes exécution (pas de grain jour ici). |
| `duration_seconds` | `curated_activity_runs.duration_seconds` | `gold_activity_performance.avg_duration_seconds`/`max_duration_seconds` | Cast DOUBLE + agrégats | Performance activité. |
| `rows_read` | `curated_activity_runs.rows_read` | `gold_activity_performance.avg_rows_read` + `avg_row_ratio` | Cast LONG + moyenne + ratio | Volume lu. |
| `rows_written` | `curated_activity_runs.rows_written` | `gold_activity_performance.avg_rows_written` + `avg_row_ratio` | Cast LONG + moyenne + ratio | Volume écrit. |
| `data_read_bytes` | `curated_activity_runs.data_read_bytes` | `gold_activity_performance.avg_data_read_bytes` | Cast LONG + moyenne | Débit lecture. |
| `data_written_bytes` | `curated_activity_runs.data_written_bytes` | `gold_activity_performance.avg_data_written_bytes` | Cast LONG + moyenne | Débit écriture. |
| `error_message` | `curated_activity_runs.error_message` | Non utilisé | Cast STRING | Détail erreur activité. |
| `tags` | `curated_activity_runs.tags` | Non utilisé | Cast STRING | Tags activité. |
| enveloppe `source_lz_id` / `cloud_provider` | colonnes homologues curated | `gold_activity_performance.source_lz_id`/`cloud_provider` | Propagation directe | Dimensions. |

### 8.9 Standard check (`curated_standard_checks` → `gold_standard_check_score`)

| Raw (metric) | Curated | Gold | Transformation | Commentaire |
|---|---|---|---|---|
| `check_id` | `curated_standard_checks.check_id` | `gold_standard_check_score.total_checks` (via `count(*)`) | Cast STRING + comptage | Identité check ; agrégé en compteur. |
| `check_name` | `curated_standard_checks.check_name` | Non utilisé | Cast STRING | Nom du contrôle. |
| `check_state` | `curated_standard_checks.check_state` | `gold_standard_check_score.compliant_count`/`non_compliant_count`/`compliance_score_pct` | Cast STRING + `count(when 'compliant')` + ratio | Variable principale conformité. |
| `resource_id` / `resource_name` / `resource_type` | colonnes homologues curated | Non utilisé | Cast STRING | Ressource évaluée. |
| `check_effect` | `curated_standard_checks.check_effect` | Non utilisé | Cast STRING | Effet de la policy. |
| `non_check_reasons` | `curated_standard_checks.non_check_reasons` | Non utilisé | Cast STRING | Motifs de non-conformité. |
| `evaluated_at` | `curated_standard_checks.evaluated_at` | `gold_standard_check_score.evaluation_date = date(evaluated_at)` | Cast TIMESTAMP + `date()` | Axe temporel. |
| `tags` | `curated_standard_checks.tags` | Non utilisé | Cast STRING | Tags check. |
| `environment` / `owner_team` (via join `dim_landing_zone`) | — | `gold_standard_check_score.environment`/`owner_team` | Jointure LZ | Dimensions gouvernance. |
| enveloppe `source_lz_id` / `cloud_provider` | colonnes homologues curated | `gold_standard_check_score.source_lz_id`/`cloud_provider` | Propagation directe | Dimensions. |

### 8.10 User (`curated_user_metrics` → dimension `dim_users`)

> Le domaine `user` **n'alimente pas d'agrégat gold** : il alimente la **dimension** `dim_users`
> (SCD Type 2). Pas de KPI mais une table de référence utilisée pour l'enrichissement/audit.

| Raw (metric) | Curated | Gold / Dimension | Transformation | Commentaire |
|---|---|---|---|---|
| `user_id` | `curated_user_metrics.user_id` | `dim_users` (clé métier) | Cast STRING | Identité utilisateur. |
| `user_name` | `curated_user_metrics.user_name` | `dim_users` | Cast STRING | Login/UPN. |
| `user_type` | `curated_user_metrics.user_type` | `dim_users` | Cast STRING | Humain / service principal. |
| `is_active` | `curated_user_metrics.is_active` | `dim_users` | Cast BOOLEAN | Statut actif. |
| `display_name` | `curated_user_metrics.display_name` | `dim_users` (piste SCD2) | Cast STRING | Nom affiché (historisé SCD2). |
| `workspace_or_account` | `curated_user_metrics.workspace_or_account` | `dim_users` | Cast STRING | Scope workspace/compte. |
| `groups` / `roles` | colonnes homologues curated | `dim_users` | Cast STRING | Appartenances/permissions. |
| `last_activity_at` | `curated_user_metrics.last_activity_at` | `dim_users` | Cast TIMESTAMP | Dernière activité. |
| `tags` | `curated_user_metrics.tags` | Non utilisé | Cast STRING | Tags utilisateur. |
| enveloppe `source_lz_id` / `cloud_provider` | colonnes homologues curated | `dim_users` (dimensions) | Propagation directe | Contexte LZ/cloud. |

