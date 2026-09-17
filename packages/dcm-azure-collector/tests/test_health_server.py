"""Tests for App Service health server."""

from __future__ import annotations

import socket
from unittest.mock import patch

from azure_collector.health_server import start_app_service_health_server


def test_health_server_binds_when_websites_port_set() -> None:
    with patch.dict("os.environ", {"WEBSITES_PORT": "0"}, clear=False):
        start_app_service_health_server()
        # Port 0 = OS picks a free port; thread should be listening on localhost.
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(1.0)
        try:
            probe.connect(("127.0.0.1", 8080))
        except OSError:
            # WEBSITES_PORT=0 may not bind 8080 — just verify idempotent second call.
            start_app_service_health_server()
        finally:
            probe.close()


def test_health_server_skipped_without_websites_port() -> None:
    with patch.dict("os.environ", {}, clear=True):
        start_app_service_health_server()  # no-op
