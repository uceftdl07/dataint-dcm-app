"""Shared helpers for Compute Metrics gold-table queries."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import IntEnum
from typing import Any

from ..routes._lz_filter import add_scope_lz_filter

__all__ = [
    "_DEFAULT_PAGE_SIZE",
    "_MAX_PAGE_SIZE",
    "_SERVERLESS_INAPPLICABLE_CATEGORIES",
    "_WAREHOUSE_UTILIZATION_ROLLING",
    "RollingWindowDays",
    "_add_rbac_scope",
    "_as_float",
    "_bounds_sql",
    "_clamp_page",
    "_date_where",
    "_empty_page",
    "_expand_workspace_id_variants",
    "_grain",
    "_idle_delta_pts",
    "_is_table_missing",
    "_iso",
    "_normalize_prev_cost",
    "_previous_period",
    "_resolve_period",
    "_round_pct",
    "_safe",
    "_scope_where",
    "_serverless_void_savings_sql",
    "_serverless_warehouse_cte",
    "_uptime_delta_pct",
    "_window_block",
    "_window_period",
    "_window_where",
]

logger = logging.getLogger(__name__)

_DEFAULT_PAGE_SIZE = 25
_MAX_PAGE_SIZE = 200

#: The only gold snapshot that says whether a SQL warehouse is serverless. Named here
#: because three modules read it for the same decision — see
#: :func:`_serverless_warehouse_cte`.
_WAREHOUSE_UTILIZATION_ROLLING = "gold_dbx_compute_warehouse_utilization_rolling"

#: Recommendation categories in which a **warehouse** rule can price a saving on a
#: classic-billing assumption — reclaim idle uptime, stop an idle warehouse — that does
#: not hold on serverless, where idle capacity is not billed. It is the **price tag** that
#: is void on serverless, not every rule of the category: the categories are a
#: pre-filter, and :func:`_serverless_void_savings_sql` carries the condition that
#: decides. Both are needed — a category alone would suppress advice, and a figure alone
#: would suppress a ``RELIABILITY`` rule the day one prices something.
_SERVERLESS_INAPPLICABLE_CATEGORIES: tuple[str, ...] = ("RIGHTSIZING", "FINOPS")

_WINDOW_DAYS: dict[str, int] = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "180d": 180,
    "365d": 365,
}


class RollingWindowDays(IntEnum):
    """Rolling windows materialized in gold (``ROLLING_WINDOWS`` of the pipeline).

    Shared by every ``*_rolling`` family — clusters and SQL warehouses alike; the
    four values are the pipeline's, not one page's.

    An ``IntEnum`` rather than ``Query(enum=[…])``: the latter only decorates the
    OpenAPI schema, so ``window_days=5`` would be accepted and silently return an
    empty page. Measured on this FastAPI/Pydantic version — a bare ``Literal``
    is no substitute either, it rejects the query string ``"7"`` along with the
    rest, never having coerced it to the int literal.
    """

    DAY = 1
    WEEK = 7
    MONTH = 30
    QUARTER = 90


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


async def _safe(coro: Any, fallback: Any, label: str) -> Any:
    try:
        return await coro
    except Exception:
        logger.exception("compute metrics soft-fail: %s", label)
        return fallback


def _clamp_page(page: int, page_size: int) -> tuple[int, int]:
    return max(1, page), min(max(1, page_size), _MAX_PAGE_SIZE)


def _resolve_period(
    period_start: date | None,
    period_end: date | None,
    *,
    window: str = "30d",
) -> tuple[date, date]:
    """Return inclusive (start, end) dates; default last 30 days including today."""
    if period_start is not None and period_end is not None:
        if period_end < period_start:
            period_start, period_end = period_end, period_start
        return period_start, period_end

    today = datetime.now(UTC).date()
    days = _WINDOW_DAYS.get(window, 30)
    start = today - timedelta(days=days - 1)
    return start, today


def _previous_period(start: date, end: date) -> tuple[date, date]:
    span = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span - 1)
    return prev_start, prev_end


def _expand_workspace_id_variants(workspace_ids: list[str]) -> list[str]:
    """Match both bare numeric and ``adb-<id>`` forms stored in gold tables."""
    expanded: list[str] = []
    seen: set[str] = set()
    for raw in workspace_ids:
        wid = (raw or "").strip()
        if not wid:
            continue
        variants = {wid}
        lower = wid.lower()
        if lower.startswith("adb-"):
            variants.add(wid[4:])
        else:
            variants.add(f"adb-{wid}")
        for variant in variants:
            if variant not in seen:
                seen.add(variant)
                expanded.append(variant)
    return expanded


def _add_rbac_scope(
    conditions: list[str],
    params: list[Any],
    *,
    allowed_lz_ids: list[str] | None,
    allowed_workspace_ids: list[str] | None,
    has_lz_column: bool,
) -> None:
    """Append the caller's project scope, both dimensions ORed.

    Mirrors :func:`app.auth.scope_model.add_scope_filter`: a row is in scope when
    its Landing Zone **or** its Databricks workspace is granted by one of the
    caller's active projects. ``None`` on both dimensions means unrestricted (no
    clause at all).

    Tables without a ``source_lz_id`` column (``has_lz_column=False`` — every
    ``gold_dbx_compute_*`` table) can only express the workspace dimension, so a
    caller whose projects grant no workspace gets ``1 = 0`` there rather than the
    whole platform's compute data.
    """
    if allowed_lz_ids is None and allowed_workspace_ids is None:
        return

    ors: list[str] = []
    scoped_params: list[Any] = []
    if has_lz_column and allowed_lz_ids:
        placeholders = ", ".join("?" for _ in allowed_lz_ids)
        ors.append(f"source_lz_id IN ({placeholders})")
        scoped_params.extend(allowed_lz_ids)
    if allowed_workspace_ids:
        expanded = _expand_workspace_id_variants(allowed_workspace_ids)
        placeholders = ", ".join("?" for _ in expanded)
        ors.append(f"workspace_id IN ({placeholders})")
        scoped_params.extend(expanded)

    if not ors:
        conditions.append("1 = 0")
        return
    conditions.append("(" + " OR ".join(ors) + ")")
    params.extend(scoped_params)


def _scope_where(
    allowed_lz_ids: list[str] | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    workspace_ids: list[str] | None,
    *,
    has_lz_column: bool = True,
    cloud_provider: str | None = None,
    allowed_workspace_ids: list[str] | None = None,
) -> tuple[list[str], list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []

    _add_rbac_scope(
        conditions,
        params,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        has_lz_column=has_lz_column,
    )

    if has_lz_column:
        # RBAC is handled above; this is the LZ filter the client asked for, ANDed
        # with it — an explicit selection never widens the scope.
        add_scope_lz_filter(
            conditions,
            params,
            None,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
        )

    if cloud_provider:
        conditions.append("LOWER(cloud_provider) = ?")
        params.append(cloud_provider.strip().lower())

    # Client-requested workspace filter — ANDed with the RBAC clause above.
    if workspace_ids is not None:
        if not workspace_ids:
            conditions.append("1 = 0")
        else:
            expanded = _expand_workspace_id_variants(workspace_ids)
            placeholders = ", ".join("?" for _ in expanded)
            conditions.append(f"workspace_id IN ({placeholders})")
            params.extend(expanded)

    return conditions, params


def _date_where(
    conditions: list[str],
    params: list[Any],
    start: date,
    end: date,
    *,
    date_col: str = "period_start",
) -> tuple[str, list[Any]]:
    c = list(conditions)
    p = list(params)
    c.append(f"{date_col} >= ?")
    p.append(start)
    c.append(f"{date_col} <= ?")
    p.append(end)
    where = ("WHERE " + " AND ".join(c)) if c else ""
    return where, p


def _empty_page(page: int, page_size: int, start: date, end: date) -> dict[str, Any]:
    return {
        "items": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
        "period": {"from": start.isoformat(), "to": end.isoformat()},
    }


def _period_dict(start: date, end: date) -> dict[str, str]:
    return {"from": start.isoformat(), "to": end.isoformat()}


def _window_where(
    scope: list[str],
    params: list[Any],
    window_days: int,
    *,
    latest_snapshot_table: str | None = None,
) -> tuple[str, list[Any]]:
    """WHERE for a ``*_rolling`` table: the caller's scope AND the asked window.

    Counterpart of :func:`_date_where` for the rolling tables: they are snapshots
    anchored on ``as_of_date``, so a free date range has nothing to filter here —
    ``period_start``/``period_end`` keep bounding the trends only.

    ``latest_snapshot_table`` adds the **stale-row guard**: only the rows of the
    latest snapshot are read. These tables are written by a ``MERGE`` with no
    delete clause, so a row whose entity has stopped being produced stays there
    forever under its old ``as_of_date``, indistinguishable from a current one.
    Measured in dev on 2026-09-07 on ``warehouse_cost_rolling``: **358 warehouses
    returned instead of 202** for ``window_days = 1``, 156 of them two days stale
    (023 ``research.md`` R9a).

    The ``MAX`` is **global to the table, not per ``window_days``**: one run writes
    a single ``as_of_date`` for its four windows, and a per-window ``MAX`` would
    resurrect the stale rows of any window whose current population is empty. It
    is deliberately unscoped too — an RBAC-narrowed ``MAX`` would drift per caller.

    No bound parameter is added: the guard is a scalar sub-query, so the caller's
    parameter order is unchanged. Opt-in on purpose — the cluster views carry the
    same latent defect but are out of this task's scope, and they must keep
    producing byte-identical SQL.
    """
    conditions = [*scope, "window_days = ?"]
    if latest_snapshot_table is not None:
        conditions.append(
            f"as_of_date = (SELECT MAX(as_of_date) FROM {latest_snapshot_table})"
        )
    return "WHERE " + " AND ".join(conditions), [*params, int(window_days)]


def _window_block(window_days: int, row: dict[str, Any] | None) -> dict[str, Any]:
    """The window actually covered, read from gold (R5) — never derived from today.

    ``as_of_date`` is the last day present in the daily table. A pipeline run late
    by one day makes the "last 7 days" window cover J-8→J-2; recomputing the
    bounds from ``today`` would caption the figures with a period the data does
    not cover, and a missing day would read as a cost drop.
    """
    return {
        "window_days": int(window_days),
        "from_date": _iso((row or {}).get("window_start")),
        "to_date": _iso((row or {}).get("as_of_date")),
    }


def _window_period(window: dict[str, Any], start: date, end: date) -> dict[str, str]:
    """``period`` block kept for existing callers, carrying the window's dates."""
    from_date, to_date = window["from_date"], window["to_date"]
    if from_date and to_date:
        return {"from": from_date, "to": to_date}
    return _period_dict(start, end)


