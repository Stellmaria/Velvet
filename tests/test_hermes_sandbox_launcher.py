from __future__ import annotations

import importlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_DIR = ROOT / "deploy" / "hermes-sandbox-launcher"


def load_modules():
    for name in ("launcher", "launcher_runtime", "launcher_contract"):
        sys.modules.pop(name, None)
    sys.path.insert(0, str(LAUNCHER_DIR))
    try:
        contract = importlib.import_module("launcher_contract")
        runtime = importlib.import_module("launcher_runtime")
        server = importlib.import_module("launcher")
    finally:
        sys.path.pop(0)
    return contract, runtime, server


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract, self.runtime, self.server = load_modules()
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root = base / "root"
        self.source = base / "release"
        self.projections = base / "projections"
        self.source.mkdir()
        (self.source / "sandbox_entrypoint.py").write_text("pass\n")
        for project in ("velvet", "max"):
            workspace = self.root / "codex-runs" / project / "workspaces" / ("a" * 32)
            (workspace / ".git").mkdir(parents=True)
            home = self.root / "codex" / project
            home.mkdir(parents=True)
            for name in (
                "AGENTS.md",
                "output.schema.json",
                "context-manifest.json",
                "auth.json",
                "config.toml",
                "extra-secret.txt",
            ):
                (home / name).write_text(name, encoding="utf-8")
            secrets = self.root / "secrets"
            secrets.mkdir(parents=True, exist_ok=True)
            (secrets / f"{project}.env").write_text(
                "GH_TOKEN=ghp_test\n"
                "BYESU_HERMES_CODEX_API_KEY=codex\n"
                "BYESU_HERMES_GPT_PRO_API_KEY=pro\n"
                "HERMES_SANDBOX_LAUNCHER_TOKEN=must-not-pass\n",
                encoding="utf-8",
            )
        self.patchers = [
            patch.object(self.contract, "ROOT", self.root.resolve()),
            patch.object(self.contract, "SOURCE_DIR", self.source.resolve()),
            patch.object(self.contract, "PROJECTION_ROOT", self.projections.resolve()),
            patch.object(
                self.contract,
                "IMAGES",
                {
                    "velvet": "sha256:" + "1" * 64,
                    "max": "sha256:" + "2" * 64,
                },
            ),
            patch.object(self.contract, "NETWORK", "fixed-egress"),
            patch.object(self.contract.os, "chown"),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp.cleanup()

    @staticmethod
    def payload(**changes):
        value = {
            "action": "run",
            "run_id": "a" * 32,
            "project": "velvet",
            "project_token": "v" * 48,
            "workspace": "/opt/codex-runs/workspaces/" + "a" * 32,
            "model": "gpt-5.6-sol",
            "route": "codex_subscription",
            "mutation_policy": "workspace_write",
            "timeout_seconds": 600,
            "prompt": "inspect",
        }
        value.update(changes)
        return value

    def test_project_auth_is_distinct_constant_time_contract(self) -> None:
        tokens = {"velvet": "v" * 48, "max": "m" * 48}
        self.assertEqual(
            "velvet", self.contract.authenticate_project("velvet", "v" * 48, tokens)
        )
        for project, token in (("velvet", "m" * 48), ("max", "v" * 48)):
            with self.assertRaises(self.contract.LauncherProtocolError):
                self.contract.authenticate_project(project, token, tokens)

    def test_run_normalization_drops_project_token(self) -> None:
        normalized = self.contract.validate_run(self.payload())
        self.assertNotIn("project_token", normalized)
        with self.assertRaises(self.contract.LauncherProtocolError):
            self.contract.validate_run({**self.payload(), "command": "sh"})

    def test_route_scoped_projection_allowlist(self) -> None:
        subscription = self.contract.create_codex_projection(
            "velvet", "a" * 32, "codex_subscription"
        )
        self.assertEqual(
            {
                "AGENTS.md",
                "output.schema.json",
                "context-manifest.json",
                "auth.json",
                "config.toml",
            },
            {path.name for path in subscription.iterdir()},
        )
        self.assertNotIn("extra-secret.txt", {path.name for path in subscription.iterdir()})
        self.contract.cleanup_codex_projection(subscription)

        provider = self.contract.create_codex_projection(
            "velvet", "a" * 32, "byesu_provider"
        )
        self.assertEqual(
            {"AGENTS.md", "output.schema.json", "context-manifest.json"},
            {path.name for path in provider.iterdir()},
        )
        self.contract.cleanup_codex_projection(provider)

    def test_docker_command_has_fixed_boundary_and_no_launcher_token(self) -> None:
        normalized = self.contract.validate_run(self.payload())
        projection = self.contract.create_codex_projection(
            "velvet", "a" * 32, "codex_subscription"
        )
        env_file = Path(self.temp.name) / "run.env"
        env_file.write_text("GH_TOKEN=x\n")
        command = self.contract.build_docker_command(normalized, env_file, projection)
        joined = " ".join(command)
        for required in (
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--security-opt=apparmor=hermes-codex-run",
            "--pull=never",
            "hermes.launcher=canonical-v1",
            "dst=/workspace",
            "dst=/opt/codex-ro,readonly",
        ):
            self.assertIn(required, joined)
        for forbidden in (
            "project_token",
            "HERMES_SANDBOX_LAUNCHER_TOKEN",
            "must-not-pass",
            "/run/docker.sock",
            "/var/run/docker.sock",
            "--privileged",
            "--cap-add",
            "unconfined",
        ):
            self.assertNotIn(forbidden, joined)
        self.contract.cleanup_codex_projection(projection)

    def test_route_secret_file_never_contains_launcher_token(self) -> None:
        normalized = self.contract.validate_run(self.payload())
        runtime_dir = Path(self.temp.name) / "runtime"
        runtime_dir.mkdir()
        real_path = Path

        def mapped_path(value):
            if str(value) == "/run/hermes-sandbox":
                return runtime_dir
            return real_path(value)

        with patch.object(self.contract, "Path", side_effect=mapped_path):
            path = self.contract.write_env_file(normalized)
        try:
            body = path.read_text()
            self.assertIn("GH_TOKEN=", body)
            self.assertNotIn("HERMES_SANDBOX_LAUNCHER_TOKEN", body)
            self.assertNotIn("must-not-pass", body)
        finally:
            path.unlink(missing_ok=True)


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract, self.runtime, self.server = load_modules()
        self.launcher = object.__new__(self.runtime.Launcher)
        self.launcher._lock = threading.RLock()
        self.launcher._processes = {}
        self.launcher._containers = {}
        self.launcher._cancelled = set()
        self.launcher._active = {}

    @staticmethod
    def request():
        return {
            "run_id": "a" * 32,
            "project": "velvet",
            "model": "gpt-5.6-terra",
            "route": "codex_subscription",
            "mutation_policy": "read_only",
            "timeout_seconds": 60,
            "prompt": "inspect",
        }

    def test_cross_project_cancel_is_rejected(self) -> None:
        self.launcher._active["a" * 32] = "velvet"
        self.assertFalse(self.launcher.cancel("max", "a" * 32))
        self.assertNotIn("a" * 32, self.launcher._cancelled)

    def test_projection_cleanup_runs_on_success(self) -> None:
        process = Mock()
        process.returncode = 0
        process.communicate.return_value = ("", "")
        process.poll.return_value = 0
        env_file = Path(tempfile.mkstemp()[1])
        projection = Path(tempfile.mkdtemp())
        try:
            with patch.object(self.launcher, "_verify_image"), patch.object(
                self.runtime, "write_env_file", return_value=env_file
            ), patch.object(
                self.runtime, "create_codex_projection", return_value=projection
            ), patch.object(
                self.runtime, "build_docker_command", return_value=["docker", "run"]
            ), patch.object(
                self.runtime.subprocess, "Popen", return_value=process
            ), patch.object(
                self.runtime.subprocess, "run", return_value=Mock(returncode=0)
            ), patch.object(self.runtime, "cleanup_codex_projection") as cleanup:
                result = self.launcher.run(self.request())
            self.assertEqual(0, result["returncode"])
            cleanup.assert_called_once_with(projection)
        finally:
            env_file.unlink(missing_ok=True)
            projection.rmdir()

    def test_timeout_is_not_owner_cancellation_and_projection_is_cleaned(self) -> None:
        process = Mock()
        process.returncode = 124
        process.poll.return_value = 124
        process.communicate.side_effect = (
            subprocess.TimeoutExpired(cmd="docker", timeout=60),
            ("", "stopped"),
        )
        env_file = Path(tempfile.mkstemp()[1])
        projection = Path(tempfile.mkdtemp())
        try:
            with patch.object(self.launcher, "_verify_image"), patch.object(
                self.runtime, "write_env_file", return_value=env_file
            ), patch.object(
                self.runtime, "create_codex_projection", return_value=projection
            ), patch.object(
                self.runtime, "build_docker_command", return_value=["docker", "run"]
            ), patch.object(
                self.runtime.subprocess, "Popen", return_value=process
            ), patch.object(
                self.runtime.subprocess, "run", return_value=Mock(returncode=0)
            ), patch.object(self.launcher, "_stop_container", return_value=True), patch.object(
                self.runtime, "cleanup_codex_projection"
            ) as cleanup:
                result = self.launcher.run(self.request())
            self.assertEqual(124, result["returncode"])
            self.assertFalse(result["cancelled"])
            self.assertIn("timed out", result["stderr"])
            cleanup.assert_called_once_with(projection)
        finally:
            env_file.unlink(missing_ok=True)
            projection.rmdir()

    def test_server_requires_matching_project_token_for_probe(self) -> None:
        left, right = socket.socketpair()
        launcher = Mock()
        try:
            right.sendall(
                json.dumps(
                    {
                        "action": "probe",
                        "project": "velvet",
                        "project_token": "m" * 48,
                    }
                ).encode()
                + b"\n"
            )
            right.shutdown(socket.SHUT_WR)
            with patch.object(self.server, "peer_identity", return_value=(1, 10000, 10000)):
                self.server.handle_connection(
                    left,
                    launcher,
                    {"velvet": "v" * 48, "max": "m" * 48},
                )
            response = json.loads(right.recv(65536).split(b"\n", 1)[0])
            self.assertFalse(response["ok"])
            launcher.probe.assert_not_called()
        finally:
            right.close()


if __name__ == "__main__":
    unittest.main()
