"""Tests de `pipelines.gold_dbx_compute.specs` (contrat metier + registre).

Verifie le grain/les cles de merge des 4 tables gold clusters vs
`specs/012-compute-metrics-ingestion/data-model.md` (§"Couche GOLD — Clusters") :
grain commun `(cloud_provider, workspace_id, cluster_id, period_start)` pour
les 3 tables `*_daily`, snapshot sans `period_start` pour `governance`. Pas de
`source_lz_id` : aucun mapping `workspace_id -> lz_id` fiable n'existe
aujourd'hui (cf. `CLUSTER_DAILY_MERGE_KEYS`). Verifie aussi la strategie de
rafraichissement (R9 : full au 1er run, incremental sur
`INCREMENTAL_LOOKBACK_DAYS` jours ensuite, `governance` toujours full).
"""

from __future__ import annotations

import re
from datetime import date

import pipelines.gold_dbx_compute.specs as specs


def test_registry_lists_the_four_cluster_tables_plus_transverse() -> None:
    # T004 ajoute "recommendations" (socle reactif transverse) et T005 ajoute
    # "forecast_daily" (socle predictif transverse, perimetre CLUSTER+WAREHOUSE)
    # au registre scaffolde par T002/T003 - sans retirer/renommer les entrees
    # clusters/warehouses existantes (cf. merge-strategy.md). "job_cluster_cost_daily"
    # ajoute le rollup FinOps par job_id des clusters JOB ephemeres (cf.
    # `pipelines.gold_dbx_compute.job_cluster_cost_daily`). "total_cost_daily"
    # (DCINT-335) ajoute le cout total deduplique par workspace/jour, lu depuis
    # les 5 tables gold `*_cost_daily` existantes (cf.
    # `pipelines.gold_dbx_compute.total_cost_daily`).
    assert specs.GOLD_SPEC_KEYS == (
        "cluster_cost_daily",
        "cluster_cost_rolling",
        "cluster_efficiency_daily",
        "cluster_efficiency_rolling",
        "cluster_reliability_daily",
        "cluster_reliability_rolling",
        "cluster_governance",
        "job_cluster_cost_daily",
        "job_cluster_cost_rolling",
        "pipeline_cost_daily",
        "pipeline_cost_rolling",
        "job_efficiency_daily",
        "job_efficiency_rolling",
        "pipeline_efficiency_daily",
        "pipeline_efficiency_rolling",
        "warehouse_cost_daily",
        "warehouse_cost_rolling",
        "warehouse_utilization_daily",
        "warehouse_utilization_rolling",
        "warehouse_query_performance_daily",
        "warehouse_query_performance_rolling",
        "recommendations",
        "forecast_daily",
        "serverless_cost_daily",
        "serverless_cost_rolling",
        "serverless_governance",
        "pipeline_update_stats",
        "total_cost_daily",
    )
    assert set(specs.GOLD_SPECS) == set(specs.GOLD_SPEC_KEYS)
    assert specs.GOLD_SPECS["cluster_cost_daily"] is specs.CLUSTER_COST_DAILY_SPEC
    assert specs.GOLD_SPECS["cluster_cost_rolling"] is specs.CLUSTER_COST_ROLLING_SPEC
    assert specs.GOLD_SPECS["cluster_efficiency_daily"] is specs.CLUSTER_EFFICIENCY_DAILY_SPEC
    assert (
        specs.GOLD_SPECS["cluster_efficiency_rolling"]
        is specs.CLUSTER_EFFICIENCY_ROLLING_SPEC
    )
    assert specs.GOLD_SPECS["cluster_reliability_daily"] is specs.CLUSTER_RELIABILITY_DAILY_SPEC
    assert (
        specs.GOLD_SPECS["cluster_reliability_rolling"]
        is specs.CLUSTER_RELIABILITY_ROLLING_SPEC
    )
    assert specs.GOLD_SPECS["cluster_governance"] is specs.CLUSTER_GOVERNANCE_SPEC
    assert specs.GOLD_SPECS["job_cluster_cost_daily"] is specs.JOB_CLUSTER_COST_DAILY_SPEC
    assert specs.GOLD_SPECS["job_cluster_cost_rolling"] is specs.JOB_CLUSTER_COST_ROLLING_SPEC
    assert specs.GOLD_SPECS["pipeline_cost_daily"] is specs.PIPELINE_COST_DAILY_SPEC
    assert specs.GOLD_SPECS["pipeline_cost_rolling"] is specs.PIPELINE_COST_ROLLING_SPEC
    assert specs.GOLD_SPECS["job_efficiency_daily"] is specs.JOB_EFFICIENCY_DAILY_SPEC
    assert specs.GOLD_SPECS["job_efficiency_rolling"] is specs.JOB_EFFICIENCY_ROLLING_SPEC
    assert specs.GOLD_SPECS["pipeline_efficiency_daily"] is specs.PIPELINE_EFFICIENCY_DAILY_SPEC
    assert (
        specs.GOLD_SPECS["pipeline_efficiency_rolling"]
        is specs.PIPELINE_EFFICIENCY_ROLLING_SPEC
    )
    assert specs.GOLD_SPECS["warehouse_cost_daily"] is specs.WAREHOUSE_COST_DAILY_SPEC
    assert specs.GOLD_SPECS["warehouse_cost_rolling"] is specs.WAREHOUSE_COST_ROLLING_SPEC
    assert (
        specs.GOLD_SPECS["warehouse_utilization_daily"] is specs.WAREHOUSE_UTILIZATION_DAILY_SPEC
    )
    assert (
        specs.GOLD_SPECS["warehouse_utilization_rolling"]
        is specs.WAREHOUSE_UTILIZATION_ROLLING_SPEC
    )
    assert (
        specs.GOLD_SPECS["warehouse_query_performance_daily"]
        is specs.WAREHOUSE_QUERY_PERFORMANCE_DAILY_SPEC
    )
    assert (
        specs.GOLD_SPECS["warehouse_query_performance_rolling"]
        is specs.WAREHOUSE_QUERY_PERFORMANCE_ROLLING_SPEC
    )
    assert specs.GOLD_SPECS["recommendations"] is specs.RECOMMENDATIONS_SPEC
    assert specs.GOLD_SPECS["forecast_daily"] is specs.FORECAST_DAILY_SPEC
    assert specs.GOLD_SPECS["serverless_cost_daily"] is specs.SERVERLESS_COST_DAILY_SPEC
    assert specs.GOLD_SPECS["serverless_cost_rolling"] is specs.SERVERLESS_COST_ROLLING_SPEC
    assert specs.GOLD_SPECS["serverless_governance"] is specs.SERVERLESS_GOVERNANCE_SPEC
    assert specs.GOLD_SPECS["pipeline_update_stats"] is specs.PIPELINE_UPDATE_STATS_SPEC
    assert specs.GOLD_SPECS["total_cost_daily"] is specs.TOTAL_COST_DAILY_SPEC


def test_table_names_follow_gold_dbx_compute_cluster_naming() -> None:
    for spec in (
        specs.CLUSTER_COST_DAILY_SPEC,
        specs.CLUSTER_EFFICIENCY_DAILY_SPEC,
        specs.CLUSTER_RELIABILITY_DAILY_SPEC,
        specs.CLUSTER_GOVERNANCE_SPEC,
    ):
        assert spec.target_table.startswith("gold_dbx_compute_cluster_")
    assert specs.GOLD_CLUSTER_COST_DAILY == "gold_dbx_compute_cluster_cost_daily"
    assert specs.GOLD_CLUSTER_EFFICIENCY_DAILY == "gold_dbx_compute_cluster_efficiency_daily"
    assert specs.GOLD_CLUSTER_RELIABILITY_DAILY == "gold_dbx_compute_cluster_reliability_daily"
    assert specs.GOLD_CLUSTER_GOVERNANCE == "gold_dbx_compute_cluster_governance"
    assert specs.GOLD_RECOMMENDATIONS == "gold_dbx_compute_recommendations"
    assert specs.GOLD_FORECAST_DAILY == "gold_dbx_compute_forecast_daily"


def test_recommendations_has_no_watermark_and_merges_on_recommendation_id() -> None:
    # Cf. R9 scope note : pas de fenetre incrementale (relit l'etat courant
    # complet a chaque run) ; cle de merge = recommendation_id (R8).
    assert specs.RECOMMENDATIONS_SPEC.watermark_column is None
    assert specs.RECOMMENDATIONS_SPEC.incremental_lookback_days is None
    assert specs.RECOMMENDATIONS_SPEC.merge_keys == ("recommendation_id",)


def test_forecast_daily_has_no_watermark_and_merges_on_documented_grain() -> None:
    # Cf. R9 scope note : pas de fenetre incrementale (ai_forecast relit tout
    # l'historique gold necessaire a chaque run). Grain = data-model.md §4.2
    # moins source_lz_id (retire de toutes les specs gold compute).
    assert specs.FORECAST_DAILY_SPEC.watermark_column is None
    assert specs.FORECAST_DAILY_SPEC.incremental_lookback_days is None
    # `workspace_id` fait partie de la cle de merge (object_id n'est pas
    # garanti unique cross-workspace, coherence avec CLUSTER_DAILY_MERGE_KEYS/
    # WAREHOUSE_DAILY_MERGE_KEYS de T002/T003).
    assert specs.FORECAST_DAILY_SPEC.merge_keys == (
        "cloud_provider",
        "workspace_id",
        "object_type",
        "object_id",
        "metric_name",
        "horizon_date",
    )
    assert "source_lz_id" not in specs.FORECAST_DAILY_COLUMN_COMMENTS


