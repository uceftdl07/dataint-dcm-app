"""Tests de `pipelines.gold_dbx_usage.specs` (contrat metier + registre)."""

from __future__ import annotations

import pipelines.gold_dbx_usage.entrypoint as entrypoint
import pipelines.gold_dbx_usage.specs as specs
from pipelines.gold_dbx_usage.sql_helpers import EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS


def test_registry_lists_all_gold_spec_tables() -> None:
    assert specs.GOLD_SPEC_KEYS == (
        "table_daily",
        "table_popularity_daily",
        "consumer_daily",
        "table_query_performance_daily",
        "table_catalog",
        "table_governance",
        "recommendations",
        "forecast_daily",
    )
    assert set(specs.GOLD_SPECS) == set(specs.GOLD_SPEC_KEYS)
    assert specs.GOLD_SPECS["table_daily"] is specs.TABLE_DAILY_SPEC
    assert specs.GOLD_SPECS["table_popularity_daily"] is specs.TABLE_POPULARITY_DAILY_SPEC
    assert specs.GOLD_SPECS["consumer_daily"] is specs.CONSUMER_DAILY_SPEC
    assert (
        specs.GOLD_SPECS["table_query_performance_daily"]
        is specs.TABLE_QUERY_PERFORMANCE_DAILY_SPEC
    )
    assert specs.GOLD_SPECS["table_catalog"] is specs.TABLE_CATALOG_SPEC
    assert specs.GOLD_SPECS["table_governance"] is specs.TABLE_GOVERNANCE_SPEC
    assert specs.GOLD_SPECS["recommendations"] is specs.RECOMMENDATIONS_SPEC
    assert specs.GOLD_SPECS["forecast_daily"] is specs.FORECAST_DAILY_SPEC


def test_table_names_follow_gold_dbx_usage_naming() -> None:
    for spec in (
        specs.TABLE_DAILY_SPEC,
        specs.TABLE_POPULARITY_DAILY_SPEC,
        specs.CONSUMER_DAILY_SPEC,
        specs.TABLE_QUERY_PERFORMANCE_DAILY_SPEC,
    ):
        assert spec.target_table.startswith("gold_dbx_usage_")


def test_table_daily_merge_keys_match_contract_grain() -> None:
    assert specs.TABLE_DAILY_MERGE_KEYS == (
        "cloud_provider",
        "catalog",
        "schema",
        "table_name",
        "consumer_id",
        "period_start",
    )


def test_table_popularity_daily_merge_keys_match_contract_grain() -> None:
    assert specs.TABLE_POPULARITY_DAILY_MERGE_KEYS == (
        "cloud_provider",
        "catalog",
        "schema",
        "table_name",
        "period_start",
    )


def test_consumer_daily_merge_keys_match_contract_grain() -> None:
    assert specs.CONSUMER_DAILY_MERGE_KEYS == ("cloud_provider", "consumer_id", "period_start")


def test_table_query_performance_daily_merge_keys_match_contract_grain() -> None:
    assert specs.TABLE_QUERY_PERFORMANCE_DAILY_MERGE_KEYS == (
        "cloud_provider",
        "catalog",
        "schema",
        "table_name",
        "period_start",
    )


def test_latency_bucket_bounds_are_strictly_increasing_and_documented() -> None:
    # Les bornes deviennent les cles du MAP `latency_bucket_counts` : deux bornes
    # egales ou desordonnees produiraient des buckets qui se recouvrent, donc une
    # somme de compteurs superieure a query_count.
    bounds = specs.LATENCY_BUCKET_UPPER_BOUNDS_MS
    assert list(bounds) == sorted(set(bounds))
    assert bounds[0] > 0
    assert specs.LATENCY_BUCKET_OVERFLOW_KEY not in {str(bound) for bound in bounds}
    assert "latency_bucket_counts" in specs.TABLE_QUERY_PERFORMANCE_DAILY_SPEC.column_comments


