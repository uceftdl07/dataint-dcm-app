"""Tests de `pipelines.system_tables.specs` (contrat metier + registre des tables)."""

from __future__ import annotations

import json
from pathlib import Path

import pipelines.system_tables.purge_specs as purge_specs
import pipelines.system_tables.specs as specs


def test_billing_specs_use_expected_tables_and_keys() -> None:
    assert specs.BILLING_USAGE_SPEC.source_table == "system.billing.usage"
    assert specs.BILLING_USAGE_SPEC.curated_table == "curated_dbx_billing_usage"
    assert specs.BILLING_USAGE_SPEC.merge_keys == ("cloud_provider", "record_id")
    assert specs.BILLING_LIST_PRICES_SPEC.source_table == "system.billing.list_prices"
    assert specs.BILLING_LIST_PRICES_SPEC.curated_table == "curated_dbx_billing_list_prices"
    assert specs.BILLING_LIST_PRICES_SPEC.merge_keys == (
        "cloud_provider",
        "sku_name",
        "price_start_time",
    )


def test_compute_and_access_specs_use_expected_tables_and_keys() -> None:
    assert specs.COMPUTE_CLUSTERS_SPEC.source_table == "system.compute.clusters"
    assert specs.COMPUTE_CLUSTERS_SPEC.curated_table == "curated_dbx_compute_clusters"
    assert specs.COMPUTE_CLUSTERS_SPEC.merge_keys == (
        "cloud_provider",
        "account_id",
        "workspace_id",
        "cluster_id",
        "change_time",
    )
    assert specs.COMPUTE_NODE_TIMELINE_SPEC.source_table == "system.compute.node_timeline"
    assert (
        specs.COMPUTE_NODE_TIMELINE_SPEC.curated_table
        == "curated_dbx_compute_node_timeline"
    )
    assert specs.ACCESS_AUDIT_SPEC.source_table == "system.access.audit"
    assert specs.ACCESS_AUDIT_SPEC.curated_table == "curated_dbx_access_audit"
    assert specs.ACCESS_AUDIT_SPEC.merge_keys == ("cloud_provider", "event_id")


def test_billing_usage_spec_is_incremental_and_partitioned_without_backfill_bound() -> None:
    # billing.usage : backfill complet intentionnel (historique de cout), donc
    # PAS de `initial_lookback_days` (contrairement aux grosses tables d'evenements).
    assert specs.BILLING_USAGE_SPEC.watermark_column == "usage_end_time"
    assert specs.BILLING_USAGE_SPEC.partition_columns == ("usage_date",)
    assert specs.BILLING_USAGE_SPEC.initial_lookback_days is None


def test_list_prices_is_full_load() -> None:
    assert specs.BILLING_LIST_PRICES_SPEC.watermark_column is None
    assert specs.BILLING_LIST_PRICES_SPEC.partition_columns == ()


def test_compute_clusters_is_incremental() -> None:
    assert specs.COMPUTE_CLUSTERS_SPEC.watermark_column == "change_time"
    assert specs.COMPUTE_CLUSTERS_SPEC.initial_lookback_days == specs.INITIAL_BACKFILL_DAYS


def test_event_tables_bound_first_run_backfill() -> None:
    # node_timeline + access.audit : premier run borne a now - N jours pour ne pas
    # depasser le maxResultSize du warehouse Azure sur l'historique complet.
    assert specs.COMPUTE_NODE_TIMELINE_SPEC.watermark_column == "start_time"
    assert specs.COMPUTE_NODE_TIMELINE_SPEC.initial_lookback_days == specs.INITIAL_BACKFILL_DAYS
    assert specs.ACCESS_AUDIT_SPEC.watermark_column == "event_time"
    assert specs.ACCESS_AUDIT_SPEC.partition_columns == ("event_date",)
    assert specs.ACCESS_AUDIT_SPEC.initial_lookback_days == specs.INITIAL_BACKFILL_DAYS