def _bounds_sql(table: str, where: str) -> str:
    """Window bounds of the scope, so an empty page still reports its period."""
    return (
        "SELECT MAX(window_start) AS window_start, MAX(as_of_date) AS as_of_date "
        f"FROM {table} {where}"
    )


def _is_table_missing(exc: BaseException, table_hint: str) -> bool:
    msg = str(exc).upper()
    return "TABLE_OR_VIEW_NOT_FOUND" in msg or table_hint.upper() in msg


def _serverless_warehouse_cte(util_table: str) -> str:
    """One row per SQL warehouse, carrying whether it is serverless and which form it is.

    Lives here rather than in a caller because three modules key the same decision off
    it: the recommendations list, the recommendations summary and the warehouse overview
    count. ``is_serverless`` exists in ``warehouse_utilization_daily``/``_rolling`` only —
    neither the cost snapshot nor ``gold_dbx_compute_recommendations`` carries it. The same
    is true of ``warehouse_type``, which the same two tables carry alongside it.

    **``warehouse_type`` answers a question ``is_serverless`` cannot**: a boolean splits the
    estate in two, while Databricks declares a *form* per warehouse. Three of them carry
    essentially the whole estate — measured on curated dev on 2026-09-11, 1 477 warehouses
    declared ``SERVERLESS``, 359 ``PRO``, 162 ``CLASSIC`` — but the vocabulary is
    Databricks', not ours, and it is **open**: the same measurement finds one ``REAL_TIME``.
    So the value is published as received and never checked against a list of three; the
    ``type`` filter carries no ``allowed`` for that reason, unlike ``surface``, whose
    twelve values *we* assign in gold. Everything a classic warehouse is diagnosed on
    applies to a pro one, so the flag stays the discriminant of every *figure*; the type is
    published next to it because "not serverless" is not a thing a user can act on.

    The type is folded so that it can never contradict the flag published beside it. A row
    reading ``PRO`` next to ``is_serverless = true`` would deny, in one column, the premise
    the neighbouring column uses to void a saving. Hence the ``CASE``: serverless wins as
    soon as ``bool_and`` says so, and otherwise only a *non*-serverless declared type is
    eligible.

    That second guard is **redundant with the pipeline** as of the change that added the
    column: both gold builders already subordinate the type to the flag, so a row with
    ``is_serverless = false`` cannot hold ``SERVERLESS``. It is kept anyway, for the same
    reason the rolling builder keeps its own unreachable branch — the coherence of what
    *this* function publishes should not depend on an invariant maintained in another
    package — and because it is what makes the fold safe on rows written **before** that
    pipeline change: those carry ``warehouse_type = NULL``, and the first branch still
    prints ``SERVERLESS`` for every warehouse the flag already resolved. A warehouse whose
    every window declares ``SERVERLESS`` while billing says at least one day was not
    resolves to ``NULL``: "billed classic, declared serverless, no honest third value to
    print". It renders as an em dash rather than as a guess.

    ``MAX`` over the eligible types is a tie-break, not a judgement: it fires only for a
    warehouse that changed between ``CLASSIC`` and ``PRO`` mid-window, and it resolves
    alphabetically, so ``PRO`` wins. What matters is that it is *stable* — the same warehouse
    reads the same way on every refresh — not which of the two it picks. How often it fires
    cannot be measured yet: the gold column does not exist until the pipeline change is
    deployed and run. Replaying this fold against the latest declared type in curated
    predicted 647 ``SERVERLESS`` / 73 ``PRO`` / 22 ``CLASSIC`` / 0 ``NULL`` over the 742
    warehouses of the dev snapshot on 2026-09-11 — a prediction about a different input
    (curated as-of-today, not the per-day type gold will fold), so worth re-measuring on
    the real column rather than trusting.

    Two things this deliberately does **not** do:

    * it does not join on ``as_of_date``. The caller's own snapshot guard anchors on its
      own table; pinning both to one ``MAX`` would drop every row the day the two
      pipelines' snapshots differ by a day. Here the sub-select anchors ``util_table`` on
      *its* latest snapshot and nothing else.
    * it does not filter ``window_days``. A warehouse can be absent from the 1-day window
      (nothing ran yesterday) while present in the 30-day one, so restricting to one
      window would silently make it "unknown". Instead every window is folded with
      ``bool_and``.

    ``bool_and`` and not ``bool_or``: a warehouse whose windows *disagree* — one migrated
    from classic to serverless mid-window — resolves to ``false``, so it keeps its
    recommendation. Doubt keeps the row, exactly like a warehouse absent from this table
    altogether. Measured in dev on 2026-09-10 the choice changes nothing yet: 742 warehouse
    identities at the latest snapshot, **742 distinct keys, 0 disagreement**, 647 serverless
    / 95 classic / 0 NULL flag. It is written for the day that stops being true.
    """
    return (
        "SELECT cloud_provider, workspace_id, warehouse_id, "
        "bool_and(is_serverless) AS is_serverless, "
        "CASE WHEN bool_and(is_serverless) THEN 'SERVERLESS' "
        "ELSE MAX(CASE WHEN warehouse_type <> 'SERVERLESS' THEN warehouse_type END) "
        "END AS warehouse_type "
        f"FROM {util_table} "
        f"WHERE as_of_date = (SELECT MAX(as_of_date) FROM {util_table}) "
        "GROUP BY cloud_provider, workspace_id, warehouse_id"
    )


