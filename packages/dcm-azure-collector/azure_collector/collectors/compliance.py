"""Azure Policy compliance collector — governance posture per subscription.

Queries Azure Policy state via the Policy Insights API to retrieve the
compliance evaluation results of all policy definitions against all resources
in the subscription.

Azure SDK used
--------------
``azure-mgmt-policyinsights`` (synchronous) — wrapped in :func:`run_sync`.

Key API call
------------
``client.policy_states.list_query_results_for_subscription(
    policy_states_resource="latest",
    subscription_id=subscription_id,
    query_options=QueryOptions(filter="complianceState eq 'NonCompliant'", top=1000)
)``

Volume management
-----------------
A subscription with broad policies may have tens of thousands of evaluations.
To manage volume:
- Default: collect only ``NonCompliant`` evaluations.
- Periodic full scan (weekly): set ``non_compliant_only=False`` to collect
  all evaluations for score computation.
- ``max_results`` caps the total number of rows per collection cycle.

Security Score computation
--------------------------
The frontend governance page computes:
  ``score = count(COMPLIANT) / count(COMPLIANT + NON_COMPLIANT) * 100``

For this to work, full scans must be triggered periodically.  The ``tags``
field includes ``{"scope": "non_compliant_only"}`` or ``{"scope": "full_scan"}``
so the backend can distinguish score-capable results from partial results.

Lakebase target
---------------
``dcm.monitoring.standard_checks``
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]
from azure.mgmt.policyinsights import PolicyInsightsClient  # type: ignore[import-untyped]

try:
    from azure.mgmt.policyinsights.models import QueryOptions  # type: ignore[import-untyped]
except ImportError:  # azure-mgmt-policyinsights >= 1.1.0b6
    QueryOptions = None  # type: ignore[misc, assignment]

from dcm_commons.collectors.base import BaseCollector
from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import get_logger
from dcm_commons.models.standard_check import StandardCheckMetric
from dcm_commons.models.enums import CheckEffect, CloudProvider, MetricDomain, StandardCheckState

from azure_collector._azure_utils import run_sync

__all__ = ["StandardCheckCollector"]

_logger = get_logger(__name__)

# Mapping Azure Policy complianceState → DCM StandardCheckState
_COMPLIANCE_STATE_MAP: dict[str, StandardCheckState] = {
    "Compliant": StandardCheckState.COMPLIANT,
    "NonCompliant": StandardCheckState.NON_COMPLIANT,
    "Exempt": StandardCheckState.COMPLIANT,       # Exempt resources are treated as compliant
    "Unknown": StandardCheckState.UNKNOWN,
    "Conflict": StandardCheckState.UNKNOWN,
}

# Mapping Azure Policy effect → DCM CheckEffect
_POLICY_EFFECT_MAP: dict[str, CheckEffect] = {
    "Deny": CheckEffect.DENY,
    "Audit": CheckEffect.AUDIT,
    "AuditIfNotExists": CheckEffect.AUDIT,
    "DeployIfNotExists": CheckEffect.DEPLOY_IF_NOT_EXISTS,
    "Modify": CheckEffect.MODIFY,
    "Disabled": CheckEffect.DISABLED,
}


class StandardCheckCollector(BaseCollector):
    """Collects Azure Policy compliance evaluation results.

    Args:
        source_lz_id:       Landing zone identifier.
        subscription_id:    Azure subscription ID.
        credential:         ``azure.identity`` credential.  If ``None``,
                            ``DefaultAzureCredential`` is used.
        non_compliant_only: When ``True`` (default), collect only
                            ``NonCompliant`` evaluations for efficiency.
                            Set to ``False`` for weekly full scans.
        max_results:        Maximum number of evaluation rows to collect.
                            Defaults to 1 000.
        max_retries:        Retry attempts on transient failures.
        retry_base_delay_seconds: Base delay for exponential back-off.
    """

    def __init__(
        self,
        source_lz_id: str,
        subscription_id: str,
        *,
        credential: Any | None = None,
        non_compliant_only: bool = True,
        max_results: int = 1000,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 2.0,
    ) -> None:
        super().__init__(
            source_lz_id=source_lz_id,
            cloud_provider=CloudProvider.AZURE,
            subscription_or_account_id=subscription_id,
            max_retries=max_retries,
            retry_base_delay_seconds=retry_base_delay_seconds,
        )
        self._subscription_id = subscription_id
        self._credential = credential or DefaultAzureCredential()
        self._non_compliant_only = non_compliant_only
        self._max_results = max_results

    @property
    def domain(self) -> MetricDomain:
        """Return the standard-check metric domain."""
        return MetricDomain.STANDARD_CHECK

    # ------------------------------------------------------------------
    # BaseCollector implementation
    # ------------------------------------------------------------------

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        """Query the Policy Insights API and return compliance metrics."""
        metrics = await run_sync(self._collect_sync)
        return [m.model_dump() for m in metrics]

    def _collect_sync(self) -> list[StandardCheckMetric]:
        client = PolicyInsightsClient(
            credential=self._credential,
            subscription_id=self._subscription_id,
        )

        # Build OData filter
        odata_filter = (
            "complianceState eq 'NonCompliant'"
            if self._non_compliant_only
            else None
        )
        scope_tag = "non_compliant_only" if self._non_compliant_only else "full_scan"

        top = min(self._max_results, 1000)  # API max per page is 1 000

        try:
            if QueryOptions is not None:
                query_options = QueryOptions(filter=odata_filter, top=top)
                pager = client.policy_states.list_query_results_for_subscription(
                    policy_states_resource="latest",
                    subscription_id=self._subscription_id,
                    query_options=query_options,
                )
            else:
                # 1.1.0b6+ — filter/top are keyword args; arg order changed
                pager = client.policy_states.list_query_results_for_subscription(
                    self._subscription_id,
                    "latest",
                    filter=odata_filter,
                    top=top,
                )
            policy_states = list(pager)
        except Exception as exc:
            raise CollectionError(
                f"[StandardCheckCollector] Policy Insights query failed: {exc}"
            ) from exc

        metrics: list[StandardCheckMetric] = []
        now = datetime.now(tz=timezone.utc)

        for state in policy_states[: self._max_results]:
            metric = self._map_policy_state(state, now, scope_tag)
            if metric:
                metrics.append(metric)

        _logger.info(
            "compliance_collected subscription=%s total=%d scope=%s",
            self._subscription_id, len(metrics), scope_tag,
        )
        return metrics

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _map_policy_state(
        state: Any,
        fallback_time: datetime,
        scope_tag: str,
    ) -> StandardCheckMetric | None:
        """Map a single Azure Policy state record to a StandardCheckMetric."""
        check_id: str = getattr(state, "policy_definition_id", None) or ""
        if not check_id:
            return None

        # Extract short name from definition ID
        # e.g. ".../policyDefinitions/Require-StorageHttps" → "Require-StorageHttps"
        check_name = check_id.split("/")[-1]

        raw_compliance: str = getattr(state, "compliance_state", "Unknown") or "Unknown"
        check_state = _COMPLIANCE_STATE_MAP.get(raw_compliance, StandardCheckState.UNKNOWN)

        raw_effect: str | None = None
        policy_def_action = getattr(state, "policy_definition_action", None)
        if policy_def_action:
            raw_effect = policy_def_action.capitalize()
        check_effect = _POLICY_EFFECT_MAP.get(raw_effect or "", None)

        resource_id: str | None = getattr(state, "resource_id", None)
        resource_name: str | None = None
        resource_type: str | None = getattr(state, "resource_type", None)
        if resource_id:
            resource_name = resource_id.split("/")[-1]

        # Compliance reason detail (available for NonCompliant evaluations)
        non_check_reasons: list[str] = []
        compliance_reason = getattr(state, "compliance_reason", None)
        if compliance_reason:
            non_check_reasons.append(str(compliance_reason))

        evaluated_at: datetime = getattr(state, "timestamp", None) or fallback_time
        if evaluated_at.tzinfo is None:
            evaluated_at = evaluated_at.replace(tzinfo=timezone.utc)

        return StandardCheckMetric(
            check_id=check_id,
            check_name=check_name,
            check_state=check_state,
            resource_id=resource_id,
            resource_name=resource_name,
            resource_type=resource_type,
            check_effect=check_effect,
            non_check_reasons=non_check_reasons,
            evaluated_at=evaluated_at,
            tags={"scope": scope_tag},
        )