def test_forecast_daily_sources_job_cluster_cost_daily_and_warehouse_cost_daily() -> None:
    # Extension : job_cluster_cost_daily (grain JOB, remplace le grain CLUSTER
    # ephemere), pipeline_cost_daily (grain PIPELINE, meme logique) et
    # warehouse_cost_daily (cost_usd/dbu_quantity warehouses, jusque-la declare
    # en source mais jamais lu par le builder - cf. forecast.py) rejoignent les
    # 4 sources historiques.
    assert specs.FORECAST_DAILY_SPEC.source_tables == (
        specs.GOLD_CLUSTER_COST_DAILY,
        specs.GOLD_CLUSTER_EFFICIENCY_DAILY,
        specs.GOLD_JOB_CLUSTER_COST_DAILY,
        specs.GOLD_PIPELINE_COST_DAILY,
        specs.GOLD_WAREHOUSE_COST_DAILY,
        specs.GOLD_WAREHOUSE_QUERY_PERFORMANCE_DAILY,
    )
    assert specs.GOLD_PIPELINE_COST_DAILY in specs.FORECAST_DAILY_SPEC.source_tables


def test_daily_tables_share_the_common_cluster_grain() -> None:
    expected_grain = (
        "cloud_provider",
        "workspace_id",
        "cluster_id",
        "period_start",
    )
    assert specs.CLUSTER_COST_DAILY_SPEC.merge_keys == expected_grain
    assert specs.CLUSTER_EFFICIENCY_DAILY_SPEC.merge_keys == expected_grain
    assert specs.CLUSTER_RELIABILITY_DAILY_SPEC.merge_keys == expected_grain


def test_governance_is_a_snapshot_without_period_start() -> None:
    assert specs.CLUSTER_GOVERNANCE_SPEC.merge_keys == (
        "cloud_provider",
        "workspace_id",
        "cluster_id",
    )
    assert "period_start" not in specs.CLUSTER_GOVERNANCE_SPEC.merge_keys


def test_daily_tables_are_full_on_first_run_then_incremental_on_the_shared_window() -> None:
    for spec in (
        specs.CLUSTER_COST_DAILY_SPEC,
        specs.CLUSTER_EFFICIENCY_DAILY_SPEC,
        specs.CLUSTER_RELIABILITY_DAILY_SPEC,
    ):
        assert spec.watermark_column == "period_start"
        assert spec.initial_mode == "full"
        assert spec.incremental_lookback_days == specs.INCREMENTAL_LOOKBACK_DAYS


def test_every_gold_table_has_a_table_comment_and_documents_every_column() -> None:
    # Chaque commentaire attache (Catalog Explorer, cf. `pipelines.common.writers
    # .merge_into_table`) doit exister et couvrir TOUTES les colonnes de sortie
    # du builder correspondant : sinon un champ resterait sans description cote
    # UI Databricks.
    builder_columns = [
        (
            specs.CLUSTER_COST_DAILY_SPEC,
            {
                "cloud_provider", "workspace_id", "cluster_id", "period_start",
                "cluster_name", "cluster_type", "owner", "cost_center", "sku_group",
                "dbu_quantity", "cost_usd", "cost_usd_prev_day", "cost_delta_pct",
                "cost_rank", "is_top_cost", "_generated_at",
            },
        ),
        (
            specs.CLUSTER_EFFICIENCY_DAILY_SPEC,
            {
                "cloud_provider", "workspace_id", "cluster_id", "period_start",
                "cluster_type", "cpu_util_avg_pct", "cpu_util_p95_pct",
                "mem_util_avg_pct", "mem_util_p95_pct", "cpu_wait_avg_pct",
                "idle_pct", "uptime_hours", "active_hours", "worker_count_avg",
                "worker_count_max", "autoscale_oscillation", "driver_node_type",
                "worker_node_type", "is_zombie", "utilization_status",
                "recommended_node_type", "rightsizing_reco", "estimated_savings_usd",
                "_generated_at",
            },
        ),
        (
            specs.CLUSTER_RELIABILITY_DAILY_SPEC,
            {
                "cloud_provider", "workspace_id", "cluster_id", "period_start",
                "cluster_name", "cluster_type", "start_count", "avg_startup_seconds",
                "unexpected_termination_count", "top_termination_reason",
                "auto_termination_minutes", "has_auto_termination", "_generated_at",
            },
        ),
        (
            specs.CLUSTER_GOVERNANCE_SPEC,
            {
                "cloud_provider", "workspace_id", "cluster_id", "cluster_name",
                "cluster_type", "has_owner_tag", "has_cost_center_tag",
                "dbr_version", "dbr_is_lts_current", "node_oversized",
                "is_single_node", "recommended_action", "severity", "_generated_at",
            },
        ),
        (
            specs.JOB_CLUSTER_COST_DAILY_SPEC,
            {
                "cloud_provider", "workspace_id", "job_id", "compute_kind",
                "job_name", "period_start", "cluster_count", "dbu_quantity",
                "cost_usd", "cost_usd_prev_day", "cost_delta_pct", "cost_rank",
                "is_top_cost", "_generated_at",
            },
        ),
    ]
    for spec, expected_columns in builder_columns:
        assert spec.table_comment, f"table_comment manquant pour {spec.target_table}"
        missing = expected_columns - spec.column_comments.keys()
        assert not missing, f"{spec.target_table} : colonnes sans commentaire {missing}"
        assert all(spec.column_comments[c] for c in expected_columns)
    # Valeur figee volontairement : la fenetre doit couvrir le retard de collecte
    # curated mesure (3 a 8 jours, mode 3-4) + une marge. La baisser reintroduit
    # des jours ecrits sous-comptes puis jamais recalcules (cf. le commentaire de
    # `INCREMENTAL_LOOKBACK_DAYS`) ; ne la modifier qu'apres avoir remesure.
    assert specs.INCREMENTAL_LOOKBACK_DAYS == 10


def test_governance_has_no_watermark_and_is_always_recomputed_in_full() -> None:
    assert specs.CLUSTER_GOVERNANCE_SPEC.watermark_column is None
    assert specs.CLUSTER_GOVERNANCE_SPEC.incremental_lookback_days is None
    assert specs.CLUSTER_GOVERNANCE_SPEC.initial_mode == "full"


def test_cost_daily_sources_billing_and_clusters() -> None:
    assert specs.CLUSTER_COST_DAILY_SPEC.source_tables == (
        "curated_dbx_billing_usage",
        "curated_dbx_billing_list_prices",
        "curated_dbx_compute_clusters",
    )


def test_cluster_cost_comments_document_the_product_restriction_and_sku_group() -> None:
    # T001c : la table ne couvre plus que le cout facture COMME du compute
    # cluster. Un lecteur de Catalog Explorer doit y lire les deux consequences
    # sans relire le code : la population restreinte, et le fait que sku_group ne
    # vaut plus jamais 'serverless'.
    table_comment = specs.CLUSTER_COST_DAILY_TABLE_COMMENT
    assert "JOBS, ALL_PURPOSE, DLT" in table_comment
    assert "exclu" in table_comment
    daily_sku_group = specs.CLUSTER_COST_DAILY_COLUMN_COMMENTS["sku_group"]
    assert "classic ou photon" in daily_sku_group
    assert "serverless n'est plus produite" in daily_sku_group
    # Et le commentaire doit dire OU lire le cout serverless, sinon il ressemble
    # a une perte de donnee.
    assert "compute_kind = SERVERLESS" in daily_sku_group
    rolling_sku_group = specs.CLUSTER_COST_ROLLING_COLUMN_COMMENTS["sku_group"]
    assert "classic ou photon" in rolling_sku_group
    assert "serverless n'est plus produite" in rolling_sku_group
    # Negatif : plus aucune enumeration promettant les trois valeurs.
    assert "classic, photon ou serverless" not in daily_sku_group
    assert "classic/photon/serverless" not in rolling_sku_group


def test_efficiency_daily_sources_node_timeline_and_cost_daily_for_savings() -> None:
    assert specs.GOLD_CLUSTER_COST_DAILY in specs.CLUSTER_EFFICIENCY_DAILY_SPEC.source_tables
    assert "curated_dbx_compute_node_timeline" in specs.CLUSTER_EFFICIENCY_DAILY_SPEC.source_tables
    assert "curated_dbx_compute_node_types" in specs.CLUSTER_EFFICIENCY_DAILY_SPEC.source_tables
    # Signal d'activite (idle_pct/active_hours) : lakeflow_job_task_run_timeline remplace
    # query_history (system.query.history ne trace que les warehouses SQL, jamais
    # les clusters classiques, cf. fix documente dans T002 Notes).
    assert (
        "curated_dbx_lakeflow_job_task_run_timeline"
        in specs.CLUSTER_EFFICIENCY_DAILY_SPEC.source_tables
    )
    assert "curated_dbx_query_history" not in specs.CLUSTER_EFFICIENCY_DAILY_SPEC.source_tables


def test_reliability_daily_sources_clusters_and_access_audit() -> None:
    assert specs.CLUSTER_RELIABILITY_DAILY_SPEC.source_tables == (
        "curated_dbx_compute_clusters",
        "curated_dbx_access_audit",
    )


def test_governance_sources_clusters_and_efficiency_daily() -> None:
    assert specs.CLUSTER_GOVERNANCE_SPEC.source_tables == (
        "curated_dbx_compute_clusters",
        specs.GOLD_CLUSTER_EFFICIENCY_DAILY,
    )


def test_job_cluster_cost_daily_table_name_and_grain() -> None:
    assert specs.GOLD_JOB_CLUSTER_COST_DAILY == "gold_dbx_compute_job_cluster_cost_daily"
    # `compute_kind` DANS le grain (T001b) : un job mixte doit produire deux
    # lignes le meme jour, une par forme de compute (926 jours-job mesures en
    # dev). En simple attribut, leur cout resterait melange -- et le MERGE
    # ecraserait arbitrairement l'une des deux formes.
    assert specs.JOB_CLUSTER_COST_DAILY_SPEC.merge_keys == (
        "cloud_provider",
        "workspace_id",
        "job_id",
        "compute_kind",
        "period_start",
    )
    assert specs.JOB_CLUSTER_COST_DAILY_SPEC.merge_keys == specs.JOB_CLUSTER_COST_DAILY_MERGE_KEYS
    # cluster_id/cluster_name ne font pas partie du grain : c'est justement le
    # point (rollup par job stable, pas par cluster ephemere).
    assert "cluster_id" not in specs.JOB_CLUSTER_COST_DAILY_SPEC.merge_keys


