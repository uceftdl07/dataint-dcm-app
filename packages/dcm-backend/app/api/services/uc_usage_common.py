"""Shared helpers for the ``/api/v1/uc-usage`` gold-table queries.

The eight ``gold_dbx_usage_*`` tables carry neither ``source_lz_id`` nor
``workspace_id``, so nothing here builds a scope predicate: the whole router is
reserved for unrestricted callers instead (``require_unrestricted_scope``).

``None`` is a value, not a missing zero: :func:`number` keeps it. ``0`` USD and
"cost could not be attributed" are different statements, and the gold tables
distinguish them on purpose.
"""

from __future__ import annotations

from collections.abc import Awaitable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException

from ...db.connection import DatabricksWarehousePool

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "GOLD_CONSUMER_DAILY",
    "GOLD_FORECAST_DAILY",
    "GOLD_QUERY_PERFORMANCE_DAILY",
    "GOLD_RECOMMENDATIONS",
    "GOLD_TABLE_CATALOG",
    "GOLD_TABLE_DAILY",
    "GOLD_TABLE_GOVERNANCE",
    "GOLD_TABLE_POPULARITY_DAILY",
    "LIFECYCLE_AGGREGATES",
    "MAX_PAGE_SIZE",
    "DeletedTableJoin",
    "as_float",
    "date_conditions",
    "deleted_flag_conditions",
    "deleted_table_conditions",
    "deleted_table_join",
    "guarded",
    "integer",
    "iso",
    "lifecycle_cte",
    "lifecycle_fields",
    "number",
    "object_filters",
    "object_id_filters",
    "offset_of",
    "page_envelope",
    "pct_delta",
    "period_dict",
    "placeholders",
    "previous_period",
    "ratio_pct",
    "resolve_period",
    "search_condition",
    "severity_order_sql",
    "table_lifecycle",
    "where_clause",
]

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200

GOLD_TABLE_DAILY = "gold_dbx_usage_table_daily"
GOLD_TABLE_POPULARITY_DAILY = "gold_dbx_usage_table_popularity_daily"
GOLD_CONSUMER_DAILY = "gold_dbx_usage_consumer_daily"
GOLD_QUERY_PERFORMANCE_DAILY = "gold_dbx_usage_table_query_performance_daily"
GOLD_TABLE_CATALOG = "gold_dbx_usage_table_catalog"
GOLD_TABLE_GOVERNANCE = "gold_dbx_usage_table_governance"
GOLD_RECOMMENDATIONS = "gold_dbx_usage_recommendations"
GOLD_FORECAST_DAILY = "gold_dbx_usage_forecast_daily"


def resolve_period(period_start: date, period_end: date) -> tuple[date, date]:
    """Validate the caller's period. No default: FR-017 forbids one."""
    if period_end < period_start:
        raise HTTPException(
            status_code=422,
            detail="period_end must be on or after period_start",
        )
    return period_start, period_end


def previous_period(start: date, end: date) -> tuple[date, date]:
    span = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    return prev_end - timedelta(days=span - 1), prev_end


def period_dict(start: date, end: date) -> dict[str, str]:
    return {"start": start.isoformat(), "end": end.isoformat()}


def placeholders(values: Sequence[Any]) -> str:
    return ", ".join("?" for _ in values)


def _clean(values: Sequence[str] | None) -> list[str]:
    if not values:
        return []
    return [item.strip() for item in values if item and item.strip()]


def date_conditions(
    start: date, end: date, *, column: str = "period_start"
) -> tuple[list[str], list[Any]]:
    return [f"{column} >= ?", f"{column} <= ?"], [start, end]


def object_filters(
    catalog: str | None,
    schema: str | None,
    tables: Sequence[str] | None,
    *,
    alias: str | None = None,
) -> tuple[list[str], list[Any]]:
    """Catalogue/schema/table predicates for a table carrying the usual columns.

    ``catalog`` and ``schema`` are quoted: both are keywords in Databricks SQL.
    """
    prefix = f"{alias}." if alias else ""
    conditions: list[str] = []
    params: list[Any] = []
    if catalog:
        conditions.append(f"{prefix}`catalog` = ?")
        params.append(catalog.strip())
    if schema:
        conditions.append(f"{prefix}`schema` = ?")
        params.append(schema.strip())
    cleaned = _clean(tables)
    if cleaned:
        conditions.append(f"{prefix}table_full_name IN ({placeholders(cleaned)})")
        params.extend(cleaned)
    return conditions, params