def test_access_audit_is_narrowed_to_table_usage_tracking_columns_and_actions() -> None:
    # Le tracking d'usage table/data product ne necessite qu'un sous-ensemble des
    # ~50 colonnes source ; les cles de merge/watermark/partition doivent y figurer.
    assert specs.ACCESS_AUDIT_SPEC.select_columns == specs.ACCESS_AUDIT_SELECT_COLUMNS
    for key in specs.ACCESS_AUDIT_MERGE_KEYS:
        if key == "cloud_provider":
            continue  # ajoutee par l'enveloppe, jamais dans select_columns.
        assert key in specs.ACCESS_AUDIT_SELECT_COLUMNS
    assert specs.ACCESS_AUDIT_SPEC.watermark_column in specs.ACCESS_AUDIT_SELECT_COLUMNS
    assert specs.ACCESS_AUDIT_SPEC.partition_columns[0] in specs.ACCESS_AUDIT_SELECT_COLUMNS
    # Row filter : actions d'acces table OU cycle de vie cluster (service_name
    # restreint pour ce 2e groupe, sinon le filtre s'elargirait aux actions
    # create/start/delete/permanentDelete de TOUS les services et recreerait le
    # risque de timeout/OOM que ce filtre etroit vise a eviter).
    assert specs.ACCESS_AUDIT_SPEC.row_filter == specs.ACCESS_AUDIT_ROW_FILTER
    assert specs.ACCESS_AUDIT_ROW_FILTER == (
        "(action_name IN ('getTable', 'createTable', 'deleteTable')) OR "
        "(service_name = 'clusters' AND action_name IN "
        "('create', 'start', 'delete', 'permanentDelete', "
        "'createResult', 'startResult', 'deleteResult'))"
    )



def test_registry_lists_all_nineteen_tables_in_order() -> None:
    assert specs.SPEC_KEYS == (
        "billing_usage",
        "billing_list_prices",
        "compute_clusters",
        "compute_node_timeline",
        "access_audit",
        "access_table_lineage",
        "query_history",
        "compute_warehouses",
        "compute_warehouse_events",
        "compute_node_types",
        "lakeflow_jobs",
        "lakeflow_pipelines",
        "lakeflow_job_run_timeline",
        "lakeflow_job_task_run_timeline",
        "uc_tables",
        "uc_table_tags",
        "uc_table_operations",
        "access_workspaces_latest",
        "lakeflow_pipeline_update_timeline",
    )
    assert set(specs.SPECS) == set(specs.SPEC_KEYS)
    assert specs.SPECS["billing_usage"] is specs.BILLING_USAGE_SPEC
    assert specs.SPECS["access_audit"] is specs.ACCESS_AUDIT_SPEC
    assert specs.SPECS["query_history"] is specs.QUERY_HISTORY_SPEC
    assert specs.SPECS["compute_warehouses"] is specs.WAREHOUSES_SPEC
    assert specs.SPECS["compute_warehouse_events"] is specs.WAREHOUSE_EVENTS_SPEC
    assert specs.SPECS["compute_node_types"] is specs.NODE_TYPES_SPEC
    assert specs.SPECS["lakeflow_jobs"] is specs.LAKEFLOW_JOBS_SPEC
    assert specs.SPECS["lakeflow_pipelines"] is specs.LAKEFLOW_PIPELINES_SPEC
    assert specs.SPECS["lakeflow_job_run_timeline"] is specs.LAKEFLOW_JOB_RUN_TIMELINE_SPEC
    assert (
        specs.SPECS["lakeflow_job_task_run_timeline"]
        is specs.LAKEFLOW_JOB_TASK_RUN_TIMELINE_SPEC
    )
    assert specs.SPECS["uc_tables"] is specs.UC_TABLES_SPEC
    assert specs.SPECS["uc_table_tags"] is specs.UC_TABLE_TAGS_SPEC
    assert specs.SPECS["uc_table_operations"] is specs.UC_TABLE_OPERATIONS_SPEC
    assert specs.SPECS["access_workspaces_latest"] is specs.WORKSPACES_LATEST_SPEC
    assert (
        specs.SPECS["lakeflow_pipeline_update_timeline"]
        is specs.LAKEFLOW_PIPELINE_UPDATE_TIMELINE_SPEC
    )


