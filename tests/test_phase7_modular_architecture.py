from __future__ import annotations

import ast
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from velvet_bot.app.commands import (
    build_admin_commands,
    build_editor_commands,
    build_public_commands,
)
from velvet_bot.app.workers import build_worker_manager
from velvet_bot.core.config.kie import KieSettings
from velvet_bot.domains.media_generation import KieModelCatalog, KiePricing
from velvet_bot.presentation.telegram.router import get_root_router


class CommandCatalogTests(unittest.TestCase):
    def test_command_catalogs_have_no_duplicates(self) -> None:
        for commands in (
            build_public_commands(),
            build_editor_commands(),
            build_admin_commands(),
        ):
            names = [item.command for item in commands]
            self.assertEqual(len(names), len(set(names)))

    def test_role_catalogs_extend_public_commands(self) -> None:
        public = {item.command for item in build_public_commands()}
        editor = {item.command for item in build_editor_commands()}
        admin = {item.command for item in build_admin_commands()}
        self.assertLessEqual(public, editor)
        self.assertLessEqual(public, admin)
        self.assertIn("menu", admin)
        self.assertIn("menu", editor)
        self.assertNotIn("system", admin)
        self.assertNotIn("backup", admin)
        self.assertNotIn("supervisor", admin)
        self.assertLessEqual(len(admin), 3)


class WorkerRegistryTests(unittest.TestCase):
    @staticmethod
    def _disabled_kie_settings() -> KieSettings:
        return KieSettings(
            enabled=False,
            api_key=None,
            base_url="https://api.kie.ai/api/v1",
            file_upload_base_url="https://kieai.redpandaai.co",
            timeout_seconds=60,
            poll_interval_seconds=4,
            task_timeout_seconds=900,
            usd_to_rub=Decimal("0"),
            models=KieModelCatalog(),
            pricing=KiePricing(),
        )

    def _build_manager(self):
        return build_worker_manager(
            bot=object(),  # type: ignore[arg-type]
            database=object(),  # type: ignore[arg-type]
            backup_service=object(),  # type: ignore[arg-type]
            kie_settings=self._disabled_kie_settings(),
        )

    def test_application_registers_expected_workers(self) -> None:
        with patch.dict(
            "os.environ",
            {"KRITA_WATERMARK_ENABLED": "false"},
            clear=False,
        ):
            manager = self._build_manager()
        self.assertEqual(
            manager.registered_names(),
            (
                "public-archive-notifications",
                "publication-queue",
                "media-quality",
                "ai-task-stale-recovery",
                "postgresql-backups",
            ),
        )

    def test_krita_worker_is_registered_when_feature_flag_is_enabled(self) -> None:
        with patch.dict(
            "os.environ",
            {"KRITA_WATERMARK_ENABLED": "true"},
            clear=False,
        ):
            manager = self._build_manager()
        self.assertEqual(
            manager.registered_names(),
            (
                "public-archive-notifications",
                "publication-queue",
                "media-quality",
                "ai-task-stale-recovery",
                "krita-watermark",
                "postgresql-backups",
            ),
        )


class CompositionRootTests(unittest.TestCase):
    def test_main_is_only_an_entrypoint(self) -> None:
        source = Path("main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertEqual(imported_modules, {"velvet_bot.app"})
        self.assertLessEqual(len(source.splitlines()), 20)

    def test_root_router_is_built_once(self) -> None:
        self.assertIs(get_root_router(), get_root_router())

    def test_architecture_document_exists(self) -> None:
        self.assertTrue(Path("docs/architecture_target.md").is_file())


if __name__ == "__main__":
    unittest.main()
