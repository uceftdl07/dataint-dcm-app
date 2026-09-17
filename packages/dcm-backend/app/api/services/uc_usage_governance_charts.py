"""Seven governance/recommendation charts over the existing Gold snapshots.

All totals are warehouse aggregates over the entire applied table scope. Only
the scatter and the matrix detail are bounded, with explicit coverage metadata.
Recommendation episodes are counted individually; affected tables use the full
(cloud, qualified name) identity. No historical health/SLA curve is inferred.
"""

from __future__ import annotations

from typing import Any

from ...db.connection import DatabricksWarehousePool
from .uc_usage_common import (
    GOLD_RECOMMENDATIONS,
    GOLD_TABLE_CATALOG,
    GOLD_TABLE_GOVERNANCE,
    deleted_flag_conditions,
    deleted_table_conditions,
    guarded,
    integer,
    iso,
    number,
    object_filters,
    object_id_filters,
    ratio_pct,
    where_clause,
)
from .uc_usage_governance_scope import AGE_BUCKET_SQL, INACTIVITY, TAGS, governance_scope

SCATTER_LIMIT = 300
MATRIX_LIMIT = 25
PRIORITY_LIMIT = 5
GOV_TABLES = [GOLD_TABLE_GOVERNANCE, GOLD_TABLE_CATALOG]
SIGNAL_COUNTS = {
    "unused": "unused_tables",
    "stale": "stale_but_consumed_tables",
    "critical": "critical_tables",
    "orphan": "orphan_tables",
}


async def fetch_governance_charts(
    db: DatabricksWarehousePool,
    *,
    catalog: str | None = None,
    schema: str | None = None,
    tables: list[str] | None = None,
    include_deleted: bool = False,
) -> dict[str, Any]:
    cte, params = governance_scope(db, catalog, schema, tables, include_deleted=include_deleted)
    inactivity_counts = ", ".join(
        f"COUNT_IF({condition}) AS inactivity_{key}" for key, condition in INACTIVITY.items()
    )
    coverage_counts = ", ".join(
        f"COUNT_IF({column}) AS {tag}_present, "
        f"COUNT_IF({column} = FALSE) AS {tag}_missing, "
        f"COUNT_IF({column} IS NULL) AS {tag}_unknown"
        for tag, column in TAGS.items()
    )
    counts_sql = """
        COUNT(*) AS tracked_tables,
        COUNT_IF(is_unused) AS unused_tables,
        COUNT_IF(is_stale_but_consumed) AS stale_but_consumed_tables,
        COUNT_IF(is_critical) AS critical_tables,
        COUNT_IF(is_orphan) AS orphan_tables,
        COUNT_IF(is_unused AND is_critical) AS unused_critical_tables
    """
    summary = (
        await guarded(
            db,
            db.fetchone(
                f"""{cte}
            SELECT {counts_sql}, {inactivity_counts}, {coverage_counts},
                COUNT(DISTINCT named_struct('catalog', `catalog`, 'schema', `schema`))
                    AS schema_count,
                COUNT_IF(days_since_last_read IS NOT NULL AND downstream_fanout IS NOT NULL)
                    AS scatter_total,
                MAX(_generated_at) AS as_of
            FROM scoped""",
                *params,
            ),
            tables=GOV_TABLES,
        )
        or {}
    )

    by_table = integer(summary.get("schema_count")) == 1
    group_columns = (
        "`catalog`, `schema`, cloud_provider, table_full_name, table_name"
        if by_table
        else "`catalog`, `schema`"
    )
    matrix_rows = await guarded(
        db,
        db.fetchall(
            f"""{cte}
            SELECT {group_columns}, {counts_sql},
                COUNT_IF(is_unused OR is_stale_but_consumed OR is_orphan) AS attention_tables
            FROM scoped
            GROUP BY {group_columns}
            ORDER BY unused_critical_tables DESC,
                attention_tables / COUNT(*) DESC, tracked_tables DESC,
                `catalog`, `schema` {", table_full_name, cloud_provider" if by_table else ""}
            LIMIT ?""",
            *params,
            MATRIX_LIMIT,
        ),
        tables=GOV_TABLES,
    )
    points = await guarded(
        db,
        db.fetchall(
            f"""{cte}
            SELECT cloud_provider, table_full_name, `catalog`, `schema`, table_name,
                days_since_last_read, downstream_fanout,
                is_unused, is_critical, is_stale_but_consumed
            FROM scoped
            WHERE days_since_last_read IS NOT NULL AND downstream_fanout IS NOT NULL
            ORDER BY (is_unused AND is_critical) DESC, is_stale_but_consumed DESC,
                is_unused DESC, downstream_fanout DESC, days_since_last_read DESC,
                table_full_name, cloud_provider
            LIMIT ?""",
            *params,
            SCATTER_LIMIT,
        ),
        tables=GOV_TABLES,
    )
    total = integer(summary.get("tracked_tables"))
    return {
        "as_of": iso(summary.get("as_of")),
        "summary": {
            key: integer(summary.get(key))
            for key in ["tracked_tables", *SIGNAL_COUNTS.values(), "unused_critical_tables"]
        },
        "inactivity": [
            {"bucket": key, "count": integer(summary.get(f"inactivity_{key}"))}
            for key in INACTIVITY
        ],
        "tag_coverage": [
            {
                "tag": tag,
                "present_count": integer(summary.get(f"{tag}_present")),
                "missing_count": integer(summary.get(f"{tag}_missing")),
                "unknown_count": integer(summary.get(f"{tag}_unknown")),
                "total_count": total,
                "coverage_pct": (
                    None
                    if integer(summary.get(f"{tag}_unknown")) >= total
                    else ratio_pct(summary.get(f"{tag}_present"), total)
                ),
            }
            for tag in TAGS
        ],
        "matrix": {
            "mode": "table" if by_table else "schema",
            "total_rows": total if by_table else integer(summary.get("schema_count")),
            "limit": MATRIX_LIMIT,
            "rows": [
                {
                    "catalog": row.get("catalog"),
                    "schema": row.get("schema"),
                    "cloud_provider": row.get("cloud_provider"),
                    "table_full_name": row.get("table_full_name"),
                    "table_name": row.get("table_name"),
                    "table_count": integer(row.get("tracked_tables")),
                    "signals": {
                        key: integer(row.get(column)) for key, column in SIGNAL_COUNTS.items()
                    },
                }
                for row in matrix_rows
            ],
        },
        "scatter": {
            "total": integer(summary.get("scatter_total")),
            "limit": SCATTER_LIMIT,
            "unobserved_reads": integer(summary.get("inactivity_unobserved")),
            "points": [
                {
                    **{
                        key: row.get(key)
                        for key in [
                            "cloud_provider",
                            "table_full_name",
                            "catalog",
                            "schema",
                            "table_name",
                            "is_unused",
                            "is_critical",
                            "is_stale_but_consumed",
                        ]
                    },
                    "days_since_last_read": number(row.get("days_since_last_read")),
                    "downstream_fanout": number(row.get("downstream_fanout")),
                }
                for row in points
            ],
        },
    }


