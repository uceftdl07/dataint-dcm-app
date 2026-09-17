"""DCM ingestion clients — Apigee gateway HTTP client.

Typical usage::

    from dcm_commons.clients import ApigeeClient

    async with ApigeeClient(
        apigee_base_url=settings.apigee_url,
        auth_client=auth,
        api_key=settings.api_key,
    ) as client:
        await client.send(payload)
"""

from __future__ import annotations

from dcm_commons.clients.apigee import ApigeeClient

__all__ = ["ApigeeClient"]
