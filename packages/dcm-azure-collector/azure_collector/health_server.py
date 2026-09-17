"""Minimal HTTP listener for App Service WEBSITES_PORT warmup/health probes."""

from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

_started = False
_lock = threading.Lock()


class _HealthHandler(BaseHTTPRequestHandler):
    """Return 200 on any GET — satisfies App Service container probes."""

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args: object) -> None:
        return


def start_app_service_health_server() -> None:
    """Bind WEBSITES_PORT when set (App Service custom container probe)."""
    global _started
    port_str = os.getenv("WEBSITES_PORT", "").strip()
    if not port_str:
        return

    with _lock:
        if _started:
            return
        port = int(port_str)

        def _serve() -> None:
            server = HTTPServer(("0.0.0.0", port), _HealthHandler)
            server.serve_forever(poll_interval=0.5)

        thread = threading.Thread(target=_serve, name="app-service-health", daemon=True)
        thread.start()
        _started = True