def test_workspaces_latest_spec_is_full_load_referential_faithful_to_source() -> None:
    # Inventaire des workspaces (system.access.workspaces_latest) : snapshot
    # « latest » petit et stable, full load comme uc_tables/compute_node_types
    # (aucun watermark, aucune partition). `cloud_provider` est dans les
    # merge_keys (table mutualisee Azure/AWS) mais ABSENT de select_columns
    # (ajoute par l'enveloppe) ; `workspace_id` (merge key) y figure bien.
    assert specs.WORKSPACES_LATEST_SPEC.source_table == "system.access.workspaces_latest"
    assert (
        specs.WORKSPACES_LATEST_SPEC.curated_table
        == "curated_dbx_access_workspaces_latest"
    )
    assert specs.WORKSPACES_LATEST_SPEC.merge_keys == ("cloud_provider", "workspace_id")
    assert specs.WORKSPACES_LATEST_SPEC.watermark_column is None
    assert specs.WORKSPACES_LATEST_SPEC.partition_columns == ()
    assert specs.WORKSPACES_LATEST_SPEC.initial_lookback_days is None
    assert specs.WORKSPACES_LATEST_SPEC.select_columns == (
        "workspace_id",
        "workspace_name",
        "workspace_url",
        "status",
        "account_id",
    )
    assert "cloud_provider" not in specs.WORKSPACES_LATEST_SPEC.select_columns


def test_uc_tables_spec_is_full_load_referential_faithful_to_source() -> None:
    # Registre UC (table_catalog/table_schema/table_name) : full load leger,
    # comme compute_node_types/billing_list_prices (faible volumetrie).
    assert specs.UC_TABLES_SPEC.source_table == "system.information_schema.tables"
    assert specs.UC_TABLES_SPEC.curated_table == "curated_dbx_uc_tables"
    assert specs.UC_TABLES_SPEC.merge_keys == (
        "cloud_provider",
        "table_catalog",
        "table_schema",
        "table_name",
    )
    assert specs.UC_TABLES_SPEC.watermark_column is None
    assert specs.UC_TABLES_SPEC.partition_columns == ()
    assert specs.UC_TABLES_SPEC.initial_lookback_days is None
    assert specs.UC_TABLES_SPEC.select_columns is None


def test_uc_table_tags_spec_is_full_load_referential_faithful_to_source() -> None:
    assert specs.UC_TABLE_TAGS_SPEC.source_table == "system.information_schema.table_tags"
    assert specs.UC_TABLE_TAGS_SPEC.curated_table == "curated_dbx_uc_table_tags"
    assert specs.UC_TABLE_TAGS_SPEC.merge_keys == (
        "cloud_provider",
        "catalog_name",
        "schema_name",
        "table_name",
        "tag_name",
    )
    assert specs.UC_TABLE_TAGS_SPEC.watermark_column is None
    assert specs.UC_TABLE_TAGS_SPEC.partition_columns == ()
    assert specs.UC_TABLE_TAGS_SPEC.initial_lookback_days is None
    assert specs.UC_TABLE_TAGS_SPEC.select_columns is None


def test_uc_table_operations_spec_is_incremental_and_bound_first_run_backfill() -> None:
    # Meme source que ACCESS_AUDIT_SPEC (system.access.audit), meme forme de cle
    # (cloud_provider, event_id) et memes colonnes projetees, mais un row_filter
    # DISTINCT (actions d'ecriture, pas d'acces table).
    assert specs.UC_TABLE_OPERATIONS_SPEC.source_table == "system.access.audit"
    assert specs.UC_TABLE_OPERATIONS_SPEC.curated_table == "curated_dbx_uc_table_operations"
    assert specs.UC_TABLE_OPERATIONS_SPEC.merge_keys == ("cloud_provider", "event_id")
    assert specs.UC_TABLE_OPERATIONS_SPEC.watermark_column == "event_time"
    assert specs.UC_TABLE_OPERATIONS_SPEC.partition_columns == ("event_date",)
    assert specs.UC_TABLE_OPERATIONS_SPEC.initial_lookback_days == specs.INITIAL_BACKFILL_DAYS
    assert specs.UC_TABLE_OPERATIONS_SPEC.azure_fetch_batch_size == specs.AZURE_BATCH_WIDE
    assert specs.UC_TABLE_OPERATIONS_SPEC.select_columns == specs.ACCESS_AUDIT_SELECT_COLUMNS
    assert specs.UC_TABLE_OPERATIONS_SPEC.row_filter == specs.ACCESS_AUDIT_WRITE_ROW_FILTER


