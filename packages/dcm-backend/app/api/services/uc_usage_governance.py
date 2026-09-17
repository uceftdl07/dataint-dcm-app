"""Governance registry and recommendations — snapshot gold tables.

``table_governance``, ``table_catalog`` and ``recommendations`` carry no
``period_start``: they describe the catalogue as it stands today, so no endpoint
here takes a period. Recommendations are always read at ``status='OPEN'`` and are
never de-duplicated by ``(object_id, category)`` — a reopened anomaly is a new
row on purpose (FR-013).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...db.connection import DatabricksWarehousePool
from .uc_usage_common import (
    GOLD_RECOMMENDATIONS,
    GOLD_TABLE_CATALOG,
    GOLD_TABLE_GOVERNANCE,
    deleted_flag_conditions,
    deleted_table_join,
    integer,
    iso,
    lifecycle_fields,
    number,
    object_filters,
    object_id_filters,
    offset_of,
    search_condition,
    severity_order_sql,
    where_clause,
)
from .uc_usage_common import guarded as _guarded
from .uc_usage_governance_scope import (
    AGE_BUCKET_SQL,
    GovernanceSignal,
    InactivityBucket,
    MissingTag,
    RecommendationAgeBucket,
    governance_scope,
    registry_focus_conditions,
)

__all__ = [
    "fetch_attention",
    "fetch_governance_kpis",
    "fetch_governance_registry",
    "fetch_recommendations",
]

_REGISTRY_SORT_SQL: dict[str, str] = {
    "severity": f"{severity_order_sql('gov.severity')} ASC, gov.downstream_fanout DESC NULLS LAST",
    "table_name": "gov.table_full_name ASC",
    "fanout": "gov.downstream_fanout DESC NULLS LAST",
}

# Alias of the recommendations table in the two queries built from
# :func:`_recommendation_scope`. The deleted-table exclusion joins on it.
_RECOMMENDATION_ALIAS = "rec"

_RECOMMENDATION_COLUMNS = """
    recommendation_id,
    cloud_provider,
    object_type,
    object_id,
    object_name,
    category,
    mode,
    title,
    detail,
    recommended_action,
    estimated_savings_usd,
    severity,
    personas,
    status,
    first_seen_date,
    last_seen_date,
    datediff(current_date(), first_seen_date) AS age_days