def test_all_daily_specs_have_incremental_watermark_on_period_start() -> None:
    for spec in (
        specs.TABLE_DAILY_SPEC,
        specs.TABLE_POPULARITY_DAILY_SPEC,
        specs.CONSUMER_DAILY_SPEC,
        specs.TABLE_QUERY_PERFORMANCE_DAILY_SPEC,
    ):
        assert spec.watermark_column == "period_start"
        assert spec.incremental_lookback_days == specs.INCREMENTAL_LOOKBACK_DAYS


def test_no_source_lz_id_or_subscription_account_id_column_comments() -> None:
    # FR-008 (non negociable) : aucune table gold usage ne porte
    # source_lz_id/subscription_or_account_id (la resolution workspace_id -> LZ
    # vit uniquement dans dim_dbx_workspace, spec 020).
    for spec in (
        specs.TABLE_DAILY_SPEC,
        specs.TABLE_POPULARITY_DAILY_SPEC,
        specs.CONSUMER_DAILY_SPEC,
        specs.TABLE_QUERY_PERFORMANCE_DAILY_SPEC,
        specs.TABLE_CATALOG_SPEC,
        specs.TABLE_GOVERNANCE_SPEC,
        specs.RECOMMENDATIONS_SPEC,
        specs.FORECAST_DAILY_SPEC,
    ):
        assert "source_lz_id" not in spec.column_comments
        assert "subscription_or_account_id" not in spec.column_comments
        assert "source_lz_id" not in spec.merge_keys
        assert "subscription_or_account_id" not in spec.merge_keys


def test_snapshot_specs_column_comments_have_no_period_start() -> None:
    # Regression : table_catalog/table_governance sont des snapshots (pas de
    # period_start) mais heritaient par erreur du commentaire `period_start`
    # via `_USAGE_DAILY_COMMON_COLUMN_COMMENTS` -- `ALTER TABLE ... ALTER
    # COLUMN period_start` echoue avec UNRESOLVED_COLUMN sur un run reel
    # (colonne absente du SELECT genere). Confirme le bug puis le fix.
    for spec in (specs.TABLE_CATALOG_SPEC, specs.TABLE_GOVERNANCE_SPEC):
        assert "period_start" not in spec.column_comments
        assert spec.watermark_column is None


def test_table_daily_source_tables_reference_t001_uc_registry() -> None:
    assert "curated_dbx_uc_tables" in specs.TABLE_DAILY_SPEC.source_tables


def test_table_catalog_merge_keys_match_contract_grain() -> None:
    assert specs.TABLE_CATALOG_MERGE_KEYS == ("cloud_provider", "catalog", "schema", "table_name")


def test_table_catalog_is_a_snapshot_without_watermark() -> None:
    assert specs.TABLE_CATALOG_SPEC.watermark_column is None
    assert specs.TABLE_CATALOG_SPEC.incremental_lookback_days is None
    assert specs.TABLE_CATALOG_SPEC.initial_mode == "full"


def test_table_catalog_reads_uc_registry_and_table_daily() -> None:
    assert specs.TABLE_CATALOG_SPEC.source_tables == (
        "curated_dbx_uc_tables",
        "curated_dbx_uc_table_tags",
        "curated_dbx_uc_table_operations",
        # Cote cible : quelle table un statement a ecrite, pour les tables que l'audit
        # ne couvre pas. Qualifie par `written_rows` cote query history, sans quoi une
        # lecture traversant une vue passerait pour une ecriture.
        "curated_dbx_access_table_lineage",
        "curated_dbx_query_history",
        specs.GOLD_TABLE_DAILY,
    )
    assert specs.TABLE_CATALOG_SPEC.target_table == specs.GOLD_TABLE_CATALOG


