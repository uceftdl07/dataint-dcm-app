"""Template answers for Talk-to-Data (Phase 0 — no LLM)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .intent import ChatIntent

LIVE_SOURCE_LABEL = "DCM API"


@dataclass(frozen=True)
class TemplateAnswer:
    text: str
    source_label: str
    sources: list[str]


def _format_currency(value: float) -> str:
    return f"${value:,.0f}"


def _format_number(value: int | float) -> str:
    return f"{value:,.0f}"


def _top_lines(items: list[Any], formatter, empty_text: str) -> str:
    if not items:
        return empty_text
    return "\n".join(formatter(item, index) for index, item in enumerate(items[:5], start=1))


def build_answer(intent: ChatIntent, data: dict[str, Any]) -> TemplateAnswer:
    builders = {
        "costs": _build_cost_answer,
        "pipelines": _build_pipeline_answer,
        "security": _build_security_answer,
        "governance": _build_governance_answer,
        "data-product-usage": _build_data_product_usage_answer,
        "compute": _build_compute_answer,
        "databases": _build_databases_answer,
        "overview": _build_overview_answer,
    }
    builder = builders.get(intent)
    if builder is None:
        return build_unsupported_answer()
    return builder(data)


def build_unsupported_answer() -> TemplateAnswer:
    return TemplateAnswer(
        source_label="DataIQ",
        sources=[],
        text="""I cannot answer this question with the current DCM data connectors.

Try a question about :
• multi-cloud costs ;
• failed pipelines ;
• security alerts ;
• governance and standard checks ;
• data product usage ;
• clusters and compute resources ;
• databases ;
• the global DCM platform overview.""",
    )


def build_api_error_answer() -> TemplateAnswer:
    return TemplateAnswer(
        source_label="Error API",
        sources=[],
        text="""I cannot reach the DCM APIs for this request.

Check that the backend is running and the frontend proxy points to the expected API. The conversation remains available to retry later.""",
    )


def _build_cost_answer(data: dict[str, Any]) -> TemplateAnswer:
    summary = data["summary"]
    by_service = data["by_service"]
    cloud_lines = (
        "\n".join(
            f"    • {cloud.upper()} : {_format_currency(total)}"
            for cloud, total in summary["by_cloud"].items()
        )
        or "    No cloud breakdown available."
    )
    service_lines = _top_lines(
        by_service["items"],
        lambda service, index: (
            f"  {index}. {service['service_name']} ({service['cloud_provider']}) : "
            f"{_format_currency(service['total_cost_usd'])}"
        ),
        "  No cost service found over the period.",
    )
    return TemplateAnswer(
        source_label=LIVE_SOURCE_LABEL,
        sources=["/api/v1/costs/summary", "/api/v1/costs/by-service"],
        text=f"""FinOps summary from DCM APIs :

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰  Total period : {_format_currency(summary['total_usd'])}

Breakdown by cloud :
{cloud_lines}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊  Top services
{service_lines}

Analyzed period : {summary['period']['start']} → {summary['period']['end']}""",
    )


def _format_pipeline_item(pipeline: dict[str, Any], index: int) -> str:
    return (
        f"  {index}. {pipeline['pipeline_name']}\n"
        f"     Start : {pipeline['start_time'] or 'n/a'}\n"
        f"     Error : {pipeline['error_message'] or 'Not provided'}"
    )


def _pipeline_lines_by_cloud(items: list[dict[str, Any]]) -> str:
    if not items:
        return "  No failed pipeline found in the returned data."

    by_cloud: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        cloud = str(item.get("cloud_provider") or "unknown").lower()
        by_cloud.setdefault(cloud, []).append(item)

    sections: list[str] = []
    for cloud in ("azure", "aws"):
        cloud_items = by_cloud.pop(cloud, [])
        if cloud_items:
            lines = "\n".join(_format_pipeline_item(p, i) for i, p in enumerate(cloud_items, start=1))
            sections.append(f"☁️  {cloud.upper()}\n{lines}")
        else:
            sections.append(f"☁️  {cloud.upper()}\n  ✅  No failed pipeline in the latest data.")

    for cloud, cloud_items in sorted(by_cloud.items()):
        lines = "\n".join(_format_pipeline_item(p, i) for i, p in enumerate(cloud_items, start=1))
        sections.append(f"☁️  {cloud.upper()}\n{lines}")

    return "\n\n".join(sections)


def _build_pipeline_answer(data: dict[str, Any]) -> TemplateAnswer:
    pipelines = data["pipelines"]
    pipeline_lines = _pipeline_lines_by_cloud(pipelines["items"])
    return TemplateAnswer(
        source_label=LIVE_SOURCE_LABEL,
        sources=["/api/v1/pipelines?status=failed"],
        text=f"""Failed pipeline state :

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴  Failures found : {_format_number(pipelines['total'])}

{pipeline_lines}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡  Priority: handle recurring or blocking errors on critical flows first.""",
    )


def _build_security_answer(data: dict[str, Any]) -> TemplateAnswer:
    alerts = data["security"]
    alert_lines = _top_lines(
        alerts["items"],
        lambda alert, index: (
            f"  {index}. {alert['title']} ({alert['severity']}, {alert['cloud_provider']})\n"
            f"     Resource : {alert['resource_type'] or 'n/a'}\n"
            f"     Detected : {alert['detected_at']}"
        ),
        "  No active alert found in the returned data.",
    )
    return TemplateAnswer(
        source_label=LIVE_SOURCE_LABEL,
        sources=["/api/v1/security/alerts?status=active"],
        text=f"""Security audit :

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛡️  Active alerts : {_format_number(alerts['total'])}