def test_job_cluster_cost_daily_is_full_on_first_run_then_incremental() -> None:
    assert specs.JOB_CLUSTER_COST_DAILY_SPEC.watermark_column == "period_start"
    assert specs.JOB_CLUSTER_COST_DAILY_SPEC.initial_mode == "full"
    assert (
        specs.JOB_CLUSTER_COST_DAILY_SPEC.incremental_lookback_days
        == specs.INCREMENTAL_LOOKBACK_DAYS
    )


def test_job_cluster_cost_daily_sources_billing_directly_not_the_gold_cluster_table() -> None:
    # BILLING-DIRECT depuis T001b : plus de rollup de cluster_cost_daily, plus de
    # lignee `job_task_run_timeline` pour resoudre cluster_id -> job_id. Ne restent
    # que la facturation (+ ses prix) et les deux sources de NOM du job
    # (`job_run_timeline` porte `run_name`, seul nom d'un run soumis par API).
    assert specs.JOB_CLUSTER_COST_DAILY_SPEC.source_tables == (
        "curated_dbx_billing_usage",
        "curated_dbx_billing_list_prices",
        "curated_dbx_lakeflow_job_run_timeline",
        "curated_dbx_lakeflow_jobs",
    )
    # Les deux tables dont la lecture etait la CAUSE de l'angle mort serverless
    # (filtre cluster_id IS NOT NULL herite) et du plafond de couverture
    # historique (retention ~1 an de la timeline de taches).
    assert specs.GOLD_CLUSTER_COST_DAILY not in specs.JOB_CLUSTER_COST_DAILY_SPEC.source_tables
    assert (
        "curated_dbx_lakeflow_job_task_run_timeline"
        not in specs.JOB_CLUSTER_COST_DAILY_SPEC.source_tables
    )


def test_job_name_comments_document_the_submitted_run_fallback() -> None:
    # Seule doc visible dans Catalog Explorer : elle doit dire qu'un run soumis
    # (jobs/runs/submit) porte le nom du RUN, faute de definition de job -- sinon
    # un consommateur lit "nom du job" alors que la valeur n'en est pas un.
    for comments in (
        specs.JOB_CLUSTER_COST_DAILY_COLUMN_COMMENTS,
        specs.JOB_CLUSTER_COST_ROLLING_COLUMN_COMMENTS,
    ):
        assert "jobs/runs/submit" in comments["job_name"]


def test_job_cost_grain_carries_compute_kind() -> None:
    # T001b, symetrique de T008 cote pipeline : `compute_kind` est dans le GRAIN
    # des DEUX tables de cout job, pas seulement de la quotidienne. Si la fenetre
    # ne le reprenait pas, elle re-melangerait ce que le grain quotidien vient de
    # separer, et le MERGE ecraserait une forme par l'autre.
    assert specs.JOB_CLUSTER_COST_DAILY_MERGE_KEYS == (
        "cloud_provider",
        "workspace_id",
        "job_id",
        "compute_kind",
        "period_start",
    )
    assert specs.JOB_CLUSTER_COST_ROLLING_MERGE_KEYS == (
        "cloud_provider",
        "workspace_id",
        "job_id",
        "compute_kind",
        "window_days",
    )
    assert specs.JOB_CLUSTER_COST_ROLLING_SPEC.merge_keys == (
        specs.JOB_CLUSTER_COST_ROLLING_MERGE_KEYS
    )
    # Grain billing-direct : le cluster ephemere n'est ni une cle ni un type
    # expose (`cluster_count` reste une mesure, cf. ses commentaires).
    for spec in (specs.JOB_CLUSTER_COST_DAILY_SPEC, specs.JOB_CLUSTER_COST_ROLLING_SPEC):
        assert "cluster_id" not in spec.merge_keys
        assert "cluster_type" not in spec.column_comments


def test_job_cost_comments_document_compute_kind_and_the_per_kind_rank() -> None:
    # Seule doc visible dans Catalog Explorer. Trois pieges a y lire sans relire
    # le code : les deux valeurs possibles (jamais NULL), le fait que `cost_rank`
    # est calcule PAR forme de compute (deux lignes peuvent porter le rang 1), et
    # `cluster_count` a 0 -- et non NULL -- sur une ligne SERVERLESS.
    for comments in (
        specs.JOB_CLUSTER_COST_DAILY_COLUMN_COMMENTS,
        specs.JOB_CLUSTER_COST_ROLLING_COLUMN_COMMENTS,
    ):
        assert "CLASSIC" in comments["compute_kind"]
        assert "SERVERLESS" in comments["compute_kind"]
        assert "Jamais NULL" in comments["compute_kind"]
        assert "compute_kind" in comments["cost_rank"]
        assert "compute_kind" in comments["is_top_cost"]
        assert "0" in comments["cluster_count"]
        assert "SERVERLESS" in comments["cluster_count"]
    # Les avertissements "NE PAS sommer" doivent dire ce qui RESTE sommable,
    # sinon un lecteur prudent renonce a un total job parfaitement legitime.
    for table_comment in (
        specs.JOB_CLUSTER_COST_DAILY_TABLE_COMMENT,
        specs.JOB_CLUSTER_COST_ROLLING_TABLE_COMMENT,
    ):
        assert "compute_kind" in table_comment


def test_pipeline_cost_grain_carries_compute_kind() -> None:
    # T008 : `compute_kind` est dans le GRAIN des deux tables de cout, pas un
    # simple attribut. Hors du grain, les pipelines qui facturent les deux formes
    # (2 sur 2 972 en dev, fenetre 30 j) garderaient un cout melange, et le MERGE
    # ecraserait une forme par l'autre.
    assert specs.PIPELINE_COST_DAILY_SPEC.merge_keys == (
        "cloud_provider",
        "workspace_id",
        "dlt_pipeline_id",
        "compute_kind",
        "period_start",
    )
    assert specs.PIPELINE_COST_ROLLING_SPEC.merge_keys == (
        "cloud_provider",
        "workspace_id",
        "dlt_pipeline_id",
        "compute_kind",
        "window_days",
    )
    # Grain billing-direct : aucun cluster, ni dans la cle ni dans les colonnes.
    for spec in (specs.PIPELINE_COST_DAILY_SPEC, specs.PIPELINE_COST_ROLLING_SPEC):
        assert "cluster_id" not in spec.merge_keys
        assert "cluster_type" not in spec.column_comments


def test_pipeline_cost_comments_document_compute_kind_and_the_per_kind_rank() -> None:
    # Seule doc visible dans Catalog Explorer. Deux pieges a y lire sans relire le
    # code : les deux valeurs possibles (jamais NULL), et le fait que `cost_rank`
    # est calcule PAR forme de compute -- deux lignes peuvent porter le rang 1.
    for comments in (
        specs.PIPELINE_COST_DAILY_COLUMN_COMMENTS,
        specs.PIPELINE_COST_ROLLING_COLUMN_COMMENTS,
    ):
        assert "CLASSIC" in comments["compute_kind"]
        assert "SERVERLESS" in comments["compute_kind"]
        assert "Jamais NULL" in comments["compute_kind"]
        assert "compute_kind" in comments["cost_rank"]
        assert "compute_kind" in comments["is_top_cost"]
    # Les avertissements "NE PAS sommer" doivent dire ce qui RESTE sommable,
    # sinon un lecteur prudent renonce a un total DLT parfaitement legitime.
    for table_comment in (
        specs.PIPELINE_COST_DAILY_TABLE_COMMENT,
        specs.PIPELINE_COST_ROLLING_TABLE_COMMENT,
    ):
        assert "compute_kind" in table_comment


def test_pipeline_cost_comments_document_the_product_restriction() -> None:
    # T001c : `dlt_pipeline_id IS NOT NULL` ne delimite pas la population. Le
    # commentaire de table doit dire QUOI est retenu et avertir que la table ne
    # couvre pas tout ce qui porte un dlt_pipeline_id -- sinon un consommateur
    # conclut a une perte de cout.
    table_comment = specs.PIPELINE_COST_DAILY_TABLE_COMMENT
    assert "billing_origin_product = 'DLT'" in table_comment
    assert "ne couvre donc pas tout ce qui porte un dlt_pipeline_id" in table_comment
    id_comment = specs.PIPELINE_COST_DAILY_COLUMN_COMMENTS["dlt_pipeline_id"]
    assert "n'est pas reserve aux pipelines DLT" in id_comment
    assert "seules les lignes du produit DLT sont retenues" in id_comment


def test_pipeline_cost_rollups_document_exactly_their_output_columns() -> None:
    # Egalite STRICTE dans les deux sens (meme regle que les rollups
    # d'efficacite) : une cle de commentaire qui n'est pas une colonne de sortie
    # fait echouer le `ALTER TABLE ... ALTER COLUMN ... COMMENT` de
    # `merge_into_table` au runtime, et une colonne non documentee reste sans
    # description dans Catalog Explorer.
    daily_columns = {
        "cloud_provider", "workspace_id", "dlt_pipeline_id", "compute_kind",
        "pipeline_name", "period_start", "dbu_quantity", "cost_usd",
        "cost_usd_prev_day", "cost_delta_pct", "cost_rank", "is_top_cost",
        "_generated_at",
    }
    rolling_columns = {
        "cloud_provider", "workspace_id", "dlt_pipeline_id", "compute_kind",
        "window_days", "as_of_date", "window_start", "pipeline_name",
        "dbu_quantity", "cost_usd", "cost_usd_prev_window", "cost_delta_pct",
        "cost_rank", "is_top_cost", "_generated_at",
    }
    for spec, expected_columns in (
        (specs.PIPELINE_COST_DAILY_SPEC, daily_columns),
        (specs.PIPELINE_COST_ROLLING_SPEC, rolling_columns),
    ):
        assert spec.table_comment, f"table_comment manquant pour {spec.target_table}"
        assert spec.column_comments.keys() == expected_columns, (
            f"{spec.target_table} : commentaires desynchronises des colonnes de sortie "
            f"(manquantes {expected_columns - spec.column_comments.keys()}, "
            f"en trop {spec.column_comments.keys() - expected_columns})"
        )
        assert all(spec.column_comments[c] for c in expected_columns)


