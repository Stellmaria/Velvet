from __future__ import annotations

import importlib.util
import sys
import tempfile
import threading
import unittest
from http import HTTPStatus
from pathlib import Path
from typing import Any
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GATEWAY = _load(
    "hermes_operator_gateway_tested",
    ROOT / "deploy/hermes-operator/gateway.py",
)
HOST = _load(
    "hermes_operator_host_tested",
    ROOT / "deploy/hermes-operator/host_start.py",
)


class FakeStartRuntime(HOST.StartRuntime):
    def __init__(self, states: list[dict[str, Any]]) -> None:
        self.token = "h" * 24
        self.targets = {
            "velvet": HOST.ServiceTarget(
                app_dir=Path("/srv/velvet"),
                env_file=".env.server",
                compose_file="docker-compose.server.yml",
                services=frozenset({"bot"}),
            ),
            "max": HOST.ServiceTarget(
                app_dir=Path("/srv/romatic-club-max"),
                env_file=".env",
                compose_file="compose.yaml",
                services=frozenset({"bot", "userbot"}),
            ),
        }
        self.command_timeout = 30
        self.health_attempts = 4
        self.health_interval = 0
        self._lock = threading.Lock()
        self.states = list(states)
        self.commands: list[list[str]] = []

    def _container_state(
        self,
        target: Any,
        service: str,
    ) -> dict[str, Any]:
        del target, service
        if len(self.states) > 1:
            return self.states.pop(0)
        return self.states[0]

    def _run(
        self,
        target: Any,
        command: list[str],
        *,
        timeout: int,
        check: bool = True,
    ) -> Any:
        del target, timeout, check
        self.commands.append(command)
        return object()


class HermesOperatorHostStartTests(unittest.TestCase):
    def test_running_service_is_a_noop(self) -> None:
        runtime = FakeStartRuntime(
            [{"running": True, "status": "running", "health": "healthy"}]
        )

        result = runtime.start("velvet", "bot")

        self.assertTrue(result["ok"])
        self.assertFalse(result["changed"])
        self.assertEqual(runtime.commands, [])

    def test_missing_service_uses_fixed_compose_up(self) -> None:
        runtime = FakeStartRuntime(
            [
                {"running": False, "status": "missing", "health": None},
                {"running": True, "status": "running", "health": "healthy"},
            ]
        )

        result = runtime.start("max", "userbot")

        self.assertTrue(result["ok"])
        self.assertTrue(result["changed"])
        self.assertEqual(
            runtime.commands,
            [
                [
                    "docker",
                    "compose",
                    "--env-file",
                    ".env",
                    "-f",
                    "compose.yaml",
                    "up",
                    "-d",
                    "userbot",
                ]
            ],
        )

    def test_unknown_service_never_runs_a_command(self) -> None:
        runtime = FakeStartRuntime(
            [{"running": False, "status": "missing", "health": None}]
        )

        result = runtime.start("velvet", "userbot")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "unknown_target")
        self.assertEqual(runtime.commands, [])

    def test_unhealthy_service_fails_after_fixed_start(self) -> None:
        runtime = FakeStartRuntime(
            [
                {"running": False, "status": "exited", "health": None},
                {"running": True, "status": "running", "health": "unhealthy"},
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "did not become healthy"):
            runtime.start("velvet", "bot")

        self.assertEqual(len(runtime.commands), 1)


class StubBridgeRuntime:
    def __init__(self) -> None:
        self.token = "s" * 24
        self.calls: list[tuple[str, str]] = []

    def start(self, project: str, service: str) -> dict[str, Any]:
        self.calls.append((project, service))
        return {
            "ok": True,
            "project": project,
            "service": service,
            "changed": True,
        }


class HermesOperatorGatewaySocketTests(unittest.TestCase):
    def test_gateway_client_can_only_request_fixed_project_and_service(self) -> None:
        runtime = StubBridgeRuntime()
        with tempfile.TemporaryDirectory() as temp_dir:
            socket_path = str(Path(temp_dir) / "start.sock")
            server = HOST.StartUnixServer(socket_path, runtime)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with patch.dict(
                    "os.environ",
                    {
                        "HERMES_OPS_HOST_SOCKET": socket_path,
                        "HERMES_OPS_HOST_TOKEN": runtime.token,
                        "HERMES_OPS_START_TIMEOUT_SECONDS": "10",
                    },
                    clear=False,
                ):
                    client = GATEWAY.HostStartClient()
                    status, payload = client.start("max", "bot")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(payload["ok"])
        self.assertEqual(runtime.calls, [("max", "bot")])

    def test_wrong_host_token_is_rejected(self) -> None:
        runtime = StubBridgeRuntime()
        with tempfile.TemporaryDirectory() as temp_dir:
            socket_path = str(Path(temp_dir) / "start.sock")
            server = HOST.StartUnixServer(socket_path, runtime)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with patch.dict(
                    "os.environ",
                    {
                        "HERMES_OPS_HOST_SOCKET": socket_path,
                        "HERMES_OPS_HOST_TOKEN": "x" * 24,
                        "HERMES_OPS_START_TIMEOUT_SECONDS": "10",
                    },
                    clear=False,
                ):
                    client = GATEWAY.HostStartClient()
                    status, payload = client.start("max", "bot")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

        self.assertEqual(status, HTTPStatus.BAD_GATEWAY)
        self.assertEqual(payload["error_code"], "unauthorized")
        self.assertEqual(runtime.calls, [])


if __name__ == "__main__":
    unittest.main()
