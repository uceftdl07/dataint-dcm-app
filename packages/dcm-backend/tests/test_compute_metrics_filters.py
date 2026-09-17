"""Per-column filters: allowlist, parsing, aliases and distinct values.

The tests that matter most here are the negative ones. A column filter is the one
mechanism in the compute API where a client word chooses a piece of SQL, so what has to
be proven is not only that a valid filter filters, but that an invalid one produces
**nothing** — no fragment, no silent drop, no arbitrated guess.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.services.compute_metrics_filters import (
    FILTERABLE_COLUMNS,
    ColumnFilterError,
    build_column_filter_sql,
    fetch_filter_options,
    needs_last_run,
    parse_column_filters,
)
from app.api.services.compute_metrics_warehouses import (
    fetch_warehouses_cost,
    fetch_warehouses_overview,
    fetch_warehouses_query_performance,
)
from app.config import Settings

# The inventory of contracts/compute-column-filters.md, view by view. Written out rather
# than summed so a column added to the wrong view is caught, not absorbed by the total.
_EXPECTED_COLUMN_COUNTS = {
    "clusters-overview": 6,
    "clusters-cost": 6,
    "clusters-efficiency": 16,
    "clusters-governance": 5,
    # 8 and not 7 since the Type column: the overview filters on the folded
    # ``warehouse_type`` of the utilization snapshot, not on the cost table.
    "warehouses-overview": 8,
    "warehouses-cost": 6,
    "warehouses-query-performance": 9,
    "warehouses-slow-queries": 5,
    "recommendations": 6,
    "lakeflow-jobs": 15,
    "lakeflow-job-runs": 7,
    # 025 T002 — the two serverless views.
    "serverless-objects": 15,
    "serverless-governance": 9,
}


def _settings() -> Settings:
    return Settings(
        databricks_host="https://example.cloud.databricks.com",
        databricks_warehouse_id="wh-1",
        databricks_catalog="cat",
        databricks_schema="sch",
    )


def _sql_and_params(filters: Any) -> tuple[str, list[Any]]:
    return build_column_filter_sql(filters)


# --------------------------------------------------------------------------------------
# The allowlist itself
# --------------------------------------------------------------------------------------


def test_allowlist_matches_the_declared_inventory() -> None:
    """113 filterable columns over 13 views — the figure the contract commits to.

    Not a tautology: the front declares 110 columns, and which 21 are *not* filterable
    is a decision (composite cells, free-text messages, links). A column silently
    appearing or disappearing here changes the API surface.
    """
    assert dict.fromkeys(FILTERABLE_COLUMNS) == dict.fromkeys(_EXPECTED_COLUMN_COUNTS)
    counts = {view: len(columns) for view, columns in FILTERABLE_COLUMNS.items()}
    assert counts == _EXPECTED_COLUMN_COUNTS
    assert sum(counts.values()) == 113


def test_every_spec_binds_exactly_its_placeholders() -> None:
    """No spec can smuggle a value into its own SQL: one ``?`` per bound value."""
    for view, columns in FILTERABLE_COLUMNS.items():
        for key, spec in columns.items():
            where = f"{view}.{key}"
            assert spec.key == key, where
            if spec.kind == "text":
                assert spec.sql.count("?") == spec.placeholders, where
            elif spec.kind == "numeric":
                assert spec.sql.count("?") == 1, where
                assert spec.options, f"{where} offers no threshold"
            elif spec.choices:
                # A derived enum binds nothing: the value selects a predicate.
                for choice in spec.choices:
                    assert "?" not in choice.sql, where
            else:
                assert spec.sql.count("?") == 1, where
            for _value, override_sql in spec.overrides:
                assert "?" not in override_sql, where


def test_same_key_on_two_views_can_carry_different_sql() -> None:
    """Why the allowlist is indexed by (view, column) and not by column alone.

    ``cost`` is a joined alias on the overview and a bare column on the cost tab. A
    global index would resolve it to one of the two and name a table the other query
    does not expose.
    """
    overview = FILTERABLE_COLUMNS["clusters-overview"]["cost"]
    cost_tab = FILTERABLE_COLUMNS["clusters-cost"]["cost"]
    assert overview.sql == "c.cost_usd >= ?"
    assert cost_tab.sql == "c.cost_usd >= ?"
    # Warehouses do differ, and that is the point.
    assert FILTERABLE_COLUMNS["warehouses-overview"]["cost"].sql == "c.cost_usd >= ?"
    assert FILTERABLE_COLUMNS["warehouses-cost"]["cost"].sql == "cost_usd >= ?"
    assert (
        FILTERABLE_COLUMNS["warehouses-overview"]["failure"].sql
        == "COALESCE(p.failure_rate_pct, 0) >= ?"
    )
    # Single table, no outer join: no COALESCE, exactly as the legacy block had it.
    assert (
        FILTERABLE_COLUMNS["warehouses-query-performance"]["failure"].sql
        == "failure_rate_pct >= ?"
    )


# --------------------------------------------------------------------------------------
# Parsing — the refusals
# --------------------------------------------------------------------------------------


def test_unknown_column_lists_the_accepted_keys() -> None:
    with pytest.raises(ColumnFilterError) as excinfo:
        parse_column_filters("warehouses-cost", ["nope:1"])
    detail = str(excinfo.value)
    assert "nope" in detail
    # A 422 that does not say what *is* accepted forces the caller to guess.
    for key in FILTERABLE_COLUMNS["warehouses-cost"]:
        assert key in detail


def test_unknown_view_is_refused() -> None:
    with pytest.raises(ColumnFilterError) as excinfo:
        parse_column_filters("warehouses-unknown", ["size:medium"])
    assert "warehouses-cost" in str(excinfo.value)


def test_same_column_twice_is_refused() -> None:
    """Two values for one column is a request the API cannot answer unambiguously."""
    with pytest.raises(ColumnFilterError) as excinfo:
        parse_column_filters("warehouses-cost", ["size:medium", "size:large"])
    assert "twice" in str(excinfo.value).lower()


def test_malformed_pair_without_separator_is_refused() -> None:
    with pytest.raises(ColumnFilterError):
        parse_column_filters("warehouses-cost", ["size"])


def test_empty_value_is_no_filter() -> None:
    """An emptied combo sends ``key:`` — that clears the filter, it does not match ''."""
    assert parse_column_filters("warehouses-cost", ["size:"]) == []
    assert parse_column_filters("warehouses-cost", ["size:   "]) == []
    assert parse_column_filters("warehouses-cost", ["", "  "]) == []
    assert parse_column_filters("warehouses-cost", None) == []
    # Emptying it twice is still emptying it: no duplicate-key refusal.
    assert parse_column_filters("warehouses-cost", ["size:", "size:"]) == []


def test_value_keeps_every_colon_past_the_first() -> None:
    """Split on the first ``:`` only — a job or warehouse name may contain one."""
    filters = parse_column_filters("warehouses-cost", ["warehouse:etl:prod:eu"])
    assert filters[0].params == ("%etl:prod:eu%", "%etl:prod:eu%")


def test_numeric_column_refuses_a_non_number() -> None:
    with pytest.raises(ColumnFilterError):
        parse_column_filters("warehouses-cost", ["cost:cheap"])


def test_derived_enum_refuses_an_unlisted_value() -> None:
    with pytest.raises(ColumnFilterError) as excinfo:
        parse_column_filters("warehouses-query-performance", ["spill:maybe"])
    assert "with" in str(excinfo.value)


def test_the_warehouse_type_filter_passes_any_sku_databricks_declares() -> None:
    """``warehouse_type`` is Databricks' vocabulary, so this filter must not close it.

    The predicate targets the folded ``sw.warehouse_type``, which is what the Type cell
    shows; filtering the raw gold column instead would select rows the page does not
    display that way. And ``case="upper"`` is what makes ``type:pro`` a legitimate spelling
    of a value gold stores uppercase.

    ``REAL_TIME`` is the reason there is no ``allowed`` here: it exists in curated dev
    (one warehouse, measured 2026-09-11) and Databricks can add a fifth SKU whenever it
    likes. Since the option list is read from the data, an allowlist would let the dropdown
    offer a value the parser then rejects — this test pins the value **not** in the trio
    precisely so nobody re-closes the set.
    """
    for requested, bound in (("pro", "PRO"), ("real_time", "REAL_TIME")):
        filters = parse_column_filters("warehouses-overview", [f"type:{requested}"])
        sql, params = _sql_and_params(filters)
        assert sql == " AND UPPER(sw.warehouse_type) = ?", requested
        assert params == [bound], requested


def test_injection_in_the_key_or_the_value_reaches_no_sql() -> None:
    """The two halves are defended differently, so both are tested.

    The key is allowlisted — an unknown one never resolves to SQL. The value is always
    bound — it can only ever be data.
    """
    with pytest.raises(ColumnFilterError):
        parse_column_filters("warehouses-cost", ["cost_usd = 1 OR 1=1:x"])

    payload = "medium' OR 1=1 --"
    filters = parse_column_filters("warehouses-cost", [f"size:{payload}"])
    sql, params = _sql_and_params(filters)
    assert sql == " AND LOWER(warehouse_size) = ?"
    assert params == [payload.lower()]
    assert "OR 1=1" not in sql


def test_build_returns_nothing_when_no_filter_applies() -> None:
    assert build_column_filter_sql([]) == ("", [])


def test_predicates_are_emitted_in_column_order() -> None:
    """Order is the view's, not the request's — the SQL text must not depend on typing.

    Two users setting the same two filters in a different order share a query plan and
    a cache entry.
    """
    forward = parse_column_filters("warehouses-cost", ["size:medium", "cost:10"])
    backward = parse_column_filters("warehouses-cost", ["cost:10", "size:medium"])
    assert _sql_and_params(forward) == _sql_and_params(backward)
    assert _sql_and_params(forward)[0] == (
        " AND LOWER(warehouse_size) = ? AND cost_usd >= ?"
    )


# --------------------------------------------------------------------------------------
# Parsing — the legacy aliases
# --------------------------------------------------------------------------------------


def test_legacy_parameter_and_column_filter_agree_on_one_predicate() -> None:
    """The same filter, asked the old way or the new way, is the same SQL."""
    legacy = parse_column_filters("warehouses-cost", None, warehouse_size="MEDIUM")
    column = parse_column_filters("warehouses-cost", ["size:MEDIUM"])
    assert _sql_and_params(legacy) == _sql_and_params(column)
    assert _sql_and_params(legacy) == (" AND LOWER(warehouse_size) = ?", ["medium"])


def test_both_at_once_with_the_same_value_is_idempotent() -> None:
    both = parse_column_filters(
        "warehouses-cost", ["size:medium"], warehouse_size="Medium"
    )
    assert _sql_and_params(both) == (" AND LOWER(warehouse_size) = ?", ["medium"])


def test_contradicting_legacy_parameter_is_refused() -> None:
    """Answering an empty page here would look like "no such warehouse"."""
    with pytest.raises(ColumnFilterError) as excinfo:
        parse_column_filters("warehouses-cost", ["size:large"], warehouse_size="medium")
    detail = str(excinfo.value)
    assert "warehouse_size" in detail
    assert "size:large" in detail


def test_boolean_legacy_parameter_maps_to_its_choice() -> None:
    """``has_spill=True`` means "with spill"; ``False`` has always meant "no filter"."""
    on = parse_column_filters("warehouses-query-performance", None, has_spill=True)
    assert _sql_and_params(on) == (" AND spill_query_count > 0", [])
    off = parse_column_filters("warehouses-query-performance", None, has_spill=False)
    assert off == []
    # So ``has_spill=False`` cannot contradict the column filter — it asks nothing.
    without = parse_column_filters(
        "warehouses-query-performance", ["spill:without"], has_spill=False
    )
    assert _sql_and_params(without) == (
        " AND COALESCE(spill_query_count, 0) = 0",
        [],
    )
    with pytest.raises(ColumnFilterError):
        parse_column_filters(
            "warehouses-query-performance", ["spill:without"], has_spill=True
        )


def test_list_valued_legacy_parameter_keeps_its_own_in_clause() -> None:
    """``status=[a,b]`` stays an ``IN (…)``; the column filter only checks agreement.

    Folding a two-value list into a mono-value predicate would silently narrow a
    filter the caller already sent.
    """
    filters = parse_column_filters(
        "lakeflow-jobs", ["status:success"], status=["SUCCESS", "FAILED"]
    )
    # Nothing emitted: the service's own IN clause covers it.
    assert _sql_and_params(filters) == ("", [])
    with pytest.raises(ColumnFilterError) as excinfo:
        parse_column_filters("lakeflow-jobs", ["status:cancelled"], status=["SUCCESS"])
    assert "status" in str(excinfo.value)


def test_list_parameter_is_never_folded_whatever_its_length() -> None:
    """A one-element list is not folded either — the service's ``IN (?)`` still runs.

    Emitting ``LOWER(status) = ?`` here on top of it would duplicate the predicate and
    make the legacy SQL depend on how many values the list happens to hold.
    """
    assert parse_column_filters("lakeflow-job-runs", None, status=["SUCCESS"]) == []
    assert parse_column_filters("lakeflow-jobs", None, trigger_type=["CRON"]) == []
    # Absent or emptied, the parameter asks nothing and the column filter applies alone.
    alone = parse_column_filters("lakeflow-job-runs", ["status:SUCCESS"], status=[])
    assert _sql_and_params(alone) == (" AND LOWER(status) = ?", ["success"])


def test_utilization_status_zombie_keeps_its_flag_predicate() -> None:
    """ZOMBIE is a flag on the efficiency table, not a ``utilization_status`` value."""
    zombie = parse_column_filters("clusters-efficiency", ["status:ZOMBIE"])
    assert _sql_and_params(zombie) == (" AND e.is_zombie = true", [])
    idle = parse_column_filters("clusters-efficiency", ["status:idle"])
    assert _sql_and_params(idle) == (" AND UPPER(e.utilization_status) = ?", ["IDLE"])
    # The overview has no zombie flag in scope, so there the status is just a status.
    overview = parse_column_filters("clusters-overview", ["utilization:ZOMBIE"])
    assert _sql_and_params(overview) == (
        " AND UPPER(e.utilization_status) = ?",
        ["ZOMBIE"],
    )


def test_last_run_columns_declare_that_they_need_the_last_run_cte() -> None:
    """Those columns are ``CAST(NULL AS …)`` literals unless the CTE is built.

    Without this flag a filter on ``status`` would compare against NULL and return an
    empty page — a wrong answer, not an error.
    """
    assert needs_last_run(parse_column_filters("lakeflow-jobs", ["status:success"]))
    assert needs_last_run(parse_column_filters("lakeflow-jobs", ["trigger:CRON"]))
    assert needs_last_run(parse_column_filters("lakeflow-jobs", ["last_duration:60"]))
    assert not needs_last_run(parse_column_filters("lakeflow-jobs", ["runs:10"]))


# --------------------------------------------------------------------------------------
# Wiring into the list services
# --------------------------------------------------------------------------------------


def _list_db() -> AsyncMock:
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(return_value=[])
    return db


@pytest.mark.asyncio
async def test_service_emits_the_column_filter_predicate() -> None:
    db = _list_db()

    await fetch_warehouses_cost(
        db, _settings(), allowed_lz_ids=None, column_filter=["cost_per_query:0.5"]
    )

    sql = db.fetchall.await_args.args[0]
    params = db.fetchall.await_args.args[1:]
    assert "cost_per_query_usd >= ?" in sql
    assert 0.5 in params


@pytest.mark.asyncio
async def test_legacy_and_column_filter_produce_byte_identical_sql() -> None:
    """The alias is a second spelling of one filter, not a second code path."""
    legacy_db = _list_db()
    await fetch_warehouses_cost(
        legacy_db, _settings(), allowed_lz_ids=None, warehouse_size="MEDIUM"
    )
    column_db = _list_db()
    await fetch_warehouses_cost(
        column_db, _settings(), allowed_lz_ids=None, column_filter=["size:MEDIUM"]
    )

    assert legacy_db.fetchall.await_args.args == column_db.fetchall.await_args.args


@pytest.mark.asyncio
async def test_service_rejects_a_bad_filter_instead_of_soft_failing() -> None:
    """The list services swallow every exception into an empty page — on purpose.

    So the filter has to be parsed *before* that guard: an unknown column must reach
    the caller as a 422, not as a plausible-looking empty table.
    """
    db = _list_db()
    with pytest.raises(ColumnFilterError):
        await fetch_warehouses_overview(
            db, _settings(), allowed_lz_ids=None, column_filter=["ohno:1"]
        )
    db.fetchall.assert_not_awaited()


@pytest.mark.asyncio
async def test_query_performance_takes_filters_on_three_kinds_at_once() -> None:
    db = _list_db()

    await fetch_warehouses_query_performance(
        db,
        _settings(),
        allowed_lz_ids=None,
        column_filter=["warehouse:etl", "p95:5000", "spill:with"],
    )

    sql = db.fetchall.await_args.args[0]
    params = db.fetchall.await_args.args[1:]
    assert "(LOWER(warehouse_name) LIKE ? OR LOWER(warehouse_id) LIKE ?)" in sql
    assert "latency_p95_ms >= ?" in sql
    assert "spill_query_count > 0" in sql
    assert "%etl%" in params
    assert 5000.0 in params


# --------------------------------------------------------------------------------------
# Distinct values
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_options_applies_no_column_filter() -> None:
    """The options describe the perimeter, not the current selection.

    Intersecting them with the active filters would empty every other column's list as
    soon as one filter is set, and the user could no longer widen what they narrowed.
    """
    db = _list_db()
    db.fetchall = AsyncMock(return_value=[{"value": "MEDIUM", "label": "MEDIUM", "n": 4}])

    result = await fetch_filter_options(
        db, _settings(), "warehouses-cost", "size", window_days=7
    )

    sql = db.fetchall.await_args.args[0]
    assert "LOWER(warehouse_size) = ?" not in sql
    assert "window_days = ?" in sql
    assert 7 in db.fetchall.await_args.args[1:]
    assert result["options"] == [{"value": "MEDIUM", "label": "MEDIUM", "count": 4}]
    assert result["kind"] == "enum"
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_filter_options_reads_only_the_latest_snapshot_on_rolling_tables() -> None:
    """Same stale-row guard as the list: an option nobody can match is noise."""
    db = _list_db()
    db.fetchall = AsyncMock(return_value=[])

    await fetch_filter_options(db, _settings(), "warehouses-cost", "size")

    assert "as_of_date = (SELECT MAX(as_of_date) FROM" in db.fetchall.await_args.args[0]


@pytest.mark.asyncio
async def test_text_options_without_a_query_say_they_are_truncated() -> None:
    """1 824 warehouses in dev: handing back an arbitrary 50 would read as the whole list."""
    db = _list_db()
    db.fetchone = AsyncMock(return_value={"n": 1824})

    result = await fetch_filter_options(
        db, _settings(), "warehouses-cost", "warehouse", limit=50
    )

    assert result["options"] == []
    assert result["truncated"] is True
    assert result["kind"] == "text"
    # No point listing values nobody asked for: the count query is the only one run.
    db.fetchall.assert_not_awaited()


@pytest.mark.asyncio
async def test_text_options_are_listed_once_the_search_narrows_them() -> None:
    db = _list_db()
    db.fetchone = AsyncMock(return_value={"n": 1824})
    db.fetchall = AsyncMock(return_value=[{"value": "etl-prod", "label": "etl-prod", "n": 2}])

    result = await fetch_filter_options(
        db, _settings(), "warehouses-cost", "warehouse", q="etl"
    )

    sql = db.fetchall.await_args.args[0]
    assert "LIKE ?" in sql
    assert "%etl%" in db.fetchall.await_args.args[1:]
    assert result["options"][0]["value"] == "etl-prod"
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_text_options_below_the_limit_are_listed_without_a_query() -> None:
    db = _list_db()
    db.fetchone = AsyncMock(return_value={"n": 3})
    db.fetchall = AsyncMock(return_value=[{"value": "etl", "label": "etl", "n": 1}])

    result = await fetch_filter_options(db, _settings(), "warehouses-cost", "warehouse")

    assert [option["value"] for option in result["options"]] == ["etl"]
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_options_beyond_the_limit_are_flagged_and_cut() -> None:
    """One row over the limit is asked for, so ``truncated`` is measured, not guessed."""
    db = _list_db()
    db.fetchall = AsyncMock(
        return_value=[{"value": f"v{i}", "label": f"v{i}", "n": 1} for i in range(3)]
    )

    result = await fetch_filter_options(
        db, _settings(), "warehouses-cost", "size", limit=2
    )

    assert db.fetchall.await_args.args[-1] == 3
    assert len(result["options"]) == 2
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_numeric_options_are_server_declared_thresholds() -> None:
    """Only the server knows what expression a threshold applies to.

    No count either: a threshold has no row count, and inventing one would be worse
    than showing none.
    """
    db = _list_db()

    result = await fetch_filter_options(db, _settings(), "warehouses-cost", "cost")

    assert result["kind"] == "numeric"
    assert [option["value"] for option in result["options"]] == ["1", "10", "100", "1000"]
    assert all("count" not in option for option in result["options"])
    assert result["options"][0]["label"] == "≥ 1"
    db.fetchall.assert_not_awaited()


@pytest.mark.asyncio
async def test_success_rate_thresholds_read_as_at_most() -> None:
    """On a success rate the useful threshold is the low one — the label must say so."""
    db = _list_db()

    result = await fetch_filter_options(db, _settings(), "lakeflow-jobs", "success")

    assert result["options"][0]["label"] == "≤ 99"


@pytest.mark.asyncio
async def test_derived_enum_options_are_the_declared_choices() -> None:
    db = _list_db()

    result = await fetch_filter_options(
        db, _settings(), "clusters-governance", "owner_tag"
    )

    assert [option["value"] for option in result["options"]] == ["present", "absent"]
    db.fetchall.assert_not_awaited()


@pytest.mark.asyncio
async def test_workspace_options_label_the_id_from_the_dimension() -> None:
    """The predicate is on the id, the label on the name: a name is not a key."""
    db = _list_db()
    db.fetchall = AsyncMock(
        return_value=[{"value": "1234", "label": "dbw-analytics-prod", "n": 9}]
    )

    result = await fetch_filter_options(
        db, _settings(), "warehouses-overview", "workspace"
    )

    sql = db.fetchall.await_args.args[0]
    assert "LEFT JOIN" in sql
    assert "dim_dbx_workspace" in sql
    assert result["options"][0] == {
        "value": "1234",
        "label": "dbw-analytics-prod",
        "count": 9,
    }


@pytest.mark.asyncio
async def test_filter_options_refuses_an_unknown_column() -> None:
    with pytest.raises(ColumnFilterError):
        await fetch_filter_options(_list_db(), _settings(), "warehouses-cost", "nope")


@pytest.mark.asyncio
async def test_filter_options_caps_the_limit() -> None:
    db = _list_db()
    db.fetchall = AsyncMock(return_value=[])

    await fetch_filter_options(db, _settings(), "warehouses-cost", "size", limit=9999)

    # 201 = the 200 cap plus the extra row that measures ``truncated``.
    assert db.fetchall.await_args.args[-1] == 201


@pytest.mark.asyncio
async def test_filter_options_soft_fails_to_an_empty_list() -> None:
    """A missing gold table must leave a usable page, as everywhere else in compute.

    ``enabled: false`` distinguishes it from "no value in your perimeter" — the case
    that actually happens in dev, where ``warehouse_slow_queries`` is not deployed and
    the list route already answers ``enabled: false`` for the very same reason.
    """
    db = _list_db()
    db.fetchall = AsyncMock(side_effect=RuntimeError("TABLE_OR_VIEW_NOT_FOUND"))

    result = await fetch_filter_options(db, _settings(), "warehouses-cost", "size")

    assert result == {
        "view": "warehouses-cost",
        "column": "size",
        "kind": "enum",
        "label": "Size",
        "options": [],
        "truncated": False,
        "enabled": False,
    }


async def test_filter_options_omits_enabled_when_the_source_answers() -> None:
    """Only the failure carries the flag: a working list has nothing to signal."""
    db = _list_db()
    db.fetchall = AsyncMock(return_value=[{"value": "medium", "label": "medium", "n": 3}])

    result = await fetch_filter_options(db, _settings(), "warehouses-cost", "size")

    assert "enabled" not in result
    assert result["options"] == [{"value": "medium", "label": "medium", "count": 3}]