async def fetch_recommendation_charts(
    db: DatabricksWarehousePool,
    *,
    catalog: str | None = None,
    schema: str | None = None,
    tables: list[str] | None = None,
    include_deleted: bool = False,
) -> dict[str, Any]:
    conditions, params = object_id_filters(catalog, schema, tables)
    conditions.extend(["UPPER(status) = 'OPEN'", "UPPER(object_type) = 'DATA_PRODUCT'"])
    # Every row here already targets a table, so the exclusion needs no guard on
    # ``object_type`` — unlike the recommendations *list*, which keeps CONSUMER rows.
    conditions.extend(deleted_table_conditions(db, include_deleted, column="object_id"))
    cte = f"""WITH recs AS (
        SELECT *,
            CASE WHEN UPPER(severity) IN ('HIGH', 'MEDIUM', 'LOW')
                THEN UPPER(severity) ELSE 'UNKNOWN' END AS normalized_severity,
            CASE WHEN first_seen_date <= current_date()
                THEN datediff(current_date(), first_seen_date) ELSE NULL END AS age_days,
            {AGE_BUCKET_SQL} AS age_bucket
        FROM {db.table(GOLD_RECOMMENDATIONS)}
        {where_clause(conditions)}
    )"""
    identity = "named_struct('cloud', cloud_provider, 'table', object_id)"
    eligible = "UPPER(category) = 'LIFECYCLE' AND normalized_severity = 'MEDIUM'"
    summary = (
        await guarded(
            db,
            db.fetchone(
                f"""{cte} SELECT
                COUNT(*) AS open_total,
                COUNT_IF(normalized_severity = 'HIGH') AS open_high,
                COUNT_IF(normalized_severity = 'MEDIUM') AS open_medium,
                COUNT(DISTINCT {identity}) AS affected_tables,
                COUNT_IF(normalized_severity = 'HIGH' AND age_days > 30) AS old_high,
                SUM(CASE WHEN {eligible} THEN estimated_savings_usd END) AS reference_cost_usd,
                COUNT(DISTINCT CASE WHEN {eligible} THEN {identity} END) AS cost_candidates,
                COUNT(DISTINCT CASE WHEN {eligible} AND estimated_savings_usd IS NOT NULL
                    THEN {identity} END) AS cost_measured_tables,
                MAX(_generated_at) AS as_of
            FROM recs""",
                *params,
            ),
            tables=[GOLD_RECOMMENDATIONS, GOLD_TABLE_CATALOG],
        )
        or {}
    )
    groups = await guarded(
        db,
        db.fetchall(
            f"""{cte}
            SELECT 'category' AS dimension, UPPER(category) AS bucket,
                normalized_severity AS severity, COUNT(*) AS count
            FROM recs GROUP BY UPPER(category), normalized_severity
            UNION ALL
            SELECT 'age' AS dimension, age_bucket AS bucket,
                normalized_severity AS severity, COUNT(*) AS count
            FROM recs GROUP BY age_bucket, normalized_severity""",
            *params,
        ),
        tables=[GOLD_RECOMMENDATIONS, GOLD_TABLE_CATALOG],
    )
    gov_conditions, gov_params = object_filters(catalog, schema, tables)
    gov_conditions.extend(deleted_flag_conditions(include_deleted))
    priorities = await guarded(
        db,
        db.fetchall(
            f"""{cte}, ranked AS (
                SELECT cloud_provider, object_id,
                    COUNT(*) AS open_total,
                    COUNT_IF(normalized_severity = 'HIGH') AS open_high,
                    COUNT_IF(normalized_severity = 'MEDIUM') AS open_medium,
                    COUNT_IF(normalized_severity = 'LOW') AS open_low,
                    COUNT_IF(normalized_severity = 'UNKNOWN') AS open_unknown,
                    MAX(CASE WHEN normalized_severity = 'HIGH' THEN age_days END)
                        AS oldest_high_days
                FROM recs GROUP BY cloud_provider, object_id
            ), gov AS (
                SELECT cloud_provider, table_full_name, MAX(downstream_fanout) AS fanout
                FROM {db.table(GOLD_TABLE_GOVERNANCE)}
                {where_clause(gov_conditions)}
                GROUP BY cloud_provider, table_full_name
            )
            SELECT ranked.*, gov.fanout AS downstream_fanout
            FROM ranked LEFT JOIN gov ON gov.table_full_name = ranked.object_id
                AND gov.cloud_provider = ranked.cloud_provider
            WHERE open_high > 0
            ORDER BY open_high DESC, oldest_high_days DESC NULLS LAST,
                gov.fanout DESC NULLS LAST, object_id, ranked.cloud_provider
            LIMIT ?""",
            *params,
            *gov_params,
            PRIORITY_LIMIT,
        ),
        tables=[GOLD_RECOMMENDATIONS, GOLD_TABLE_GOVERNANCE],
    )

    def distribution(dimension: str, keys: list[str]) -> list[dict[str, Any]]:
        values: dict[str, dict[str, Any]] = {
            key: {"bucket": key, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0} for key in keys
        }
        for row in groups:
            if row.get("dimension") != dimension:
                continue
            key = str(row.get("bucket") or "UNKNOWN")
            entry = values.setdefault(
                key, {"bucket": key, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
            )
            level = str(row.get("severity") or "UNKNOWN")
            entry[level if level in {"HIGH", "MEDIUM", "LOW"} else "UNKNOWN"] += integer(
                row.get("count")
            )
        return [
            dict(entry, total=sum(entry[level] for level in ["HIGH", "MEDIUM", "LOW", "UNKNOWN"]))
            for entry in values.values()
        ]

    return {
        "as_of": iso(summary.get("as_of")),
        "summary": {
            **{
                key: integer(summary.get(key))
                for key in [
                    "open_total",
                    "open_high",
                    "open_medium",
                    "affected_tables",
                    "old_high",
                    "cost_candidates",
                    "cost_measured_tables",
                ]
            },
            "reference_cost_usd": number(summary.get("reference_cost_usd"), decimals=2),
        },
        "categories": distribution(
            "category", ["LIFECYCLE", "FRESHNESS", "GOVERNANCE", "RELIABILITY"]
        ),
        "ages": distribution("age", ["0_7", "8_30", "31_90", "over_90", "unknown"]),
        "priorities": [
            {
                "cloud_provider": row.get("cloud_provider"),
                "table_full_name": row["object_id"],
                **{
                    key: integer(row.get(key))
                    for key in [
                        "open_total",
                        "open_high",
                        "open_medium",
                        "open_low",
                        "open_unknown",
                    ]
                },
                "oldest_high_days": number(row.get("oldest_high_days")),
                "downstream_fanout": number(row.get("downstream_fanout")),
            }
            for row in priorities
        ],
    }