def object_id_filters(
    catalog: str | None,
    schema: str | None,
    tables: Sequence[str] | None,
    *,
    column: str = "object_id",
) -> tuple[list[str], list[Any]]:
    """Same filters against a table that only carries the qualified name.

    ``forecast_daily`` and ``recommendations`` store ``catalog.schema.table`` in a
    single column, so the two leading parts are extracted rather than matched by
    prefix — a ``LIKE`` would treat ``%`` and ``_`` in a catalogue name as wildcards.
    """
    conditions: list[str] = []
    params: list[Any] = []
    if catalog:
        conditions.append(f"SPLIT_PART({column}, '.', 1) = ?")
        params.append(catalog.strip())
    if schema:
        conditions.append(f"SPLIT_PART({column}, '.', 2) = ?")
        params.append(schema.strip())
    cleaned = _clean(tables)
    if cleaned:
        conditions.append(f"{column} IN ({placeholders(cleaned)})")
        params.extend(cleaned)
    return conditions, params


def deleted_table_conditions(
    db: DatabricksWarehousePool,
    include_deleted: bool,
    *,
    column: str = "table_full_name",
) -> list[str]:
    """Drop the tables flagged deleted, unless the caller asked to keep them.

    ``is_deleted`` lives on ``table_catalog`` only: the daily facts are rebuilt by
    a 3-day MERGE, so denormalising the flag there would freeze it (spec 027).
    Consumers therefore filter by anti-membership on the catalogue.

    Returns conditions but **no** parameters on purpose: the callers below thread
    positional parameters by hand, and a predicate that adds none can be appended
    to any condition list without renumbering what follows.

    ``table_full_name`` is the grain the API exposes — ``cloud_provider`` is never
    surfaced (FR-019) — so a name flagged deleted on **any** cloud is excluded,
    the same reading as the ``BOOL_OR`` of :func:`lifecycle_cte`. Filter and
    displayed flag must agree, or a row would show up marked deleted and then
    vanish once the box is unticked.
    """
    if include_deleted:
        return []
    return [
        f"{column} NOT IN (SELECT table_full_name FROM {db.table(GOLD_TABLE_CATALOG)} "
        "WHERE is_deleted AND table_full_name IS NOT NULL)"
    ]


@dataclass(frozen=True)
class DeletedTableJoin:
    """The deleted-table exclusion as a join, for a predicate that must sit under an ``OR``.

    Three fragments to splice into the caller's query — a ``WITH``, a ``JOIN``, and
    the conditions to nest. All three are empty when the caller asked to keep the
    deleted tables, so the query comes out exactly as it would without the feature.
    """

    cte: str
    join: str
    conditions: list[str]


