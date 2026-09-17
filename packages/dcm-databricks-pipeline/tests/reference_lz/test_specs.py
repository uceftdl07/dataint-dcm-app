"""Tests de `pipelines.reference_lz.specs` (contrat metier + registre des tables)."""

from __future__ import annotations

import pipelines.reference_lz.specs as specs


def test_dbx_workspace_specs_use_expected_source_tables_and_keys() -> None:
    assert specs.WORKSPACE_AWS_SPEC.source_table == specs.SOURCE_WORKSPACE_INVENTORY_AWS
    assert specs.WORKSPACE_AWS_SPEC.curated_table == specs.CURATED_DBX_WORKSPACE
    assert specs.WORKSPACE_AWS_SPEC.merge_keys == ("workspace_id",)
    assert specs.WORKSPACE_AWS_SPEC.select_columns == (
        "workspace_id",
        "workspace_name",
        "aws_account_id",
        "cloud",
    )

    assert specs.WORKSPACE_AZURE_SPEC.source_table == specs.SOURCE_WORKSPACE_INVENTORY_AZURE
    assert specs.WORKSPACE_AZURE_SPEC.curated_table == specs.CURATED_DBX_WORKSPACE
    assert specs.WORKSPACE_AZURE_SPEC.merge_keys == ("workspace_id",)
    assert specs.WORKSPACE_AZURE_SPEC.select_columns == (
        "workspace_id",
        "workspace_name",
        "subscription_id",
        "cloud",
    )


def test_source_catalog_with_dash_is_backtick_quoted() -> None:
    # `onedatalake-ppd-internal` contient un tiret : backticks obligatoires
    # dans l'identifiant 3-parties (research.md §2).
    assert specs.SOURCE_WORKSPACE_INVENTORY_AWS.startswith("`onedatalake-ppd-internal`.")
    assert specs.SOURCE_WORKSPACE_INVENTORY_AZURE.startswith("`onedatalake-ppd-internal`.")


def test_business_application_spec_uses_azure_only_source() -> None:
    assert specs.BA_LZ_SPEC.source_table == specs.SOURCE_BA_LZ
    assert specs.BA_LZ_SPEC.curated_table == specs.CURATED_BUSINESS_APPLICATION
    assert specs.BA_LZ_SPEC.merge_keys == ("subscription_or_account_id",)
    assert specs.BA_LZ_SPEC.select_columns == ("name", "ba_id", "lz_id", "cloud")


def test_business_application_dim_spec_projects_distinct_ba_from_same_source() -> None:
    # Meme source Azure `ref_ba_lz`, projete sur (name, ba_id), dedup par
    # `business_application_id` : catalogue distinct des BA.
    assert specs.BA_DIM_SPEC.source_table == specs.SOURCE_BA_LZ
    assert specs.BA_DIM_SPEC.curated_table == specs.CURATED_BUSINESS_APPLICATION_DIM
    assert specs.BA_DIM_SPEC.merge_keys == ("business_application_id",)
    assert specs.BA_DIM_SPEC.select_columns == ("name", "ba_id")


def test_registry_lists_all_tables_in_order() -> None:
    assert specs.TABLE_KEYS == (
        specs.TABLE_DBX_WORKSPACE,
        specs.TABLE_BUSINESS_APPLICATION,
        specs.TABLE_BUSINESS_APPLICATION_DIM,
    )
    assert set(specs.CURATED_TABLES) == set(specs.TABLE_KEYS)
    assert specs.CURATED_TABLES[specs.TABLE_DBX_WORKSPACE] == specs.CURATED_DBX_WORKSPACE
    assert (
        specs.CURATED_TABLES[specs.TABLE_BUSINESS_APPLICATION]
        == specs.CURATED_BUSINESS_APPLICATION
    )
    assert (
        specs.CURATED_TABLES[specs.TABLE_BUSINESS_APPLICATION_DIM]
        == specs.CURATED_BUSINESS_APPLICATION_DIM
    )


def test_no_watermark_full_load_semantics() -> None:
    # FR-005 : full-load, aucun watermark/partitionnement sur ces specs.
    for spec in (
        specs.WORKSPACE_AWS_SPEC,
        specs.WORKSPACE_AZURE_SPEC,
        specs.BA_LZ_SPEC,
        specs.BA_DIM_SPEC,
    ):
        assert spec.watermark_column is None
        assert spec.partition_columns == ()
        assert spec.initial_lookback_days is None