def test_table_catalog_column_comments_document_the_three_lifecycle_columns() -> None:
    # Les commentaires sont attaches par `ALTER TABLE ... ALTER COLUMN` a chaque
    # ecriture : une colonne exposee sans commentaire arrive nue au consommateur,
    # qui ne peut pas distinguer UNKNOWN (non prouve) de DELETED (prouve).
    comments = specs.TABLE_CATALOG_COLUMN_COMMENTS
    assert "ACTIVE" in comments["lifecycle_state"]
    assert "DELETED" in comments["lifecycle_state"]
    assert "UNKNOWN" in comments["lifecycle_state"]
    assert "deleteTable" in comments["lifecycle_state"]
    assert "jamais NULL" in comments["is_deleted"]
    assert "deleteTable" in comments["deleted_at"]


def test_table_catalog_table_comment_states_the_corroboration_rule() -> None:
    # La regle a deux signaux : sans elle, un lecteur suppose qu'une absence du
    # referentiel suffit a marquer supprimee -- le faux positif que la
    # corroboration existe justement pour ecarter (SC-002).
    comment = specs.TABLE_CATALOG_TABLE_COMMENT
    assert "curated_dbx_uc_tables" in comment
    assert "deleteTable" in comment
    assert "lifecycle_state" in comment


def test_every_purged_table_warns_in_its_contract_that_a_row_can_disappear() -> None:
    """Les 5 tables purgees le DISENT, pas seulement le registre.

    Un contrat qui promet un comportement uniquement additif alors que des lignes
    disparaissent est pire qu'un contrat muet : il fonde un raisonnement faux chez le
    consommateur (« ce compte ne peut que croitre »). Le perimetre teste est celui de
    `entrypoint.PURGED_OF_EPHEMERAL_TABLES`, pas une liste recopiee : ajouter une table a
    la purge sans amender son contrat doit faire tomber ce test.
    """
    for table in entrypoint.PURGED_OF_EPHEMERAL_TABLES:
        comment = specs.GOLD_SPECS[table].table_comment
        assert comment is not None, table
        assert "EPHEMERE" in comment, table
        assert str(EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS) in comment, table
        assert "disparait" in comment, table


def test_table_governance_merge_keys_match_contract_grain() -> None:
    assert specs.TABLE_GOVERNANCE_MERGE_KEYS == (
        "cloud_provider",
        "catalog",
        "schema",
        "table_name",
    )


def test_table_governance_is_a_snapshot_without_watermark() -> None:
    assert specs.TABLE_GOVERNANCE_SPEC.watermark_column is None
    assert specs.TABLE_GOVERNANCE_SPEC.incremental_lookback_days is None
    assert specs.TABLE_GOVERNANCE_SPEC.initial_mode == "full"


def test_table_governance_reads_table_catalog_and_popularity_daily() -> None:
    assert specs.TABLE_GOVERNANCE_SPEC.source_tables == (
        specs.GOLD_TABLE_CATALOG,
        specs.GOLD_TABLE_POPULARITY_DAILY,
    )
    assert specs.TABLE_GOVERNANCE_SPEC.target_table == specs.GOLD_TABLE_GOVERNANCE


def test_governance_thresholds_match_clarified_values() -> None:
    # Seuils clarifies (spec.md Acceptance Scenario 2) : 90 j inutilise, SLA
    # fraicheur 24h, fan-out critique >= 5.
    assert specs.UNUSED_AFTER_DAYS == 90
    assert specs.STALE_WRITE_LAG_HOURS == 24
    assert specs.CRITICAL_FANOUT_THRESHOLD == 5


def test_table_governance_column_comments_document_the_three_lifecycle_columns() -> None:
    # Colonnes recopiees du registre : leur commentaire doit dire qu'elles en
    # viennent, sinon un lecteur les croit calculees ici et cherche une regle qui
    # n'existe pas.
    comments = specs.TABLE_GOVERNANCE_COLUMN_COMMENTS
    for column in ("lifecycle_state", "is_deleted", "deleted_at"):
        assert "gold_dbx_usage_table_catalog" in comments[column]


