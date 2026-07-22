from __future__ import annotations

import unittest
from pathlib import Path

from velvet_bot.presentation.telegram.routers.workspace_quick_setup import _parse_target


class WorkspaceSetupParserTests(unittest.TestCase):
    def test_parses_numeric_chat_and_optional_thread(self) -> None:
        self.assertEqual((-1001234567890, None), _parse_target("-1001234567890"))
        self.assertEqual((-1001234567890, 42), _parse_target("-1001234567890 42"))

    def test_normalizes_public_username(self) -> None:
        self.assertEqual(("@velvet_archive", None), _parse_target("velvet_archive"))
        self.assertEqual(("@velvet_archive", None), _parse_target("@velvet_archive"))

    def test_rejects_invalid_thread(self) -> None:
        with self.assertRaises(ValueError):
            _parse_target("-100123 nope")


class WorkspaceSetupSourceContractTests(unittest.TestCase):
    def test_access_extensions_cover_lifecycle_routes(self) -> None:
        source = Path("velvet_bot/core/access/workspace_extensions.py").read_text(
            encoding="utf-8"
        )
        for command in (
            "workspace_setup",
            "workspace_bind",
            "workspace_quick_setup",
            "workspace_delete",
        ):
            self.assertIn(f'"{command}"', source)
        for prefix in ("wob:", "wqs:", "wsdel:"):
            self.assertIn(f'"{prefix}"', source)

    def test_quick_setup_precedes_old_workspace_name_handlers(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        quick = source.index("router.include_router(workspace_quick_setup_router)")
        onboarding = source.index("router.include_router(workspace_onboarding_router)")
        legacy = source.index("router.include_router(workspaces_router)")
        self.assertLess(quick, onboarding)
        self.assertLess(quick, legacy)

    def test_start_and_workspace_home_expose_remove_action(self) -> None:
        start_source = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public_controllers/start.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Продолжить быструю настройку", start_source)
        self.assertIn("Удалить моё пространство", start_source)

        workspace_ui = Path("velvet_bot/workspace_ui.py").read_text(encoding="utf-8")
        self.assertIn("🗑 Удалить пространство", workspace_ui)
        self.assertIn('callback_data=f"wsdel:request:{workspace.id}"', workspace_ui)
        self.assertIn("if not workspace.is_system", workspace_ui)

    def test_lifecycle_migration_cascades_blocking_foreign_keys(self) -> None:
        migration = Path("migrations/911_workspace_self_delete.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("characters_workspace_id_fkey", migration)
        self.assertIn("watermark_jobs_workspace_id_fkey", migration)
        self.assertEqual(2, migration.count("ON DELETE CASCADE"))

    def test_remove_flow_requires_explicit_confirmation(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/workspace_delete.py"
        ).read_text(encoding="utf-8")
        self.assertIn('action="confirm"', source)
        self.assertIn("удалить безвозвратно", source)
        service = Path("velvet_bot/domains/workspaces/deletion.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("Системное пространство Velvet удалить нельзя", service)


if __name__ == "__main__":
    unittest.main()