{alert_lines}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Analysis based on available DCM alerts.""",
    )


def _build_governance_answer(data: dict[str, Any]) -> TemplateAnswer:
    score = data["score"]
    checks = data["checks"]
    check_lines = _top_lines(
        checks["items"],
        lambda check, index: (
            f"  {index}. {check['check_name']} ({check['cloud_provider']})\n"
            f"     Resource : {check['resource_name'] or check['resource_id'] or 'n/a'}\n"
            f"     Type : {check['resource_type'] or 'n/a'}"
        ),
        "  No no-compliant check found in the returned data.",
    )
    return TemplateAnswer(
        source_label=LIVE_SOURCE_LABEL,
        sources=["/api/v1/standard-checks/score", "/api/v1/standard-checks?check_state=non_compliant"],
        text=f"""Summary governance :

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅  Global score : {score['global_score_pct'] or 'n/a'}%
    Compliant checks : {_format_number(score['compliant_count'])}
    Non-compliant checks : {_format_number(score['no_compliant_count'])}
    Total evaluated : {_format_number(score['total_evaluated'])}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  Non-compliance examples
{check_lines}""",
    )


def _build_data_product_usage_answer(data: dict[str, Any]) -> TemplateAnswer:
    overview = data["overview"]
    consumers = data["consumers"]
    consumer_lines = _top_lines(
        consumers["items"],
        lambda consumer, index: (
            f"  {index}. {consumer['consumer_name'] or consumer['consumer_id']} "
            f"({consumer['cloud_provider']}) : "
            f"{_format_number(consumer['request_count'])} requests"
        ),
        "  No consumer found in the returned data.",
    )
    return TemplateAnswer(
        source_label=LIVE_SOURCE_LABEL,
        sources=[
            "/api/v1/data-product-usage/overview",
            "/api/v1/data-product-usage/top-consumers",
        ],
        text=f"""Data product usage :

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦  Data products : {_format_number(overview['total_data_products'])}
    Active consumers : {_format_number(overview['active_consumers'])}
    Requests : {_format_number(overview['request_count'])}
    Associated cost : {_format_currency(overview['cost_usd'])}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊  Top consumers
{consumer_lines}

Analyzed period : {overview['period']['start']} → {overview['period']['end']}""",
    )


def _build_compute_answer(data: dict[str, Any]) -> TemplateAnswer:
    computes = data["compute"]["items"]
    running_count = sum(1 for compute in computes if compute["state"] == "running")
    error_count = sum(1 for compute in computes if compute["state"] == "error")
    compute_lines = _top_lines(
        computes,
        lambda compute, index: (
            f"  {index}. {compute['resource_name']} ({compute['cloud_provider']}, {compute['state']})\n"
            f"     Type : {compute['compute_type'] or 'n/a'} · Workers : {compute['num_workers'] or 'n/a'}\n"
            f"     CPU : {compute['avg_cpu_utilization_pct'] or 'n/a'}% · "
            f"Memory : {compute['avg_mem_utilization_pct'] or 'n/a'}%"
        ),
        "  No compute resource found in the returned data.",
    )
    return TemplateAnswer(
        source_label=LIVE_SOURCE_LABEL,
        sources=["/api/v1/clusters"],
        text=f"""Cluster and compute resource state :

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚙️  Tracked resources : {_format_number(len(computes))}
✅  Running : {_format_number(running_count)}
🔴  In error : {_format_number(error_count)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊  Main resources
{compute_lines}""",
    )


def _build_databases_answer(data: dict[str, Any]) -> TemplateAnswer:
    databases = data["databases"]["items"]
    unavailable_count = sum(1 for database in databases if not database["is_available"])
    database_lines = _top_lines(
        databases,
        lambda database, index: (
            f"  {index}. {database['db_name'] or database['db_id']} "
            f"({database['db_type']}, {database['cloud_provider']})\n"
            f"     Available : {'yes' if database['is_available'] else 'no'} · "
            f"Connections : {database['active_connections'] or 'n/a'}\n"
            f"     Storage : {database['storage_used_gb'] or 'n/a'} / "
            f"{database['storage_limit_gb'] or 'n/a'} Go"
        ),
        "  No database found in the returned data.",
    )
    return TemplateAnswer(
        source_label=LIVE_SOURCE_LABEL,
        sources=["/api/v1/databases"],
        text=f"""Database state :

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🗄️  Tracked databases : {_format_number(len(databases))}
✅  Available : {_format_number(len(databases) - unavailable_count)}
🔴  Unavailable : {_format_number(unavailable_count)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊  Databases to monitor
{database_lines}""",
    )


def _build_overview_answer(data: dict[str, Any]) -> TemplateAnswer:
    overview = data["overview"]
    return TemplateAnswer(
        source_label=LIVE_SOURCE_LABEL,
        sources=["/api/v1/dashboard/overview"],
        text=f"""DCM global overview :

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊  Pipelines over the period : {_format_number(overview['total_pipelines'])}
🔴  Pipelines failed in 24h : {_format_number(overview['failed_pipelines_24h'])}
⚙️  Active compute : {_format_number(overview['active_clusters'])}
💰  Cost total : {_format_currency(overview['total_cost_usd'])}
🛡️  Open alerts : {_format_number(overview['open_alerts'])}
☁️  Covered clouds : {', '.join(overview['cloud_coverage']) or 'n/a'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Analyzed period : {overview['period']['start']} → {overview['period']['end']}""",
    )