def _serverless_void_savings_sql(reco: str, flag: str) -> str:
    """``true`` when a recommendation's **figure** is arithmetically void on its target.

    A rightsizing or auto-stop saving on a **serverless** SQL warehouse is priced by
    reclaiming idle uptime, which serverless does not bill. The dollar amount is therefore
    not merely uncertain, it is money that cannot be saved. Measured in dev on 2026-09-10
    the withheld figures are **93 359,94 $** over **487** rows, every one of them
    ``RESOLVED``.

    **The condition is the figure, not the category**, and this is the correction of an
    earlier version of this function (spec 025, T001i). It used to suppress every
    ``RIGHTSIZING``/``FINOPS`` row on a serverless warehouse, and it justified that by a
    measurement — 69 OPEN rows carrying 27 104,73 $ — which the gold layer has since made
    obsolete: those dollars were **inherited** from another rule by a ``COALESCE`` in the
    builder's ``merged`` CTE, and no longer exist
    (``pipelines/gold_dbx_compute/recommendations.py``). What is left on serverless
    warehouses today is **69 OPEN rows carrying 0 $**: 34 saturated queues and 35 spilling
    query sets, whose actions — raise ``max_clusters``, upsize or tune the query — apply to
    a serverless warehouse exactly as they do to a classic one, since serverless still has
    a size and a scaling range. Suppressing them removed real advice and no false figure.

    That is the same test this module already applies to ``RELIABILITY``, which is
    deliberately absent from :data:`_SERVERLESS_INAPPLICABLE_CATEGORIES` because its 337
    OPEN serverless rows carry 0 $. Keying on the figure makes that exemption a
    **consequence of the rule** instead of a hand-maintained exception.

    What is still suppressed, and why this function is not simply deleted: the list route
    can be asked for ``status = 'RESOLVED'``, and the resolved serverless rows still carry
    the pre-fix money. Those two categories hold **524** resolved serverless rows, of which
    the **487** carrying a figure above zero are withheld — **90 828,91 $** of rightsizing
    plus **2 531,03 $** of auto-stop. The builder's ``_existing_state_cte`` reads only
    ``OPEN``/``ACK``, so its merge can never rewrite them.

    ``> 0`` and not ``IS NOT NULL``: a figure of exactly ``0`` promises nothing, so it has
    no void saving to withhold, and it must stay visible like a ``NULL`` one (3 such rows
    in dev). Negative amounts would be a builder defect and are deliberately **not**
    caught — there are 0 today, and hiding one would hide the defect.

    The outer ``COALESCE`` is the other point of this function. ``flag`` comes from a LEFT
    JOIN, so it is ``NULL`` for a warehouse absent from the utilization snapshot — and
    ``NOT (true AND NULL AND true)`` is ``NULL``, which a ``WHERE`` drops. Written naively,
    the predicate meant to protect the unknown case would be the one thing that hides it.
    Folding to ``false`` states the rule out loud: **suppress only what is known to be
    serverless**. In dev there is exactly 1 such unknown row, and it must stay visible.
    """
    categories = ", ".join(f"'{name}'" for name in _SERVERLESS_INAPPLICABLE_CATEGORIES)
    return (
        "COALESCE("
        f"UPPER({reco}.object_type) = 'WAREHOUSE' "
        f"AND {flag}.is_serverless = true "
        f"AND UPPER({reco}.category) IN ({categories}) "
        f"AND COALESCE({reco}.estimated_savings_usd, 0) > 0"
        ", false)"
    )


