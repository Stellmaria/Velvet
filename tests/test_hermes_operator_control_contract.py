from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HermesOperatorControlContractTests(unittest.TestCase):
    def setUp(self) -> None:
        base = ROOT / "deploy/hermes-operator"
        self.compose = (base / "compose.yaml").read_text(encoding="utf-8")
        self.gateway = (base / "gateway.py").read_text(encoding="utf-8")
        self.host_start = (base / "host_start.py").read_text(encoding="utf-8")
        self.opsctl = (base / "opsctl.py").read_text(encoding="utf-8")
        self.installer = (base / "install.sh").read_text(encoding="utf-8")
        self.soul = (base / "SOUL.operator.md").read_text(encoding="utf-8")
        self.gateway_unit = (
            ROOT / "deploy/systemd/hermes-operator-control.service"
        ).read_text(encoding="utf-8")
        self.host_unit = (
            ROOT / "deploy/systemd/hermes-operator-host.service"
        ).read_text(encoding="utf-8")
        self.coders_compose = (
            ROOT / "deploy/hermes-coders/compose.yaml"
        ).read_text(encoding="utf-8")

    def test_gateway_has_only_dedicated_host_socket_mount(self) -> None:
        self.assertNotIn("docker.sock", self.compose)
        self.assertNotIn("/srv/velvet", self.compose)
        self.assertNotIn("/srv/romatic-club-max", self.compose)
        self.assertNotIn("ports:", self.compose)
        self.assertIn("/srv/hermes-operator-control/runtime", self.compose)
        self.assertIn('user: "10001:${HERMES_OPS_SOCKET_GID:-10001}"', self.compose)
        self.assertIn("read_only: true", self.compose)
        self.assertIn("cap_drop:\n      - ALL", self.compose)
        self.assertIn("no-new-privileges:true", self.compose)
        self.assertIn("hermes-supervisor-control", self.compose)
        self.assertIn("velvet_backend", self.compose)

    def test_gateway_exposes_only_fixed_actions(self) -> None:
        for action in (
            'action == "status"',
            'action == "logs"',
            'action == "start"',
            'action == "restart"',
            'action in {"update", "rollback"}',
        ):
            self.assertIn(action, self.gateway)
        self.assertIn("value == {}", self.gateway)
        self.assertIn("_SENSITIVE_KEY", self.gateway)
        self.assertIn("HostStartClient", self.gateway)
        self.assertNotIn("subprocess", self.gateway)
        self.assertNotIn("shell=True", self.gateway)
        self.assertNotIn("target_sha", self.gateway)

    def test_host_bridge_has_a_fixed_start_allowlist(self) -> None:
        self.assertIn('services=frozenset({"bot"})', self.host_start)
        self.assertIn('services=frozenset({"bot", "userbot"})', self.host_start)
        self.assertIn('self._compose(target, "up", "-d", service)', self.host_start)
        self.assertIn('set(payload) != {', self.host_start)
        self.assertIn('"token",', self.host_start)
        self.assertIn('"project",', self.host_start)
        self.assertIn('"service",', self.host_start)
        self.assertNotIn("shell=True", self.host_start)
        self.assertNotIn("git ", self.host_start)
        self.assertNotIn("systemctl", self.host_start)

    def test_client_uses_dedicated_token_file_and_fixed_projects(self) -> None:
        self.assertIn("/opt/data/.hermes-ops-client-token", self.opsctl)
        self.assertIn('"velvet": {"bot"}', self.opsctl)
        self.assertIn('"max": {"bot", "userbot"}', self.opsctl)
        self.assertNotIn("SUPERVISOR_TOKEN", self.opsctl)
        self.assertNotIn("docker", self.opsctl)
        self.assertNotIn("systemctl", self.opsctl)

    def test_installer_copies_only_required_control_tokens(self) -> None:
        self.assertIn('velvet.get("SUPERVISOR_TOKEN", "")', self.installer)
        self.assertIn('romatic.get("SUPERVISOR_TOKEN", "")', self.installer)
        self.assertIn('existing.get("HERMES_OPS_HOST_TOKEN", "")', self.installer)
        self.assertIn("secrets.token_urlsafe(48)", self.installer)
        self.assertIn("docker network inspect", self.installer)
        self.assertNotIn("docker network create", self.installer)
        self.assertIn("chmod 0600", self.installer)
        self.assertIn("BEGIN MANAGED HERMES OPERATOR CONTROL", self.installer)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", self.installer)
        self.assertNotIn("OPENAI_API_KEY", self.installer)
        self.assertNotIn("POSTGRES_PASSWORD", self.installer)

    def test_systemd_components_run_unprivileged(self) -> None:
        for unit in (self.gateway_unit, self.host_unit):
            self.assertIn("User=velvet", unit)
            self.assertIn("Group=velvet", unit)
            self.assertNotIn("User=root", unit)
        self.assertIn("NoNewPrivileges=true", self.host_unit)
        self.assertIn("ProtectSystem=strict", self.host_unit)
        self.assertIn("ReadWritePaths=/srv/hermes-operator-control/runtime", self.host_unit)
        self.assertIn(
            "EnvironmentFile=/srv/hermes-operator-control/operator.env",
            self.gateway_unit,
        )
        self.assertIn("docker compose -f compose.yaml", self.gateway_unit)
        self.assertIn("hermes-operator-host.service", self.installer)
        self.assertIn("hermes-operator-control.service", self.installer)

    def test_coders_remain_outside_operator_control(self) -> None:
        self.assertNotIn("hermes-supervisor-control", self.coders_compose)
        self.assertNotIn("hermes-operator-control/runtime", self.coders_compose)
        self.assertIn("@velvet_private_coder_bot", self.soul)
        self.assertIn("@romatic_max_coder_bot", self.soul)
        self.assertIn("Не проси их запускать Docker", self.soul)


if __name__ == "__main__":
    unittest.main()