def test_access_audit_write_actions_is_distinct_from_table_actions() -> None:
    # P9/gate de validation : nouvelle constante dediee, ne reutilise/n'etend
    # PAS ACCESS_AUDIT_TABLE_ACTIONS (comportement de curated_dbx_access_audit
    # inchange, cf. story T001 acceptance criteria).
    #
    # Ces 3 actions sont les seules du service `unityCatalog` documentees par
    # Databricks (Diagnostic log reference) et confirmees sur donnee reelle :
    # toute autre valeur (`commit`, `writeIntoTable`, `mergeIntoTable`,
    # `updateTableMetadata`, `optimize`, `vacuumEnd`, `setTableTags`) n'existe
    # pas dans le vocabulaire `action_name` de ce service (les ecritures de
    # CONTENU Delta passent par le moteur Spark, pas par l'API control-plane
    # Unity Catalog) et ne doit jamais y etre ajoutee.
    assert specs.ACCESS_AUDIT_WRITE_ACTIONS == (
        "createTable",
        "deleteTable",
        "updateTables",
    )
    # Constante DISTINCTE (pas une extension/reutilisation de
    # ACCESS_AUDIT_TABLE_ACTIONS) : un chevauchement partiel est attendu
    # (createTable/deleteTable relevent des 2 notions), mais ce n'est PAS le
    # meme objet ni construit a partir de l'autre.
    assert specs.ACCESS_AUDIT_WRITE_ACTIONS is not specs.ACCESS_AUDIT_TABLE_ACTIONS
    assert specs.ACCESS_AUDIT_WRITE_ROW_FILTER == (
        "action_name IN ('createTable', 'deleteTable', 'updateTables')"
    )
    # ACCESS_AUDIT_SPEC (curated_dbx_access_audit existante) reste inchange.
    assert specs.ACCESS_AUDIT_SPEC.row_filter == specs.ACCESS_AUDIT_ROW_FILTER
    assert specs.ACCESS_AUDIT_SPEC.curated_table == "curated_dbx_access_audit"


def test_warehouses_spec_uses_expected_table_and_keys() -> None:
    assert specs.WAREHOUSES_SPEC.source_table == "system.compute.warehouses"
    assert specs.WAREHOUSES_SPEC.curated_table == "curated_dbx_compute_warehouses"
    # `change_time` reste dans la cle : le grain curated est la VERSION du
    # warehouse, pas le warehouse. Le retirer aplatirait l'historique dont la
    # couche gold a besoin (cf. test de resolution historique ci-dessous).
    assert specs.WAREHOUSES_SPEC.merge_keys == (
        "cloud_provider",
        "account_id",
        "workspace_id",
        "warehouse_id",
        "change_time",
    )
    assert specs.WAREHOUSES_SPEC.partition_columns == ()
    assert specs.WAREHOUSES_SPEC.azure_fetch_batch_size == specs.AZURE_BATCH_NESTED


def test_warehouses_spec_is_full_load_because_source_is_a_dimension_not_an_event_log() -> None:
    # NE PAS remettre de watermark ici, meme si la table porte une colonne
    # temporelle : `system.compute.warehouses` est une DIMENSION A EVOLUTION
    # LENTE (1 ligne par version de config, historique depuis 2023), pas un
    # journal d'evenements. Le `change_time` d'une ligne peut avoir des annees
    # et decrire pourtant l'etat courant du warehouse. Un premier run borne a
    # `now - INITIAL_BACKFILL_DAYS` ecarte DEFINITIVEMENT tout warehouse non
    # modifie dans la fenetre (le watermark n'avance que vers l'avant, aucun run
    # ulterieur ne rattrape la longue traine) : mesure en dev le 2026-09-07,
    # 293 warehouses en curated pour 1429 en source, dont 323 manquants ayant
    # TOUS leur `change_time` le plus recent anterieur au demarrage de
    # l'ingestion. `initial_lookback_days` borne les GROSSES tables
    # d'evenements ; sur celle-ci (2583 lignes AWS) il ne protege rien.
    assert specs.WAREHOUSES_SPEC.watermark_column is None
    assert specs.WAREHOUSES_SPEC.initial_lookback_days is None


