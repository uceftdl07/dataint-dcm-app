"""Shared snapshot scope and drill-down predicates for governance charts/lists."""

from __future__ import annotations

from typing import Any, Literal

from ...db.connection import DatabricksWarehousePool
from .uc_usage_common import (
    GOLD_TABLE_CATALOG,
    GOLD_TABLE_GOVERNANCE,
    deleted_flag_conditions,
    object_filters,
    where_clause,
)

GovernanceSignal = Literal["unused", "stale", "critical", "orphan", "unused_critical"]
InactivityBucket = Literal["0_7", "8_30", "31_90", "over_90", "unobserved"]
MissingTag = Literal["owner", "domain", "cost_center", "classification"]
RecommendationAgeBucket = Literal["0_7", "8_30", "31_90", "over_90", "unknown"]

SIGNALS = {
    "unused": "is_unused",
    "stale": "is_stale_but_consumed",
    "critical": "is_critical",
    "orphan": "is_orphan",
    "unused_critical": "(is_unused AND is_critical)",
}
INACTIVITY = {
    "0_7": "days_since_last_read BETWEEN 0 AND 7",
    "8_30": "days_since_last_read BETWEEN 8 AND 30",
    "31_90": "days_since_last_read BETWEEN 31 AND 90",
    "over_90": "days_since_last_read > 90",
    "unobserved": "days_since_last_read IS NULL",
}
TAGS = {
    "owner": "has_owner_tag",
    "domain": "has_domain_tag",
    "cost_center": "has_cost_center_tag",
    "classification": "has_classification_tag",
}
AGE_BUCKET_SQL = """CASE
    WHEN first_seen_date IS NULL OR first_seen_date > current_date() THEN 'unknown'
    WHEN datediff(current_date(), first_seen_date) <= 7 THEN '0_7'
    WHEN datediff(current_date(), first_seen_date) <= 30 THEN '8_30'
    WHEN datediff(current_date(), first_seen_date) <= 90 THEN '31_90'
    ELSE 'over_90' END"""


def governance_scope(
    db: DatabricksWarehousePool,
    catalog: str | None,
    schema: str | None,
    tables: list[str] | None,
    *,
    include_deleted: bool = False,
) -> tuple[str, list[Any]]:
    """One row per Gold governance identity, including its cloud.

    Keep both clouds in scope. Join metadata on the complete identity, so the
    owner/classification of a namesake in another cloud cannot leak into a row.
    NULL classification coverage means the catalogue row was not resolved.

    Both tables carry ``is_deleted`` — ``table_governance`` propagates it from the
    catalogue — so the exclusion is a plain predicate on each side rather than the
    anti-join the fact tables need. Filtering ``cat`` as well as ``gov`` keeps a
    deleted namesake from supplying the metadata of a live row.
    """
    conditions, params = object_filters(catalog, schema, tables)
    conditions.extend(deleted_flag_conditions(include_deleted))
    where = where_clause(conditions)
    return (
        f"""WITH cat AS (
            SELECT cloud_provider, table_full_name, table_type,
                NULLIF(TRIM(owner), '') AS owner, classification,
                last_operation, last_operation_at, last_operation_by
            FROM {db.table(GOLD_TABLE_CATALOG)}
            {where}
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY cloud_provider, table_full_name
                ORDER BY _generated_at DESC, last_operation_at DESC NULLS LAST
            ) = 1
        ), scoped AS (
            SELECT gov.*, cat.table_type, cat.owner,
                cat.last_operation, cat.last_operation_at, cat.last_operation_by,
                CASE WHEN cat.table_full_name IS NOT NULL
                    THEN cat.classification IS NOT NULL ELSE NULL
                END AS has_classification_tag
            FROM (
                SELECT * FROM {db.table(GOLD_TABLE_GOVERNANCE)} {where}
            ) gov
            LEFT JOIN cat ON cat.table_full_name = gov.table_full_name
                AND cat.cloud_provider = gov.cloud_provider
        )""",
        [*params, *params],
    )


def registry_focus_conditions(
    signal: GovernanceSignal | None,
    inactivity: InactivityBucket | None,
    missing_tag: MissingTag | None,
) -> list[str]:
    """Only enum-selected SQL; no caller-supplied identifiers/interpolation."""
    conditions = []
    if signal:
        conditions.append(SIGNALS[signal])
    if inactivity:
        conditions.append(INACTIVITY[inactivity])
    if missing_tag:
        conditions.append(f"{TAGS[missing_tag]} = FALSE")
    return conditions