def test_dbr_lts_release_dates_reference_list() -> None:
    # Referentiel documente comme "a completer" (pas de table/API dediee dans
    # cet Epic) : verifie juste la presence des versions attendues, avec leur
    # date GA (la fin de support s'en deduit, cf. `DBR_LTS_SUPPORT_WINDOW_YEARS`).
    assert frozenset(
        {
            "13.3.x-lts",
            "14.3.x-lts",
            "15.4.x-lts",
            "16.4.x-lts",
            "17.3.x-lts",
            "18.x-lts",
        }
    ) == frozenset(specs.DBR_LTS_RELEASE_DATES)
    assert specs.DBR_LTS_SUPPORT_WINDOW_YEARS == 3


def test_gold_aggregation_spec_is_frozen_dataclass() -> None:
    spec = specs.GoldAggregationSpec(
        source_tables=("a",), target_table="t", merge_keys=("k",)
    )
    assert spec.watermark_column is None
    assert spec.initial_mode == "full"
    assert spec.incremental_lookback_days is None


# --- T003 : tables gold SQL Warehouses ---------------------------------------
# Verifie le grain/les cles de merge des 3 tables gold warehouses vs
# `specs/012-compute-metrics-ingestion/data-model.md` (Section "Couche GOLD —
# SQL Warehouses") : grain commun `(cloud_provider, workspace_id, warehouse_id,
# period_start)`, meme strategie de rafraichissement que les clusters (full au
# 1er run, incremental sur `INCREMENTAL_LOOKBACK_DAYS` jours ensuite). Pas de
# `source_lz_id`/`ba_name` ni de `cost_rank`/`is_top_cost` sur ces tables
# (cf. `WAREHOUSE_DAILY_MERGE_KEYS`).


def test_table_names_follow_gold_dbx_compute_warehouse_naming() -> None:
    for spec in (
        specs.WAREHOUSE_COST_DAILY_SPEC,
        specs.WAREHOUSE_UTILIZATION_DAILY_SPEC,
        specs.WAREHOUSE_QUERY_PERFORMANCE_DAILY_SPEC,
    ):
        assert spec.target_table.startswith("gold_dbx_compute_warehouse_")
    assert specs.GOLD_WAREHOUSE_COST_DAILY == "gold_dbx_compute_warehouse_cost_daily"
    assert (
        specs.GOLD_WAREHOUSE_UTILIZATION_DAILY == "gold_dbx_compute_warehouse_utilization_daily"
    )
    assert (
        specs.GOLD_WAREHOUSE_QUERY_PERFORMANCE_DAILY
        == "gold_dbx_compute_warehouse_query_performance_daily"
    )


def test_warehouse_daily_tables_share_the_common_warehouse_grain() -> None:
    expected_grain = (
        "cloud_provider",
        "workspace_id",
        "warehouse_id",
        "period_start",
    )
    assert specs.WAREHOUSE_COST_DAILY_SPEC.merge_keys == expected_grain
    assert specs.WAREHOUSE_UTILIZATION_DAILY_SPEC.merge_keys == expected_grain
    assert specs.WAREHOUSE_QUERY_PERFORMANCE_DAILY_SPEC.merge_keys == expected_grain
    assert expected_grain == specs.WAREHOUSE_DAILY_MERGE_KEYS


def test_warehouse_daily_tables_are_full_on_first_run_then_incremental() -> None:
    for spec in (
        specs.WAREHOUSE_COST_DAILY_SPEC,
        specs.WAREHOUSE_UTILIZATION_DAILY_SPEC,
        specs.WAREHOUSE_QUERY_PERFORMANCE_DAILY_SPEC,
    ):
        assert spec.watermark_column == "period_start"
        assert spec.initial_mode == "full"
        assert spec.incremental_lookback_days == specs.INCREMENTAL_LOOKBACK_DAYS


def test_warehouse_cost_daily_sources_billing_warehouses_and_query_history() -> None:
    assert specs.WAREHOUSE_COST_DAILY_SPEC.source_tables == (
        "curated_dbx_billing_usage",
        "curated_dbx_billing_list_prices",
        "curated_dbx_compute_warehouses",
        "curated_dbx_query_history",
    )


def test_warehouse_utilization_daily_sources_events_query_history_and_cost_daily() -> None:
    source_tables = specs.WAREHOUSE_UTILIZATION_DAILY_SPEC.source_tables
    assert "curated_dbx_compute_warehouse_events" in source_tables
    assert "curated_dbx_query_history" in source_tables
    assert "curated_dbx_compute_warehouses" in source_tables
    assert specs.GOLD_WAREHOUSE_COST_DAILY in source_tables


def test_warehouse_query_performance_daily_sources_query_history_and_warehouses() -> None:
    # `curated_dbx_compute_warehouses` ajoute par la spec 023 T001 : cette table
    # resout desormais `warehouse_name` au dernier etat connu du warehouse, comme
    # `warehouse_cost_daily`. La declarer ici est ce qui rend la dependance
    # visible (lineage, ordre des taches).
    assert specs.WAREHOUSE_QUERY_PERFORMANCE_DAILY_SPEC.source_tables == (
        "curated_dbx_query_history",
        "curated_dbx_compute_warehouses",
    )


def test_warehouse_name_is_an_attribute_never_a_merge_key() -> None:
    """`warehouse_name` documente sur les 4 tables, absent de toutes les cles de merge.

    Un renommage de warehouse ne doit pas creer une seconde ligne : le grain
    reste `(cloud_provider, workspace_id, warehouse_id, period_start)` pour les
    quotidiennes et `(..., window_days)` pour les fenetres glissantes.
    """
    for spec in (
        specs.WAREHOUSE_UTILIZATION_DAILY_SPEC,
        specs.WAREHOUSE_UTILIZATION_ROLLING_SPEC,
        specs.WAREHOUSE_QUERY_PERFORMANCE_DAILY_SPEC,
        specs.WAREHOUSE_QUERY_PERFORMANCE_ROLLING_SPEC,
    ):
        assert spec.column_comments.get("warehouse_name"), (
            f"{spec.target_table} : warehouse_name sans commentaire de colonne"
        )
        assert "warehouse_name" not in spec.merge_keys


def test_warehouse_type_is_an_attribute_never_a_merge_key() -> None:
    """`warehouse_type` documente sur les 2 tables d'utilisation, hors cles de merge.

    Le garder HORS du grain est ce qui rend son ajout deployable a chaud : la
    `LIMITE` de `pipelines.common.writers.merge_into_table` ne mord que sur les
    cles (la condition `ON` est resolue contre le schema COURANT de la cible, donc
    une cle inconnue fait echouer le MERGE a l'analyse, et un `DROP TABLE` devient
    le seul chemin -- vecu en dev le 2026-09-09 sur `compute_kind`). Une colonne de
    payload, elle, est ajoutee par `MERGE WITH SCHEMA EVOLUTION` sans DROP ni
    migration. Ce test echoue si quelqu'un promeut le type au rang de cle en
    croyant « affiner le grain ».
    """
    for spec in (
        specs.WAREHOUSE_UTILIZATION_DAILY_SPEC,
        specs.WAREHOUSE_UTILIZATION_ROLLING_SPEC,
    ):
        assert spec.column_comments.get("warehouse_type"), (
            f"{spec.target_table} : warehouse_type sans commentaire de colonne"
        )
        assert "warehouse_type" not in spec.merge_keys
    # Le grain des deux tables reste exactement celui d'avant l'ajout.
    assert specs.WAREHOUSE_UTILIZATION_DAILY_SPEC.merge_keys == specs.WAREHOUSE_DAILY_MERGE_KEYS
    assert specs.WAREHOUSE_UTILIZATION_ROLLING_SPEC.merge_keys == (
        "cloud_provider",
        "workspace_id",
        "warehouse_id",
        "window_days",
    )


def test_every_warehouse_gold_table_has_a_table_comment_and_documents_every_column() -> None:
    builder_columns = [
        (
            specs.WAREHOUSE_COST_DAILY_SPEC,
            {
                "cloud_provider", "workspace_id", "warehouse_id", "period_start",
                "warehouse_name", "warehouse_size", "dbu_quantity", "cost_usd",
                "cost_usd_prev_day", "cost_delta_pct", "query_count",
                "cost_per_query_usd", "top_consumer", "_generated_at",
            },
        ),
        (
            specs.WAREHOUSE_UTILIZATION_DAILY_SPEC,
            {
                "cloud_provider", "workspace_id", "warehouse_id", "period_start",
                "warehouse_name", "is_serverless", "warehouse_type",
                "running_hours", "active_query_hours", "idle_pct",
                "active_to_running_ratio", "auto_stop_minutes", "has_auto_stop",
                "scale_up_events", "scale_down_events", "avg_cluster_count",
                "max_cluster_count", "peak_concurrency", "utilization_status",
                "rightsizing_reco", "estimated_savings_usd", "_generated_at",
            },
        ),
        (
            specs.WAREHOUSE_QUERY_PERFORMANCE_DAILY_SPEC,
            {
                "cloud_provider", "workspace_id", "warehouse_id", "period_start",
                "warehouse_name",
                "query_count", "failed_count", "failure_rate_pct", "latency_p50_ms",
                "latency_p95_ms", "latency_p99_ms", "queue_time_avg_ms",
                "queue_time_p95_ms", "spill_query_count", "cache_hit_pct",
                "bytes_scanned", "rows_scanned", "top_slow_statement_id",
                "_generated_at",
            },
        ),
    ]
    for spec, expected_columns in builder_columns:
        assert spec.table_comment, f"table_comment manquant pour {spec.target_table}"
        missing = expected_columns - spec.column_comments.keys()
        assert not missing, f"{spec.target_table} : colonnes sans commentaire {missing}"
        assert all(spec.column_comments[c] for c in expected_columns)


