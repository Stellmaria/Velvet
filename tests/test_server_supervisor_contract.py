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

    def test_proxy_has_only_dedicated_control_socket_and_private_network(self) -> None:
        service = self.compose.split("  supervisor-proxy:", 1)[1].split(
            "\n  bot:", 1
        )[0]
        self.assertIn("Dockerfile.server-supervisor-proxy", service)
        self.assertIn("/control/supervisor:/run/velvet-supervisor:ro", service)
        self.assertNotIn("/runtime:/runtime", service)
        self.assertIn("read_only: true", service)
        self.assertIn("SERVER_SUPERVISOR_CLIENT_GID", service)
        self.assertIn("SERVER_SUPERVISOR_CLIENT_UID", service)
        self.assertIn("cap_drop:\n      - ALL", service)
        self.assertIn("no-new-privileges:true", service)
        self.assertNotIn("docker.sock", service)
        self.assertNotIn("/srv/velvet", service)
        self.assertNotIn("ports:", service)

    def test_bot_uses_proxy_without_host_control_socket(self) -> None:
        bot = self.compose.split("  bot:", 1)[1].split(
            "\n  # Серверная Krita", 1
        )[0]
        self.assertIn("supervisor-proxy:", bot)
        self.assertIn("condition: service_started", bot)
        self.assertNotIn("control/supervisor", bot)
        self.assertNotIn("run/velvet-supervisor", bot)
        self.assertNotIn("docker.sock", bot)
        self.assertNotIn("privileged:", bot)

    def test_runtime_enforces_socket_mode_peer_credentials_and_rate_limit(self) -> None:
        self.assertIn('SERVER_SUPERVISOR_SOCKET_MODE", 0o660', self.runtime)
        self.assertIn("socket.SO_PEERCRED", self.runtime)
        self.assertIn("peer_allowed", self.runtime)
        self.assertIn("auth_blocked", self.runtime)
        self.assertIn("record_auth_failure", self.runtime)
        self.assertIn("os.chown(runtime.socket_path", self.runtime)
        self.assertIn("os.chmod(runtime.socket_path, runtime.socket_mode)", self.runtime)
        self.assertNotIn("os.chmod(runtime.socket_path, 0o666)", self.runtime)
        self.assertIn("Refusing to replace stale Server Supervisor path", self.runtime)
        self.assertIn("Internal Supervisor error.", self.runtime)
        self.assertNotIn('{"ok": False, "error": str(error)}', self.runtime)

    def test_deploy_preserves_backup_gate_and_supports_verified_rollback(self) -> None:
        self.assertIn('TARGET_OVERRIDE="${VELVET_DEPLOY_TARGET_SHA:-}"', self.deploy)
        self.assertIn("git merge-base --is-ancestor", self.deploy)
        self.assertIn("Creating pre-deploy PostgreSQL dump", self.deploy)
        self.assertIn("deploy/server/verify-dump.sh", self.deploy)
        self.assertIn("scripts/server_smoke.py", self.deploy)
        self.assertIn('"${compose[@]}" build --pull supervisor-proxy', self.deploy)
        self.assertIn('IMAGE_OVERRIDE="${VELVET_DEPLOY_IMAGE:-}"', self.deploy)
        self.assertIn('docker pull "$IMAGE_OVERRIDE"', self.deploy)
        self.assertIn("org.opencontainers.image.revision", self.deploy)
        self.assertIn("Running image mismatch", self.deploy)
        self.assertIn("start_core_services()", self.deploy)
        self.assertIn(
            '"${compose[@]}" up -d --remove-orphans postgres supervisor-proxy',
            self.deploy,
        )
        self.assertIn('"${compose[@]}" rm -sf bot', self.deploy)
        self.assertIn('"${compose[@]}" up -d --no-deps bot', self.deploy)
        self.assertIn("wait_for_service_health postgres", self.deploy)
        self.assertIn("wait_for_service_health supervisor-proxy", self.deploy)
        self.assertIn('${TMPDIR:-/tmp}/velvet-deploy.lock', self.deploy)
        self.assertIn(
            'docker_config="${DOCKER_CONFIG:-$data_dir/runtime/docker-config}"',
            self.deploy,
        )
        self.assertIn('export COMPOSE_BAKE="${COMPOSE_BAKE:-false}"', self.deploy)
        self.assertIn('chmod 0700 "$docker_config"', self.deploy)

    def test_deploy_requires_checkout_owner_and_safe_reset_umask(self) -> None:
        before_lock = self.deploy.split('exec 9>"${TMPDIR:-/tmp}/velvet-deploy.lock"', 1)[0]
        self.assertIn('checkout_owner_uid="$(stat -c \'%u\' "$APP_DIR")"', before_lock)
        self.assertIn('current_uid="$(id -u)"', before_lock)
        self.assertIn("Deployment must run as checkout owner", before_lock)
        self.assertIn("exit 77", before_lock)
        self.assertIn("reset_checkout() (\n  umask 022", self.deploy)
        self.assertEqual(self.deploy.count("git reset --hard"), 1)
        self.assertIn('reset_checkout "$target_sha"', self.deploy)
        rollback = self.deploy.split("rollback_code() {", 1)[1].split(
            "trap rollback_code", 1
        )[0]
        self.assertIn('reset_checkout "$previous_sha"', rollback)

    def test_deploy_preserves_exact_running_image_for_local_rollback(self) -> None:
        self.assertIn("previous_bot_image_id", self.deploy)
        self.assertIn(
            'rollback_bot_image="velvet-bot:rollback-${previous_sha:0:12}"',
            self.deploy,
        )
        self.assertIn(
            'docker image tag "$previous_bot_image_id" "$rollback_bot_image"',
            self.deploy,
        )
        self.assertIn(
            'docker image inspect "$rollback_bot_image"',
            self.deploy,
        )
        self.assertNotIn('docker pull "$rollback_bot_image"', self.deploy)
        self.assertNotIn('docker pull "$previous_bot_image" >&2 || true', self.deploy)

    def test_local_build_overrides_digest_config_with_buildable_tag(self) -> None:
        fallback = self.deploy.split('if [[ -n "$IMAGE_OVERRIDE" ]]', 2)[2]
        self.assertIn(
            'local_build_image="velvet-bot:deploy-${target_sha:0:12}"', fallback
        )
        self.assertIn('export VELVET_IMAGE="$local_build_image"', fallback)
        self.assertLess(
            fallback.index('export VELVET_IMAGE="$local_build_image"'),
            fallback.index('"${compose[@]}" build --pull bot'),
        )
        self.assertIn(
            "Docker Compose cannot use a digest\n  # reference as a build output tag",
            fallback,
        )

    def test_deploy_rollback_requires_health_and_smoke(self) -> None:
        rollback = self.deploy.split("rollback_code() {", 1)[1].split(
            "trap rollback_code", 1
        )[0]
        self.assertIn("wait_for_service_health bot", rollback)
        self.assertIn("scripts/server_smoke.py --skip-telegram", rollback)
        self.assertIn("manual intervention is required", rollback)
        self.assertIn("trap - ERR INT TERM", rollback)

    def test_systemd_runtime_has_dedicated_client_group_and_umask(self) -> None:
        self.assertIn("User=velvet", self.unit)
        self.assertIn("Group=velvet", self.unit)
        self.assertIn("SupplementaryGroups=velvet-supervisor-client", self.unit)
        self.assertIn("UMask=0007", self.unit)
        self.assertIn("NoNewPrivileges=true", self.unit)
        self.assertIn("ProtectSystem=strict", self.unit)
        self.assertIn("ProtectHome=read-only", self.unit)
        self.assertIn(
            "ReadWritePaths=/srv/velvet /srv/velvet/data /tmp",
            self.unit,
        )
        self.assertIn(
            "Environment=DOCKER_CONFIG=/srv/velvet/data/runtime/docker-config",
            self.unit,
        )
        self.assertIn("Environment=COMPOSE_BAKE=false", self.unit)
        self.assertIn("Restart=always", self.unit)
        self.assertIn("scripts/server_supervisor.py", self.unit)
        self.assertNotIn("User=root", self.unit)
        self.assertNotIn("PrivateTmp=true", self.unit)

    def test_installer_creates_group_and_confined_control_directory(self) -> None:
        self.assertIn(
            'CLIENT_GROUP="${SERVER_SUPERVISOR_CLIENT_GROUP:-velvet-supervisor-client}"',
            self.installer,
        )
        self.assertIn("groupadd --system", self.installer)
        self.assertIn('usermod -a -G "$CLIENT_GROUP" velvet', self.installer)
        self.assertIn('"SUPERVISOR_ENABLED": "true"', self.installer)
        self.assertIn(
            '"SUPERVISOR_BASE_URL": "http://supervisor-proxy:8765"',
            self.installer,
        )
        self.assertIn("secrets.token_urlsafe(48)", self.installer)
        self.assertIn("SERVER_SUPERVISOR_CLIENT_GID", self.installer)
        self.assertIn("SERVER_SUPERVISOR_SOCKET_MODE", self.installer)
        self.assertIn('control_dir="$data_dir/control/supervisor"', self.installer)
        self.assertIn('chown velvet:"$CLIENT_GROUP" "$control_dir"', self.installer)
        self.assertIn('chmod 0750 "$control_dir"', self.installer)
        self.assertIn("systemctl enable velvet-server-supervisor.service", self.installer)
        self.assertIn("systemctl restart velvet-server-supervisor.service", self.installer)
        self.assertIn("systemctl reload velvet-compose.service", self.installer)
        self.assertIn('chmod 0700 "$docker_config"', self.installer)
        self.assertIn("permission-confined", self.installer)

    def test_proxy_forwards_to_unix_socket_without_auth_secrets(self) -> None:
        self.assertIn("asyncio.open_unix_connection", self.proxy)
        self.assertIn("asyncio.start_server", self.proxy)
        self.assertNotIn("SUPERVISOR_TOKEN", self.proxy)
        self.assertNotIn("subprocess", self.proxy)


if __name__ == "__main__":
    unittest.main()
