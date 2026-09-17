"""AWS IAM user collector — identity governance for the AWS account.

Collects IAM user accounts from the AWS account, enriched with group
memberships and the last-activity timestamp from the IAM credential report.

Key API calls
-------------
``iam.generate_credential_report()`` / ``iam.get_credential_report()``
    CSV report that includes ``password_last_used`` and ``access_key_last_used``
    per user.  Must be generated before reading (may take up to 4 hours to
    generate on first call; subsequent calls update within ~4 hours).
``iam.list_users(PathPrefix="/", MaxItems=1000)``
    Paginated list of all IAM users.
``iam.list_groups_for_user(UserName=...)``
    Groups this user belongs to.
``iam.list_attached_user_policies(UserName=...)``
    Managed policies attached to this user (used to infer roles).

Volume management
-----------------
AWS accounts with thousands of users use ``max_users`` to cap collection.
Default: 2 000 users per collection cycle.

Lakebase target
---------------
``dcm.monitoring.user_metrics``
"""

from __future__ import annotations

import csv
import io
import time
from datetime import datetime, timezone
from typing import Any

from dcm_commons.collectors.base import BaseCollector
from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import get_logger
from dcm_commons.models.enums import CloudProvider, MetricDomain, UserType
from dcm_commons.models.user import UserMetric

from aws_collector._aws_utils import create_aws_client, run_sync

__all__ = ["IAMUserCollector"]

_logger = get_logger(__name__)

_CREDENTIAL_REPORT_WAIT_SECONDS = 5
_CREDENTIAL_REPORT_MAX_ATTEMPTS = 10


class IAMUserCollector(BaseCollector):
    """Collects IAM user identity snapshots with last-activity timestamps.

    Args:
        source_lz_id:   Landing zone identifier.
        region_name:    AWS region (used for session; IAM is global but
                        boto3 client requires a region for endpoint config).
        account_id:     AWS account ID.
        max_users:      Cap on users collected per cycle.
        max_retries:    Retry attempts on transient failures.
        retry_base_delay_seconds: Base delay for exponential back-off.
    """

    def __init__(
        self,
        source_lz_id: str,
        region_name: str,
        account_id: str,
        *,
        max_users: int = 2000,
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
        self._max_users = max_users

    async def _collect_metrics(self) -> list[UserMetric]:
        return await run_sync(self._collect_sync)

    def _collect_sync(self) -> list[UserMetric]:
        iam = create_aws_client("iam", region_name=self._region)

        # Build last-activity map from credential report
        last_activity: dict[str, datetime | None] = {}
        try:
            last_activity = self._build_last_activity_map(iam)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("iam_credential_report_skip reason=%s", exc)

        # Enumerate users
        metrics: list[UserMetric] = []
        paginator = iam.get_paginator("list_users")
        for page in paginator.paginate(MaxItems=100):
            for user in page.get("Users", []):
                if len(metrics) >= self._max_users:
                    break
                metric = self._map_user(iam, user, last_activity)
                if metric:
                    metrics.append(metric)
            if len(metrics) >= self._max_users:
                break

        _logger.info(
            "iam_user_collected region=%s account=%s total=%d",
            self._region, self._account_id, len(metrics),
        )
        return metrics

    def _build_last_activity_map(self, iam: Any) -> dict[str, datetime | None]:
        """Generate (or retrieve) the IAM credential report and parse it."""
        # Trigger generation
        for _ in range(_CREDENTIAL_REPORT_MAX_ATTEMPTS):
            resp = iam.generate_credential_report()
            if resp.get("State") == "COMPLETE":
                break
            time.sleep(_CREDENTIAL_REPORT_WAIT_SECONDS)

        report = iam.get_credential_report()
        content: str = report["Content"].decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))

        activity: dict[str, datetime | None] = {}
        for row in reader:
            user_name = row.get("user", "")
            if user_name == "<root_account>":
                continue
            # password_last_used is "N/A" or "no_information" when not set
            pw_used = row.get("password_last_used", "")
            key1_used = row.get("access_key_1_last_used_date", "")
            # Take the most recent of password_used and access_key1_used
            candidates: list[datetime] = []
            for raw in (pw_used, key1_used):
                if raw and raw not in ("N/A", "no_information", ""):
                    try:
                        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                        candidates.append(dt)
                    except ValueError:
                        pass
            activity[user_name] = max(candidates) if candidates else None

        return activity

    def _map_user(
        self,
        iam: Any,
        user: dict[str, Any],
        last_activity: dict[str, datetime | None],
    ) -> UserMetric | None:
        """Map a single IAM ListUsers entry to a UserMetric."""
        user_name: str = user.get("UserName", "")
        user_id: str = user.get("UserId", "")
        if not user_id:
            return None

        # Groups
        groups: list[str] = []
        try:
            grp_resp = iam.list_groups_for_user(UserName=user_name)
            groups = [g.get("GroupName", "") for g in grp_resp.get("Groups", [])]
        except Exception:  # noqa: BLE001
            pass

        # Roles (inferred from attached managed policies)
        roles: list[str] = []
        try:
            pol_resp = iam.list_attached_user_policies(UserName=user_name)
            roles = [p.get("PolicyName", "") for p in pol_resp.get("AttachedPolicies", [])]
        except Exception:  # noqa: BLE001
            pass

        arn: str = user.get("Arn", "")
        create_date: datetime | None = user.get("CreateDate")
        if create_date and create_date.tzinfo is None:
            create_date = create_date.replace(tzinfo=timezone.utc)

        return UserMetric(
            user_id=user_id,
            user_name=user_name,
            display_name=user_name,
            user_type=UserType.AWS_IAM,
            is_active=True,  # IAM doesn't have an active/inactive status; use access key status for a refined check
            workspace_or_account=self._account_id,
            last_activity_at=last_activity.get(user_name),
            groups=groups,
            roles=roles,
            tags={
                "arn": arn,
                "region": self._region,
                "account_id": self._account_id,
            },
        )