def test_warehouses_spec_is_not_purge_eligible_to_preserve_historical_name_resolution() -> None:
    # Full load n'implique PAS purgeable (les 2 champs sont orthogonaux, cf.
    # docstring de `IngestionSpec.purge_eligible`). La purge ne garde que l'etat
    # courant de la source ; or le gold resout le nom du warehouse A LA DATE DU
    # JOUR AGREGE (`change_time < period_start + INTERVAL 1 DAY`, cf.
    # `gold_dbx_compute/warehouse_*_daily.py`). Purger les versions anterieures
    # casserait cette resolution historique, la ou `node_types` / `list_prices`
    # / les registres UC sont des referentiels SANS historique.
    assert specs.WAREHOUSES_SPEC.purge_eligible is False
    assert "compute_warehouses" not in purge_specs.PURGE_ENABLED_KEYS


def test_warehouse_events_spec_uses_expected_table_and_keys() -> None:
    assert specs.WAREHOUSE_EVENTS_SPEC.source_table == "system.compute.warehouse_events"
    assert (
        specs.WAREHOUSE_EVENTS_SPEC.curated_table == "curated_dbx_compute_warehouse_events"
    )
    assert specs.WAREHOUSE_EVENTS_SPEC.merge_keys == (
        "cloud_provider",
        "account_id",
        "workspace_id",
        "warehouse_id",
        "event_time",
        "event_type",
    )
    assert specs.WAREHOUSE_EVENTS_SPEC.watermark_column == "event_time"
    # Source sans colonne date native -> curated fidele source stricte, pas de
    # partitionnement invente (contrairement a usage_date/event_date qui, elles,
    # existent nativement sur billing.usage / access.audit).
    assert specs.WAREHOUSE_EVENTS_SPEC.partition_columns == ()
    assert specs.WAREHOUSE_EVENTS_SPEC.initial_lookback_days == specs.INITIAL_BACKFILL_DAYS


def test_node_types_spec_is_full_load_referential_faithful_to_source() -> None:
    # Table de reference (petite, quasi statique) : pas de watermark, pas de
    # partitionnement, pas de backfill borne (comme billing.list_prices).
    assert specs.NODE_TYPES_SPEC.source_table == "system.compute.node_types"
    assert specs.NODE_TYPES_SPEC.curated_table == "curated_dbx_compute_node_types"
    assert specs.NODE_TYPES_SPEC.merge_keys == (
        "cloud_provider",
        "account_id",
        "node_type",
    )
    assert specs.NODE_TYPES_SPEC.watermark_column is None
    assert specs.NODE_TYPES_SPEC.partition_columns == ()
    assert specs.NODE_TYPES_SPEC.initial_lookback_days is None


def test_lakeflow_jobs_spec_uses_expected_table_and_keys() -> None:
    assert specs.LAKEFLOW_JOBS_SPEC.source_table == "system.lakeflow.jobs"
    assert specs.LAKEFLOW_JOBS_SPEC.curated_table == "curated_dbx_lakeflow_jobs"
    # `change_time` reste dans la cle : le grain curated est la VERSION de la
    # definition de job, pas le job. Le retirer aplatirait l'historique que le
    # gold interroge en "as of" (cf. test de resolution historique ci-dessous).
    assert specs.LAKEFLOW_JOBS_SPEC.merge_keys == (
        "cloud_provider",
        "account_id",
        "workspace_id",
        "job_id",
        "change_time",
    )
    assert specs.LAKEFLOW_JOBS_SPEC.partition_columns == ()
    assert specs.LAKEFLOW_JOBS_SPEC.azure_fetch_batch_size == specs.AZURE_BATCH_NESTED


