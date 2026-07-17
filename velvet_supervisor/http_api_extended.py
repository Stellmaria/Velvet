from __future__ import annotations

import logging
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .http_api import SupervisorRequestHandler as BaseSupervisorRequestHandler
from .runtime_extended import VelvetSupervisor

logger = logging.getLogger(__name__)


class SupervisorHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        runtime: VelvetSupervisor,
    ) -> None:
        self.runtime = runtime
        super().__init__(server_address, SupervisorRequestHandler)


class SupervisorRequestHandler(BaseSupervisorRequestHandler):
    server: SupervisorHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/v1/krita/status":
            super().do_GET()
            return
        if not self._require_auth():
            return
        try:
            self._send(
                HTTPStatus.OK,
                {"ok": True, "krita": self.server.runtime.krita_status()},
            )
        except Exception as error:
            logger.exception("Supervisor Krita GET failed")
            self._send(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": str(error)},
            )

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        actions = {
            "/v1/krita/ensure": "ensure",
            "/v1/krita/touch": "touch",
            "/v1/krita/stop": "stop",
        }
        action = actions.get(parsed.path)
        if action is None:
            super().do_POST()
            return
        if not self._require_auth():
            return
        try:
            payload = self._read_json()
            if action == "ensure":
                result = self.server.runtime.ensure_krita()
            elif action == "touch":
                result = self.server.runtime.touch_krita()
            else:
                result = self.server.runtime.stop_krita(
                    force=bool(payload.get("force", False))
                )
            self._send(HTTPStatus.OK, {"ok": True, "krita": result})
        except (ValueError, RuntimeError, KeyError) as error:
            self._send(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": str(error)},
            )
        except Exception as error:
            logger.exception("Supervisor Krita POST failed action=%s", action)
            self._send(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": str(error)},
            )


__all__ = ("SupervisorHTTPServer",)