def test_table_governance_column_comments_state_the_neutralisation_when_deleted() -> None:
    # Changement de VALEUR sans changement de schema : sans mention explicite,
    # un NULL sur ces deux colonnes se lit comme « rien a signaler » au lieu de
    # « objet inexistant, aucune action possible ».
    comments = specs.TABLE_GOVERNANCE_COLUMN_COMMENTS
    assert "is_deleted" in comments["recommended_action"]
    assert "is_deleted" in comments["severity"]


def test_recommendations_merge_key_is_the_stable_hash_column() -> None:
    assert specs.RECOMMENDATIONS_MERGE_KEYS == ("recommendation_id",)


def test_recommendations_is_a_snapshot_without_watermark() -> None:
    assert specs.RECOMMENDATIONS_SPEC.watermark_column is None
    assert specs.RECOMMENDATIONS_SPEC.incremental_lookback_days is None
    assert specs.RECOMMENDATIONS_SPEC.initial_mode == "full"


def test_recommendations_reads_governance_catalog_query_performance_and_consumer() -> None:
    assert specs.RECOMMENDATIONS_SPEC.source_tables == (
        specs.GOLD_TABLE_GOVERNANCE,
        specs.GOLD_TABLE_CATALOG,
        specs.GOLD_TABLE_POPULARITY_DAILY,
        specs.GOLD_TABLE_QUERY_PERFORMANCE_DAILY,
        specs.GOLD_CONSUMER_DAILY,
    )
    assert specs.RECOMMENDATIONS_SPEC.target_table == specs.GOLD_RECOMMENDATIONS


def test_usage_reliability_and_finops_thresholds_are_data_grounded() -> None:
    # Non clarifies dans spec.md (contrairement a UNUSED_AFTER_DAYS/
    # STALE_WRITE_LAG_HOURS/CRITICAL_FANOUT_THRESHOLD) : valeurs choisies a
    # partir de la distribution reelle des donnees dev (cf. docstring
    # recommendations.py), pas inventees.
    assert specs.USAGE_FAILURE_RATE_PCT_THRESHOLD == 5.0
    assert specs.USAGE_HIGH_COST_USD_THRESHOLD == 1.0


def test_forecast_daily_merge_key_matches_contract_grain() -> None:
    assert specs.FORECAST_DAILY_MERGE_KEYS == (
        "cloud_provider",
        "object_type",
        "object_id",
        "metric_name",
        "horizon_date",
    )


def test_forecast_daily_is_a_snapshot_without_watermark() -> None:
    assert specs.FORECAST_DAILY_SPEC.watermark_column is None
    assert specs.FORECAST_DAILY_SPEC.incremental_lookback_days is None
    assert specs.FORECAST_DAILY_SPEC.initial_mode == "full"


def test_forecast_daily_reads_table_popularity_daily_and_the_table_catalog() -> None:
    # `table_catalog` est lue pour EXCLURE les tables supprimees de l'historique
    # d'entrainement, pas pour projeter une metrique : source de filtre, mais
    # source quand meme -- la declarer ici garde le registre fidele au SQL emis.
    assert specs.FORECAST_DAILY_SPEC.source_tables == (
        specs.GOLD_TABLE_POPULARITY_DAILY,
        specs.GOLD_TABLE_CATALOG,
    )
    assert specs.FORECAST_DAILY_SPEC.target_table == specs.GOLD_FORECAST_DAILY


def test_forecast_daily_parameters_match_no_new_python_dependency_design() -> None:
    # ai_forecast : entrainement 14j, horizon 7j, intervalle 95 % -- aucune
    # valeur n'est fixee par usage_datamapping.md §4.2, memes valeurs que
    # gold_dbx_compute.specs (meme convention).
    assert specs.FORECAST_OBSERVED_LOOKBACK_DAYS == 14
    assert specs.FORECAST_HORIZON_DAYS == 7
    assert specs.FORECAST_PREDICTION_INTERVAL_WIDTH == 0.95