def test_warehouse_daily_tables_have_no_cost_rank_or_landing_zone_columns() -> None:
    # Pas de source_lz_id/ba_name ni de cost_rank/is_top_cost sur ces tables
    # (cf. data-model.md "Couche GOLD — SQL Warehouses").
    for spec in (
        specs.WAREHOUSE_COST_DAILY_SPEC,
        specs.WAREHOUSE_UTILIZATION_DAILY_SPEC,
        specs.WAREHOUSE_QUERY_PERFORMANCE_DAILY_SPEC,
    ):
        assert "source_lz_id" not in spec.merge_keys
        assert "cost_rank" not in spec.column_comments
        assert "is_top_cost" not in spec.column_comments
        assert "ba_name" not in spec.column_comments


# --- T004 : tables gold efficacite par job / pipeline -------------------------
# Grain STABLE (`job_id` / `dlt_pipeline_id`) plutot que le `cluster_id`
# ephemere, cf. `specs/024-job-dlt-cluster-split/data-model.md`. Symetriques
# entre elles (job vs pipeline) ET vis-a-vis des rollups de cout du meme grain :
# ces tests verrouillent cette symetrie, une divergence de grain rendant les
# deux familles injoignables cote lecture.

_JOB_EFFICIENCY_DAILY_COLUMNS = frozenset(
    {
        "cloud_provider", "workspace_id", "job_id", "job_name", "period_start",
        "cluster_count", "cpu_util_avg_pct", "cpu_util_p95_pct",
        "mem_util_avg_pct", "mem_util_p95_pct", "cpu_wait_avg_pct",
        "cpu_util_hist", "mem_util_hist", "idle_pct", "uptime_hours",
        "active_hours", "worker_count_avg", "worker_count_max",
        "autoscale_oscillation", "driver_node_type", "worker_node_type",
        "autoscale_enabled", "autoscale_min_workers", "autoscale_max_workers",
        "configured_worker_count", "utilization_status", "recommended_node_type",
        "rightsizing_reco", "estimated_savings_usd", "_generated_at",
    }
)
# Les histogrammes ne sont PAS exposes par les tables `_rolling` (internes a la
# CTE qui recalcule les percentiles) ; elles ajoutent en revanche la fenetre
# (window_days/as_of_date/window_start) et la comparaison a la precedente.
_JOB_EFFICIENCY_ROLLING_COLUMNS = frozenset(
    (_JOB_EFFICIENCY_DAILY_COLUMNS - {"period_start", "cpu_util_hist", "mem_util_hist"})
    | {
        "window_days", "as_of_date", "window_start",
        "uptime_hours_prev_window", "idle_pct_prev_window",
    }
)
_PIPELINE_EFFICIENCY_DAILY_COLUMNS = frozenset(
    (_JOB_EFFICIENCY_DAILY_COLUMNS - {"job_id", "job_name"})
    | {"dlt_pipeline_id", "pipeline_name"}
)
_PIPELINE_EFFICIENCY_ROLLING_COLUMNS = frozenset(
    (_JOB_EFFICIENCY_ROLLING_COLUMNS - {"job_id", "job_name"})
    | {"dlt_pipeline_id", "pipeline_name"}
)


def test_efficiency_rollup_table_names_follow_the_gold_naming() -> None:
    assert specs.GOLD_JOB_EFFICIENCY_DAILY == "gold_dbx_compute_job_efficiency_daily"
    assert specs.GOLD_JOB_EFFICIENCY_ROLLING == "gold_dbx_compute_job_efficiency_rolling"
    assert specs.GOLD_PIPELINE_EFFICIENCY_DAILY == "gold_dbx_compute_pipeline_efficiency_daily"
    assert (
        specs.GOLD_PIPELINE_EFFICIENCY_ROLLING == "gold_dbx_compute_pipeline_efficiency_rolling"
    )


def test_efficiency_rollups_share_the_grain_of_the_cost_rollups() -> None:
    # Identite VOULUE : une ligne par job/pipeline et par jour (resp. par
    # fenetre) dans les deux familles, jointes telles quelles cote lecture.
    # L'identite s'arrete a `compute_kind`, DES DEUX COTES : le cout le porte dans
    # son grain (pipeline T008, job T001b), l'efficacite NON -- elle descend de
    # `node_timeline`, qui n'echantillonne que des clusters, donc ne connait que le
    # compute classique et n'a pas cette colonne. Ecart VOULU, pas une derive a
    # "realigner" : reprendre `compute_kind` ici ferait echouer le MERGE sur une
    # colonne inconnue. C'est aussi pourquoi les deux tuples job ne sont plus des
    # ALIAS de ceux du cout -- ils l'etaient, et l'ajout de `compute_kind` cote
    # cout se serait propage ici sans qu'aucun test ne le voie.
    assert specs.JOB_EFFICIENCY_DAILY_SPEC.merge_keys == (
        "cloud_provider",
        "workspace_id",
        "job_id",
        "period_start",
    )
    assert specs.JOB_EFFICIENCY_ROLLING_SPEC.merge_keys == (
        "cloud_provider",
        "workspace_id",
        "job_id",
        "window_days",
    )
    assert specs.JOB_EFFICIENCY_DAILY_SPEC.merge_keys == tuple(
        key for key in specs.JOB_CLUSTER_COST_DAILY_MERGE_KEYS if key != "compute_kind"
    )
    assert specs.JOB_EFFICIENCY_ROLLING_SPEC.merge_keys == tuple(
        key for key in specs.JOB_CLUSTER_COST_ROLLING_MERGE_KEYS if key != "compute_kind"
    )
    for spec in (
        specs.JOB_EFFICIENCY_DAILY_SPEC,
        specs.JOB_EFFICIENCY_ROLLING_SPEC,
    ):
        assert "compute_kind" not in spec.merge_keys
        assert "compute_kind" not in spec.column_comments
    assert specs.PIPELINE_EFFICIENCY_DAILY_SPEC.merge_keys == (
        "cloud_provider",
        "workspace_id",
        "dlt_pipeline_id",
        "period_start",
    )
    assert specs.PIPELINE_EFFICIENCY_ROLLING_SPEC.merge_keys == (
        "cloud_provider",
        "workspace_id",
        "dlt_pipeline_id",
        "window_days",
    )
    # L'invariant de grain survit sous cette forme : identique au cout A
    # `compute_kind` PRES, dans les deux familles. Toute autre divergence casse.
    assert specs.PIPELINE_EFFICIENCY_DAILY_SPEC.merge_keys == tuple(
        key for key in specs.PIPELINE_COST_DAILY_MERGE_KEYS if key != "compute_kind"
    )
    assert specs.PIPELINE_EFFICIENCY_ROLLING_SPEC.merge_keys == tuple(
        key for key in specs.PIPELINE_COST_ROLLING_MERGE_KEYS if key != "compute_kind"
    )
    for spec in (
        specs.PIPELINE_EFFICIENCY_DAILY_SPEC,
        specs.PIPELINE_EFFICIENCY_ROLLING_SPEC,
    ):
        assert "compute_kind" not in spec.merge_keys
        assert "compute_kind" not in spec.column_comments
    # Le cluster ephemere n'est PAS dans le grain : c'est tout l'objet du rollup.
    for spec in (
        specs.JOB_EFFICIENCY_DAILY_SPEC,
        specs.JOB_EFFICIENCY_ROLLING_SPEC,
        specs.PIPELINE_EFFICIENCY_DAILY_SPEC,
        specs.PIPELINE_EFFICIENCY_ROLLING_SPEC,
    ):
        assert "cluster_id" not in spec.merge_keys
        assert "cluster_id" not in spec.column_comments


def test_efficiency_daily_rollups_are_incremental_and_rolling_ones_are_full() -> None:
    for spec in (specs.JOB_EFFICIENCY_DAILY_SPEC, specs.PIPELINE_EFFICIENCY_DAILY_SPEC):
        assert spec.watermark_column == "period_start"
        assert spec.initial_mode == "full"
        assert spec.incremental_lookback_days == specs.INCREMENTAL_LOOKBACK_DAYS
    # Les `_rolling` sont ancrees sur MAX(period_start) de leur source : aucune
    # fenetre incrementale possible (meme regle que cluster_efficiency_rolling).
    for spec in (specs.JOB_EFFICIENCY_ROLLING_SPEC, specs.PIPELINE_EFFICIENCY_ROLLING_SPEC):
        assert spec.watermark_column is None
        assert spec.incremental_lookback_days is None
        assert spec.initial_mode == "full"


def test_efficiency_rollups_source_cluster_efficiency_daily_and_the_shared_mapping() -> None:
    # Cote job : `task_run_timeline` pour cluster_id -> job_id (le cout, passe
    # billing-direct en T001b, ne la lit plus : il tient `job_id` de la
    # facturation), `jobs` + `job_run_timeline` pour le nom -- ces deux dernieres
    # restant communes aux deux familles.
    assert specs.JOB_EFFICIENCY_DAILY_SPEC.source_tables == (
        specs.GOLD_CLUSTER_EFFICIENCY_DAILY,
        "curated_dbx_lakeflow_job_task_run_timeline",
        "curated_dbx_lakeflow_job_run_timeline",
        "curated_dbx_lakeflow_jobs",
    )
    # Cote pipeline : la resolution cluster_id -> dlt_pipeline_id vient de la
    # facturation, MEME source que pipeline_cost_daily (R7) -- cout et efficacite
    # ne peuvent donc pas rattacher un meme cluster a deux pipelines differents.
    assert specs.PIPELINE_EFFICIENCY_DAILY_SPEC.source_tables == (
        specs.GOLD_CLUSTER_EFFICIENCY_DAILY,
        "curated_dbx_billing_usage",
        "curated_dbx_lakeflow_pipelines",
    )
    # Les `_rolling` ne relisent AUCUNE table curated.
    assert specs.JOB_EFFICIENCY_ROLLING_SPEC.source_tables == (
        specs.GOLD_JOB_EFFICIENCY_DAILY,
    )
    assert specs.PIPELINE_EFFICIENCY_ROLLING_SPEC.source_tables == (
        specs.GOLD_PIPELINE_EFFICIENCY_DAILY,
    )