def deleted_table_join(
    db: DatabricksWarehousePool,
    include_deleted: bool,
    *,
    column: str,
    alias: str = "deleted_tables",
) -> DeletedTableJoin:
    """Same exclusion as :func:`deleted_table_conditions`, hoisted into the ``FROM``.

    Reserved for the one caller that has to **nest** the exclusion in a disjunction:
    the recommendations table mixes grains, so it may only narrow ``DATA_PRODUCT``
    rows (FR-011). A subquery under an ``OR`` cannot be rewritten as an anti-join:
    Spark evaluates it per row against every deleted name of the catalogue, and a
    correlated ``NOT EXISTS`` in that position is planned the same way. A join is not
    subject to the disjunction, so it is placed unconditionally and only a column
    comparison remains under the ``OR``.

    ``SELECT DISTINCT`` in the CTE is load-bearing. The catalogue holds one row per
    ``(cloud_provider, table_full_name)``; without it a table deleted on two clouds
    would match twice, and every row kept by the *other* branch of the disjunction
    would be duplicated — inflating each ``COUNT(*)`` built on this source.

    Unlike the null-aware ``NOT IN``, this form **keeps** a row whose ``column`` is
    NULL rather than dropping it: no name, no deleted table. That is the reading the
    API documents — ``is_deleted`` is never NULL in a response (spec 027).

    The eight top-level callers keep :func:`deleted_table_conditions`: their ``NOT IN``
    sits at the top of the ``WHERE``, where it does plan as an anti-join and needs no
    join plumbing.
    """
    if include_deleted:
        return DeletedTableJoin(cte="", join="", conditions=[])
    if "." not in column:
        raise ValueError(
            f"deleted_table_join needs a column qualified by the outer alias, got {column!r}"
        )
    return DeletedTableJoin(
        cte=(
            f"WITH {alias} AS ("
            f"SELECT DISTINCT table_full_name FROM {db.table(GOLD_TABLE_CATALOG)} "
            "WHERE is_deleted AND table_full_name IS NOT NULL)"
        ),
        join=f"LEFT JOIN {alias} ON {alias}.table_full_name = {column}",
        conditions=[f"{alias}.table_full_name IS NULL"],
    )


def deleted_flag_conditions(include_deleted: bool, *, alias: str | None = None) -> list[str]:
    """Same exclusion, for a query already reading a table carrying the flag.

    ``table_catalog`` and ``table_governance`` both hold ``is_deleted``; there the
    anti-join of :func:`deleted_table_conditions` would re-read the catalogue for
    nothing. ``COALESCE`` guards a warehouse not yet backfilled by spec 027.
    """
    if include_deleted:
        return []
    prefix = f"{alias}." if alias else ""
    return [f"NOT COALESCE({prefix}is_deleted, false)"]


LIFECYCLE_AGGREGATES = """
            BOOL_OR(COALESCE(is_deleted, false)) AS is_deleted,
            MAX(CASE WHEN COALESCE(is_deleted, false) THEN deleted_at END) AS deleted_at,
            CASE
                WHEN BOOL_OR(COALESCE(is_deleted, false)) THEN 'DELETED'
                WHEN BOOL_OR(UPPER(lifecycle_state) = 'ACTIVE') THEN 'ACTIVE'
                ELSE 'UNKNOWN'
            END AS lifecycle_state"""
"""The three lifecycle columns, aggregated per ``table_full_name``.

Deleted on any cloud counts as deleted — the same reading as
:func:`deleted_table_conditions` — and ``deleted_at`` is then the latest deletion
seen. The state is rebuilt rather than aggregated: ``MAX`` on the string would
rank ``UNKNOWN`` above ``ACTIVE`` and hide a live table behind an unresolved one.

Only valid in a ``GROUP BY table_full_name`` over ``table_catalog``.
"""


def lifecycle_cte(db: DatabricksWarehousePool, *, alias: str = "life") -> str:
    """CTE giving the three lifecycle fields per ``table_full_name``.

    For the queries that do not already read ``table_catalog`` and cannot borrow
    its columns from an existing CTE.
    """
    return f"""{alias} AS (
        SELECT
            table_full_name,{LIFECYCLE_AGGREGATES}
        FROM {db.table(GOLD_TABLE_CATALOG)}
        WHERE table_full_name IS NOT NULL
        GROUP BY table_full_name
    )"""


def lifecycle_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    """The three lifecycle fields of a table-grain row, always present.

    A table absent from the catalogue yields ``UNKNOWN``/``false`` rather than
    ``null``: the contract of spec 027 forbids a null ``is_deleted``, because a
    reader cannot tell a missing flag from "not deleted" (contracts/
    api-include-deleted.md). ``is_deleted`` is authoritative — gold derives it as
    ``lifecycle_state = 'DELETED'``.
    """
    deleted = bool(row.get("is_deleted"))
    state = str(row.get("lifecycle_state") or "").upper()
    if deleted:
        state = "DELETED"
    elif state != "ACTIVE":
        state = "UNKNOWN"
    return {
        "is_deleted": deleted,
        "deleted_at": iso(row.get("deleted_at")),
        "lifecycle_state": state,
    }