def test_lakeflow_jobs_spec_is_full_load_because_job_definitions_outlive_the_window() -> None:
    # NE PAS remettre de watermark ici. Meme mecanisme que WAREHOUSES_SPEC, mais
    # la mesure est propre a cette table : un watermark sur `change_time` n'ecarte
    # pas les entites "anciennes", il ecarte les entites DURABLES ET NON MODIFIEES
    # dans les `INITIAL_BACKFILL_DAYS` precedant le premier run — et une definition
    # de job vit des annees sans etre touchee. C'est pourquoi COMPUTE_CLUSTERS_SPEC
    # y echappe (un cluster de job est recree a chaque execution, son `change_time`
    # est toujours dans la fenetre) alors que celle-ci non : mesure en dev le
    # 2026-09-07, `job_name` resolu sur seulement 70,2 % des 68 918 lignes de
    # `gold_dbx_compute_job_cluster_cost_daily`, via un LEFT JOIN (les 29,8 %
    # manquants sont bien des jobs absents de curated, pas des lignes exclues).
    assert specs.LAKEFLOW_JOBS_SPEC.watermark_column is None
    assert specs.LAKEFLOW_JOBS_SPEC.initial_lookback_days is None


def test_lakeflow_jobs_spec_is_not_purge_eligible_to_preserve_as_of_job_name_resolution() -> None:
    # Full load n'implique PAS purgeable (champs orthogonaux, cf. docstring de
    # `IngestionSpec.purge_eligible`, qui reserve la purge aux MIROIRS D'ETAT
    # COURANT et l'interdit aux historiques versionnes). Justification propre a
    # cette table, verifiee et non deduite des warehouses : `gold_dbx_compute/
    # job_cluster_cost_daily.py` (CTE `jobs_as_of`) resout `job_name` avec
    # `j.change_time < period_start + INTERVAL 1 DAY` puis garde la version la plus
    # recente par ROW_NUMBER. Purger vers l'etat courant laisserait `job_name` NULL
    # sur tout jour anterieur au dernier `change_time` du job.
    # Le repli sur `job_run_timeline.run_name` NE COUVRE PAS ce cas : `run_name` est
    # renseigne a 100 % sur les runs soumis par API et a 0 % sur les runs issus
    # d'une definition de job -- exactement les lignes que cette table nomme.
    assert specs.LAKEFLOW_JOBS_SPEC.purge_eligible is False
    assert "lakeflow_jobs" not in purge_specs.PURGE_ENABLED_KEYS


def test_lakeflow_pipelines_spec_uses_expected_table_and_keys() -> None:
    assert specs.LAKEFLOW_PIPELINES_SPEC.source_table == "system.lakeflow.pipelines"
    assert specs.LAKEFLOW_PIPELINES_SPEC.curated_table == "curated_dbx_lakeflow_pipelines"
    # Meme grain que les jobs : `change_time` reste dans la cle (VERSION de la
    # definition de pipeline, pas le pipeline) pour completer l'historique sans
    # ecraser les versions deja presentes.
    assert specs.LAKEFLOW_PIPELINES_SPEC.merge_keys == (
        "cloud_provider",
        "account_id",
        "workspace_id",
        "pipeline_id",
        "change_time",
    )
    assert specs.LAKEFLOW_PIPELINES_SPEC.partition_columns == ()
    # Lot Azure NESTED : colonnes larges `tags` (MAP), `settings` (struct) et
    # `configuration` (MAP), comme LAKEFLOW_JOBS_SPEC.
    assert specs.LAKEFLOW_PIPELINES_SPEC.azure_fetch_batch_size == specs.AZURE_BATCH_NESTED


def test_lakeflow_pipelines_spec_is_full_load_like_jobs() -> None:
    # Table de definition, semantiquement identique a system.lakeflow.jobs :
    # full load, PAS de watermark. Une definition de pipeline durable vit des
    # mois sans etre modifiee ; un watermark sur `change_time` en ecarterait la
    # longue traine (meme raisonnement que LAKEFLOW_JOBS_SPEC).
    assert specs.LAKEFLOW_PIPELINES_SPEC.watermark_column is None
    assert specs.LAKEFLOW_PIPELINES_SPEC.initial_lookback_days is None
    # Pas `purge_eligible` (historique versionne, pas un miroir d'etat courant).
    assert specs.LAKEFLOW_PIPELINES_SPEC.purge_eligible is False
    assert "lakeflow_pipelines" not in purge_specs.PURGE_ENABLED_KEYS


