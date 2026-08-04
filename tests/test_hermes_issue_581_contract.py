from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


delegate = load("issue581_delegate", "deploy/hermes-coders/codex_delegate.py")


class Issue581ContractTests(unittest.TestCase):
    def test_canonical_identity_and_direct_router_contract(self) -> None:
        router = load("issue581_router", "deploy/hermes-operator/coder_router.py")
        targets = router.load_targets()
        self.assertEqual("Велвет", targets["velvet"].identity)
        self.assertEqual("Макс", targets["max"].identity)
        payload = delegate.build_payload(
            "Inspect README",
            project="velvet",
            model=None,
            task_type="read_only",
            complexity="small",
            risk="low",
            mutation_policy="read_only",
            requested_tier="small",
        )
        self.assertEqual("owner-direct", payload["source"])
        self.assertRegex(payload["task_id"], r"^[a-f0-9]{32}$")
        self.assertNotIn("input", payload)
        self.assertNotIn("model", payload)
        runtime = (ROOT / "deploy/hermes-coders/compose.runtime.yaml").read_text()
        self.assertEqual(2, runtime.count("http://hermes-coder-router:8878"))
        source = (ROOT / "deploy/hermes-coders/codex_delegate.py").read_text()
        self.assertIn("HERMES_CODER_ROUTER_CLIENT_TOKEN", source)
        self.assertNotIn("subprocess", source)

    def test_direct_router_is_fail_closed(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(delegate.DelegateError):
                delegate.RunnerClient()

    def test_three_layer_compose_uses_launcher_security(self) -> None:
        security = (ROOT / "deploy/hermes-coders/compose.security.yaml").read_text()
        self.assertEqual(2, security.count("apparmor=hermes-codex-runner"))
        for forbidden in (
            "hermes-chat-",
            "hermes-codex-bwrap",
            "seccomp-bwrap",
            "unconfined",
        ):
            self.assertNotIn(forbidden, security)
        if subprocess.run(
            ["docker", "compose", "version"], capture_output=True
        ).returncode:
            self.skipTest("docker compose CLI unavailable")
        source = ROOT / "deploy/hermes-coders"
        with tempfile.TemporaryDirectory() as directory:
            secrets = Path(directory) / "secrets"
            secrets.mkdir()
            for name in (
                "velvet.env",
                "velvet-db.env",
                "max.env",
                "max-db.env",
            ):
                (secrets / name).touch()
            env = os.environ | {
                "HERMES_CODERS_ROOT": directory,
                "HERMES_SANDBOX_GID": "10001",
            }
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "--profile",
                    "velvet",
                    "--profile",
                    "max",
                    "-f",
                    "compose.yaml",
                    "-f",
                    "compose.runtime.yaml",
                    "-f",
                    "compose.security.yaml",
                    "config",
                    "--quiet",
                ],
                cwd=source,
                env=env,
                capture_output=True,
                text=True,
            )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_orchestration_installer_keeps_canonical_context_reconcile(self) -> None:
        source = (ROOT / "deploy/hermes-orchestration/install.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'set_value(velvet_path, "HERMES_CODER_ROUTER_CLIENT_TOKEN"', source
        )
        self.assertIn(
            'set_value(max_path, "HERMES_CODER_ROUTER_CLIENT_TOKEN"', source
        )
        self.assertIn('"$CODERS_SOURCE/install.sh"', source)
        self.assertIn("--entity kael", source)
        self.assertIn("--mode hermes", source)
        self.assertNotIn("SOUL.operator.md", source)
        verify = source.rfind("verify_installed_context.py")
        self.assertGreater(verify, source.rfind("install_context_pack.py"))
        context_installer = (
            ROOT / "deploy/hermes-brain/install_context_pack.py"
        ).read_text()
        self.assertIn("mode=0o600", context_installer)

    def test_lifecycle_preserves_existing_control_plane(self) -> None:
        unit = (ROOT / "deploy/systemd/hermes-coders.service").read_text()
        layers = "-f compose.yaml -f compose.runtime.yaml -f compose.security.yaml"
        self.assertGreaterEqual(unit.count(layers), 4)
        self.assertIn(
            "Requires=docker.service hermes-sandbox-launcher.socket", unit
        )
        self.assertIn("sandbox_preflight.py", unit)

        runtime = (ROOT / "deploy/hermes-coders/compose.runtime.yaml").read_text()
        compose = (ROOT / "deploy/hermes-coders/compose.yaml").read_text()
        self.assertEqual(2, runtime.count("/app/codex_launcher_runner.py"))
        self.assertEqual(2, runtime.count("CODEX_EXECUTION_BACKEND: launcher"))
        self.assertEqual(2, compose.count(":/workspace-base:ro"))
        self.assertIn("init: true", compose)

        tier = (ROOT / "deploy/hermes-coders/codex_tier_runner.py").read_text()
        for marker in (
            '"--filter=blob:none"',
            '"--single-branch"',
            "CODEX_ISOLATED_WORKSPACE_ROOT",
            "baseline_head",
            "final_head",
            "refs_changed",
            "base_workspace_changed",
            "workspace_preparation_failed",
        ):
            self.assertIn(marker, tier)
        launcher = (
            ROOT / "deploy/hermes-coders/codex_launcher_runner.py"
        ).read_text()
        self.assertIn("AuditedTierProviderManager", launcher)
        self.assertIn("route=self.primary_route", launcher)
        self.assertIn("route=self.provider_route", launcher)
        self.assertIn("Sandbox launcher failed closed", launcher)
        self.assertNotIn("subprocess.Popen", launcher)

    def test_runtime_smoke_uses_launcher_instead_of_nested_bwrap(self) -> None:
        smoke = (ROOT / "deploy/hermes-coders/runtime_smoke.py").read_text()
        for marker in (
            "SandboxLauncherClient",
            "client.probe",
            "host-sandbox-launcher",
            "disposable-docker-container",
            "nested_bwrap",
            "fingerprint_before",
            "hermes-codex-runner",
            "NoNewPrivs",
            "Seccomp",
            'CRYPTOGRAPHY_VERSION = "50.0.0"',
            "docker-compose.server.yml",
            "--filter=blob:none",
            "--single-branch",
            "coder container contains zombie processes",
        ):
            self.assertIn(marker, smoke)
        for forbidden in (
            "bwrap --unshare-user",
            "unshare --user",
            "seccomp=unconfined",
        ):
            self.assertNotIn(forbidden, smoke)


if __name__ == "__main__":
    unittest.main()
