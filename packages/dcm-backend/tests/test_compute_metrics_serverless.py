"""Unit tests for the serverless compute service (spec 025 T002).

What these tests are for is the set of decisions the SQL cannot state about itself. Three
of them carry the page:

* the 12 surfaces are duplicated from the gold builder because the backend cannot import
  the pipeline package — so the duplication needs a guard, not a comment;
* ``run_count`` is ``None`` and never ``0``, because gold leaves it NULL on eleven of the
  twelve surfaces and carries no zero anywhere;
* an out-of-range bucket label is invisible in a chart. A histogram rebuilt from a sparse
  ``GROUP BY`` shifts every label after the first gap and still renders perfectly.

The executed-SQL tests of the serverless-warehouse neutralisation live in
``test_compute_metrics_services.py``, next to the sqlite harness they need.
"""

from __future__ import annotations

import pytest

from app.api.services.compute_metrics_filters import (
    _SERVERLESS_SURFACE_VALUES,
    ColumnFilterError,
    parse_column_filters,
)
from app.api.services.compute_metrics_serverless import (
    _COST_PER_RUN_BUCKETS,
    _COST_PER_RUN_EDGES,
    _MIN_COMPARISON_REQUESTS,
    _OBJECT_KEY,
    _OTHER_SURFACES_BUCKET,
    SERVERLESS_OBJECT_ID_SENTINEL,
    ServerlessSurface,
    _histogram_buckets,
    _optional_int,
    _order,
    _share_pct,
    _strip_sentinel,
)

# ``sql_helpers.SERVERLESS_SURFACES``, written out. The backend cannot import the pipeline
# package, so this list is the only thing that ties the enum to the builder: a surface
# added to ``serverless_surface_case_expr`` and not here stays unreachable through the API,
# and gold's rows for it silently land nowhere.
_GOLD_SURFACES = frozenset(
    {
        "JOB",
        "DLT_PIPELINE",
        "MV_ST_REFRESH",
        "SQL_WAREHOUSE",
        "NOTEBOOK",
        "APP",
        "GENIE",
        "AI_ENDPOINT",
        "LAKEBASE",
        "NETWORKING",
        "PLATFORM_AUTO",
        "OTHER",
    }
)


# --------------------------------------------------------------------------------------
# The surfaces
# --------------------------------------------------------------------------------------


def test_surface_enum_mirrors_the_gold_builder() -> None:
    """Compared as a **set**: the two declaration orders differ (the builder lists
    ``GENIE`` before ``AI_ENDPOINT``) and neither order means anything."""
    assert {member.value for member in ServerlessSurface} == _GOLD_SURFACES
    assert len(ServerlessSurface) == 12


def test_the_trend_other_bucket_is_not_the_other_surface() -> None:
    """``OTHER`` is one of the 12 real surfaces; ``OTHER_SURFACES`` is the fold of
    everything outside the top 5. Sharing one name would add the two into a single series
    and put a wrong figure behind a legend entry."""
    assert _OTHER_SURFACES_BUCKET == "OTHER_SURFACES"
    assert _OTHER_SURFACES_BUCKET not in _GOLD_SURFACES
    assert ServerlessSurface.OTHER.value == "OTHER"


def test_surface_and_column_filter_cannot_contradict_each_other() -> None:
    """``surface=JOB&column_filter=surface:APP`` is a 422, not an arbitration.

    Dropping either one shows a table whose content matches neither request. The two spell
    the same predicate, which is exactly why the contradiction is detectable.
    """
    with pytest.raises(ColumnFilterError):
        parse_column_filters("serverless-objects", ["surface:APP"], surface="JOB")

    # Agreeing is not contradicting: the same value twice is one predicate.
    applied = parse_column_filters("serverless-objects", ["surface:JOB"], surface="JOB")
    assert [item.value for item in applied] == ["JOB"]