def test_lakeflow_job_run_timeline_spec_uses_expected_table_and_keys() -> None:
    assert specs.LAKEFLOW_JOB_RUN_TIMELINE_SPEC.source_table == (
        "system.lakeflow.job_run_timeline"
    )
    assert specs.LAKEFLOW_JOB_RUN_TIMELINE_SPEC.curated_table == (
        "curated_dbx_lakeflow_job_run_timeline"
    )
    assert specs.LAKEFLOW_JOB_RUN_TIMELINE_SPEC.merge_keys == (
        "cloud_provider",
        "account_id",
        "workspace_id",
        "job_id",
        "run_id",
        "period_start_time",
    )
    assert specs.LAKEFLOW_JOB_RUN_TIMELINE_SPEC.watermark_column == "period_start_time"
    # Pas de colonne DATE native sur system.lakeflow.job_run_timeline (uniquement
    # des TIMESTAMP) : curated fidele source stricte, pas de partitionnement
    # invente (meme raison que WAREHOUSE_EVENTS_SPEC/QUERY_HISTORY_SPEC).
    assert specs.LAKEFLOW_JOB_RUN_TIMELINE_SPEC.partition_columns == ()
    assert (
        specs.LAKEFLOW_JOB_RUN_TIMELINE_SPEC.initial_lookback_days
        == specs.INITIAL_BACKFILL_DAYS
    )


def test_lakeflow_job_task_run_timeline_spec_uses_expected_table_and_keys() -> None:
    assert specs.LAKEFLOW_JOB_TASK_RUN_TIMELINE_SPEC.source_table == (
        "system.lakeflow.job_task_run_timeline"
    )
    assert specs.LAKEFLOW_JOB_TASK_RUN_TIMELINE_SPEC.curated_table == (
        "curated_dbx_lakeflow_job_task_run_timeline"
    )
    # Grain reel : plusieurs lignes par tache (une par periode d'etat/compute) ;
    # `run_id` est deja l'ID du run de TACHE sur cette table (pas du run de job,
    # cf. commentaire de `LAKEFLOW_JOB_TASK_RUN_TIMELINE_MERGE_KEYS`) ->
    # `period_start_time` doit figurer dans la cle sinon un MERGE ecraserait les
    # differentes periodes d'une meme tache. `task_key` n'est PAS necessaire :
    # `run_id` seul suffit deja a identifier une execution de tache.
    assert specs.LAKEFLOW_JOB_TASK_RUN_TIMELINE_SPEC.merge_keys == (
        "cloud_provider",
        "account_id",
        "workspace_id",
        "job_id",
        "run_id",
        "period_start_time",
    )
    assert (
        specs.LAKEFLOW_JOB_TASK_RUN_TIMELINE_SPEC.watermark_column == "period_start_time"
    )
    assert specs.LAKEFLOW_JOB_TASK_RUN_TIMELINE_SPEC.partition_columns == ()
    assert (
        specs.LAKEFLOW_JOB_TASK_RUN_TIMELINE_SPEC.initial_lookback_days
        == specs.INITIAL_BACKFILL_DAYS
    )
    # Ligne plus etroite que job_run_timeline (pas de `job_parameters` MAP) ->
    # lot Azure NARROW, comme compute.node_timeline (cf. specs.py).
    assert (
        specs.LAKEFLOW_JOB_TASK_RUN_TIMELINE_SPEC.azure_fetch_batch_size
        == specs.AZURE_BATCH_NARROW
    )
    assert specs.LAKEFLOW_JOB_TASK_RUN_TIMELINE_SPEC.select_columns is None


