from __future__ import annotations

import ast
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path("deploy/hermes-coders")


class HermesCodersContractTests(unittest.TestCase):
    def test_coders_do_not_mount_production_or_docker_socket(self) -> None:
        source = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.assertNotIn("docker.sock", source)
        self.assertNotIn(".env.server", source)
        self.assertNotIn("/srv/velvet:/workspace", source)
        self.assertNotIn("/srv/romatic-club:/workspace", source)
        self.assertNotIn("/var/lib/postgresql", source)
        self.assertIn("/workspaces/velvet:/workspace", source)
        self.assertIn("/workspaces/max:/workspace", source)

    def test_coders_are_not_connected_to_production_networks(self) -> None:
        source = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        velvet = source.split("  hermes-coder-velvet:", 1)[1].split(
            "\n  max-db-proxy:", 1
        )[0]
        max_coder = source.split("  hermes-coder-max:", 1)[1].split(
            "\nnetworks:", 1
        )[0]

        self.assertIn("- egress", velvet)
        self.assertIn("- velvet-db", velvet)
        self.assertNotIn("velvet-production", velvet)
        self.assertNotIn("max-production", velvet)

        self.assertIn("- egress", max_coder)
        self.assertIn("- max-db", max_coder)
        self.assertNotIn("velvet-production", max_coder)
        self.assertNotIn("max-production", max_coder)

    def test_only_db_proxies_bridge_production_networks(self) -> None:
        source = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        velvet_proxy = source.split("  velvet-db-proxy:", 1)[1].split(
            "\n  hermes-coder-velvet:", 1
        )[0]
        max_proxy = source.split("  max-db-proxy:", 1)[1].split(
            "\n  hermes-coder-max:", 1
        )[0]

        self.assertIn("velvet-production", velvet_proxy)
        self.assertIn("velvet-db", velvet_proxy)
        self.assertNotIn("egress", velvet_proxy)
        self.assertIn("max-production", max_proxy)
        self.assertIn("max-db", max_proxy)
        self.assertNotIn("egress", max_proxy)

    def test_parallel_builds_use_distinct_image_tags(self) -> None:
        source = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        expected = (
            "velvet-hermes-coder-velvet:local",
            "velvet-hermes-coder-max:local",
            "velvet-hermes-db-proxy-velvet:local",
            "velvet-hermes-db-proxy-max:local",
        )
        for image in expected:
            with self.subTest(image=image):
                self.assertEqual(1, source.count(f"image: {image}"))

        self.assertNotIn("image: velvet-hermes-coder:local", source)
        self.assertNotIn("image: velvet-hermes-db-proxy:local", source)

    def test_model_routing_uses_only_verified_gpt_routes(self) -> None:
        source = (ROOT / "config.yaml").read_text(encoding="utf-8")
        self.assertIn("default: gpt-5.4-mini", source)
        self.assertIn("model: gpt-5.6-terra", source)
        self.assertIn("model: gpt-5.6-luna", source)
        self.assertNotIn("gpt-5.3-codex-spark", source)
        self.assertNotIn("api_key:", source)
        self.assertIn("cwd: /workspace", source)

    def test_github_token_passthrough_is_explicit_and_narrow(self) -> None:
        config = (ROOT / "config.yaml").read_text(encoding="utf-8")
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

        self.assertIn("env_passthrough:", config)
        self.assertIn("- GH_TOKEN", config)
        self.assertIn("TERMINAL_ENV_PASSTHROUGH: '[\"GH_TOKEN\"]'", compose)
        self.assertNotIn("BYESU_HERMES_CODEX_API_KEY\"]", compose)
        self.assertNotIn("BYESU_HERMES_GPT_PRO_API_KEY\"]", compose)
        self.assertNotIn("TELEGRAM_BOT_TOKEN\"]", compose)

    def test_preflight_requires_distinct_tokens_and_read_only_roles(self) -> None:
        source = (ROOT / "preflight.py").read_text(encoding="utf-8")
        self.assertIn("TELEGRAM_BOT_TOKEN", source)
        self.assertIn("GH_TOKEN", source)
        self.assertIn("hermes_velvet_ro", source)
        self.assertIn("hermes_max_ro", source)
        self.assertIn("Velvet и Max должны использовать разные", source)

    def test_installer_prepares_without_optional_operator_model_key(self) -> None:
        source = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn('if line.startswith("export ")', source)
        self.assertIn(
            'existing.get("BYESU_HERMES_GPT_PRO_API_KEY", "")',
            source,
        )
        self.assertIn("поле оставлено пустым", source)
        self.assertIn("Preflight не позволит запустить gateway", source)
        self.assertNotIn(
            'raise SystemExit("В operator env не найден ключ маршрута gpt-5.6-luna")',
            source,
        )
        self.assertNotIn(
            'raise SystemExit("В operator env отсутствует BYESU_HERMES_CODEX_API_KEY")',
            source,
        )

    def test_service_user_can_read_preflight_metadata(self) -> None:
        installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        preflight = (ROOT / "preflight.py").read_text(encoding="utf-8")

        self.assertIn(
            'install -d -o "$HERMES_UID_VALUE" -g "$APP_GROUP" -m 0750',
            installer,
        )
        self.assertIn(
            'chown "$HERMES_UID_VALUE:$APP_GROUP"',
            installer,
        )
        self.assertIn("chmod 0640", installer)
        self.assertIn("def require_readable_file", preflight)
        self.assertIn("except PermissionError as exc", preflight)
        self.assertIn("Нет доступа к Hermes-файлу", preflight)

    def test_systemd_runs_preflight_before_start(self) -> None:
        source = Path("deploy/systemd/hermes-coders.service").read_text(
            encoding="utf-8"
        )
        self.assertLess(source.index("preflight.py"), source.index("config --quiet"))
        self.assertLess(source.index("config --quiet"), source.index("up -d --build"))
        self.assertIn("User=velvet", source)
        self.assertIn("After=docker.service", source)

    def test_python_sources_parse(self) -> None:
        for path in (ROOT / "db_proxy.py", ROOT / "preflight.py"):
            with self.subTest(path=path):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def test_install_script_parses_with_bash(self) -> None:
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("bash is unavailable")
        source = (ROOT / "install.sh").read_text(encoding="utf-8")
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
        self.assertEqual(0, result.returncode, details)

    def test_coder_image_pins_hermes_and_installs_db_tools(self) -> None:
        source = (ROOT / "Dockerfile.coder").read_text(encoding="utf-8")
        self.assertIn("nousresearch/hermes-agent@sha256:", source)
        self.assertIn("postgresql-client", source)
        self.assertIn("gh", source)


if __name__ == "__main__":
    unittest.main()
