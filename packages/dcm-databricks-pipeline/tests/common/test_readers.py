"""Tests de `pipelines.common.readers` (lecture native + requete Azure)."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pipelines.common.readers as readers
import pipelines.system_tables.specs as specs

# ---------------------------------------------------------------------------
# read_native_source — filtre watermark en incremental
# ---------------------------------------------------------------------------


def test_read_native_source_filters_when_lower_bound(
    fake_functions: None, fakes: SimpleNamespace
) -> None:
    src = fakes.DataFrame("aws_usage")
    spark = fakes.Spark()
    spark.read.table.return_value = src

    lower = datetime(2026, 7, 27, 0, 0, 0)
    result = readers.read_native_source(spark, specs.BILLING_USAGE_SPEC, lower)

    assert result is src
    # 2 filtres : watermark + partition pruning (BILLING_USAGE_SPEC a usage_date comme partition).
    assert len(src.filters) == 2


def test_read_native_source_no_filter_without_lower_bound(
    fake_functions: None, fakes: SimpleNamespace
) -> None:
    src = fakes.DataFrame("aws_usage")
    spark = fakes.Spark()
    spark.read.table.return_value = src

    result = readers.read_native_source(spark, specs.BILLING_USAGE_SPEC, None)

    assert result is src
    assert src.filters == []


# ---------------------------------------------------------------------------
# build_azure_query — push-down du filtre watermark
# ---------------------------------------------------------------------------


def test_build_azure_query_pushes_watermark_filter() -> None:
    lower = datetime(2026, 7, 27, 8, 30, 0)
    query = readers.build_azure_query(specs.BILLING_USAGE_SPEC, lower)

    assert query.startswith("SELECT * FROM system.billing.usage")
    assert "WHERE usage_end_time >= '2026-07-27 08:30:00'" in query


def test_build_azure_query_full_when_no_lower_bound() -> None:
    query = readers.build_azure_query(specs.BILLING_LIST_PRICES_SPEC, None)

    assert query == "SELECT * FROM system.billing.list_prices"


# ---------------------------------------------------------------------------
# select_columns / row_filter — narrow scope (ex. access.audit) sur les 2 readers
# ---------------------------------------------------------------------------


def test_read_native_source_applies_row_filter_and_select_columns(
    fake_functions: None, fakes: SimpleNamespace
) -> None:
    src = fakes.DataFrame("aws_audit")
    spark = fakes.Spark()
    spark.read.table.return_value = src

    result = readers.read_native_source(spark, specs.ACCESS_AUDIT_SPEC, None)

    assert result is src
    # 1 filtre supplementaire (row_filter, pas de watermark ici car lower_bound=None).
    assert src.filters == [("expr", specs.ACCESS_AUDIT_ROW_FILTER)]
    assert result.selected_columns == list(specs.ACCESS_AUDIT_SELECT_COLUMNS)


def test_build_azure_query_projects_columns_and_combines_filters() -> None:
    lower = datetime(2026, 7, 27, 8, 30, 0)
    query = readers.build_azure_query(specs.ACCESS_AUDIT_SPEC, lower)

    assert query.startswith(
        f"SELECT {', '.join(specs.ACCESS_AUDIT_SELECT_COLUMNS)} FROM system.access.audit"
    )
    assert "WHERE event_time >= '2026-07-27 08:30:00'" in query
    assert f"AND ({specs.ACCESS_AUDIT_ROW_FILTER})" in query


def test_build_azure_query_row_filter_only_without_lower_bound() -> None:
    query = readers.build_azure_query(specs.ACCESS_AUDIT_SPEC, None)

    assert query == (
        f"SELECT {', '.join(specs.ACCESS_AUDIT_SELECT_COLUMNS)} FROM system.access.audit "
        f"WHERE ({specs.ACCESS_AUDIT_ROW_FILTER})"
    )
