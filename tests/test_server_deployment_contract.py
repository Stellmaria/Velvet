from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


class ServerDeploymentContractTests(unittest.TestCase):
    def test_postgres_and_bot_have_no_public_ports(self) -> None:
        source = Path("docker-compose.server.yml").read_text(encoding="utf-8")
        postgres = source.split("  postgres:", 1)[1].split("\n  bot:", 1)[0]
        bot = source.split("  bot:", 1)[1].split("\n  # Запускается", 1)[0]
        self.assertNotIn("\n    ports:", postgres)
        self.assertNotIn("\n    ports:", bot)
        self.assertIn("no-new-privileges:true", postgres)
        self.assertIn("cap_drop:", bot)

    def test_hermes_is_isolated_from_production_secrets_and_docker(self) -> None:
        source = Path("docker-compose.server.yml").read_text(encoding="utf-8")
        hermes = source.split("  hermes:", 1)[1]
        self.assertIn(".env.hermes", hermes)
        self.assertNotIn(".env.server", hermes)
        self.assertNotIn("docker.sock", hermes)
        self.assertNotIn("/var/lib/postgresql", hermes)
        self.assertIn('"127.0.0.1:${HERMES_LOOPBACK_PORT:-8642}:8642"', hermes)

    def test_hermes_preserves_s6_overlay_as_pid_one(self) -> None:
        source = Path("docker-compose.server.yml").read_text(encoding="utf-8")
        bot = source.split("  bot:", 1)[1].split("\n  # Запускается", 1)[0]
        hermes = source.split("  hermes:", 1)[1]
        self.assertIn("init: true", bot)
        self.assertNotIn("init: true", hermes)
        self.assertIn("s6-overlay", hermes)
        self.assertIn('command: ["gateway", "run"]', hermes)

    def test_hermes_has_only_required_s6_init_capabilities(self) -> None:
        source = Path("docker-compose.server.yml").read_text(encoding="utf-8")
        hermes = source.split("  hermes:", 1)[1]
        self.assertIn("cap_drop:\n      - ALL", hermes)
        self.assertIn(
            "cap_add:\n"
            "      - CHOWN\n"
            "      - DAC_OVERRIDE\n"
            "      - FOWNER\n"
            "      - SETGID\n"
            "      - SETUID",
            hermes,
        )
        self.assertNotIn("privileged:", hermes)
        self.assertNotIn("SYS_ADMIN", hermes)
        self.assertNotIn("NET_ADMIN", hermes)
        self.assertIn("no-new-privileges:true", hermes)

    def test_server_env_starts_with_expensive_features_disabled(self) -> None:
        source = Path(".env.server.example").read_text(encoding="utf-8")
        for line in (
            "AI_TEXT_ENABLED=false",
            "AI_VISION_ENABLED=false",
            "AI_VISION_QUEUE_ENABLED=false",
            "KIE_ENABLED=false",
            "HERMES_INCIDENT_ENABLED=false",
            "CODEX_ENABLED=false",
            "KRITA_WATERMARK_ENABLED=false",
        ):
            self.assertIn(line, source)
        self.assertIn("@postgres:5432/velvet", source)
        self.assertIn("HERMES_BASE_URL=http://hermes:8642", source)

    def test_runtime_data_is_excluded_from_docker_build_context(self) -> None:
        ignored = {
            line.strip()
            for line in Path(".dockerignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertIn("data", ignored)
        self.assertIn("server-data", ignored)

    def test_deploy_verifies_dump_before_resetting_code(self) -> None:
        source = Path("deploy/server/deploy.sh").read_text(encoding="utf-8")
        self.assertLess(
            source.index("verify-dump.sh"),
            source.index('reset_checkout "$target_sha"'),
        )
        self.assertIn("scripts/server_preflight.py", source)
        self.assertIn("scripts/server_smoke.py", source)
        self.assertIn("Database was not automatically restored", source)

    def test_predeploy_dump_is_readable_by_bot_container(self) -> None:
        source = Path("deploy/server/deploy.sh").read_text(encoding="utf-8")
        self.assertIn('chmod 0644 "$backup_path"', source)
        self.assertNotIn('chmod 600 "$backup_path"', source)
        self.assertIn("normalize_backup_permissions()", source)
        self.assertIn('find "$backup_root" -maxdepth 1 -type f', source)
        self.assertIn("-name '*.dump'", source)
        self.assertIn("-name '*.dump.json'", source)
        self.assertIn('chmod 0644 -- "$candidate"', source)
        self.assertIn("-print0", source)
        self.assertLess(
            source.index('normalize_backup_permissions "$data_dir/backups"'),
            source.index('if [[ "$target_sha" == "$previous_sha"'),
        )

    def test_dump_verifier_uses_disposable_database_and_forced_cleanup(self) -> None:
        source = Path("deploy/server/verify-dump.sh").read_text(encoding="utf-8")
        self.assertIn("velvet_restore_check_", source)
        self.assertIn("pg_restore --list", source)
        self.assertIn("pg_restore --exit-on-error", source)
        self.assertIn("dropdb --force --if-exists", source)
        self.assertIn("schema_migrations", source)
        self.assertNotIn("DROP DATABASE velvet", source)

    def test_systemd_runs_preflight_before_compose(self) -> None:
        source = Path("deploy/systemd/velvet-compose.service").read_text(
            encoding="utf-8"
        )
        preflight = source.index("scripts/server_preflight.py")
        compose_config = source.index("config --quiet")
        compose_start = source.index("up -d --remove-orphans")
        self.assertLess(preflight, compose_config)
        self.assertLess(compose_config, compose_start)
        self.assertIn("User=velvet", source)

    def test_shell_scripts_parse_with_bash(self) -> None:
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("bash is unavailable")

        probe = subprocess.run(
            [bash, "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            details = (probe.stderr or probe.stdout).strip()
            self.skipTest(
                f"bash is unusable: {details or f'exit code {probe.returncode}'}"
            )

        for path in (
            "deploy/server/deploy.sh",
            "deploy/server/verify-dump.sh",
        ):
            with self.subTest(path=path):
                source = Path(path).read_text(encoding="utf-8")
                result = subprocess.run(
                    [bash, "-n"],
                    input=source,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                details = "\n".join(
                    part.strip()
                    for part in (result.stderr, result.stdout)
                    if part.strip()
                )
                self.assertEqual(
                    0,
                    result.returncode,
                    details or f"bash -n exited with {result.returncode}",
                )


if __name__ == "__main__":
    unittest.main()
