"""Dry-run evaluator for admin alert rules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status

from ..config import Settings
from ..db.connection import DatabricksWarehousePool
from ..db.tables import qualified_table

__all__ = ["CONDITION_FIELDS", "evaluate_alert_rule", "validate_alert_condition"]

CONDITION_FIELDS: dict[str, set[str]] = {
    "pipeline": {"failure_rate_pct", "avg_duration_seconds", "run_count"},
    "cluster": {"error_rate_pct", "avg_cpu_utilization_pct", "avg_mem_utilization_pct"},
    "cost": {"cost_usd", "budget_consumed_pct"},
    "security": {"open_alert_count"},
    "governance": {"compliance_score_pct"},
}
CONDITION_OPERATORS = {"gt", "lt", "gte", "lte", "eq"}


def validate_alert_condition(metric_domain: str, condition_field: str, operator: str) -> None:
    if metric_domain not in CONDITION_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported metric_domain: {metric_domain}",
        )
    if condition_field not in CONDITION_FIELDS[metric_domain]:
        allowed = ", ".join(sorted(CONDITION_FIELDS[metric_domain]))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported condition_field for {metric_domain}; allowed: {allowed}",
        )
    if operator not in CONDITION_OPERATORS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="condition_operator must be one of eq, gt, gte, lt, lte",
        )


def _comparison(measured_value: float | None, operator: str, threshold: float) -> bool:
    if measured_value is None:
        return False
    if operator == "gt":
        return measured_value > threshold
    if operator == "gte":
        return measured_value >= threshold
    if operator == "lt":
        return measured_value < threshold
    if operator == "lte":
        return measured_value <= threshold
    return measured_value == threshold


def _source_query(settings: Settings, metric_domain: str, condition_field: str) -> tuple[str, str]:
    if metric_domain == "pipeline":
        table = qualified_table(settings, "curated_pipeline_metrics")
        if condition_field == "failure_rate_pct":
            return table, (
                "AVG(CASE WHEN LOWER(status) IN ('failed', 'error') "
                "THEN 100.0 ELSE 0.0 END)"
            )
        if condition_field == "avg_duration_seconds":
            return table, "AVG(duration_seconds)"
        return table, "COUNT(*)"

    if metric_domain == "cluster":
        table = qualified_table(settings, "curated_compute_metrics")
        if condition_field == "error_rate_pct":
            return table, (
                "AVG(CASE WHEN LOWER(state) IN ('error', 'failed') "
                "THEN 100.0 ELSE 0.0 END)"
            )
        return table, f"AVG({condition_field})"

    if metric_domain == "cost":
        table = qualified_table(settings, "curated_cost_metrics")
        if condition_field == "cost_usd":
            return table, "SUM(cost_usd)"
        return table, "AVG(budget_consumed_pct)"

    if metric_domain == "security":
        table = qualified_table(settings, "curated_security_alerts")
        return table, "COUNT(*)"

    table = qualified_table(settings, "gold_standard_check_score")
    return table, (
        "AVG(CASE WHEN total_checks > 0 "
        "THEN compliant_count / total_checks * 100 ELSE NULL END)"
    )


async def evaluate_alert_rule(
    db: DatabricksWarehousePool,
    settings: Settings,
    rule: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate an existing rule and return dry-run firing details."""
    validate_alert_condition(
        rule["metric_domain"],
        rule["condition_field"],
        rule["condition_operator"],
    )
    table, expression = _source_query(settings, rule["metric_domain"], rule["condition_field"])
    lz_ids = rule.get("applies_to_lz_ids") or []
    where_clauses = ["collected_at >= current_timestamp() - make_interval(0, 0, 0, 0, ?)"]
    params: list[Any] = [int(rule["eval_window_hours"])]
    if rule["metric_domain"] == "security":
        where_clauses = ["detected_at >= current_timestamp() - make_interval(0, 0, 0, 0, ?)"]
    elif rule["metric_domain"] == "cost":
        where_clauses = ["period_end >= current_date() - ?"]
    elif rule["metric_domain"] == "governance":
        where_clauses = ["evaluation_date >= current_date() - ?"]
    if lz_ids:
        placeholders = ", ".join("?" for _ in lz_ids)
        where_clauses.append(f"source_lz_id IN ({placeholders})")
        params.extend(lz_ids)

    rows = await db.fetchall(
        f"""
        SELECT source_lz_id, {expression} AS measured_value
        FROM {table}
        WHERE {" AND ".join(where_clauses)}
        GROUP BY source_lz_id
        ORDER BY source_lz_id
        """,
        *params,
    )
    threshold = float(rule["condition_threshold"])
    by_landing_zone = [
        {
            "lz_id": row["source_lz_id"],
            "measured_value": (
                float(row["measured_value"]) if row["measured_value"] is not None else None
            ),
            "would_fire": _comparison(
                float(row["measured_value"]) if row["measured_value"] is not None else None,
                rule["condition_operator"],
                threshold,
            ),
        }
        for row in rows
    ]
    firing_values = [row["measured_value"] for row in by_landing_zone if row["would_fire"]]
    measured_value = max(firing_values) if firing_values else None
    return {
        "rule_id": rule["id"],
        "would_fire": bool(firing_values),
        "measured_value": measured_value,
        "threshold": threshold,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "by_landing_zone": by_landing_zone,
    }