def test_lakeflow_pipeline_update_timeline_spec_uses_expected_table_and_keys() -> None:
    assert specs.LAKEFLOW_PIPELINE_UPDATE_TIMELINE_SPEC.source_table == (
        "system.lakeflow.pipeline_update_timeline"
    )
    assert specs.LAKEFLOW_PIPELINE_UPDATE_TIMELINE_SPEC.curated_table == (
        "curated_dbx_lakeflow_pipeline_update_timeline"
    )
    # Grain PERIODISE, comme les deux timelines de jobs : 1 ligne par tranche
    # d'etat d'un update, jusqu'a 12 pour un seul (422 167 lignes pour 412 350
    # updates, mesure dev 2026-09-10). `update_id` seul comme cle ferait donc
    # tomber 9 817 lignes dans le `dropDuplicates` de `merge_into_table`, en
    # silence : `period_start_time` est indispensable a la cle, et l'egalite
    # exacte ci-dessous est ce qui l'attrape. Ne PAS y ajouter un
    # `!= (... sans period_start_time)` pour « montrer » le mode de panne :
    # l'egalite le couvre deja, et une telle comparaison est toujours vraie
    # (mypy la signale, `comparison-overlap`), donc elle n'assure rien.
    assert specs.LAKEFLOW_PIPELINE_UPDATE_TIMELINE_SPEC.merge_keys == (
        "cloud_provider",
        "workspace_id",
        "pipeline_id",
        "update_id",
        "period_start_time",
    )
    assert (
        specs.LAKEFLOW_PIPELINE_UPDATE_TIMELINE_SPEC.watermark_column == "period_start_time"
    )
    # Aucune colonne DATE native sur la source (que des TIMESTAMP) : curated
    # fidele source stricte, pas de partitionnement invente (meme raison que les
    # deux timelines de jobs).
    assert specs.LAKEFLOW_PIPELINE_UPDATE_TIMELINE_SPEC.partition_columns == ()
    assert (
        specs.LAKEFLOW_PIPELINE_UPDATE_TIMELINE_SPEC.initial_lookback_days
        == specs.INITIAL_BACKFILL_DAYS
    )
    # Ligne porteuse de structs et de 3 ARRAY (`trigger_details`, `compute`,
    # `*_selection`) -> lot Azure NESTED, comme job_run_timeline.
    assert (
        specs.LAKEFLOW_PIPELINE_UPDATE_TIMELINE_SPEC.azure_fetch_batch_size
        == specs.AZURE_BATCH_NESTED
    )
    # Fidele source : aucune projection (les deux jumelles n'en ont pas non plus,
    # et `select_columns` ne peut de toute facon pas aplatir `compute.type` --
    # aucun alias possible cote reader AWS comme Azure). Le flatten vit en gold.
    assert specs.LAKEFLOW_PIPELINE_UPDATE_TIMELINE_SPEC.select_columns is None
    assert specs.LAKEFLOW_PIPELINE_UPDATE_TIMELINE_SPEC.row_filter is None
    # Log immuable a retention source ~1 an glissant : la curated est la memoire
    # longue, aucune purge (`purge_eligible=False` -> absent du registre de purge).
    assert specs.LAKEFLOW_PIPELINE_UPDATE_TIMELINE_SPEC.purge_eligible is False
    assert "lakeflow_pipeline_update_timeline" not in purge_specs.PURGE_ENABLED_KEYS


def test_job_inputs_match_the_registry_exactly() -> None:
    # Le garde-fou de l'entrypoint ne couvre qu'UN sens : une cle inconnue dans
    # `inputs` echoue, une cle MANQUANTE est silencieuse -- la spec existe, ses
    # tests passent, et la table n'est jamais ingeree. Ce test ferme l'autre
    # sens en verrouillant l'egalite de LISTE (ordre compris) entre le registre
    # et la liste JSON codee en dur dans le `for_each_task` du job.
    job_yaml = (
        Path(__file__).resolve().parents[2] / "resources" / "job_dcm_system_tables.yml"
    ).read_text(encoding="utf-8")
    inputs_line = next(
        line for line in job_yaml.splitlines() if line.strip().startswith("inputs:")
    )
    raw = inputs_line.split("inputs:", 1)[1].strip().strip("'")
    assert json.loads(raw) == list(specs.SPEC_KEYS)
    # Le decompte annonce dans le YAML doit suivre : une liste juste sous un
    # commentaire faux se relit mal en incident.
    assert f"les {len(specs.SPEC_KEYS)} system tables" in job_yaml
    assert f"Ingestion parallèle des {len(specs.SPEC_KEYS)} system tables" in job_yaml
