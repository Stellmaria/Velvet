from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_DIR = ROOT / "deploy" / "hermes-sandbox-launcher"
CONTRACT = LAUNCHER_DIR / "launcher_contract.py"
RUNTIME = LAUNCHER_DIR / "launcher_runtime.py"
SERVER = LAUNCHER_DIR / "launcher.py"


def load_module(name: str, path: Path):
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"could not load {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class SandboxLauncherContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_module("launcher_contract_test", CONTRACT)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "hermes"
        self.source = Path(self.temp.name) / "installed"
        self.source.mkdir(parents=True)
        (self.source / "sandbox_entrypoint.py").write_text(
            "print('ok')\n", encoding="utf-8"
        )
        for project in ("velvet", "max"):
            workspace = (
                self.root
                / "codex-runs"
                / project
                / "workspaces"
                / ("a" * 32)
            )
            (workspace / ".git").mkdir(parents=True)
            (self.root / "codex" / project).mkdir(parents=True)
            secrets = self.root / "secrets"
            secrets.mkdir(parents=True, exist_ok=True)
            (secrets / f"{project}.env").write_text(
                "GH_TOKEN=ghp_test_value\n"
                "BYESU_HERMES_CODEX_API_KEY=coder-key\n"
                "BYESU_HERMES_GPT_PRO_API_KEY=pro-key\n"
                "TELEGRAM_BOT_TOKEN=must-not-pass\n"
                "API_SERVER_KEY=must-not-pass\n",
                encoding="utf-8",
            )
        self.patchers = (
            patch.object(self.contract, "ROOT", self.root.resolve()),
            patch.object(self.contract, "SOURCE_DIR", self.source.resolve()),
            patch.object(
                self.contract,
                "IMAGES",
                {"velvet": "velvet-image:fixed", "max": "max-image:fixed"},
            ),
            patch.object(self.contract, "NETWORK", "fixed-egress"),
        )
        for item in self.patchers:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patchers):
            item.stop()
        self.temp.cleanup()

    @staticmethod
    def request(**changes):
        payload = {
            "action": "run",
            "run_id": "a" * 32,
            "project": "velvet",
            "workspace": "/opt/codex-runs/workspaces/" + "a" * 32,
            "model": "gpt-5.6-sol",
            "route": "codex_subscription",
            "mutation_policy": "workspace_write",
            "timeout_seconds": 600,
            "prompt": "inspect repository",
        }
        payload.update(changes)
        return payload

    def test_request_schema_rejects_arbitrary_fields_paths_and_routes(self) -> None:
        invalid = (
            {**self.request(), "command": "sh"},
            self.request(workspace="/srv/velvet"),
            self.request(project="other"),
            self.request(model="arbitrary-model"),
            self.request(model="gpt-5.4-mini", route="codex_subscription"),
            self.request(model="gpt-5.6-sol", route="byesu_provider"),
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                with self.assertRaises(self.contract.LauncherProtocolError):
                    self.contract.validate_run(payload)

    def test_fixed_docker_command_mounts_only_current_run(self) -> None:
        request = self.contract.validate_run(self.request())
        env_file = Path(self.temp.name) / "run.env"
        env_file.write_text("GH_TOKEN=x\n", encoding="utf-8")
        command = self.contract.build_docker_command(request, env_file)
        joined = " ".join(command)
        for marker in (
            "--interactive",
            "--pull=never",
            "--log-driver=none",
            "--ipc=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=apparmor=hermes-codex-run",
            "--security-opt=no-new-privileges:true",
            "--network fixed-egress",
            "HERMES_SANDBOX_PROJECT=velvet",
            "dst=/workspace",
            "dst=/opt/codex-ro,readonly",
        ):
            self.assertIn(marker, joined)
        for forbidden in (
            "/run/docker.sock",
            "--privileged",
            "--cap-add",
            "seccomp=unconfined",
            str(self.root / "codex-runs" / "max"),
            str(request["prompt"]),
        ):
            self.assertNotIn(forbidden, joined)

    def test_read_only_policy_is_kernel_enforced_by_mount(self) -> None:
        request = self.contract.validate_run(
            self.request(mutation_policy="read_only")
        )
        env_file = Path(self.temp.name) / "run.env"
        env_file.write_text("GH_TOKEN=x\n", encoding="utf-8")
        command = self.contract.build_docker_command(request, env_file)
        mounts = [
            command[index + 1]
            for index, value in enumerate(command)
            if value == "--mount"
        ]
        workspace_mount = next(item for item in mounts if "dst=/workspace" in item)
        self.assertTrue(workspace_mount.endswith(",readonly"), workspace_mount)

    def _write_env(self, request: dict[str, object]) -> str:
        runtime_dir = Path(self.temp.name) / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        real_path = Path

        def mapped_path(value: object) -> Path:
            if str(value) == "/run/hermes-sandbox":
                return runtime_dir
            return real_path(value)

        with patch.object(self.contract, "Path", side_effect=mapped_path):
            path = self.contract.write_env_file(request)
        try:
            self.assertEqual(0o600, path.stat().st_mode & 0o777)
            return path.read_text(encoding="utf-8")
        finally:
            path.unlink(missing_ok=True)

    def test_secret_environment_is_route_scoped(self) -> None:
        primary = self._write_env(self.contract.validate_run(self.request()))
        self.assertIn("GH_TOKEN=", primary)
        self.assertNotIn("BYESU_HERMES_CODEX_API_KEY", primary)
        self.assertNotIn("BYESU_HERMES_GPT_PRO_API_KEY", primary)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", primary)
        self.assertNotIn("API_SERVER_KEY", primary)

        provider = self._write_env(
            self.contract.validate_run(
                self.request(model="gpt-5.6-luna", route="byesu_provider")
            )
        )
        self.assertIn("GH_TOKEN=", provider)
        self.assertIn("BYESU_HERMES_GPT_PRO_API_KEY=", provider)
        self.assertNotIn("BYESU_HERMES_CODEX_API_KEY", provider)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", provider)
        self.assertNotIn("API_SERVER_KEY", provider)

    def test_execution_evidence_is_detected_before_output_truncation(self) -> None:
        output = '{"item":{"type":"command_execution"}}\n' + ("x" * 1_100_000)
        self.assertTrue(self.contract.execution_started(output))


class SandboxLauncherRuntimeTests(unittest.TestCase):
    def test_timeout_fails_without_claiming_owner_cancellation(self) -> None:
        runtime = load_module("launcher_runtime_test", RUNTIME)
        launcher = object.__new__(runtime.Launcher)
        launcher._lock = threading.RLock()
        launcher._processes = {}
        launcher._containers = {}
        launcher._cancelled = set()
        launcher._active = set()

        process = Mock()
        process.returncode = 124
        process.poll.return_value = 124
        process.communicate.side_effect = (
            subprocess.TimeoutExpired(cmd="docker", timeout=60),
            ("", "stopped"),
        )
        request = {
            "run_id": "a" * 32,
            "project": "velvet",
            "model": "gpt-5.6-terra",
            "route": "codex_subscription",
            "mutation_policy": "read_only",
            "timeout_seconds": 60,
            "prompt": "inspect",
        }
        env_file = Path(tempfile.mkstemp()[1])
        try:
            with patch.object(runtime, "write_env_file", return_value=env_file), patch.object(
                runtime, "build_docker_command", return_value=["docker", "run"]
            ), patch.object(runtime.subprocess, "Popen", return_value=process), patch.object(
                runtime.subprocess, "run", return_value=Mock(returncode=0, stdout="", stderr="")
            ), patch.object(launcher, "_stop_container", return_value=True):
                result = launcher.run(request)
        finally:
            env_file.unlink(missing_ok=True)
        self.assertEqual(124, result["returncode"])
        self.assertFalse(result["cancelled"])
        self.assertIn("timed out", result["stderr"])

    def test_launcher_server_imports_its_security_constants(self) -> None:
        module = load_module("launcher_server_test", SERVER)
        self.assertTrue(callable(module.receive_json))
        self.assertGreater(module._MAX_CONNECTIONS, 0)


if __name__ == "__main__":
    unittest.main()
