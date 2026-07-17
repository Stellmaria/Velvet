from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from velvet_supervisor.bootstrap import BootstrapLaunch, launch_bootstrap
from velvet_supervisor.http_api import SupervisorHTTPServer
from velvet_supervisor.models import JsonStateStore
from velvet_supervisor.remote_console import RemoteCommandRegistry
from velvet_supervisor.runtime import VelvetSupervisor


class _Process:
    pid = 4321

    @staticmethod
    def poll():
        return None


class RuntimeRemoteControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        project_dir = Path(self.temp_dir.name)
        settings = SimpleNamespace(
            project_dir=project_dir,
            runtime_dir=project_dir / "runtime",
            python_executable="python.exe",
            test_command=("python.exe", "-m", "unittest"),
            command_timeout_seconds=900,
            api_token="t" * 32,
            notification_bot_token=None,
            notification_chat_id=None,
            update_remote="origin",
            update_branch="main",
        )
        runtime = object.__new__(VelvetSupervisor)
        runtime.settings = settings
        runtime._lock = threading.RLock()
        runtime._operation_lock = threading.Lock()
        runtime._state_store = JsonStateStore(settings.runtime_dir / "state.json")
        runtime._state = {}
        runtime._last_operation = None
        runtime._console = RemoteCommandRegistry(settings)  # type: ignore[arg-type]
        runtime._process = _Process()
        self.runtime = runtime

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_console_preview_is_single_use(self) -> None:
        request = self.runtime.preview_console_command(
            command="git status --short",
            command_key="",
            requested_by="1:@owner",
        )
        consumed = self.runtime._consume_console_request(str(request["id"]))
        self.assertEqual("git-status", consumed["command_key"])
        with self.assertRaisesRegex(ValueError, "не найден"):
            self.runtime._consume_console_request(str(request["id"]))

    def test_self_restart_is_handed_to_bootstrap(self) -> None:
        launch = BootstrapLaunch(
            operation_id="abc123",
            action="restart",
            task_name="VelvetSupervisorBootstrap-abc123",
            command=("python.exe", "-m", "velvet_supervisor.bootstrap"),
        )
        with patch("velvet_supervisor.runtime.launch_bootstrap", return_value=launch) as helper:
            operation = self.runtime.schedule_supervisor_restart(update=False)

        self.assertEqual("supervisor-restart", operation.kind)
        self.assertEqual("handed-off", operation.status)
        helper.assert_called_once()
        self.assertEqual(4321, helper.call_args.kwargs["bot_pid"])
        history = self.runtime.operation_history(10)
        self.assertEqual(operation.id, history[0]["id"])


class BootstrapLaunchTests(unittest.TestCase):
    def test_windows_launch_uses_independent_scheduled_task(self) -> None:
        settings = SimpleNamespace(
            python_executable=r"E:\\python\\main\\velevt\\.venv\\Scripts\\python.exe",
            project_dir=Path(r"E:\\python\\main\\velevt"),
        )
        calls = []

        def fake_run(command, **kwargs):
            calls.append(tuple(command))
            return SimpleNamespace(returncode=0, stdout="")

        with patch("velvet_supervisor.bootstrap.os.name", "nt"), patch(
            "velvet_supervisor.bootstrap._run", side_effect=fake_run
        ), patch.dict(os.environ, {"SUPERVISOR_TASK_NAME": "VelvetSupervisor"}, clear=False):
            launch = launch_bootstrap(
                settings,  # type: ignore[arg-type]
                action="update",
                operation_id="abc123def456",
                supervisor_pid=100,
                bot_pid=200,
            )

        self.assertEqual("update", launch.action)
        self.assertEqual(2, len(calls))
        create, run = calls
        self.assertEqual("schtasks.exe", create[0])
        self.assertIn("/Create", create)
        self.assertIn("VelvetSupervisorBootstrap-abc123def456", create)
        action_text = create[create.index("/TR") + 1]
        self.assertIn("velvet_supervisor.bootstrap", action_text)
        self.assertIn("--supervisor-pid 100", action_text)
        self.assertIn("--bot-pid 200", action_text)
        self.assertEqual(("schtasks.exe", "/Run", "/TN", launch.task_name), run)

    def test_unknown_bootstrap_action_is_rejected(self) -> None:
        settings = SimpleNamespace(project_dir=Path("."), python_executable="python")
        with self.assertRaises(ValueError):
            launch_bootstrap(
                settings,  # type: ignore[arg-type]
                action="shell",
                operation_id="abc",
                supervisor_pid=1,
                bot_pid=None,
            )


class _FakeRuntime:
    def __init__(self, token: str) -> None:
        self.settings = SimpleNamespace(api_token=token)
        self.codex = SimpleNamespace(list_tasks=lambda limit: [])
        self.calls: list[tuple[str, object]] = []

    def status(self):
        return {"supervisor": {"pid": 1}, "bot": {}, "git": {}}

    def log_tail(self, lines):
        return []

    def console_commands(self):
        return [{"key": "git-status", "command": "git status --short"}]

    def operation_history(self, limit):
        return [{"id": "op1", "kind": "console-command", "status": "success"}]

    def preview_console_command(self, **kwargs):
        self.calls.append(("preview", kwargs))
        return {"id": "req1", "command": "git status --short"}

    def schedule_console_command(self, request_id):
        self.calls.append(("run", request_id))
        return SimpleNamespace(to_dict=lambda: {"id": "op1", "kind": "console-command"})

    def schedule_supervisor_restart(self, *, update):
        self.calls.append(("self", update))
        return SimpleNamespace(
            to_dict=lambda: {
                "id": "op-self",
                "kind": "supervisor-update" if update else "supervisor-restart",
            }
        )


class RemoteSupervisorHTTPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.token = "z" * 32
        self.runtime = _FakeRuntime(self.token)
        self.server = SupervisorHTTPServer(("127.0.0.1", 0), self.runtime)  # type: ignore[arg-type]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _request(self, method: str, path: str, payload=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            method=method,
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_console_catalog_preview_and_run_routes(self) -> None:
        status, catalog = self._request("GET", "/v1/console")
        self.assertEqual(200, status)
        self.assertEqual("git-status", catalog["commands"][0]["key"])

        status, preview = self._request(
            "POST",
            "/v1/console/preview",
            {"command": "git status --short", "requested_by": "owner"},
        )
        self.assertEqual(200, status)
        self.assertEqual("req1", preview["request"]["id"])

        status, accepted = self._request(
            "POST", "/v1/console/run", {"request_id": "req1"}
        )
        self.assertEqual(202, status)
        self.assertEqual("op1", accepted["operation"]["id"])

    def test_self_restart_and_update_routes_are_distinct(self) -> None:
        restart_status, restart = self._request("POST", "/v1/self/restart", {})
        update_status, update = self._request("POST", "/v1/self/update", {})
        self.assertEqual(202, restart_status)
        self.assertEqual(202, update_status)
        self.assertEqual("supervisor-restart", restart["operation"]["kind"])
        self.assertEqual("supervisor-update", update["operation"]["kind"])
        self.assertIn(("self", False), self.runtime.calls)
        self.assertIn(("self", True), self.runtime.calls)


if __name__ == "__main__":
    unittest.main()