def test_every_efficiency_rollup_documents_exactly_its_output_columns() -> None:
    # Egalite STRICTE (et non "aucune colonne manquante") dans les deux sens :
    # une cle de commentaire qui n'est pas une colonne de sortie fait echouer le
    # `ALTER TABLE ... ALTER COLUMN ... COMMENT` de `merge_into_table` au runtime.
    builder_columns = [
        (specs.JOB_EFFICIENCY_DAILY_SPEC, _JOB_EFFICIENCY_DAILY_COLUMNS),
        (specs.JOB_EFFICIENCY_ROLLING_SPEC, _JOB_EFFICIENCY_ROLLING_COLUMNS),
        (specs.PIPELINE_EFFICIENCY_DAILY_SPEC, _PIPELINE_EFFICIENCY_DAILY_COLUMNS),
        (specs.PIPELINE_EFFICIENCY_ROLLING_SPEC, _PIPELINE_EFFICIENCY_ROLLING_COLUMNS),
    ]
    for spec, expected_columns in builder_columns:
        assert spec.table_comment, f"table_comment manquant pour {spec.target_table}"
        assert spec.column_comments.keys() == expected_columns, (
            f"{spec.target_table} : commentaires desynchronises des colonnes de sortie "
            f"(manquantes {expected_columns - spec.column_comments.keys()}, "
            f"en trop {spec.column_comments.keys() - expected_columns})"
        )
        assert all(spec.column_comments[c] for c in expected_columns)


def test_efficiency_rollups_expose_no_zombie_no_cluster_name_no_governance_column() -> None:
    # `is_zombie` serait `false` partout a ce grain (un cluster JOB/PIPELINE
    # s'arrete avec sa tache) et se lirait comme un controle qui passe.
    # `cluster_name`/`cluster_type` n'ont pas de sens au grain job/pipeline.
    for spec in (
        specs.JOB_EFFICIENCY_DAILY_SPEC,
        specs.JOB_EFFICIENCY_ROLLING_SPEC,
        specs.PIPELINE_EFFICIENCY_DAILY_SPEC,
        specs.PIPELINE_EFFICIENCY_ROLLING_SPEC,
    ):
        for absent in ("is_zombie", "cluster_name", "cluster_type", "cost_usd", "dbu_quantity"):
            assert absent not in spec.column_comments, f"{spec.target_table} : {absent}"


def test_efficiency_rollup_comments_document_the_traps() -> None:
    # Histogrammes : exposes par les `_daily` (source des percentiles du
    # `_rolling`), absents des `_rolling`.
    for spec in (specs.JOB_EFFICIENCY_DAILY_SPEC, specs.PIPELINE_EFFICIENCY_DAILY_SPEC):
        assert "sommable" in spec.column_comments["cpu_util_hist"]
        # uptime_hours peut depasser 24 h/jour (clusters en parallele) : le dire.
        assert "24 h" in spec.column_comments["uptime_hours"]
    for spec in (specs.JOB_EFFICIENCY_ROLLING_SPEC, specs.PIPELINE_EFFICIENCY_ROLLING_SPEC):
        # Fenetre precedente : NULL et jamais 0 (une comparaison absente n'est
        # pas une baisse de 100 %).
        assert "jamais 0" in spec.column_comments["uptime_hours_prev_window"]
        assert "jamais 0" in spec.column_comments["idle_pct_prev_window"]
        # Percentiles recalcules depuis les histogrammes, jamais moyennes.
        assert "recalcule" in spec.column_comments["cpu_util_p95_pct"]
    # Meme piege de nom que le rollup de cout : un run soumis n'a que run_name.
    assert "jobs/runs/submit" in specs.JOB_EFFICIENCY_DAILY_COLUMN_COMMENTS["job_name"]
    assert "jobs/runs/submit" in specs.JOB_EFFICIENCY_ROLLING_COLUMN_COMMENTS["job_name"]


def test_efficiency_rollup_table_comments_warn_about_the_population_gap() -> None:
    # Seule doc visible dans Catalog Explorer : elle doit dire que la population
    # est plus petite que celle des tables de cout (serverless = aucun cluster,
    # donc aucune ligne node_timeline) et qu'il ne faut pas sommer les heures
    # avec le grain cluster.
    for spec in (specs.JOB_EFFICIENCY_DAILY_SPEC, specs.PIPELINE_EFFICIENCY_DAILY_SPEC):
        assert "SERVERLESS" in spec.table_comment.upper()
        assert "Ne PAS sommer" in spec.table_comment


# --- T001d : tables gold depense serverless ----------------------------------


def test_serverless_cost_grain_carries_the_surface_and_the_object() -> None:
    # Le grain serverless n'est PAS celui des rollups cluster : il n'y a ni
    # `cluster_id` ni ligne dans `curated_dbx_compute_clusters`. `object_id` est
    # une cle a part entiere (`serverless_surface` seule agregerait tous les jobs
    # d'un workspace en une ligne), et `merge_into_table` fusionnant sur `<=>`
    # null-safe, une cle retiree ici ne leve pas : elle ECRASE silencieusement
    # les lignes qu'elle ne distingue plus.
    assert specs.SERVERLESS_COST_DAILY_MERGE_KEYS == (
        "cloud_provider",
        "workspace_id",
        "serverless_surface",
        "object_id",
        "period_start",
    )
    assert specs.SERVERLESS_COST_ROLLING_MERGE_KEYS == (
        "cloud_provider",
        "workspace_id",
        "serverless_surface",
        "object_id",
        "window_days",
    )
    assert specs.SERVERLESS_COST_DAILY_SPEC.merge_keys == specs.SERVERLESS_COST_DAILY_MERGE_KEYS
    assert specs.SERVERLESS_COST_ROLLING_SPEC.merge_keys == (
        specs.SERVERLESS_COST_ROLLING_MERGE_KEYS
    )
    for spec in (specs.SERVERLESS_COST_DAILY_SPEC, specs.SERVERLESS_COST_ROLLING_SPEC):
        assert "cluster_id" not in spec.merge_keys
        assert "cluster_id" not in spec.column_comments
        assert "compute_kind" not in spec.merge_keys


def test_serverless_cost_specs_document_the_two_non_nullable_keys() -> None:
    # Seule doc visible dans Catalog Explorer, et elle porte le piege le plus
    # couteux de ces deux tables : les deux cles derivees ne sont jamais NULL, et
    # `_NO_OBJECT` est une valeur technique et non un objet.
    for spec in (specs.SERVERLESS_COST_DAILY_SPEC, specs.SERVERLESS_COST_ROLLING_SPEC):
        assert "_NO_OBJECT" in spec.column_comments["object_id"]
        assert "has_object_key" in spec.column_comments["object_id"]
        assert "jamais null" in spec.column_comments["serverless_surface"].lower()
        # Anti-double-comptage : ces tables voient les MEMES lignes de facturation
        # que les rollups cluster / job / pipeline / warehouse, sous un autre axe.
        # Les 4 tables a ne pas sommer avec doivent etre NOMMEES : "ne pas sommer"
        # sans dire avec quoi ne se verifie pas cote consommateur.
        assert "double comptage" in spec.table_comment
        for sibling in ("cluster_cost_", "job_cluster_cost_", "pipeline_cost_", "warehouse_cost_"):
            assert sibling in spec.table_comment
    # Le repli du CASE n'est documente que la ou il est calcule ; la table fenetre
    # reprend la valeur sans la deriver.
    assert "OTHER" in specs.SERVERLESS_COST_DAILY_COLUMN_COMMENTS["serverless_surface"]


# --- T001e : table gold gouvernance serverless -------------------------------

SERVERLESS_GOVERNANCE_OUTPUT_COLUMNS = {
    "cloud_provider", "workspace_id", "serverless_surface", "cost_usd",
    "cost_usd_with_owner_tag", "owner_tag_coverage_pct",
    "cost_usd_with_cost_center_tag", "cost_center_tag_coverage_pct",
    "cost_usd_with_budget_policy", "budget_policy_coverage_pct",
    "cost_usd_without_identity", "identity_coverage_pct",
    "cost_usd_without_object_key", "identity_source_mix", "budget_policy_count",
    "budget_policy_inventory", "window_start", "window_end", "_generated_at",
}


def test_serverless_governance_is_a_bounded_snapshot_at_the_surface_grain() -> None:
    # Grain volontairement plus GROSSIER que celui des deux tables de cout
    # serverless : une matrice de couverture se lit par surface, une part de
    # dollars par objet-jour n'est ni sommable ni actionnable. Meme gabarit de
    # snapshot que `CLUSTER_GOVERNANCE_SPEC`.
    spec = specs.SERVERLESS_GOVERNANCE_SPEC
    assert spec.merge_keys == ("cloud_provider", "workspace_id", "serverless_surface")
    assert spec.merge_keys == specs.SERVERLESS_GOVERNANCE_MERGE_KEYS
    assert spec.watermark_column is None
    assert spec.incremental_lookback_days is None
    assert spec.initial_mode == "full"
    assert "object_id" not in spec.merge_keys
    assert "period_start" not in spec.merge_keys
    assert "period_start" not in spec.column_comments
    # Recalcul complet sur un perimetre BORNE : sans garde-fou de suppression,
    # une surface qui cesse de couter survivrait indefiniment dans la matrice
    # avec ses derniers pourcentages.
    assert spec.absent_row_delete_guard == specs.SNAPSHOT_ABSENT_ROW_DELETE_GUARD
    assert spec.resolve_absent_row_delete_predicate(window_floor=None) == (
        specs.SNAPSHOT_ABSENT_ROW_DELETE_GUARD
    )


