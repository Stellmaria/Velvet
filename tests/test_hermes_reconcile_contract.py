from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "deploy/hermes-reconcile"


def load_host_module():
    path = BASE / "host_reconcile.py"
    spec = importlib.util.spec_from_file_location("host_reconcile_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class HermesReconcileRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.host = load_host_module()

    def runtime(self, app_dir: str, state_dir: str):
        with mock.patch.dict(
            os.environ,
            {
                "HERMES_OPS_RECONCILE_TOKEN": "x" * 48,
                "VELVET_APP_DIR": app_dir,
                "HERMES_OPS_RECONCILE_STATE_DIR": state_dir,
            },
            clear=False,
        ):
            return self.host.ReconcileRuntime()

    def test_submit_is_asynchronous_and_returns_task_id_before_steps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state"
            runtime = self.runtime(temporary, str(state))
            runtime._verify_checkout = mock.Mock(return_value="abc123")
            started = mock.Mock()

            class FakeThread:
                def __init__(self, *, target, args, name, daemon):
                    self.target = target
                    self.args = args
                    self.name = name
                    self.daemon = daemon

                def start(self):
                    started(self.target, self.args, self.name, self.daemon)

            with mock.patch.object(self.host.threading, "Thread", FakeThread):
                result = runtime.submit("all")

            self.assertTrue(result["ok"])
            self.assertTrue(result["accepted"])
            self.assertRegex(result["task_id"], r"^reconcile_[0-9a-f]{32}$")
            self.assertEqual(result["status"], "queued")
            started.assert_called_once()
            persisted = json.loads(runtime.state_file.read_text(encoding="utf-8"))
            self.assertIn(result["task_id"], persisted)

    def test_all_runs_entities_last_so_kael_restart_cannot_interrupt_other_steps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = self.runtime(temporary, str(Path(temporary) / "state"))
            names = [step[0] for step in runtime._steps["all"]]
            self.assertEqual(
                names,
                [
                    "install-coders",
                    "enable-coders",
                    "restart-coders",
                    "smoke-coders",
                    "install-librarian",
                    "install-entities",
                ],
            )

    def test_execute_persists_completed_steps_and_terminal_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = self.runtime(temporary, str(Path(temporary) / "state"))
            task_id = "reconcile_" + "a" * 32
            runtime._tasks[task_id] = {
                "target": "coders",
                "status": "queued",
                "head": "abc123",
                "created_at": "now",
                "started_at": None,
                "finished_at": None,
                "completed_steps": [],
                "error": None,
            }
            runtime._persist()
            runtime._verify_checkout = mock.Mock(return_value="abc123")
            runtime._run = mock.Mock(
                return_value=subprocess.CompletedProcess([], 0, "", "")
            )

            runtime._execute(task_id, "coders", "abc123")

            result = runtime.status(task_id)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(
                result["completed_steps"],
                ["install-coders", "enable-coders", "restart-coders", "smoke-coders"],
            )
            self.assertIsNone(result["error"])

    def test_only_one_reconcile_task_can_be_active(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = self.runtime(temporary, str(Path(temporary) / "state"))
            runtime._tasks["reconcile_" + "b" * 32] = {
                "target": "coders",
                "status": "running",
                "created_at": "now",
            }
            result = runtime.submit("librarian")
            self.assertFalse(result["ok"])
            self.assertEqual(result["error_code"], "busy")

    def test_unknown_target_is_rejected_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = self.runtime(temporary, str(Path(temporary) / "state"))
            runtime._run = mock.Mock()
            result = runtime.submit("shell")
            self.assertFalse(result["ok"])
            self.assertEqual(result["error_code"], "unknown_target")
            runtime._run.assert_not_called()

    def test_checkout_must_be_clean_main_at_fetched_origin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = self.runtime(temporary, str(Path(temporary) / "state"))
            runtime._git = mock.Mock(
                side_effect=[temporary, "main", " M deploy/file.py", "head", "head"]
            )
            with self.assertRaisesRegex(RuntimeError, "not clean"):
                runtime._verify_checkout()

    def test_redaction_removes_github_and_bearer_tokens(self) -> None:
        value = self.host._redact(
            "token=github_pat_ABC123 authorization: Bearer ghp_ABC123 password=hunter2"
        )
        self.assertNotIn("github_pat_ABC123", value)
        self.assertNotIn("ghp_ABC123", value)
        self.assertNotIn("hunter2", value)


class HermesReconcileStaticContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.host = (BASE / "host_reconcile.py").read_text(encoding="utf-8")
        self.gateway = (BASE / "gateway.py").read_text(encoding="utf-8")
        self.client = (BASE / "reconcilectl.py").read_text(encoding="utf-8")
        self.compose = (BASE / "compose.yaml").read_text(encoding="utf-8")
        self.installer = (BASE / "install.sh").read_text(encoding="utf-8")
        self.host_unit = (
            ROOT / "deploy/systemd/hermes-operator-reconcile.service"
        ).read_text(encoding="utf-8")
        self.gateway_unit = (
            ROOT / "deploy/systemd/hermes-reconcile-gateway.service"
        ).read_text(encoding="utf-8")

    def test_host_accepts_only_fixed_targets_and_actions(self) -> None:
        self.assertIn(
            '_TARGETS = frozenset({"coders", "entities", "librarian", "all"})',
            self.host,
        )
        self.assertIn('action == "submit"', self.host)
        self.assertIn('action == "status"', self.host)
        self.assertIn('action == "list"', self.host)
        self.assertIn('"status", "--porcelain", "--untracked-files=all"', self.host)
        self.assertIn('refs/remotes/origin/{self.branch}', self.host)
        self.assertNotIn("shell=True", self.host)
        self.assertNotIn("git fetch", self.host)
        self.assertNotIn("target_sha", self.host)

    def test_gateway_is_http_only_and_has_no_command_execution(self) -> None:
        self.assertIn(
            '_TARGETS = frozenset({"coders", "entities", "librarian", "all"})',
            self.gateway,
        )
        self.assertIn('parts[:2] != ["v1", "reconcile"]', self.gateway)
        self.assertIn('["v1", "tasks"]', self.gateway)
        self.assertIn("value == {}", self.gateway)
        self.assertNotIn("subprocess", self.gateway)
        self.assertNotIn("shell=True", self.gateway)

    def test_gateway_container_has_only_socket_and_internal_network(self) -> None:
        self.assertIn("/run/hermes-operator-reconcile", self.compose)
        self.assertIn("read_only: true", self.compose)
        self.assertIn("cap_drop:\n      - ALL", self.compose)
        self.assertIn("no-new-privileges:true", self.compose)
        self.assertNotIn("docker.sock", self.compose)
        self.assertNotIn("ports:", self.compose)
        self.assertNotIn("/srv/velvet", self.compose)
        self.assertNotIn("hermes-supervisor-control", self.compose)

    def test_root_bridge_is_separate_and_sandboxed(self) -> None:
        self.assertIn("User=root", self.host_unit)
        self.assertIn("ProtectSystem=strict", self.host_unit)
        self.assertIn("NoNewPrivileges=true", self.host_unit)
        self.assertIn("RuntimeDirectory=hermes-operator-reconcile", self.host_unit)
        read_write_line = next(
            line
            for line in self.host_unit.splitlines()
            if line.startswith("ReadWritePaths=")
        )
        read_write_paths = read_write_line.removeprefix("ReadWritePaths=").split()
        self.assertIn("/usr/local/lib/hermes-sandbox-launcher", read_write_paths)
        self.assertIn("/etc/apparmor.d", read_write_paths)
        self.assertNotIn("/usr/local", read_write_paths)
        self.assertNotIn("/etc", read_write_paths)
        self.assertIn(
            "/usr/local/libexec/velvet-hermes-operator-reconcile-entrypoint.py",
            self.host_unit,
        )
        self.assertNotIn(
            "/srv/velvet/deploy/hermes-reconcile/host_reconcile_entrypoint.py",
            self.host_unit,
        )
        self.assertIn("User=velvet", self.gateway_unit)

    def test_installer_preserves_existing_operator_env_and_hides_tokens(self) -> None:
        self.assertIn('values.get("HERMES_OPS_RECONCILE_TOKEN", "")', self.installer)
        self.assertIn("secrets.token_urlsafe(48)", self.installer)
        self.assertIn("without printing secret values", self.installer)
        self.assertIn("chmod 0600", self.installer)
        self.assertIn("reconcilectl.py", self.installer)
        self.assertIn("HOST_ENTRYPOINT_TARGET", self.installer)
        self.assertIn("host_reconcile_entrypoint.py", self.installer)
        self.assertIn(
            "install -d -m 0755 -o root -g root /usr/local/lib/hermes-sandbox-launcher",
            self.installer,
        )
        self.assertNotIn("TELEGRAM_BOT_TOKEN", self.installer)
        self.assertNotIn("SUPERVISOR_TOKEN", self.installer)

    def test_client_reuses_operator_token_and_fixed_gateway(self) -> None:
        self.assertIn("/opt/data/.hermes-ops-client-token", self.client)
        self.assertIn("http://hermes-reconcile-gateway:8878", self.client)
        self.assertIn(
            'TARGETS = ("coders", "entities", "librarian", "all")',
            self.client,
        )
        self.assertIn('subparsers.add_parser("submit")', self.client)
        self.assertIn('subparsers.add_parser("status")', self.client)
        self.assertIn('subparsers.add_parser("wait")', self.client)
        self.assertIn('subparsers.add_parser("list")', self.client)
        self.assertNotIn("docker", self.client)
        self.assertNotIn("systemctl", self.client)


if __name__ == "__main__":
    unittest.main()