async def table_lifecycle(db: DatabricksWarehousePool, table_full_name: str) -> dict[str, Any]:
    """Lifecycle fields of a single table, for the two table-grain drill-downs.

    A name unknown to the catalogue yields ``UNKNOWN``/``false`` rather than an
    error: the drill-down describes observed usage, which can outlive the registry.
    """
    row = await guarded(
        db,
        db.fetchone(
            f"""
            SELECT{LIFECYCLE_AGGREGATES}
            FROM {db.table(GOLD_TABLE_CATALOG)}
            WHERE table_full_name = ?
            GROUP BY table_full_name
            """,
            table_full_name,
        ),
        tables=[GOLD_TABLE_CATALOG],
    )
    return lifecycle_fields(row or {})


def search_condition(search: str | None, *, columns: Sequence[str]) -> tuple[list[str], list[Any]]:
    term = (search or "").strip().lower()
    if not term:
        return [], []
    pattern = f"%{term}%"
    ors = " OR ".join(f"LOWER({column}) LIKE ?" for column in columns)
    return [f"({ors})"], [pattern] * len(columns)


def where_clause(conditions: Sequence[str]) -> str:
    return ("WHERE " + " AND ".join(conditions)) if conditions else ""


def severity_order_sql(column: str) -> str:
    """Rank severities highest-first, case-insensitively (FR-015).

    ``table_governance`` writes them lowercase and ``recommendations`` uppercase;
    an ``ORDER BY severity`` would interleave the two vocabularies.
    """
    return (
        f"CASE UPPER({column}) WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 3 ELSE 4 END"
    )


def offset_of(page: int, page_size: int) -> int:
    return (page - 1) * page_size


def page_envelope(
    items: list[dict[str, Any]],
    total: int,
    page: int,
    page_size: int,
    start: date,
    end: date,
) -> dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "period": period_dict(start, end),
    }


def iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def number(value: Any, *, decimals: int | None = None) -> int | float | None:
    """Driver ``Decimal`` → JSON number, ``None`` preserved (SC-005)."""
    result = as_float(value)
    if result is None:
        return None
    if decimals is not None:
        return round(result, decimals)
    return int(result) if result.is_integer() else result


def integer(value: Any) -> int:
    """Counting aggregate → ``int``. Only for ``COUNT``, which is never ``NULL``."""
    result = as_float(value)
    return 0 if result is None else int(result)


def pct_delta(current: Any, previous: Any) -> float | None:
    now = as_float(current)
    before = as_float(previous)
    if now is None or before is None or before <= 0:
        return None
    return round((now - before) / before * 100, 1)


def ratio_pct(numerator: Any, denominator: Any) -> float | None:
    """``numerator / denominator * 100`` — never an average of percentages."""
    top = as_float(numerator)
    bottom = as_float(denominator)
    if top is None or not bottom:
        return None
    return round(top / bottom * 100, 2)


def _missing_table(exc: BaseException, tables: Sequence[str]) -> str | None:
    message = str(exc).upper()
    if "TABLE_OR_VIEW_NOT_FOUND" not in message:
        return None
    for name in tables:
        if name.upper() in message:
            return name
    return tables[0] if tables else None


async def guarded[T](
    db: DatabricksWarehousePool,
    operation: Awaitable[T],
    *,
    tables: Sequence[str],
) -> T:
    """Turn a missing gold table into an explicit 503 instead of a 500 (FR-018).

    An empty page and an absent table must not look alike: the first is a period
    without usage, the second means the usage pipeline never ran.
    """
    try:
        return await operation
    except HTTPException:
        raise
    except Exception as exc:
        missing = _missing_table(exc, tables)
        if missing is None:
            raise
        raise HTTPException(
            status_code=503,
            detail={
                "status": "degraded",
                "database": "available",
                "table": db.table(missing),
                "code": f"{missing}_missing",
                "error": (
                    f"Unity Catalog table {missing} is missing. Run the "
                    "gold_dbx_usage Databricks pipeline before using these endpoints."
                ),
            },
        ) from exc