def test_an_unknown_surface_is_refused_rather_than_answered_empty() -> None:
    """This one failed when it was written, and the defect was real.

    ``surface`` is an ``enum`` fed by an ``option_table``, so its ``choices`` are empty and
    nothing was checked: ``SQL_WAREHOUSSE`` reached the query as a bound value and came back
    as a perfectly rendered empty page — a filtered-looking table that is not filtered the
    way the user asked, which is the exact failure mode the module docstring forbids. The
    closed value set now lives on the spec (``allowed``) and is verified in ``_build``.
    """
    with pytest.raises(ColumnFilterError):
        parse_column_filters("serverless-objects", ["surface:SQL_WAREHOUSSE"])


def test_the_surface_filter_accepts_exactly_the_declared_surfaces() -> None:
    """Three lists have to stay equal — the gold builder's, the enum's and the filter's.

    ``FastAPI`` validates the ``surface=`` query parameter against
    :class:`ServerlessSurface`, but that validation does **not** reach the
    ``column_filter=surface:…`` path: the two spellings of the same predicate would
    otherwise disagree on what a valid surface is. Checked on **both** serverless views,
    since each declares its own spec.
    """
    assert set(_SERVERLESS_SURFACE_VALUES) == {member.value for member in ServerlessSurface}

    for view in ("serverless-objects", "serverless-governance"):
        for member in ServerlessSurface:
            applied = parse_column_filters(view, [f"surface:{member.value}"])
            assert [item.value for item in applied] == [member.value]

        # ``case="upper"``: a lowercase surface is a normalisation, not a refusal — the
        # stored values are upper-case and the predicate folds the bound value the same way.
        assert [item.value for item in parse_column_filters(view, ["surface:job"])] == ["JOB"]

        with pytest.raises(ColumnFilterError):
            parse_column_filters(view, ["surface:SQL_WAREHOUSSE"])
        # ``OTHER_SURFACES`` is a chart bucket, never a stored value.
        with pytest.raises(ColumnFilterError):
            parse_column_filters(view, [f"surface:{_OTHER_SURFACES_BUCKET}"])


# --------------------------------------------------------------------------------------
# run_count — NULL is not zero
# --------------------------------------------------------------------------------------


def test_optional_int_keeps_an_unmeasured_run_count_unmeasured() -> None:
    """Eleven of the twelve surfaces never count runs and the table holds no
    ``run_count = 0`` at all, so ``0`` here would be a claim gold never makes."""
    assert _optional_int(None) is None
    assert _optional_int(0) == 0
    assert _optional_int(531) == 531
    # A Decimal comes back from the warehouse driver for a SUM.
    assert _optional_int(156197.0) == 156197


def test_optional_int_result_is_falsy_for_none_exactly_as_for_zero() -> None:
    """Why the callers can keep writing ``if runs:``: a cost per run guarded that way is
    silent on an unmeasured object instead of dividing by zero."""
    assert not _optional_int(None)
    assert not _optional_int(0)


def test_share_pct_returns_none_without_a_denominator() -> None:
    assert _share_pct(10.0, None) is None
    assert _share_pct(10.0, 0.0) is None
    assert _share_pct(None, 100.0) is None
    assert _share_pct(43.5, 100.0) == 43.5


# --------------------------------------------------------------------------------------
# The cost-per-run histogram
# --------------------------------------------------------------------------------------


def test_cost_per_run_edges_mirror_the_gold_constant() -> None:
    """``sql_helpers.HISTOGRAM_COST_PER_RUN_EDGES``: 18 edges doubling from one cent.

    The bucket **counts** come from gold; only their labels are rebuilt here. An edge list
    that drifted would relabel counts it did not produce — the worst kind of wrong, since
    the numbers stay plausible.
    """
    assert len(_COST_PER_RUN_EDGES) == 18
    assert _COST_PER_RUN_EDGES[0] == 0.01
    assert _COST_PER_RUN_EDGES[-1] == 1310.72
    for index in range(1, len(_COST_PER_RUN_EDGES)):
        assert _COST_PER_RUN_EDGES[index] == pytest.approx(_COST_PER_RUN_EDGES[index - 1] * 2)
    assert _COST_PER_RUN_BUCKETS == 19


