from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from aiogram.types import User

from velvet_bot.core.config.arthur import ArthurSettings
from velvet_bot.presentation.telegram.arthur_librarian import _caller_allowed


ROOT = Path(__file__).resolve().parents[1]


def _compose_service(source: str, name: str) -> str:
    lines = source.splitlines()
    marker = f"  {name}:"
    start = lines.index(marker)
    selected = [lines[start]]
    for line in lines[start + 1 :]:
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            break
        selected.append(line)
    return "\n".join(selected)


class ArthurSettingsTests(unittest.TestCase):
    def test_separate_token_and_owner_allowlist_are_required(self) -> None:
        environment = {
            "ARTHUR_BOT_TOKEN": "123456:arthur-token-value",
            "BOT_TOKEN": "654321:velvet-token-value",
            "DATABASE_URL": "postgresql://velvet@postgres/velvet",
            "ARTHUR_ALLOWED_USER_IDS": "42,84",
            "ARTHUR_STORAGE_GATEWAY_API_KEY": "a" * 32,
            "STORAGE_LIBRARIAN_AUTO_ENQUEUE": "false",
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = ArthurSettings.from_env()
        self.assertEqual(frozenset({42, 84}), settings.allowed_user_ids)
        self.assertNotEqual(environment["BOT_TOKEN"], settings.bot_token)

    def test_token_reuse_fails_closed(self) -> None:
        environment = {
            "ARTHUR_BOT_TOKEN": "123456:shared-token-value",
            "BOT_TOKEN": "123456:shared-token-value",
            "DATABASE_URL": "postgresql://velvet@postgres/velvet",
            "ARTHUR_ALLOWED_USER_IDS": "42",
            "ARTHUR_STORAGE_GATEWAY_API_KEY": "a" * 32,
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ValueError, "must not reuse"):
                ArthurSettings.from_env()

    def test_auto_enqueue_fails_closed(self) -> None:
        environment = {
            "ARTHUR_BOT_TOKEN": "123456:arthur-token-value",
            "DATABASE_URL": "postgresql://velvet@postgres/velvet",
            "ARTHUR_ALLOWED_USER_IDS": "42",
            "ARTHUR_STORAGE_GATEWAY_API_KEY": "a" * 32,
            "STORAGE_LIBRARIAN_AUTO_ENQUEUE": "true",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ValueError, "AUTO_ENQUEUE=false"):
                ArthurSettings.from_env()

    def test_owner_policy_accepts_id_or_normalized_username(self) -> None:
        environment = {
            "ARTHUR_BOT_TOKEN": "123456:arthur-token-value",
            "DATABASE_URL": "postgresql://velvet@postgres/velvet",
            "ARTHUR_ALLOWED_USER_IDS": "42",
            "ARTHUR_ALLOWED_USERNAMES": "@Stellmaria",
            "ARTHUR_STORAGE_GATEWAY_API_KEY": "a" * 32,
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = ArthurSettings.from_env()
        self.assertTrue(
            _caller_allowed(
                User(id=42, is_bot=False, first_name="Owner"),
                settings,
            )
        )
        self.assertTrue(
            _caller_allowed(
                User(
                    id=100,
                    is_bot=False,
                    first_name="Owner",
                    username="STELLMARIA",
                ),
                settings,
            )
        )
        self.assertFalse(
            _caller_allowed(
                User(id=101, is_bot=False, first_name="Other"),
                settings,
            )
        )


class ArthurArchitectureContractTests(unittest.TestCase):
    def test_main_owner_router_no_longer_executes_librarian_registration(self) -> None:
        path = (
            ROOT
            / "velvet_bot"
            / "presentation"
            / "telegram"
            / "routers"
            / "core_operations_controllers"
            / "owner_menu.py"
        )
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertNotIn("register_storage_librarian", calls)

    def test_arthur_commands_are_dedicated_and_manual_first(self) -> None:
        source = (
            ROOT
            / "velvet_bot"
            / "presentation"
            / "telegram"
            / "arthur_librarian.py"
        ).read_text(encoding="utf-8")
        for command in (
            "start",
            "status",
            "analyze",
            "result",
            "ask",
            "digest",
            "queue",
            "download",
            "help",
        ):
            self.assertIn(f'Command("{command}")', source)
        self.assertNotIn('Command("cancel")', source)
        self.assertIn("manual-first", source)

    def test_manual_analysis_claims_only_requested_object(self) -> None:
        repository = (
            ROOT
            / "velvet_bot"
            / "domains"
            / "telegram_storage"
            / "arthur_repository.py"
        ).read_text(encoding="utf-8")
        base_repository = (
            ROOT
            / "velvet_bot"
            / "domains"
            / "telegram_storage"
            / "librarian_repository.py"
        ).read_text(encoding="utf-8")
        application = (
            ROOT
            / "velvet_bot"
            / "application"
            / "arthur_librarian.py"
        ).read_text(encoding="utf-8")
        self.assertIn("WHERE storage_object_id = $1::BIGINT", repository)
        self.assertIn("status <> 'running'", base_repository)
        self.assertIn("target_object_id=object_id", application)
        self.assertIn("process_once(auto_enqueue=False)", application)

    def test_gateway_exists_because_telegram_file_ids_are_bot_scoped(self) -> None:
        runbook = (
            ROOT / "docs" / "runbooks" / "arthur_librarian.md"
        ).read_text(encoding="utf-8")
        gateway = (
            ROOT
            / "velvet_bot"
            / "infrastructure"
            / "telegram"
            / "arthur_storage_gateway_server.py"
        ).read_text(encoding="utf-8")
        self.assertIn("file_id", runbook)
        self.assertIn("bot-scoped", runbook)
        self.assertIn("Authorization", gateway)
        self.assertIn("hmac.compare_digest", gateway)

    def test_status_probes_live_gateway_ollama_alias_and_hermes(self) -> None:
        application = (
            ROOT
            / "velvet_bot"
            / "application"
            / "arthur_librarian.py"
        ).read_text(encoding="utf-8")
        presentation = (
            ROOT
            / "velvet_bot"
            / "presentation"
            / "telegram"
            / "arthur_librarian.py"
        ).read_text(encoding="utf-8")
        self.assertIn('ollama_base_url.rstrip("/") + "/api/tags"', application)
        self.assertIn('hermes_base_url.rstrip("/") + "/health"', application)
        self.assertIn('payload.get("status") == "ok"', application)
        self.assertIn("self.librarian_settings.text_model in names", application)
        self.assertIn("arthur_app.service_health()", presentation)
        for label in ("Gateway:", "Ollama:", "Text alias:", "Hermes:"):
            self.assertIn(label, presentation)


class ArthurDeploymentContractTests(unittest.TestCase):
    def setUp(self) -> None:
        compose_path = ROOT / "deploy" / "hermes-librarian" / "compose.yaml"
        self.compose_text = compose_path.read_text(encoding="utf-8")
        self.arthur = _compose_service(self.compose_text, "arthur")
        self.gateway = _compose_service(
            self.compose_text,
            "arthur-storage-gateway",
        )
        self.ollama = _compose_service(self.compose_text, "ollama-librarian")

    def test_arthur_and_gateway_are_isolated_profile_services(self) -> None:
        for service in (self.arthur, self.gateway):
            self.assertIn('profiles: ["arthur"]', service)
            self.assertIn("read_only: true", service)
            self.assertIn("cap_drop:\n      - ALL", service)
            self.assertNotIn("ports:", service)
        self.assertNotIn("ports:", self.compose_text)

    def test_arthur_does_not_receive_velvet_or_operator_credentials(self) -> None:
        self.assertNotIn("\n      BOT_TOKEN:", self.arthur)
        self.assertNotIn("GH_TOKEN", self.arthur)
        self.assertNotIn("OPENAI_API_KEY", self.arthur)
        self.assertNotIn("/var/run/docker.sock", self.compose_text)
        self.assertIn("\n      BOT_TOKEN:", self.gateway)
        self.assertNotIn("ARTHUR_BOT_TOKEN", self.gateway)

    def test_auto_enqueue_and_ollama_model_limit_remain_fixed(self) -> None:
        self.assertIn('STORAGE_LIBRARIAN_AUTO_ENQUEUE: "false"', self.arthur)
        self.assertIn('OLLAMA_MAX_LOADED_MODELS: "1"', self.ollama)

    def test_installer_prepares_arthur_data_dir_without_recursive_chown(self) -> None:
        installer = (
            ROOT / "deploy" / "hermes-librarian" / "install.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'ARTHUR_TARGET_DIR="$VELVET_DATA_DIR/arthur"',
            installer,
        )
        self.assertIn(
            'install -d -m 0750 -o 10001 -g 10001 "$ARTHUR_TARGET_DIR"',
            installer,
        )

    def test_start_script_smokes_actual_arthur_to_ollama_path(self) -> None:
        start = (
            ROOT / "deploy" / "hermes-librarian" / "start.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("--profile arthur", start)
        self.assertIn("--no-deps --force-recreate", start)
        self.assertIn("hmac.compare_digest", start)
        self.assertIn("9223372036854775807", start)
        self.assertIn("response.status == 404", start)
        self.assertIn("OllamaStorageAnalysisClient", start)
        self.assertIn("arthur-install-smoke", start)
        self.assertIn('result.analyzer == "ollama"', start)


if __name__ == "__main__":
    unittest.main()
