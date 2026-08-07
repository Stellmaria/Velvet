from __future__ import annotations

import stat
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODERS = ROOT / "deploy" / "hermes-coders"
ENTITIES = ROOT / "deploy" / "hermes-entities"
LAUNCHER = ROOT / "deploy" / "hermes-sandbox-launcher"
SYSTEMD = ROOT / "deploy" / "systemd"


class SandboxDeploymentContractTests(unittest.TestCase):
    def test_launcher_installer_stages_exact_version_without_activation(self) -> None:
        source = (LAUNCHER / "install.sh").read_text(encoding="utf-8")
        self.assertIn('EXACT_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"', source)
        self.assertIn('RELEASE_DIR="$RELEASES_DIR/$EXACT_SHA"', source)
        self.assertIn('CURRENT_LINK="$INSTALL_ROOT/current"', source)
        self.assertIn("HERMES_SANDBOX_PENDING_INSTALL_DIR", source)
        self.assertIn("docker network create --driver bridge --attachable", source)
        self.assertIn("apparmor_parser -r", source)
        self.assertIn("systemctl daemon-reload", source)
        self.assertNotIn("systemctl enable --now hermes-sandbox-launcher.socket", source)
        self.assertNotIn("systemctl restart hermes-sandbox-launcher.service", source)
        self.assertNotIn("systemctl restart hermes-coders.service", source)
        self.assertNotIn("docker compose", source)

    def test_canonical_installer_order_is_atomic_and_authenticated(self) -> None:
        source = (CODERS / "install.sh").read_text(encoding="utf-8")
        positions = [
            source.index('python3 "$SOURCE_DIR/ensure_idle.py"'),
            source.index('python3 "$SOURCE_DIR/ensure_launcher_tokens.py"'),
            source.rindex('  "$LAUNCHER_INSTALLER"'),
            source.index('"${compose[@]}" build'),
            source.index('python3 "$SOURCE_DIR/pin_launcher_images.py"'),
            source.index("systemctl restart hermes-sandbox-launcher.service"),
            source.index('python3 "$SOURCE_DIR/sandbox_preflight.py"'),
            source.index('mv -Tf "$link_tmp" "$CURRENT_LINK"'),
            source.index("systemctl restart hermes-coders.service"),
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("launcher-secrets.env", source)
        self.assertIn("sha256:[0-9a-f]{64}", source)
        self.assertIn("--project-name hermes-coders", source)
        self.assertNotIn("compose.bwrap.override.yaml", source)
        self.assertNotIn("docker compose down -v", source)

    def test_preflight_requires_exact_release_tokens_images_and_both_probes(self) -> None:
        source = (CODERS / "sandbox_preflight.py").read_text(encoding="utf-8")
        for marker in (
            "current не является symlink",
            "exact-SHA release",
            "launcher-secrets.env",
            "Velvet и Max launcher tokens совпадают",
            "immutable image ID",
            'os.environ["HERMES_CODER_PROJECT"] = project',
            "client.probe(project)",
            "apparmor=hermes-codex-runner",
        ):
            self.assertIn(marker, source)
        for forbidden in (
            "velvet-codex-coder-velvet:local",
            "velvet-codex-coder-max:local",
        ):
            self.assertNotIn(forbidden, source)

    def test_systemd_contract_uses_current_release_and_no_build(self) -> None:
        coders = (SYSTEMD / "hermes-coders.service").read_text(encoding="utf-8")
        launcher = (SYSTEMD / "hermes-sandbox-launcher.service").read_text(
            encoding="utf-8"
        )
        socket_unit = (SYSTEMD / "hermes-sandbox-launcher.socket").read_text(
            encoding="utf-8"
        )
        self.assertIn("Requires=docker.service hermes-sandbox-launcher.socket", coders)
        self.assertIn("sandbox_preflight.py", coders)
        self.assertIn("--project-name hermes-coders", coders)
        self.assertIn("--no-build", coders)
        self.assertNotIn(" up -d --build", coders)
        self.assertIn(
            "ExecStart=/usr/bin/python3 /usr/local/lib/hermes-sandbox-launcher/current/launcher.py",
            launcher,
        )
        self.assertIn("EnvironmentFile=/srv/hermes-coders/launcher-secrets.env", launcher)
        self.assertIn("RuntimeDirectory=hermes-sandbox-private", launcher)
        self.assertIn("RuntimeDirectoryMode=0700", launcher)
        self.assertIn("ReadWritePaths=/run/hermes-sandbox-private", launcher)
        self.assertIn("NoNewPrivileges=yes", launcher)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", launcher)
        self.assertIn("SocketGroup=hermes-sandbox", socket_unit)
        self.assertIn("SocketMode=0660", socket_unit)

    def test_entity_reconciler_is_executable(self) -> None:
        mode = (ENTITIES / "reconcile.sh").stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR)

    def test_runtime_code_has_single_fixed_boundary(self) -> None:
        contract = (LAUNCHER / "launcher_contract.py").read_text(encoding="utf-8")
        runtime = (LAUNCHER / "launcher_runtime.py").read_text(encoding="utf-8")
        server = (LAUNCHER / "launcher.py").read_text(encoding="utf-8")
        client = (CODERS / "sandbox_launcher_client.py").read_text(encoding="utf-8")
        combined = contract + runtime + server + client
        for marker in (
            "hmac.compare_digest",
            "create_codex_projection",
            "cleanup_codex_projection",
            "project_auth",
            '"project_token"',
            "hermes.launcher={_LAUNCHER_LABEL}",
        ):
            self.assertIn(marker, combined)
        self.assertIn("launcher.cancel(project, run_id)", server)
        self.assertIn("self._active.get(run_id) != project", runtime)
        for forbidden in (
            "--privileged",
            "--cap-add",
            "seccomp=unconfined",
            "apparmor=unconfined",
            "/var/run/docker.sock",
            "/run/docker.sock",
        ):
            self.assertNotIn(forbidden, contract)


if __name__ == "__main__":
    unittest.main()
