"""AWS Config Rule compliance collector — governance posture for the AWS account.

Queries AWS Config to retrieve compliance evaluation results for all active
Config Rules in the account and region.

Key API calls
-------------
``config.describe_config_rules()``
    List all Config Rules (up to 100 per page).
``config.get_compliance_details_by_config_rule(ConfigRuleName=..., ComplianceTypes=[...])``
    For each rule, retrieve the NON_COMPLIANT (default) or all evaluation results.
``config.describe_compliance_by_config_rule()``
    Summary-level compliance state per rule (used for score computation).

Volume management
-----------------
- Default: collect only ``NON_COMPLIANT`` evaluations to limit payload size.
- Set ``non_compliant_only=False`` for periodic full scans (score computation).
- ``max_results_per_rule`` caps evaluation rows per rule (default: 100).

Analogous to
------------
:class:`~azure_collector.collectors.compliance.ComplianceCollector` (Azure Policy)

Lakebase target
---------------
``dcm.monitoring.standard_checks``
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dcm_commons.collectors.base import BaseCollector
from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import get_logger
from dcm_commons.models.standard_check import StandardCheckMetric
from dcm_commons.models.enums import CloudProvider, MetricDomain, StandardCheckState

from aws_collector._aws_utils import create_aws_client, run_sync

__all__ = ["ConfigStandardCheckCollector"]

_logger = get_logger(__name__)

_CONFIG_COMPLIANCE_MAP: dict[str, StandardCheckState] = {
    "COMPLIANT": StandardCheckState.COMPLIANT,
    "NON_COMPLIANT": StandardCheckState.NON_COMPLIANT,
    "NOT_APPLICABLE": StandardCheckState.COMPLIANT,   # NOT_APPLICABLE = resource exempt
    "INSUFFICIENT_DATA": StandardCheckState.UNKNOWN,
}


class ConfigStandardCheckCollector(BaseCollector):
    """Collects AWS Config Rule compliance evaluation results.

    Args:
        source_lz_id:           Landing zone identifier.
        region_name:            AWS region to query.
        account_id:             AWS account ID.
        non_compliant_only:     When ``True`` (default), collect only
                                NON_COMPLIANT evaluations.
        max_results_per_rule:   Maximum evaluation rows per Config Rule.
        max_retries:            Retry attempts on transient failures.
        retry_base_delay_seconds: Base delay for exponential back-off.
    """

    def __init__(
        self,
        source_lz_id: str,
        region_name: str,
        account_id: str,
        *,
        non_compliant_only: bool = True,
        max_results_per_rule: int = 100,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 2.0,
    ) -> None:
        super().__init__(
            source_lz_id=source_lz_id,
            cloud_provider=CloudProvider.AWS,
            subscription_or_account_id=account_id,
            max_retries=max_retries,
            retry_base_delay_seconds=retry_base_delay_seconds,
        )
        self._region = region_name
        self._account_id = account_id
        self._non_compliant_only = non_compliant_only
        self._max_results_per_rule = max_results_per_rule

    async def _collect_metrics(self) -> list[StandardCheckMetric]:
        return await run_sync(self._collect_sync)

    def _collect_sync(self) -> list[StandardCheckMetric]:
        config = create_aws_client("config", region_name=self._region)
        scope_tag = "non_compliant_only" if self._non_compliant_only else "full_scan"

        # List all Config Rules
        rule_names: list[str] = []
        paginator = config.get_paginator("describe_config_rules")
        for page in paginator.paginate():
            for rule in page.get("ConfigRules", []):
                rule_name = rule.get("ConfigRuleName", "")
                if rule_name:
                    rule_names.append(rule_name)

        if not rule_names:
            _logger.info("config_compliance_no_rules region=%s", self._region)
            return []

        metrics: list[StandardCheckMetric] = []
        compliance_types = ["NON_COMPLIANT"] if self._non_compliant_only else [
            "COMPLIANT", "NON_COMPLIANT", "NOT_APPLICABLE"
        ]

        for rule_name in rule_names:
            try:
                rule_metrics = self._collect_rule_evaluations(
                    config, rule_name, compliance_types, scope_tag
                )
                metrics.extend(rule_metrics)
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "config_compliance_rule_skip rule=%s reason=%s",
                    rule_name, exc,
                )

        _logger.info(
            "config_compliance_collected region=%s account=%s total=%d scope=%s",
            self._region, self._account_id, len(metrics), scope_tag,
        )
        return metrics

    def _collect_rule_evaluations(
        self,
        config: Any,
        rule_name: str,
        compliance_types: list[str],
        scope_tag: str,
    ) -> list[StandardCheckMetric]:
        """Collect evaluation details for a single Config Rule."""
        metrics: list[StandardCheckMetric] = []
        now = datetime.now(tz=timezone.utc)

        paginator = config.get_paginator("get_compliance_details_by_config_rule")
        count = 0
        for page in paginator.paginate(
            ConfigRuleName=rule_name,
            ComplianceTypes=compliance_types,
        ):
            for result in page.get("EvaluationResults", []):
                if count >= self._max_results_per_rule:
                    break

                qualifier = result.get("EvaluationResultIdentifier", {})
                eval_id = qualifier.get("EvaluationResultQualifier", {})
                resource_id = eval_id.get("ResourceId")
                resource_type = eval_id.get("ResourceType")
                resource_name = resource_id.split("/")[-1] if resource_id else None

                raw_state = result.get("ComplianceType", "INSUFFICIENT_DATA")
                check_state = _CONFIG_COMPLIANCE_MAP.get(
                    raw_state, StandardCheckState.UNKNOWN
                )

                result_time: datetime = result.get("ResultRecordedTime", now)
                if result_time.tzinfo is None:
                    result_time = result_time.replace(tzinfo=timezone.utc)

                # AWS Config annotations (when available, e.g. for custom rules)
                annotation = result.get("Annotation", "")
                reasons = [annotation] if annotation else []

                metrics.append(
                    StandardCheckMetric(
                        check_id=f"arn:aws:config:{self._region}:{self._account_id}:config-rule/{rule_name}",
                        check_name=rule_name,
                        check_state=check_state,
                        resource_id=resource_id,
                        resource_name=resource_name,
                        resource_type=resource_type,
                        check_effect=None,  # AWS Config doesn't have an "effect" concept
                        non_check_reasons=reasons,
                        evaluated_at=result_time,
                        tags={
                            "region": self._region,
                            "account_id": self._account_id,
                            "scope": scope_tag,
                        },
                    )
                )
                count += 1
            if count >= self._max_results_per_rule:
                break

        return metrics
