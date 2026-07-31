from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ServerSupervisorContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = (ROOT / "scripts/server_supervisor.py").read_text(
            encoding="utf-8"
        )
        self.proxy = (ROOT / "scripts/server_supervisor_proxy.py").read_text(
            encoding="utf-8"
        )
        self.compose = (ROOT / "docker-compose.server.yml").read_text(
            encoding="utf-8"
        )
        self.deploy = (ROOT / "deploy/server/deploy.sh").read_text(
            encoding="utf-8"
        )
        self.installer = (
            ROOT / "deploy/server/install-server-supervisor.sh"
        ).read_text(encoding="utf-8")
        self.unit = (
            ROOT / "deploy/systemd/velvet-server-supervisor.service"
        ).read_text(encoding="utf-8")

    def test_windows_supervisor_remains_separate_deprecated_runtime(self) -> None:
        self.assertTrue((ROOT / "velvet_supervisor/http_api.py").is_file())
        self.assertNotIn("from velvet_supervisor", self.runtime)
        self.assertIn('"deprecated_windows_runtime": "velvet_supervisor"', self.runtime)
        self.assertIn(
            "velvet_supervisor remains the deprecated Windows runtime",
            self.installer,
        )

    def test_server_runtime_exposes_only_fixed_supervisor_actions(self) -> None:
        for route in (
            '"/v1/status"',
            '"/v1/logs"',
            '"/v1/restart"',
            '"/v1/update"',
            '"/v1/rollback"',
        ):
            self.assertIn(route, self.runtime)
        self.assertIn('self._compose("restart", "bot")', self.runtime)
        self.assertIn('["bash", "deploy/server/deploy.sh"]', self.runtime)
        self.assertIn(
            "Console and Codex actions remain disabled",
            self.runtime,
        )
        self.assertNotIn("shell=True", self.runtime)
        self.assertNotIn("docker.sock", self.runtime)

    def test_proxy_has_only_runtime_socket_and_private_network_access(self) -> None:
        service = self.compose.split("  supervisor-proxy:", 1)[1].split(
            "\n  bot:", 1
        )[0]
        self.assertIn("Dockerfile.server-supervisor-proxy", service)
        self.assertIn("/runtime", service)
        self.assertIn("read_only: true", service)
        self.assertIn('user: "10001:10001"', service)
        self.assertIn("cap_drop:\n      - ALL", service)
        self.assertIn("no-new-privileges:true", service)
        self.assertNotIn("docker.sock", service)
        self.assertNotIn("/srv/velvet", service)
        self.assertNotIn("ports:", service)

    def test_bot_uses_proxy_without_host_privileges(self) -> None:
        bot = self.compose.split("  bot:", 1)[1].split(
            "\n  # Серверная Krita", 1
        )[0]
        self.assertIn("supervisor-proxy:", bot)
        self.assertIn("condition: service_started", bot)
        self.assertNotIn("docker.sock", bot)
        self.assertNotIn("privileged:", bot)

    def test_deploy_preserves_backup_gate_and_supports_verified_rollback(self) -> None:
        self.assertIn('TARGET_OVERRIDE="${VELVET_DEPLOY_TARGET_SHA:-}"', self.deploy)
        self.assertIn("git merge-base --is-ancestor", self.deploy)
        self.assertIn("Creating pre-deploy PostgreSQL dump", self.deploy)
        self.assertIn("deploy/server/verify-dump.sh", self.deploy)
        self.assertIn("scripts/server_smoke.py", self.deploy)
        self.assertIn("build --pull bot supervisor-proxy", self.deploy)
        self.assertIn("postgres supervisor-proxy bot", self.deploy)
        self.assertIn('${TMPDIR:-/tmp}/velvet-deploy.lock', self.deploy)

    def test_systemd_runtime_is_unprivileged_and_restartable(self) -> None:
        self.assertIn("User=velvet", self.unit)
        self.assertIn("Group=velvet", self.unit)
        self.assertIn("NoNewPrivileges=true", self.unit)
        self.assertIn("ProtectSystem=strict", self.unit)
        self.assertIn("ProtectHome=read-only", self.unit)
        self.assertIn(
            "ReadWritePaths=/srv/velvet /srv/velvet/data /tmp",
            self.unit,
        )
        self.assertIn("Restart=always", self.unit)
        self.assertIn("scripts/server_supervisor.py", self.unit)
        self.assertNotIn("User=root", self.unit)
        self.assertNotIn("PrivateTmp=true", self.unit)

    def test_installer_generates_token_and_enables_server_endpoint(self) -> None:
        self.assertIn('"SUPERVISOR_ENABLED": "true"', self.installer)
        self.assertIn(
            '"SUPERVISOR_BASE_URL": "http://supervisor-proxy:8765"',
            self.installer,
        )
        self.assertIn("secrets.token_urlsafe(48)", self.installer)
        self.assertIn("systemctl enable velvet-server-supervisor.service", self.installer)
        self.assertIn("systemctl restart velvet-server-supervisor.service", self.installer)
        self.assertIn("systemctl reload velvet-compose.service", self.installer)
        self.assertNotIn(
            "install -d -m 0755 -o velvet -g velvet",
            self.installer,
        )
        self.assertNotIn(
            "install -d -m 0750 -o velvet -g velvet",
            self.installer,
        )

    def test_proxy_forwards_to_unix_socket_without_auth_secrets(self) -> None:
        self.assertIn("asyncio.open_unix_connection", self.proxy)
        self.assertIn("asyncio.start_server", self.proxy)
        self.assertNotIn("SUPERVISOR_TOKEN", self.proxy)
        self.assertNotIn("subprocess", self.proxy)


if __name__ == "__main__":
    unittest.main()
