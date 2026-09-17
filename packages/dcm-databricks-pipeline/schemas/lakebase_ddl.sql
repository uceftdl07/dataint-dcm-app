
CREATE SCHEMA "ba_data_connect_monitoring__d";
CREATE TABLE "ba_data_connect_monitoring__d"."dim_landing_zone_sync" (
	"lz_id" text PRIMARY KEY,
	"cloud_provider" text,
	"subscription_or_account_id" text,
	"_ingested_at" timestamp with time zone,
	"lz_name" text,
	"environment" text,
	"region" text,
	"owner_team" text,
	"onboarded_at" date,
	"is_active" boolean
);
CREATE TABLE "ba_data_connect_monitoring__d"."dim_users_sync" (
	"row_id" text PRIMARY KEY,
	"collection_run_id" text,
	"source_lz_id" text,
	"cloud_provider" text,
	"subscription_or_account_id" text,
	"collected_at" timestamp with time zone,
	"_ingested_at" timestamp with time zone,
	"user_id" text,
	"user_name" text,
	"user_type" text,
	"is_active" boolean,
	"display_name" text,
	"workspace_or_account" text,
	"groups" text,
	"roles" text,
	"last_activity_at" timestamp with time zone,
	"tags" text,
	"__START_AT" timestamp with time zone,
	"__END_AT" timestamp with time zone
);
CREATE TABLE "ba_data_connect_monitoring__d"."gold_activity_performance_sync" (
	"source_lz_id" text,
	"cloud_provider" text,
	"activity_type" text,
	"status" text,
	"total_runs" bigint,
	"avg_duration_seconds" double precision,
	"max_duration_seconds" double precision,
	"avg_rows_read" double precision,
	"avg_rows_written" double precision,
	"avg_row_ratio" double precision,
	"avg_data_read_bytes" double precision,
	"avg_data_written_bytes" double precision,
	CONSTRAINT "gold_activity_performance_sync_pkey" PRIMARY KEY("source_lz_id","cloud_provider","activity_type","status")
);
CREATE TABLE "ba_data_connect_monitoring__d"."gold_compute_summary_sync" (
	"period_start" text,
	"source_lz_id" text,
	"cloud_provider" text,
	"environment" text,
	"service_name" text,
	"total_cost_usd" double precision,
	"resource_count" bigint,
	"avg_budget_consumed_pct" double precision,
	CONSTRAINT "gold_compute_summary_sync_pkey" PRIMARY KEY("period_start","source_lz_id","cloud_provider","environment","service_name")
);
CREATE TABLE "ba_data_connect_monitoring__d"."gold_compute_utilization_sync" (
	"source_lz_id" text,
	"cloud_provider" text,
	"compute_type" text,
	"cpu_utilization_status" text,
	"mem_utilization_status" text,
	"cluster_count" bigint,
	"avg_cpu_pct" double precision,
	"avg_mem_pct" double precision,
	"avg_num_workers" double precision,
	"total_estimated_cost_usd" double precision,
	CONSTRAINT "gold_compute_utilization_sync_pkey" PRIMARY KEY("source_lz_id","cloud_provider","compute_type","cpu_utilization_status","mem_utilization_status")
);
CREATE TABLE "ba_data_connect_monitoring__d"."gold_cost_summary_sync" (
	"period_start" text,
	"source_lz_id" text,
	"cloud_provider" text,
	"environment" text,
	"service_name" text,
	"total_cost_usd" double precision,
	"resource_count" bigint,
	"avg_budget_consumed_pct" double precision,
	CONSTRAINT "gold_cost_summary_sync_pkey" PRIMARY KEY("period_start","source_lz_id","cloud_provider","environment","service_name")
);
CREATE TABLE "ba_data_connect_monitoring__d"."gold_database_capacity_alerts_sync" (
	"source_lz_id" text,
	"cloud_provider" text,
	"db_id" text,
	"db_name" text,
	"db_type" text,
	"server_name" text,
	"region" text,
	"cpu_percent" double precision,
	"memory_percent" double precision,
	"storage_used_gb" double precision,
	"storage_limit_gb" double precision,
	"available_space_gb" double precision,
	"storage_utilization_pct" double precision,
	"is_available" boolean,
	"alert_level" text,
	"_ingested_at" timestamp with time zone,
	CONSTRAINT "gold_database_capacity_alerts_sync_pkey" PRIMARY KEY("source_lz_id","db_id")
);
CREATE TABLE "ba_data_connect_monitoring__d"."gold_pipeline_summary_sync" (
	"source_lz_id" text,
	"cloud_provider" text,
	"execution_date" date,
	"status" text,
	"total_runs" bigint,
	"avg_duration_seconds" double precision,
	"max_duration_seconds" double precision,
	"min_duration_seconds" double precision,
	"failed_with_error" bigint,
	CONSTRAINT "gold_pipeline_summary_sync_pkey" PRIMARY KEY("source_lz_id","cloud_provider","execution_date","status")
);
CREATE TABLE "ba_data_connect_monitoring__d"."gold_security_summary_sync" (
	"source_lz_id" text,
	"cloud_provider" text,
	"environment" text,
	"severity" text,
	"status" text,
	"detection_date" date,
	"alert_count" bigint,
	CONSTRAINT "gold_security_summary_sync_pkey" PRIMARY KEY("source_lz_id","cloud_provider","environment","severity","status","detection_date")
);
CREATE TABLE "ba_data_connect_monitoring__d"."gold_standard_check_score_sync" (
	"source_lz_id" text,
	"cloud_provider" text,
	"environment" text,
	"owner_team" text,
	"evaluation_date" date,
	"total_checks" bigint,
	"compliant_count" bigint,
	"non_compliant_count" bigint,
	"compliance_score_pct" double precision,
	CONSTRAINT "gold_standard_check_score_sync_pkey" PRIMARY KEY("source_lz_id","cloud_provider","environment","owner_team","evaluation_date")
);
CREATE TABLE "ba_data_connect_monitoring__d"."gold_dbx_workflow_success_rate_sync" (
	"source_lz_id" text,
	"cloud_provider" text,
	"workspace_id" text,
	"workflow_id" text,
	"workflow_name" text,
	"execution_date" date,
	"terminal_runs" bigint,
	"succeeded_runs" bigint,
	"failed_runs" bigint,
	"cancelled_runs" bigint,
	"timed_out_runs" bigint,
	"success_rate_24h_pct" double precision,
	"success_rate_7d_pct" double precision,
	CONSTRAINT "gold_dbx_workflow_success_rate_sync_pkey" PRIMARY KEY("source_lz_id","workspace_id","workflow_id","execution_date")
);
CREATE TABLE "ba_data_connect_monitoring__d"."gold_dbx_workflow_duration_percentiles_sync" (
	"source_lz_id" text,
	"cloud_provider" text,
	"workspace_id" text,
	"workflow_id" text,
	"workflow_name" text,
	"execution_date" date,
	"total_runs" bigint,
	"avg_duration_seconds" double precision,
	"p50_duration_seconds" double precision,
	"p95_duration_seconds" double precision,
	"p99_duration_seconds" double precision,
	"max_duration_seconds" double precision,
	"avg_queued_duration_seconds" double precision,
	"avg_schedule_lag_seconds" double precision,
	"max_schedule_lag_seconds" double precision,
	"avg_retry_count" double precision,
	CONSTRAINT "gold_dbx_workflow_duration_percentiles_sync_pkey" PRIMARY KEY("source_lz_id","workspace_id","workflow_id","execution_date")
);
CREATE TABLE "ba_data_connect_monitoring__d"."gold_dbx_workflow_duration_drift_sync" (
	"source_lz_id" text,
	"cloud_provider" text,
	"workspace_id" text,
	"workflow_id" text,
	"workflow_name" text,
	"execution_date" date,
	"total_runs" bigint,
	"avg_duration_seconds" double precision,
	"baseline_avg_14d" double precision,
	"duration_drift_pct" double precision,
	CONSTRAINT "gold_dbx_workflow_duration_drift_sync_pkey" PRIMARY KEY("source_lz_id","workspace_id","workflow_id","execution_date")
);
CREATE TABLE "ba_data_connect_monitoring__d"."gold_dbx_workflow_task_failure_rate_sync" (
	"source_lz_id" text,
	"cloud_provider" text,
	"workspace_id" text,
	"workflow_id" text,
	"workflow_name" text,
	"execution_date" date,
	"runs_with_tasks" bigint,
	"tasks_total" bigint,
	"tasks_failed" bigint,
	"task_failure_rate_pct" double precision,
	CONSTRAINT "gold_dbx_workflow_task_failure_rate_sync_pkey" PRIMARY KEY("source_lz_id","workspace_id","workflow_id","execution_date")
);
CREATE TABLE "ba_data_connect_monitoring__d"."gold_dbx_workflow_concurrency_1min_sync" (
	"source_lz_id" text,
	"cloud_provider" text,
	"workspace_id" text,
	"minute_bucket" timestamp with time zone,
	"concurrent_runs_active" bigint,
	CONSTRAINT "gold_dbx_workflow_concurrency_1min_sync_pkey" PRIMARY KEY("source_lz_id","workspace_id","minute_bucket")
);
CREATE TABLE "ba_data_connect_monitoring__d"."gold_dbx_workflow_task_health_sync" (
	"source_lz_id" text,
	"cloud_provider" text,
	"workspace_id" text,
	"workflow_id" text,
	"workflow_name" text,
	"task_key" text,
	"execution_date" date,
	"total_task_runs" bigint,
	"failed_task_runs" bigint,
	"task_failure_rate_pct" double precision,
	"avg_task_duration_seconds" double precision,
	"p95_task_duration_seconds" double precision,
	CONSTRAINT "gold_dbx_workflow_task_health_sync_pkey" PRIMARY KEY("source_lz_id","workspace_id","workflow_id","task_key","execution_date")
);
CREATE TABLE "ba_data_connect_monitoring__d"."gold_dbx_workflow_runs_sync" (
	"source_lz_id" text,
	"cloud_provider" text,
	"workspace_id" text,
	"workspace_name" text,
	"workflow_id" text,
	"workflow_name" text,
	"run_id" text,
	"execution_date" date,
	"status" text,
	"trigger_type" text,
	"run_type" text,
	"start_time" timestamp with time zone,
	"end_time" timestamp with time zone,
	"duration_seconds" double precision,
	"queued_duration_seconds" double precision,
	"execution_duration_seconds" double precision,
	"schedule_lag_seconds" double precision,
	"retry_count" integer,
	"tasks_total" integer,
	"tasks_failed" integer,
	"task_failure_rate" double precision,
	"creator_user_name" text,
	"cluster_instance_id" text,
	"run_page_url" text,
	"error_message" text,
	CONSTRAINT "gold_dbx_workflow_runs_sync_pkey" PRIMARY KEY("source_lz_id","workspace_id","workflow_id","run_id")
);
CREATE TABLE "ba_data_connect_monitoring__d"."gold_dbx_workflow_tasks_sync" (
	"source_lz_id" text,
	"cloud_provider" text,
	"workspace_id" text,
	"workspace_name" text,
	"workflow_id" text,
	"workflow_name" text,
	"run_id" text,
	"task_id" text,
	"task_key" text,
	"execution_date" date,
	"status" text,
	"start_time" timestamp with time zone,
	"end_time" timestamp with time zone,
	"duration_seconds" double precision,
	"attempt_number" integer,
	"cluster_instance_id" text,
	"error_message" text,
	CONSTRAINT "gold_dbx_workflow_tasks_sync_pkey" PRIMARY KEY("source_lz_id","workspace_id","workflow_id","run_id","task_id")
);
