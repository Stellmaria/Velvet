from __future__ import annotations

import ast
import importlib.util
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from velvet_bot.domains.telegram_storage.librarian_models import (
    StorageLibrarianSettings,
)


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class HermesEntitySeparationTests(unittest.TestCase):
    def test_kael_soul_contains_identity_not_operational_commands(self) -> None:
        soul = (ROOT / "deploy/hermes-operator/SOUL.kael.md").read_text(
            encoding="utf-8"
        )
        agents = (ROOT / "deploy/hermes-operator/AGENTS.kael.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Ты Каэль", soul)
        self.assertNotIn("python /opt/data/tools/", soul)
        self.assertNotIn("docker compose", soul)
        self.assertIn("python /opt/data/tools/opsctl.py", agents)
        self.assertIn("python /opt/data/tools/coderctl.py", agents)
        self.assertIn("python /opt/data/tools/runctl.py", agents)

    def test_coder_souls_are_personas_and_project_rules_are_separate(self) -> None:
        cases = {
            "velvet": ("Velvet Coder", "Stellmaria/Velvet"),
            "max": ("Ты Макс", "Stellmaria/romatic_club_bot_max"),
        }
        for project, (identity, repository) in cases.items():
            with self.subTest(project=project):
                soul = (ROOT / f"deploy/hermes-coders/SOUL.{project}.md").read_text(
                    encoding="utf-8"
                )
                agents = (
                    ROOT / f"deploy/hermes-coders/AGENTS.{project}.md"
                ).read_text(encoding="utf-8")
                self.assertIn(identity, soul)
                self.assertNotIn("/workspace", soul)
                self.assertNotIn("default_transaction_read_only", soul)
                self.assertNotIn("STATUS: completed|blocked|failed", soul)
                self.assertIn(repository, agents)
                self.assertIn("/workspace", agents)
                self.assertIn("STATUS: completed|blocked|failed", agents)

    def test_librarian_has_own_identity_and_machine_contract(self) -> None:
        soul = (ROOT / "deploy/hermes-librarian/SOUL.md").read_text(encoding="utf-8")
        agents = (ROOT / "deploy/hermes-librarian/AGENTS.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Velvet Librarian", soul)
        self.assertIn("Storage ID", soul)
        self.assertIn('"summary"', agents)
        self.assertIn("без Markdown", agents)
        self.assertIn("Не используй внешние знания", agents)


class LibrarianRuntimeIsolationTests(unittest.TestCase):
    def test_compose_has_no_telegram_github_host_port_or_host_control(self) -> None:
        compose = (ROOT / "deploy/hermes-librarian/compose.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn('TELEGRAM_BOT_TOKEN: ""', compose)
        self.assertIn('GH_TOKEN: ""', compose)
        self.assertIn("STORAGE_LIBRARIAN_HERMES_API_KEY", compose)
        self.assertIn("hermes-librarian:/opt/data", compose)
        self.assertIn("ollama-librarian", compose)
        self.assertIn("librarian-ollama:/root/.ollama", compose)
        self.assertIn("name: velvet_backend", compose)
        self.assertNotIn("ports:", compose)
        self.assertNotIn("docker.sock", compose)
        self.assertNotIn("/srv/velvet:/", compose)
        self.assertNotIn("/run/systemd", compose)

    def test_profile_builder_uses_explicit_empty_api_whitelist_and_deny_list(self) -> None:
        source = (ROOT / "deploy/hermes-librarian/prepare_profile.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        self.assertIsNotNone(tree)
        self.assertIn('config["platform_toolsets"] = {"api_server": []}', source)
        self.assertIn('"provider": "custom"', source)
        self.assertIn('config["fallback_providers"] = []', source)
        for toolset in (
            "terminal",
            "file",
            "web",
            "browser",
            "memory",
            "delegation",
            "code_execution",
            "messaging",
        ):
            self.assertIn(f'"{toolset}"', source)
        self.assertIn('config["mcp_servers"] = {}', source)

    def test_storage_settings_prefer_dedicated_librarian_endpoint(self) -> None:
        with patch.dict(
            os.environ,
            {
                "STORAGE_LIBRARIAN_ENABLED": "true",
                "STORAGE_LIBRARIAN_HERMES_BASE_URL": "http://librarian-hermes:8642",
                "STORAGE_LIBRARIAN_HERMES_API_KEY": "l" * 48,
                "HERMES_BASE_URL": "http://hermes:8642",
                "HERMES_API_KEY": "k" * 48,
            },
            clear=True,
        ):
            settings = StorageLibrarianSettings.from_env()
        self.assertEqual("http://librarian-hermes:8642", settings.hermes_base_url)
        self.assertEqual("l" * 48, settings.hermes_api_key)
        self.assertEqual(
            "velvet-librarian:qwen3.5-9b-local:v3",
            settings.analyzer_version,
        )
        self.assertEqual(900, settings.run_timeout_seconds)


class HermesEntityDeploymentTests(unittest.TestCase):
    def test_reconcile_repairs_tools_ledger_and_generates_project_context(self) -> None:
        source = (ROOT / "deploy/hermes-entities/reconcile.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('install -d -m 0750 -o "$hermes_uid" -g "$hermes_gid"', source)
        self.assertIn('ledger="$hermes_data/orchestration/tasks.json"', source)
        self.assertIn('lock="$ledger.lock"', source)
        self.assertIn('chmod 0600 "$ledger" "$lock"', source)
        self.assertIn('workspace / ".hermes.md"', source)
        self.assertIn('workspace / "AGENTS.md"', source)
        self.assertIn('lines.append(".hermes.md")', source)

    def test_runctl_targets_only_loopback_main_runs_api(self) -> None:
        runctl = load_module(
            "hermes_runctl_entity_test",
            ROOT / "deploy/hermes-operator/runctl.py",
        )
        with patch.dict(
            os.environ,
            {"KAEL_RUNS_BASE_URL": "http://127.0.0.1:8642"},
            clear=False,
        ):
            self.assertEqual("http://127.0.0.1:8642", runctl._base_url())
        with patch.dict(
            os.environ,
            {"KAEL_RUNS_BASE_URL": "https://example.invalid"},
            clear=False,
        ):
            with self.assertRaises(runctl.RunCtlError):
                runctl._base_url()
        self.assertEqual(
            "run_6b7d8f5f18974285a892fce4e1b1ffa9",
            runctl._validate_run_id("run_6b7d8f5f18974285a892fce4e1b1ffa9"),
        )

    def test_installers_and_reconcile_parse_as_bash(self) -> None:
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("bash is unavailable")
        for relative in (
            "deploy/hermes-entities/reconcile.sh",
            "deploy/hermes-entities/install.sh",
            "deploy/hermes-librarian/install.sh",
            "deploy/hermes-librarian/start.sh",
        ):
            result = subprocess.run(
                [bash, "-n", str(ROOT / relative)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, f"{relative}: {result.stderr}")

    def test_systemd_units_have_boot_lifecycle(self) -> None:
        entities = (
            ROOT / "deploy/systemd/hermes-entities-reconcile.service"
        ).read_text(encoding="utf-8")
        librarian = (ROOT / "deploy/systemd/velvet-librarian.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("Before=velvet-compose.service hermes-coders.service", entities)
        self.assertIn("WantedBy=multi-user.target", entities)
        self.assertIn("After=docker.service velvet-compose.service", librarian)
        self.assertIn("User=velvet", librarian)
        self.assertIn("deploy/hermes-librarian/start.sh", librarian)
        self.assertIn("WantedBy=multi-user.target", librarian)


if __name__ == "__main__":
    unittest.main()
