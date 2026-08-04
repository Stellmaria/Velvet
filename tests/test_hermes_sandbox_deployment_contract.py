from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODERS = ROOT / "deploy" / "hermes-coders"
LAUNCHER = ROOT / "deploy" / "hermes-sandbox-launcher"
SYSTEMD = ROOT / "deploy" / "systemd"


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


class SandboxLauncherDeploymentContractTests(unittest.TestCase):
    def test_compose_selects_launcher_without_nested_bwrap(self) -> None:
        runtime = (CODERS / "compose.runtime.yaml").read_text(encoding="utf-8")
        security = (CODERS / "compose.security.yaml").read_text(encoding="utf-8")
        self.assertEqual(2, runtime.count("CODEX_EXECUTION_BACKEND: launcher"))
        self.assertEqual(2, runtime.count("/app/codex_launcher_runner.py"))
        self.assertEqual(2, runtime.count("sandbox_launcher_client.py"))
        self.assertEqual(2, runtime.count("launcher.sock"))
        self.assertEqual(2, security.count("apparmor=hermes-codex-runner"))
        for forbidden in (
            "hermes-codex-bwrap",
            "seccomp-bwrap",
            "seccomp=unconfined",
            "apparmor=unconfined",
            "privileged: true",
        ):
            self.assertNotIn(forbidden, runtime + security)

    def test_systemd_uses_fixed_launcher_install_and_socket_activation(self) -> None:
        coders = (SYSTEMD / "hermes-coders.service").read_text(encoding="utf-8")
        launcher = (SYSTEMD / "hermes-sandbox-launcher.service").read_text(
            encoding="utf-8"
        )
        socket_unit = (SYSTEMD / "hermes-sandbox-launcher.socket").read_text(
            encoding="utf-8"
        )
        self.assertIn("Requires=docker.service hermes-sandbox-launcher.socket", coders)
        self.assertIn("EnvironmentFile=/srv/hermes-coders/launcher.env", coders)
        self.assertIn("sandbox_preflight.py", coders)
        self.assertIn(
            "ExecStart=/usr/bin/python3 /usr/local/lib/hermes-sandbox-launcher/launcher.py",
            launcher,
        )
        self.assertIn("RestrictAddressFamilies=AF_UNIX", launcher)
        self.assertIn("NoNewPrivileges=yes", launcher)
        self.assertIn("SocketGroup=hermes-sandbox", socket_unit)
        self.assertIn("SocketMode=0660", socket_unit)
        self.assertIn("Accept=no", socket_unit)

    def test_installer_creates_dedicated_network_and_does_not_switch_traffic(self) -> None:
        source = (LAUNCHER / "install.sh").read_text(encoding="utf-8")
        self.assertIn("docker network create --driver bridge --attachable", source)
        self.assertIn("/usr/local/lib/hermes-sandbox-launcher", source)
        self.assertIn("apparmor_parser -r", source)
        self.assertIn("systemctl enable --now hermes-sandbox-launcher.socket", source)
        self.assertNotIn("systemctl restart hermes-coders.service", source)
        self.assertNotIn("docker compose", source)

    def test_runner_preserves_existing_control_plane_and_fails_closed(self) -> None:
        source = (CODERS / "codex_launcher_runner.py").read_text(encoding="utf-8")
        self.assertIn(
            "class LauncherTierProviderManager(AuditedTierProviderManager)", source
        )
        self.assertIn("route=self.primary_route", source)
        self.assertIn("route=self.provider_route", source)
        self.assertIn("Sandbox launcher failed closed", source)
        self.assertIn("HERMES_ALLOW_LOCAL_ROLLBACK", source)
        self.assertNotIn("subprocess.Popen", source)
        self.assertNotIn("return super()._run_once", source)

    def test_entrypoint_copies_only_explicit_codex_home_files(self) -> None:
        entrypoint = CODERS / "sandbox_entrypoint.py"
        module = load_module("sandbox_entrypoint_contract", entrypoint)
        source = entrypoint.read_text(encoding="utf-8")
        provider = module.provider_config("gpt-5.6-terra")
        self.assertEqual(
            ("AGENTS.md", "output.schema.json", "context-manifest.json"),
            module._COMMON_HOME_FILES,
        )
        self.assertEqual(("auth.json", "config.toml"), module._SUBSCRIPTION_HOME_FILES)
        self.assertIn('sandbox_mode = "danger-full-access"', provider)
        self.assertIn('"--sandbox",\n        "danger-full-access"', source)
        self.assertNotIn("for child in source.iterdir()", source)
        self.assertNotIn("{**os.environ", source)
        self.assertIn("child", "child")  # keep test body explicit and non-empty

    def test_apparmor_separates_runner_and_disposable_run(self) -> None:
        runner = (CODERS / "security/apparmor-hermes-codex-runner").read_text(
            encoding="utf-8"
        )
        run = (CODERS / "security/apparmor-hermes-codex-run").read_text(
            encoding="utf-8"
        )
        self.assertIn("/run/hermes-sandbox/launcher.sock rw", runner)
        self.assertIn("/opt/codex-runs/** rwk", runner)
        self.assertIn("deny /workspace/** rwklx", runner)
        self.assertIn("/workspace/** rwkix", run)
        self.assertIn("/opt/codex-ro/** r", run)
        self.assertIn("deny /run/hermes-sandbox/** rwklx", run)
        self.assertNotIn("userns", runner + run)
        self.assertNotIn("mount options=", runner + run)

    def test_adr_declares_single_boundary_and_no_automatic_downgrade(self) -> None:
        text = (
            ROOT / "docs/adr/0001-hermes-host-sandbox-launcher.md"
        ).read_text(encoding="utf-8")
        self.assertIn("disposable", text)
        self.assertIn("no automatic downgrade", text)
        self.assertIn("Give the runner Docker socket access", text)
        self.assertIn("Rejected", text)


if __name__ == "__main__":
    unittest.main()