def test_histogram_buckets_keep_their_labels_across_a_gap() -> None:
    """A ``GROUP BY pos`` skips empty buckets; appending in arrival order would present the
    0,04–0,08 $ count as the 0–0,01 $ one."""
    buckets = _histogram_buckets({0: 18135, 3: 7})

    assert len(buckets) == 19
    assert buckets[0] == {"from_usd": 0.0, "to_usd": 0.01, "run_count": 18135}
    assert buckets[1]["run_count"] == 0
    assert buckets[2]["run_count"] == 0
    assert buckets[3] == {"from_usd": 0.04, "to_usd": 0.08, "run_count": 7}


def test_the_last_histogram_bucket_is_unbounded() -> None:
    """``to_usd = None`` and not the last edge: runs above 1 310,72 $ exist — the maximum
    measured in dev is 983,04 $ at p99 and a single run reached 672,56 $."""
    buckets = _histogram_buckets({})

    assert buckets[-1]["from_usd"] == 1310.72
    assert buckets[-1]["to_usd"] is None
    assert all(bucket["run_count"] == 0 for bucket in buckets)


def test_histogram_ignores_a_bucket_index_gold_could_not_produce() -> None:
    """Defensive by construction, not by chance: the loop reads the mapping, it does not
    iterate it, so an out-of-range position cannot append a 20th bucket."""
    buckets = _histogram_buckets({19: 4, -1: 9})

    assert len(buckets) == 19
    assert sum(bucket["run_count"] for bucket in buckets) == 0


# --------------------------------------------------------------------------------------
# The object key and its sentinel
# --------------------------------------------------------------------------------------


def test_the_object_key_counts_only_rows_carrying_a_real_object() -> None:
    """``COUNT(DISTINCT object_id)`` would add one phantom object per keyless surface —
    the sentinel — and fold every workspace of that surface into it."""
    assert _OBJECT_KEY.startswith("CASE WHEN has_object_key THEN CONCAT_WS('|', ")
    assert "cloud_provider" in _OBJECT_KEY
    assert "serverless_surface" in _OBJECT_KEY
    # No ELSE: a keyless row must produce NULL, which COUNT(DISTINCT) skips.
    assert "ELSE" not in _OBJECT_KEY


def test_the_sentinel_is_never_served_as_an_object_id() -> None:
    """It is a merge key in gold — ``merge_into_table`` merges on null-safe ``<=>``, so a
    NULL there would fuse rows. The API has no such constraint, and handing the sentinel to
    the UI would hand it a deep link that 404s."""
    assert _strip_sentinel({"object_id": SERVERLESS_OBJECT_ID_SENTINEL})["object_id"] is None
    assert _strip_sentinel({"object_id": "114088010544136"})["object_id"] == (
        "114088010544136"
    )


# --------------------------------------------------------------------------------------
# Sorting and the DLT comparison floor
# --------------------------------------------------------------------------------------


def test_sorting_puts_missing_values_last_in_both_directions() -> None:
    """``performance_target`` is NULL on 39,6 % of the serverless rows and
    ``cost_per_run_p50_usd`` on every non-JOB surface. An ascending sort without this opens
    the page on a screenful of dashes."""
    assert _order("asc") == "ASC NULLS LAST"
    assert _order("desc") == "DESC NULLS LAST"
    assert _order("; DROP TABLE t") == "DESC NULLS LAST"


def test_the_dlt_comparison_floor_is_thirty_requests() -> None:
    """Azure classic DLT weighs 6 requests in dev. Two failures out of six render as
    "33,33 %" beside a serverless rate resting on thousands, and the page would announce
    that classic fails 5,6× more on azure out of two rows."""
    assert _MIN_COMPARISON_REQUESTS == 30