def test_serverless_governance_sources_the_billing_lines_not_the_daily_gold_table() -> None:
    # Decision structurante, mesuree : cette table partage le perimetre EXACT de
    # `gold_dbx_compute_serverless_cost_daily`, la lire serait donc tentant. Mais
    # au grain jour-objet du daily, des lignes sans identite fusionnent avec des
    # lignes qui en portent une : les orphelins tombent a 8 605,66 $ au lieu de
    # 8 704,20 $ sur une meme fenetre de 31 jours. La cause est dans le
    # commentaire de table, sinon la prochaine refonte "simplifiera" en lisant le
    # daily et perdra la mesure.
    spec = specs.SERVERLESS_GOVERNANCE_SPEC
    assert spec.source_tables == (
        "curated_dbx_billing_usage",
        "curated_dbx_billing_list_prices",
    )
    assert specs.GOLD_SERVERLESS_COST_DAILY not in spec.source_tables
    assert not any(source.startswith("gold_") for source in spec.source_tables)
    assert "8 605,66" in spec.table_comment
    assert "8 704,20" in spec.table_comment


def test_serverless_governance_documents_exactly_its_output_columns() -> None:
    # `merge_into_table` attache un `ALTER COLUMN ... COMMENT` par entree : une
    # cle orpheline echoue au RUNTIME. Egalite stricte des deux cotes.
    assert set(specs.SERVERLESS_GOVERNANCE_COLUMN_COMMENTS) == (
        SERVERLESS_GOVERNANCE_OUTPUT_COLUMNS
    )
    assert set(specs.SERVERLESS_GOVERNANCE_MERGE_KEYS) <= SERVERLESS_GOVERNANCE_OUTPUT_COLUMNS
    assert all(specs.SERVERLESS_GOVERNANCE_COLUMN_COMMENTS.values())
    # Un numerateur en dollars par axe PLUS sa part : publier les deux moities
    # d'un axe inviterait a les sommer avec `cost_usd`, qui les contient deja.
    for mirror in (
        "cost_usd_with_identity",
        "cost_usd_without_owner_tag",
        "cost_usd_without_cost_center_tag",
        "cost_usd_without_budget_policy",
    ):
        assert mirror not in specs.SERVERLESS_GOVERNANCE_COLUMN_COMMENTS


def test_serverless_governance_publishes_no_boolean_any_tag_coverage() -> None:
    # LE piege de cette table, et il est mesure : sur azure la cle plateforme
    # `Environment` est presente sur 100,0 % de la depense. Une couverture "au
    # moins un tag" afficherait 0 % de non-tague et dirait a FinOps qu'il n'y a
    # rien a faire sur azure, alors que sa meilleure cle METIER plafonne a 60,5 %.
    # Les booleens de presence restent des intermediaires de calcul : la table ne
    # publie que des DOLLARS et des parts de dollars.
    comments = specs.SERVERLESS_GOVERNANCE_COLUMN_COMMENTS
    for absent in ("has_owner_tag", "has_cost_center_tag", "has_any_tag", "custom_tags"):
        assert absent not in comments
    warning = comments["cost_center_tag_coverage_pct"]
    assert "Environment" in warning
    assert "100,0 %" in warning
    assert "60,5 %" in warning
    # Et le taux owner tres bas doit renvoyer vers la mesure qui, elle, dit si la
    # depense a un responsable connu (97,8 %), sinon il se lit comme un constat
    # d'abandon de la depense serverless.
    assert "identity_coverage_pct" in comments["owner_tag_coverage_pct"]


def test_serverless_governance_percentages_declare_their_window_and_both_clouds() -> None:
    # Ces commentaires sont lus dans Catalog Explorer par des utilisateurs FinOps
    # qui n'ouvriront jamais le code. Un pourcentage sans fenetre y est faux par
    # construction (2,2 % sur 90 jours contre 7,22 % sur l'historique complet) et
    # une moyenne bi-cloud sans les deux clouds ne decrit aucun des deux parcs
    # (couverture policy 7,6 % aws contre 29,8 % azure).
    for column, comment in specs.SERVERLESS_GOVERNANCE_COLUMN_COMMENTS.items():
        if not column.endswith("_pct"):
            continue
        assert "2026-06-12..2026-09-09" in comment, column
        assert "aws" in comment, column
        assert "azure" in comment, column
        # Une part de dollars n'est pas definie sans dollars : le SKU
        # GENIE_FREE_USAGE facture des DBU gratuits, la surface peut couter 0 $.
        assert "0 $" in comment, column


def test_serverless_governance_promises_no_budget_policy_name() -> None:
    # `system.billing` n'expose que account_prices / attributed_usage /
    # list_prices / usage : il n'existe AUCUNE table de politiques de budget. Le
    # commentaire doit dire l'absence ET sa cause, sinon une IHM promettra un nom
    # de policy qu'aucune source ne peut fournir.
    inventory = specs.SERVERLESS_GOVERNANCE_COLUMN_COMMENTS["budget_policy_inventory"]
    assert "AUCUN NOM" in inventory
    assert "system.billing" in inventory
    for column in specs.SERVERLESS_GOVERNANCE_COLUMN_COMMENTS:
        assert "policy_name" not in column
    # Le tri du tableau depend de l'ORDRE DES CHAMPS du struct : le documenter est
    # la seule protection contre une permutation qui trierait par identifiant
    # sans rien casser.
    assert "PREMIER champ" in inventory
    # `budget_policy_count` n'est pas sommable : une meme politique couvre
    # plusieurs surfaces (69 politiques distinctes, 49 aws + 20 azure).
    assert "Ne PAS sommer" in specs.SERVERLESS_GOVERNANCE_COLUMN_COMMENTS["budget_policy_count"]


def test_serverless_governance_table_comment_carries_the_window_and_the_double_count() -> None:
    comment = specs.SERVERLESS_GOVERNANCE_TABLE_COMMENT
    assert f"{specs.GOVERNANCE_ACTIVITY_WINDOW_DAYS} derniers jours" in comment
    assert "window_start / window_end" in comment
    # Memes lignes de facturation que 5 autres tables gold, sous d'autres axes.
    # Les nommer : "ne pas sommer" sans dire avec quoi ne se verifie pas cote
    # consommateur.
    assert "double comptage" in comment
    for sibling in (
        "gold_dbx_compute_serverless_cost_daily",
        "cluster",
        "job",
        "pipeline",
        "warehouse",
    ):
        assert sibling in comment
    # ... mais la somme des surfaces d'un MEME cloud est legitime (le CASE de
    # surface partitionne les lignes) : sans cette phrase, la seule interdiction
    # laisse croire que rien n'est sommable dans cette table.
    assert "MEME cloud" in comment


# --- T001f : statistiques par EXECUTION de pipeline --------------------------

PIPELINE_UPDATE_STATS_OUTPUT_COLUMNS = {
    "cloud_provider", "update_id", "workspace_id", "pipeline_id", "compute_type",
    "result_state", "duration_sec", "update_start_time", "update_end_time",
    "request_id", "trigger_type", "update_type", "run_as_user_name",
    "performance_target", "period_count", "_generated_at",
}


def test_pipeline_update_stats_merges_on_the_globally_unique_update_id() -> None:
    # Cle de merge VOLONTAIREMENT plus courte que le grain annonce : `update_id`
    # est globalement unique (412 350 ids pour autant de triplets avec
    # workspace/pipeline, mesure dev 2026-09-10), les deux parents n'ajoutent
    # aucun pouvoir discriminant mais un mode de panne -- si le rattachement
    # d'un update changeait, un MERGE sur 4 colonnes INSERERAIT un doublon au
    # lieu de mettre a jour, cassant le grain qui est la raison d'etre de la
    # table. Ils restent donc des colonnes, documentees comme telles.
    spec = specs.PIPELINE_UPDATE_STATS_SPEC
    assert spec.merge_keys == specs.PIPELINE_UPDATE_STATS_MERGE_KEYS
    assert spec.merge_keys == ("cloud_provider", "update_id")
    assert "workspace_id" not in spec.merge_keys
    assert "pipeline_id" not in spec.merge_keys
    assert "period_start_time" not in spec.merge_keys
    assert {"workspace_id", "pipeline_id"} <= set(spec.column_comments)
    assert spec.target_table == specs.GOLD_PIPELINE_UPDATE_STATS
    assert specs.GOLD_PIPELINE_UPDATE_STATS == "gold_dbx_compute_pipeline_update_stats"


def test_pipeline_update_stats_is_incremental_on_the_end_of_the_update() -> None:
    # Watermark sur la FIN de l'update et non sur son debut : un update commence
    # avant la borne mais termine apres resterait fige dans son etat partiel.
    # Fenetre partagee avec les tables `*_daily` (retard de collecte mesure a
    # 3-8 jours), et upsert PUR : la source ne conserve qu'environ un an
    # glissant, supprimer les lignes absentes du recalcul effacerait justement
    # l'historique que cette table existe pour garder.
    spec = specs.PIPELINE_UPDATE_STATS_SPEC
    assert spec.watermark_column == "update_end_time"
    assert spec.incremental_lookback_days == specs.INCREMENTAL_LOOKBACK_DAYS
    assert spec.initial_mode == "full"
    assert spec.absent_row_delete_guard is None
    assert spec.resolve_absent_row_delete_predicate(window_floor=date(2026, 8, 31)) is None
    assert spec.resolve_absent_row_delete_predicate(window_floor=None) is None


def test_pipeline_update_stats_sources_only_the_curated_periodized_table() -> None:
    # Une seule source, curated, aucune table gold : c'est ce qui justifie
    # l'absence de `depends_on` dans le job. Et jamais `system.*` : la couche
    # curated porte `cloud_provider` (AWS natif + Azure cross-tenant).
    spec = specs.PIPELINE_UPDATE_STATS_SPEC
    assert spec.source_tables == ("curated_dbx_lakeflow_pipeline_update_timeline",)
    assert not any(source.startswith("gold_") for source in spec.source_tables)
    assert not any(source.startswith("system.") for source in spec.source_tables)