"""


def _personas(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _recommendation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "recommendation_id": row["recommendation_id"],
        "cloud_provider": row["cloud_provider"],
        "object_type": row["object_type"],
        "object_id": row["object_id"],
        "object_name": row["object_name"],
        "category": row["category"],
        "mode": row["mode"],
        "title": row["title"],
        "detail": row["detail"],
        "recommended_action": row["recommended_action"],
        # NULL outside the LIFECYCLE "unused" rule — no savings can be estimated
        # for the four other categories (FR-014).
        "estimated_savings_usd": number(row["estimated_savings_usd"], decimals=2),
        "severity": row["severity"],
        "personas": _personas(row["personas"]),
        "status": row["status"],
        "first_seen_date": iso(row["first_seen_date"]),
        "last_seen_date": iso(row["last_seen_date"]),
        "age_days": number(row.get("age_days")),
    }


@dataclass(frozen=True)
class _RecommendationScope:
    """The three SQL fragments both recommendation queries share.

    ``cte`` and ``source`` and not just a list of conditions, because the
    deleted-table exclusion is a join: see :func:`_recommendation_scope`.
    """

    cte: str
    source: str
    conditions: list[str]
    params: list[Any]


def _recommendation_scope(
    db: DatabricksWarehousePool,
    *,
    catalog: str | None,
    schema: str | None,
    tables: list[str] | None,
    category: str | None,
    object_type: str | None,
    include_deleted: bool = False,
) -> _RecommendationScope:
    """Common FROM and WHERE for the recommendations table, severity excluded on purpose.

    The severity filter is applied by the caller only to the listing, never to the
    High/Medium/Total counters: filtering on ``HIGH`` must not zero the Medium KPI.

    Callers must splice all of :attr:`cte`, :attr:`source` and :attr:`conditions`
    into their query. The deleted-table exclusion cannot be a plain predicate here:
    it has to be nested in a disjunction, where a subquery is evaluated row by row
    instead of being planned as an anti-join — so it is a ``LEFT JOIN`` carried by
    ``source`` instead (SC-007).
    """
    alias = _RECOMMENDATION_ALIAS
    conditions: list[str] = [f"UPPER({alias}.status) = 'OPEN'"]
    params: list[Any] = []

    if category:
        conditions.append(f"UPPER({alias}.category) = ?")
        params.append(category.strip().upper())
    if object_type:
        conditions.append(f"UPPER({alias}.object_type) = ?")
        params.append(object_type.strip().upper())

    # FR-011: the catalogue filter identifies tables, so it can only narrow
    # DATA_PRODUCT rows. CONSUMER rows carry an identity in ``object_id`` and stay
    # visible — filtering them out would silently drop half the recommendations.
    object_conditions, object_params = object_id_filters(
        catalog, schema, tables, column=f"{alias}.object_id"
    )
    if object_conditions:
        conditions.append(
            f"(UPPER({alias}.object_type) <> 'DATA_PRODUCT' OR ("
            + " AND ".join(object_conditions)
            + "))"
        )
        params.extend(object_params)

    # Same reasoning for the deleted-table exclusion: it identifies a table, so it
    # can only narrow DATA_PRODUCT rows. A CONSUMER recommendation survives it.
    exclusion = deleted_table_join(db, include_deleted, column=f"{alias}.object_id")
    conditions.extend(
        f"(UPPER({alias}.object_type) <> 'DATA_PRODUCT' OR {predicate})"
        for predicate in exclusion.conditions
    )

    return _RecommendationScope(
        cte=exclusion.cte,
        source=f"{db.table(GOLD_RECOMMENDATIONS)} AS {alias} {exclusion.join}".rstrip(),
        conditions=conditions,
        params=params,
    )


async def fetch_recommendations(
    db: DatabricksWarehousePool,
    *,
    catalog: str | None = None,
    schema: str | None = None,
    tables: list[str] | None = None,
    category: str | None = None,
    severity: str | None = None,
    object_type: str | None = None,
    age_bucket: RecommendationAgeBucket | None = None,
    sort: str = "savings",
    page: int = 1,
    page_size: int = 25,
    include_deleted: bool = False,
) -> dict[str, Any]:
    """Paginated OPEN recommendations plus the High/Medium/Total counters."""
    scope = _recommendation_scope(
        db,
        catalog=catalog,
        schema=schema,
        tables=tables,
        category=category,
        object_type=object_type,
        include_deleted=include_deleted,
    )

    counts = await _guarded(
        db,
        db.fetchone(
            f"""
            {scope.cte}
            SELECT
                COUNT_IF(UPPER(severity) = 'HIGH') AS open_high,
                COUNT_IF(UPPER(severity) = 'MEDIUM') AS open_medium,
                COUNT(*) AS open_total,
                SUM(estimated_savings_usd) AS estimated_savings_usd
            FROM {scope.source}
            {where_clause(scope.conditions)}
            """,
            *scope.params,
        ),
        tables=[GOLD_RECOMMENDATIONS, GOLD_TABLE_CATALOG],
    )

    conditions = list(scope.conditions)
    params = list(scope.params)
    if severity:
        conditions.append("UPPER(severity) = ?")
        params.append(severity.strip().upper())
    if age_bucket:
        conditions.append(f"({AGE_BUCKET_SQL}) = ?")
        params.append(age_bucket)

    where = where_clause(conditions)
    total = await _guarded(
        db,
        db.fetchscalar(f"{scope.cte} SELECT COUNT(*) FROM {scope.source} {where}", *params),
        tables=[GOLD_RECOMMENDATIONS, GOLD_TABLE_CATALOG],
    )

    rows = await _guarded(
        db,
        db.fetchall(
            f"""
            {scope.cte}
            SELECT {_RECOMMENDATION_COLUMNS}
            FROM {scope.source}
            {where}
            ORDER BY {severity_order_sql("severity")} ASC,
                     {"age_days DESC NULLS LAST," if sort == "age" else ""}
                     estimated_savings_usd DESC NULLS LAST,
                     last_seen_date DESC, recommendation_id
            LIMIT ? OFFSET ?
            """,
            *params,
            page_size,
            offset_of(page, page_size),
        ),
        tables=[GOLD_RECOMMENDATIONS, GOLD_TABLE_CATALOG],
    )

    summary = counts or {}
    return {
        "items": [_recommendation(row) for row in rows],
        "total": integer(total),
        "page": page,
        "page_size": page_size,
        "counts": {
            "open_high": integer(summary.get("open_high")),
            "open_medium": integer(summary.get("open_medium")),
            "open_total": integer(summary.get("open_total")),
            # LIFECYCLE "unused" only — the label must say so (FR-014).
            "estimated_savings_usd": number(summary.get("estimated_savings_usd"), decimals=2),
        },
    }


async def fetch_attention(
    db: DatabricksWarehousePool,
    *,
    catalog: str | None = None,
    schema: str | None = None,
    tables: list[str] | None = None,
    limit: int = 3,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    """Top OPEN recommendations by severity — the overview "attention" block."""
    scope = _recommendation_scope(
        db,
        catalog=catalog,
        schema=schema,
        tables=tables,
        category=None,
        object_type=None,
        include_deleted=include_deleted,
    )
    rows = await _guarded(
        db,
        db.fetchall(
            f"""
            {scope.cte}
            SELECT {_RECOMMENDATION_COLUMNS}
            FROM {scope.source}
            {where_clause(scope.conditions)}
            ORDER BY {severity_order_sql("severity")} ASC,
                     estimated_savings_usd DESC NULLS LAST,
                     last_seen_date DESC
            LIMIT ?
            """,
            *scope.params,
            limit,
        ),
        tables=[GOLD_RECOMMENDATIONS, GOLD_TABLE_CATALOG],
    )
    return [_recommendation(row) for row in rows]


async def fetch_governance_kpis(
    db: DatabricksWarehousePool,
    *,
    catalog: str | None = None,
    schema: str | None = None,
    tables: list[str] | None = None,
    include_deleted: bool = False,
) -> dict[str, Any]:
    conditions, params = object_filters(catalog, schema, tables)
    # ``tracked_tables`` is the denominator of the whole page: counting a deleted
    # table there would make every "X sur N" disagree with the list below it.
    conditions.extend(deleted_flag_conditions(include_deleted))
    row = await _guarded(
        db,
        db.fetchone(
            f"""
            SELECT
                COUNT_IF(is_unused) AS unused_tables,
                COUNT_IF(is_stale_but_consumed) AS stale_but_consumed_tables,
                COUNT_IF(is_critical) AS critical_tables,
                COUNT(*) AS tracked_tables
            FROM {db.table(GOLD_TABLE_GOVERNANCE)}
            {where_clause(conditions)}
            """,
            *params,
        ),
        tables=[GOLD_TABLE_GOVERNANCE],
    )
    summary = row or {}
    return {
        "unused_tables": integer(summary.get("unused_tables")),
        "stale_but_consumed_tables": integer(summary.get("stale_but_consumed_tables")),
        "critical_tables": integer(summary.get("critical_tables")),
        "tracked_tables": integer(summary.get("tracked_tables")),
    }


async def count_unused_tables(
    db: DatabricksWarehousePool,
    *,
    catalog: str | None = None,
    schema: str | None = None,
    tables: list[str] | None = None,
    include_deleted: bool = False,
) -> int:
    """``unused_tables`` for the overview KPI — a snapshot, period-insensitive."""
    conditions, params = object_filters(catalog, schema, tables)
    conditions.extend(deleted_flag_conditions(include_deleted))
    value = await _guarded(
        db,
        db.fetchscalar(
            f"""
            SELECT COUNT_IF(is_unused)
            FROM {db.table(GOLD_TABLE_GOVERNANCE)}
            {where_clause(conditions)}
            """,
            *params,
        ),
        tables=[GOLD_TABLE_GOVERNANCE],
    )
    return integer(value)


async def fetch_governance_registry(
    db: DatabricksWarehousePool,
    *,
    catalog: str | None = None,
    schema: str | None = None,
    tables: list[str] | None = None,
    search: str | None = None,
    signal: GovernanceSignal | None = None,
    inactivity: InactivityBucket | None = None,
    missing_tag: MissingTag | None = None,
    sort: str = "severity",
    page: int = 1,
    page_size: int = 25,
    include_deleted: bool = False,
) -> dict[str, Any]:
    catalog_cte, scope_params = governance_scope(
        db, catalog, schema, tables, include_deleted=include_deleted
    )
    conditions = registry_focus_conditions(signal, inactivity, missing_tag)
    search_conditions, search_params = search_condition(search, columns=["gov.table_full_name"])
    conditions.extend(search_conditions)
    params = [*scope_params, *search_params]
    where = where_clause(conditions)

    total = await _guarded(
        db,
        db.fetchscalar(f"{catalog_cte} SELECT COUNT(*) FROM scoped gov {where}", *params),
        tables=[GOLD_TABLE_GOVERNANCE, GOLD_TABLE_CATALOG],
    )

    order_by = _REGISTRY_SORT_SQL.get(sort, _REGISTRY_SORT_SQL["severity"])
    rows = await _guarded(
        db,
        db.fetchall(
            f"""
            {catalog_cte}
            SELECT
                gov.cloud_provider,
                gov.table_full_name,
                gov.`catalog` AS catalog,
                gov.`schema` AS schema,
                gov.table_name,
                gov.table_type,
                gov.owner,
                gov.last_operation,
                gov.last_operation_at,
                gov.last_operation_by,
                gov.downstream_fanout,
                gov.days_since_last_read,
                gov.is_unused,
                gov.is_orphan,
                gov.is_stale_but_consumed,
                gov.is_critical,
                gov.recommended_action,
                gov.severity,
                gov.is_deleted,
                gov.deleted_at,
                gov.lifecycle_state
            FROM scoped gov
            {where}
            ORDER BY {order_by}, gov.table_full_name ASC, gov.cloud_provider
            LIMIT ? OFFSET ?
            """,
            *params,
            page_size,
            offset_of(page, page_size),
        ),
        tables=[GOLD_TABLE_GOVERNANCE, GOLD_TABLE_CATALOG],
    )

    items = [
        {
            "cloud_provider": row.get("cloud_provider"),
            "table_full_name": row["table_full_name"],
            "catalog": row["catalog"],
            "schema": row["schema"],
            "table_name": row["table_name"],
            "table_type": row["table_type"],
            # NULL, never "": the UI shows "Non renseigné" for a missing UC tag,
            # which an empty string would render as a blank cell instead (FR-012).
            "owner": row["owner"],
            "last_operation": row["last_operation"],
            "last_operation_at": iso(row["last_operation_at"]),
            "last_operation_by": row["last_operation_by"],
            "downstream_fanout": number(row["downstream_fanout"]),
            "days_since_last_read": number(row["days_since_last_read"]),
            "is_unused": row["is_unused"],
            "is_orphan": row["is_orphan"],
            "is_stale_but_consumed": row["is_stale_but_consumed"],
            "is_critical": row["is_critical"],
            "recommended_action": row["recommended_action"],
            "severity": row["severity"],
            # Straight from ``table_governance``, which propagates the three
            # columns from the catalogue: no join to add here.
            **lifecycle_fields(row),
        }
        for row in rows
    ]

    return {
        "items": items,
        "total": integer(total),
        "page": page,
        "page_size": page_size,
    }
