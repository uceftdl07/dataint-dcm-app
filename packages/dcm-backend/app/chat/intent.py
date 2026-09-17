"""Natural-language intent detection for Talk-to-Data (Phase 0 regex router)."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

ChatIntent = Literal[
    "costs",
    "pipelines",
    "security",
    "governance",
    "data-product-usage",
    "compute",
    "databases",
    "overview",
    "unsupported",
]

_THINKING_STEPS: dict[ChatIntent, list[str]] = {
    "costs": [
        "Checking cost summary...",
        "Comparing services by cloud...",
        "Preparing the FinOps summary...",
    ],
    "pipelines": [
        "Checking failed pipeline runs...",
        "Ranking recent failures...",
        "Summarizing main errors...",
    ],
    "security": [
        "Checking security alerts...",
        "Filtering active alerts...",
        "Summarizing main risks...",
    ],
    "governance": [
        "Checking compliance score...",
        "Reviewing standard checks...",
        "Summarizing non-compliant checks...",
    ],
    "data-product-usage": [
        "Checking data product usage...",
        "Ranking top consumers...",
        "Summarizing main usage patterns...",
    ],
    "compute": [
        "Checking compute resources...",
        "Analyzing compute states...",
        "Summarizing active resources...",
    ],
    "databases": [
        "Checking database inventory...",
        "Checking availability and capacity...",
        "Summarizing databases to monitor...",
    ],
    "overview": [
        "Checking platform overview...",
        "Aggregating key KPIs...",
        "Preparing the global summary...",
    ],
    "unsupported": [
        "Analyzing the request...",
        "Querying DCM data...",
        "Preparing supported suggestions...",
    ],
}


def _normalize_query(query: str) -> str:
    lowered = query.lower()
    normalized = unicodedata.normalize("NFD", lowered)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def detect_intent(query: str) -> ChatIntent:
    """Map a user question to a supported DCM data domain."""
    normalized = _normalize_query(query)

    if re.search(r"(security|alert|vulnerability|risk|defender|mfa)", normalized):
        return "security"
    if re.search(r"(governance|compliance|standard|check|landing zone|score)", normalized):
        return "governance"
    if re.search(r"(data product|data products|usage|consumer|consumption)", normalized):
        return "data-product-usage"
    if re.search(r"(cluster|clusters|compute|databricks|emr|compute resource|compute resources)", normalized):
        return "compute"
    if re.search(r"(database|databases|db|sql|rds|postgres|mysql|cosmos|redshift)", normalized):
        return "databases"
    if re.search(
        r"(pipeline|pipelines|tuyau|flux|job|jobs|glue|adf|data factory|"
        r"failed|failure|failing|failures|fail|echec|echou|en panne|"
        r"(azure|aws).{0,30}(pipeline|job|fail)|"
        r"(pipeline|job|fail).{0,30}(azure|aws))",
        normalized,
    ):
        return "pipelines"
    if re.search(r"(cost|costs|finops|budget|spend|spending)", normalized):
        return "costs"
    if re.search(r"(overview|global|summary|platform|dashboard|kpi|state|status)", normalized):
        return "overview"

    return "unsupported"


def get_thinking_steps(intent: ChatIntent) -> list[str]:
    return list(_THINKING_STEPS[intent])