def test_pipeline_update_stats_documents_exactly_its_output_columns() -> None:
    # `merge_into_table` attache un `ALTER COLUMN ... COMMENT` par entree : une
    # cle orpheline echoue au RUNTIME, pas ici. Egalite stricte des deux cotes.
    assert set(specs.PIPELINE_UPDATE_STATS_COLUMN_COMMENTS) == (
        PIPELINE_UPDATE_STATS_OUTPUT_COLUMNS
    )
    assert set(specs.PIPELINE_UPDATE_STATS_MERGE_KEYS) <= PIPELINE_UPDATE_STATS_OUTPUT_COLUMNS
    assert all(specs.PIPELINE_UPDATE_STATS_COLUMN_COMMENTS.values())
    # Colonnes deliberement absentes (mesurees) : le cluster_id est NULL sur
    # 81,7 % des lignes, et un rang de tentative materialise deviendrait faux en
    # silence (6 requetes etalent leurs tentatives sur 10 jours ou plus).
    for absent in ("cluster_id", "attempt_number", "is_last_attempt", "refresh_selection"):
        assert absent not in specs.PIPELINE_UPDATE_STATS_COLUMN_COMMENTS


def test_pipeline_update_stats_publishes_the_retry_deduplication_in_the_schema() -> None:
    # LE piege de cette table, et il doit etre lisible dans Catalog Explorer par
    # quelqu'un qui n'ouvrira jamais le code : un update est une TENTATIVE. La
    # colonne qui porte le probleme porte donc aussi la requete qui le corrige.
    request_id = specs.PIPELINE_UPDATE_STATS_COLUMN_COMMENTS["request_id"]
    assert "347 683" in request_id
    assert "14 056" in request_id
    assert "1,49x" in request_id
    assert "row_number() OVER (PARTITION BY cloud_provider, request_id" in request_id
    assert "rn = 1" in request_id
    # Et la colonne d'ou part la faute (`result_state`) doit renvoyer vers elle.
    assert "request_id" in specs.PIPELINE_UPDATE_STATS_COLUMN_COMMENTS["result_state"]


def test_pipeline_update_stats_keeps_the_null_terminal_state_readable() -> None:
    # `result_state` NULL = update encore en cours, ce n'est pas une anomalie :
    # ne PAS replier sur 'UNKNOWN', sinon un taux d'echec ne peut plus exclure
    # ces lignes de son denominateur. La regle vit dans le commentaire de TABLE
    # (le consommateur la cherche la) et la limite de `MAX()` dans celui de la
    # colonne.
    result_state = specs.PIPELINE_UPDATE_STATS_COLUMN_COMMENTS["result_state"]
    assert "'UNKNOWN'" in specs.PIPELINE_UPDATE_STATS_TABLE_COMMENT
    assert "denominateur" in specs.PIPELINE_UPDATE_STATS_TABLE_COMMENT
    assert "ALPHABETIQUE" in result_state
    assert "par MESURE et non par contrat" in result_state


def test_pipeline_update_stats_table_comment_carries_both_windows() -> None:
    # Le meme indicateur s'inverse selon la fenetre (par update : serverless
    # 23,16 % sur l'historique complet mais classique 27,76 % sur 30 jours) :
    # publier une seule fenetre serait publier un artefact. Et la fenetre de
    # 30 jours est posee sur `update_end_time`, l'axe qu'un consommateur
    # filtrera : la meme mesure scopee sur `period_start_time` rend 27,90 %,
    # ecart assez petit pour passer inapercu et assez grand pour etre cite.
    comment = specs.PIPELINE_UPDATE_STATS_TABLE_COMMENT
    assert "2025-09-08..2026-09-10" in comment
    assert "2026-08-11..2026-09-10" in comment
    assert "23,16 %" in comment
    assert "27,76 %" in comment
    assert "update_end_time" in comment
    assert "S'INVERSE" in comment
    assert f"{specs.INCREMENTAL_LOOKBACK_DAYS} jours" in comment
    # L'entree n'est pas bornee, et la raison chiffree doit rester dans le
    # schema : sans elle, la prochaine optimisation "evidente" filtrera la
    # lecture curated et tronquera les updates a cheval.
    assert "427" in comment
    assert "curated" in comment


def test_pipeline_update_stats_figures_declare_their_measurement_date() -> None:
    # Ces commentaires sont lus dans Catalog Explorer, pas dans un rapport dont
    # on connait la date. Tout chiffre publie (part en % ou grand nombre) doit
    # donc porter la date de mesure : la source est VIVANTE (une remesure a
    # quelques minutes d'intervalle rend 412 362 updates au lieu de 412 350) et
    # ces totaux sont des instantanes, pas des invariants.
    for column, comment in specs.PIPELINE_UPDATE_STATS_COLUMN_COMMENTS.items():
        if re.search(r"\d\s\d{3}", comment) or "%" in comment:
            assert "2026-09-10" in comment, column


# --- T001h : garde-fou de suppression des lignes absentes du recalcul --------


def test_every_rolling_spec_deletes_the_rows_its_recompute_no_longer_produces() -> None:
    # Les 11 tables `*_rolling` sont des snapshots d'etat courant reecrits en
    # entier : un upsert pur y accumule les objets disparus. Ce test vaut
    # inventaire — une 12e table rolling ajoutee sans garde-fou le fait tomber.
    rolling = {key: spec for key, spec in specs.GOLD_SPECS.items() if key.endswith("_rolling")}
    assert len(rolling) == 11
    assert all(
        spec.absent_row_delete_guard == specs.SNAPSHOT_ABSENT_ROW_DELETE_GUARD
        for spec in rolling.values()
    )


def test_no_rolling_spec_carries_as_of_date_in_its_merge_keys() -> None:
    # C'est CE fait qui rend la suppression legitime sur ces tables (et non un
    # choix esthetique) : `as_of_date` n'etant pas une cle, une ligne perimee
    # n'est jamais remplacee par le recalcul, elle SURVIT telle quelle. Si
    # `as_of_date` entrait un jour dans une de ces cles, la table deviendrait une
    # serie temporelle et son garde-fou de suppression devrait etre retire.
    for key, spec in specs.GOLD_SPECS.items():
        if key.endswith("_rolling"):
            assert "as_of_date" not in spec.merge_keys, key


def test_only_two_daily_specs_delete_and_each_for_its_own_reason() -> None:
    # Deux exceptions assumees et bornees parmi les `*_daily` :
    #   - `warehouse_utilization_daily` : jours-warehouse reconstruits par
    #     sessionnisation, cf. le commentaire de la spec ;
    #   - `forecast_daily` : une PROJECTION n'est pas un fait date. Un horizon
    #     futur que le recalcul ne produit plus est perime, pas historique.
    # Les autres `*_daily` sont des faits dates : un jour ecrit reste vrai, rien
    # ne doit disparaitre.
    deleting = {
        key
        for key, spec in specs.GOLD_SPECS.items()
        if key.endswith("_daily") and spec.absent_row_delete_guard is not None
    }
    assert deleting == {"warehouse_utilization_daily", "forecast_daily"}


def test_forecast_daily_only_deletes_horizons_still_in_the_future() -> None:
    # Le garde-fou ne peut pas etre la grace volumetrique des snapshots : sur un
    # horizon de 7 jours, `_generated_at < J-7` ne toucherait presque aucune
    # ligne. Il borne donc sur l'horizon lui-meme, ce qui laisse intactes les
    # projections passees — la trace de ce qui avait ete predit.
    spec = specs.FORECAST_DAILY_SPEC
    assert spec.watermark_column is None
    assert spec.absent_row_delete_guard == "t.horizon_date >= current_date()"
    assert (
        spec.resolve_absent_row_delete_predicate(window_floor=None)
        == "t.horizon_date >= current_date()"
    )


def test_grace_delay_stays_shorter_than_the_incremental_window() -> None:
    # Invariant non evident : sur une table a watermark, une ligne n'est
    # supprimable que si elle est A LA FOIS hors grace ET encore dans la fenetre
    # recalculee. Grace >= fenetre => les deux conditions ne se rencontrent
    # jamais et l'orpheline devient immortelle, sans qu'aucun test de SQL
    # genere ne le voie.
    assert specs.SNAPSHOT_ABSENT_ROW_GRACE_DAYS < specs.INCREMENTAL_LOOKBACK_DAYS


def test_resolve_delete_predicate_returns_the_bare_guard_for_a_snapshot() -> None:
    # Sans watermark, la source est la reference complete : la borne de fenetre
    # n'a pas d'objet, et un `window_floor` fourni par erreur est ignore.
    spec = specs.WAREHOUSE_UTILIZATION_ROLLING_SPEC
    assert (
        spec.resolve_absent_row_delete_predicate(window_floor=None)
        == specs.SNAPSHOT_ABSENT_ROW_DELETE_GUARD
    )
    assert (
        spec.resolve_absent_row_delete_predicate(window_floor=date(2026, 7, 15))
        == specs.SNAPSHOT_ABSENT_ROW_DELETE_GUARD
    )


def test_resolve_delete_predicate_binds_a_watermarked_spec_to_the_window() -> None:
    predicate = specs.WAREHOUSE_UTILIZATION_DAILY_SPEC.resolve_absent_row_delete_predicate(
        window_floor=date(2026, 8, 31)
    )
    assert predicate == (
        "t.period_start >= DATE '2026-08-31' "
        "AND (t._generated_at < date_add(current_date(), "
        f"-{specs.SNAPSHOT_ABSENT_ROW_GRACE_DAYS}))"
    )


def test_resolve_delete_predicate_refuses_an_unbounded_watermarked_delete() -> None:
    # Le coeur du mecanisme : sur une table a watermark, pas de borne => pas de
    # suppression. Renvoyer le garde-fou seul supprimerait tout l'historique hors
    # fenetre, la condition `ON` du MERGE ne prunant rien (aucun
    # `partition_predicate` cote gold).
    assert (
        specs.WAREHOUSE_UTILIZATION_DAILY_SPEC.resolve_absent_row_delete_predicate(
            window_floor=None
        )
        is None
    )


def test_resolve_delete_predicate_is_none_without_a_guard() -> None:
    for spec in specs.GOLD_SPECS.values():
        if spec.absent_row_delete_guard is None:
            assert spec.resolve_absent_row_delete_predicate(window_floor=None) is None
            assert spec.resolve_absent_row_delete_predicate(window_floor=date(2026, 8, 31)) is None
