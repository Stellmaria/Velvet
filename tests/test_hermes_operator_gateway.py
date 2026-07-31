from __future__ import annotations

import importlib.util
import sys
import unittest
from http import HTTPStatus
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GATEWAY_PATH = ROOT / "deploy/hermes-operator/gateway.py"
SPEC = importlib.util.spec_from_file_location("hermes_operator_gateway_tested", GATEWAY_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load Hermes operator gateway module")
GATEWAY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GATEWAY
SPEC.loader.exec_module(GATEWAY)


class RecordingClient(GATEWAY.UpstreamClient):
    def __init__(
        self,
        status_payload: dict[str, Any],
        *,
        status_code: int = HTTPStatus.OK,
    ) -> None:
        projects = {
            "velvet": GATEWAY.Project(
                base_url="http://velvet.invalid",
                token="v" * 24,
                services=frozenset({"bot"}),
                restart_routes={"bot": "/v1/restart"},
            ),
            "max": GATEWAY.Project(
                base_url="http://max.invalid",
                token="m" * 24,
                services=frozenset({"bot", "userbot"}),
                restart_routes={
                    "bot": "/v1/restart",
                    "userbot": "/v1/restart-userbot",
                },
            ),
        }
        super().__init__(projects)
        self.status_payload = status_payload
        self.status_code = status_code
        self.calls: list[tuple[str, str, str]] = []

    def request(
        self,
        project_name: str,
        method: str,
        route: str,
    ) -> tuple[int, dict[str, Any]]:
        self.calls.append((project_name, method, route))
        if method == "GET" and route == "/v1/status":
            return self.status_code, self.status_payload
        return HTTPStatus.ACCEPTED, {"ok": True, "route": route}


class HermesOperatorGatewayStartTests(unittest.TestCase):
    def test_running_velvet_bot_is_a_noop(self) -> None:
        client = RecordingClient(
            {"ok": True, "status": {"bot": {"running": True, "pid": 42}}}
        )

        status, payload = client.start("velvet", "bot")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(payload["ok"])
        self.assertEqual(client.calls, [("velvet", "GET", "/v1/status")])

    def test_missing_velvet_bot_uses_verified_update_gate(self) -> None:
        client = RecordingClient(
            {"ok": True, "status": {"bot": {"running": False, "pid": None}}}
        )

        status, _payload = client.start("velvet", "bot")

        self.assertEqual(status, HTTPStatus.ACCEPTED)
        self.assertEqual(
            client.calls,
            [
                ("velvet", "GET", "/v1/status"),
                ("velvet", "POST", "/v1/update"),
            ],
        )

    def test_exited_velvet_bot_uses_fixed_restart_route(self) -> None:
        client = RecordingClient(
            {
                "ok": True,
                "status": {
                    "bot": {"running": False, "pid": 0, "status": "exited"}
                },
            }
        )

        status, _payload = client.start("velvet", "bot")

        self.assertEqual(status, HTTPStatus.ACCEPTED)
        self.assertEqual(client.calls[-1], ("velvet", "POST", "/v1/restart"))

    def test_missing_max_userbot_uses_verified_update_gate(self) -> None:
        client = RecordingClient(
            {
                "ok": True,
                "bot": {"running": True, "status": "running"},
                "userbot": {"running": False, "pid": None, "status": "missing"},
            }
        )

        status, _payload = client.start("max", "userbot")

        self.assertEqual(status, HTTPStatus.ACCEPTED)
        self.assertEqual(client.calls[-1], ("max", "POST", "/v1/update"))

    def test_status_probe_error_never_mutates_runtime(self) -> None:
        client = RecordingClient(
            {
                "ok": True,
                "status": {
                    "bot": {
                        "running": False,
                        "pid": None,
                        "error": "Bot status probe failed.",
                    }
                },
            }
        )

        status, payload = client.start("velvet", "bot")

        self.assertEqual(status, HTTPStatus.BAD_GATEWAY)
        self.assertEqual(payload["error_code"], "status_probe_failed")
        self.assertEqual(client.calls, [("velvet", "GET", "/v1/status")])

    def test_upstream_status_failure_is_returned_without_mutation(self) -> None:
        client = RecordingClient(
            {"ok": False, "error": "unavailable"},
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        )

        status, payload = client.start("max", "bot")

        self.assertEqual(status, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertFalse(payload["ok"])
        self.assertEqual(client.calls, [("max", "GET", "/v1/status")])


if __name__ == "__main__":
    unittest.main()
