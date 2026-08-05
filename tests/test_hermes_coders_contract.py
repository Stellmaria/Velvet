from __future__ import annotations

import ast
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path("deploy/hermes-coders")
LAUNCHER = Path("deploy/hermes-sandbox-launcher")
RELEASE_PREFIX = "/srv/hermes-coders/releases/current-hermes-coders/deploy/hermes-coders"


class HermesCodersContractTests(unittest.TestCase):
    def test_project_workspaces_and_networks_remain_isolated(self) -> None:
        source = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        for marker in (
            "/workspaces/velvet:/workspace",
            "/workspaces/max:/workspace",
            "/workspaces/velvet-codex:/workspace-base:ro",
            "/workspaces/max-codex:/workspace-base:ro",
            "CODEX_ISOLATED_WORKSPACE_ROOT: /opt/codex-runs/workspaces",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("docker.sock", source)
        for service, end in (
            ("hermes-coder-velvet", "max-db-proxy"),
            ("hermes-coder-max", "networks:"),
        ):
            section = source.split(f"  {service}:", 1)[1].split(f"\n  {end}:", 1)[0] if end != "networks:" else source.split(f"  {service}:", 1)[1].split("\nnetworks:", 1)[0]
            self.assertIn("- egress", section)
            self.assertIn("- agent-control", section)
            self.assertNotIn("production", section)

    def test_model_and_cli_contract_are_preserved(self) -> None:
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        dockerfile = (ROOT / "Dockerfile.coder").read_text(encoding="utf-8")
        runner = (ROOT / "codex_runner.py").read_text(encoding="utf-8")
        self.assertIn("CODEX_DEFAULT_MODEL: gpt-5.6-terra", compose)
        self.assertIn("gpt-5.6-luna,gpt-5.6-terra,gpt-5.6-sol", compose)
        self.assertIn("ARG CODEX_VERSION=0.144.1", dockerfile)
        self.assertIn("sha256sum -c -", dockerfile)
        self.assertIn("model-capacity-only", runner)

    def test_context_and_auth_remain_project_scoped(self) -> None:
        installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        preflight = (ROOT / "preflight.py").read_text(encoding="utf-8")
        for marker in (
            "context_compiler.py",
            "install_context_pack.py",
            "verify_installed_context.py",
            "--mode hermes",
            "--mode codex",
            "ensure_launcher_tokens.py",
        ):
            self.assertIn(marker, installer)
        self.assertIn("/codex/velvet:/opt/codex", compose)
        self.assertIn("/codex/max:/opt/codex", compose)
        self.assertIn("auth.json", preflight)

    def test_runtime_smoke_uses_only_canonical_launcher_boundary(self) -> None:
        source = (ROOT / "runtime_smoke.py").read_text(encoding="utf-8")
        for marker in (
            "SandboxLauncherClient",
            "client.probe",
            "project_auth",
            "host-sandbox-launcher",
            "disposable-docker-container",
            "nested_bwrap",
            "hermes-codex-runner",
            "--project-name",
            "gh api repos/",
        ):
            self.assertIn(marker, source)
        for forbidden in (
            "bwrap --unshare-user",
            "unshare --user",
            "hermes-codex-bwrap",
        ):
            self.assertNotIn(forbidden, source)

    def test_systemd_orders_both_preflights_before_no_build_activation(self) -> None:
        source = Path("deploy/systemd/hermes-coders.service").read_text(encoding="utf-8")
        preflight = f"ExecStartPre=+/usr/bin/python3 {RELEASE_PREFIX}/preflight.py"
        sandbox = f"ExecStartPre=+/usr/bin/python3 {RELEASE_PREFIX}/sandbox_preflight.py"
        start = "ExecStart=/usr/bin/docker compose --project-name hermes-coders"
        smoke = f"ExecStartPost=/usr/bin/python3 {RELEASE_PREFIX}/runtime_smoke.py"
        for marker in (preflight, sandbox, start, smoke, "--no-build"):
            self.assertIn(marker, source)
        self.assertLess(source.index(preflight), source.index(sandbox))
        self.assertLess(source.index(sandbox), source.index(start))
        self.assertLess(source.index(start), source.index(smoke))
        self.assertNotIn(" up -d --build", source)

    def test_python_and_bash_sources_parse(self) -> None:
        for path in (
            ROOT / "codex_runner.py",
            ROOT / "runtime_smoke.py",
            ROOT / "codex_launcher_runner.py",
            ROOT / "sandbox_launcher_client.py",
            ROOT / "sandbox_preflight.py",
            LAUNCHER / "launcher_contract.py",
            LAUNCHER / "launcher_runtime.py",
            LAUNCHER / "launcher.py",
        ):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("bash is unavailable")
        for path in (
            ROOT / "install.sh",
            ROOT / "release.sh",
            ROOT / "reconcile_release_systemd.sh",
            LAUNCHER / "install.sh",
        ):
            result = subprocess.run(
                [bash, "-n", str(path)], check=False, capture_output=True, text=True
            )
            self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