def _pct_delta(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous <= 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _as_float(value: Any) -> float | None:
    """Driver ``Decimal``/``str`` → ``float``: mixed-type arithmetic would raise."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _grain(granularity: str) -> str:
    """``day``/``week``/``month``, anything else read as ``day``.

    Interpolated into ``date_trunc``, so the whitelist is also what keeps the
    value out of the SQL string.
    """
    return granularity if granularity in {"day", "week", "month"} else "day"


def _round_pct(value: Any) -> float | None:
    """Percentage rounded for display, ``None`` kept as ``None``."""
    result = _as_float(value)
    return None if result is None else round(result, 1)


def _uptime_delta_pct(item: dict[str, Any]) -> float | None:
    """Percentage change vs the previous window, ``None`` when incomparable.

    ``_pct_delta`` returns ``None`` for a previous window that is ``NULL`` or
    zero — the gold tables leave it ``NULL`` on purpose, and a ``0`` divisor would
    otherwise read as a 100 % collapse instead of "no comparison available".

    Grain-agnostic: the three ``*_efficiency_rolling`` families (cluster, job,
    DLT pipeline) all carry ``uptime_hours``/``uptime_hours_prev_window``.
    """
    return _pct_delta(
        _as_float(item.get("uptime_hours")), _as_float(item.get("uptime_hours_prev_window"))
    )


def _idle_delta_pts(item: dict[str, Any]) -> float | None:
    """Variation of ``idle_pct`` in percentage **points**, not per cent.

    ``idle_pct`` is already a percentage: 20 % → 30 % is "+10 pts", not "+50 %".
    """
    current = _as_float(item.get("idle_pct"))
    previous = _as_float(item.get("idle_pct_prev_window"))
    if current is None or previous is None:
        return None
    return round(current - previous, 1)


def _normalize_prev_cost(item: dict[str, Any]) -> None:
    """Turn a zero previous cost into ``None`` — "no comparison", not "it was free".

    Both ``*_cost_rolling`` tables aggregate the previous window with
    ``SUM(CASE … ELSE 0 END)`` (`cluster_cost_rolling.py:131-134`,
    `warehouse_cost_rolling.py:115`), so the column is structurally never ``NULL``: an
    entity with no predecessor is indistinguishable from one that cost exactly nothing,
    and both come back as ``0``. Gold has already drawn that conclusion for the ratio —
    ``NULLIF(cost_usd_prev_window, 0)`` leaves ``cost_delta_pct`` ``NULL`` — so the value
    is made to agree with its own delta. Without this, the same row reads "Prev cost $0"
    next to "Prev lifetime —", the latter being ``NULL`` because efficiency uses a
    ``LEFT JOIN`` (R1).

    The threshold is ``<= 0``, the same rule ``_pct_delta`` applies to its divisor: a
    credit note would make the previous cost negative, and no percentage of a negative
    baseline is meaningful either.
    """
    previous = _as_float(item.get("cost_usd_prev_window"))
    if previous is not None and previous <= 0:
        item["cost_usd_prev_window"] = None


def _json_safe(value: Any) -> Any:
    """Normalize Databricks driver values for JSON responses."""
    if value is None:
        return None
    # The driver returns DECIMAL as ``Decimal``, and the routes annotate their return
    # as ``dict[str, Any]`` — which FastAPI uses as a response model, so Pydantic v2
    # serializes a ``Decimal`` to a JSON *string*. The front types these fields as
    # `number`: ``formatPct`` would then call ``toFixed`` on a string and throw, and
    # ``formatNumber`` would silently print the raw 21-digit value. Convert here, the
    # one place every compute payload passes through.
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    # Databricks ARRAY columns often come back as numpy.ndarray
    module = type(value).__module__
    if module.startswith("numpy") and hasattr(value, "tolist"):
        return [_json_safe(item) for item in value.tolist()]
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, bytearray)):
        try:
            return [_json_safe(item) for item in value.tolist()]
        except TypeError:
            pass
    return value


def _row_to_dict(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key.startswith("_"):
            continue
        out[key] = _json_safe(value)
    return out
