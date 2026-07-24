from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.presentation.telegram.routers.core_operations_controllers.workspace_command_filtering import (
    command_name,
)
from velvet_bot.presentation.telegram.workspace_archive_dashboard import (
    WorkspaceArchiveCharacter,
    build_workspace_archive_dashboard,
    build_workspace_archive_dashboard_keyboard,
)

ROOT = Path(__file__).resolve().parents[1]
CONTROLLERS = (
    ROOT
    / "velvet_bot/presentation/telegram/routers/core_operations_controllers"
)
PRESENTATION = ROOT / "velvet_bot/presentation/telegram"
ROUTERS = PRESENTATION / "routers"


class WorkspaceCommandFilteringTests(unittest.TestCase):
    def test_command_name_accepts_bot_suffix(self) -> None:
        message = SimpleNamespace(
            text="/archive@DominusVelvetBot extra",
            caption=None,
        )

        self.assertEqual("archive", command_name(message))

    def test_command_name_falls_back_to_caption(self) -> None:
        message = SimpleNamespace(
            text=None,
            caption="/watermark@DominusVelvetBot",
        )

        self.assertEqual("watermark", command_name(message))


class WorkspaceArchiveDashboardContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_contract_returns_ready_to_render_dashboard(self) -> None:
        now = datetime.now(UTC)
        workspace = Workspace(9, "private-9", "Мой архив", False, now, now)
        database = SimpleNamespace()
        characters = (
            WorkspaceArchiveCharacter(3, "Каэль", None, 2),
            WorkspaceArchiveCharacter(4, "Эрик", None, 0),
        )

        with patch(
            "velvet_bot.presentation.telegram.workspace_archive_dashboard."
            "load_workspace_archive_characters",
            new=AsyncMock(return_value=characters),
        ) as loader:
            dashboard = await build_workspace_archive_dashboard(
                database,  # type: ignore[arg-type]
                workspace,
                command_context=True,
            )

        labels = [
            button.text
            for row in dashboard.keyboard.inline_keyboard
            for button in row
        ]
        self.assertEqual(2, dashboard.character_count)
        self.assertIn("Архив · Мой архив", dashboard.text)
        self.assertIn("Персонажей: <b>2</b>", dashboard.text)
        self.assertIn("активного пользовательского пространства", dashboard.text)
        self.assertIn("🖼 Каэль · 2", labels)
        self.assertIn("➖ Эрик · пусто", labels)
        loader.assert_awaited_once_with(database, workspace_id=9)

    def test_keyboard_keeps_topic_links_and_workspace_navigation(self) -> None:
        keyboard = build_workspace_archive_dashboard_keyboard(
            workspace_id=9,
            characters=(
                WorkspaceArchiveCharacter(
                    3,
                    "Каэль",
                    "https://t.me/c/1/2",
                    0,
                ),
            ),
        )
        buttons = [button for row in keyboard.inline_keyboard for button in row]

        topic = next(button for button in buttons if button.text.startswith("📂"))
        back = next(button for button in buttons if button.text == "↩️ Моё пространство")
        self.assertEqual("https://t.me/c/1/2", topic.url)
        self.assertIsNotNone(back.callback_data)
        self.assertTrue(back.callback_data.startswith("wsp:home:9:"))


class WorkspaceControllerSplitTests(unittest.TestCase):
    def test_home_hint_controller_only_keeps_home_preference_flow(self) -> None:
        source = (
            CONTROLLERS / "workspace_home_hint_controller.py"
        ).read_text(encoding="utf-8")

        self.assertIn("handle_workspace_help_toggle", source)
        for forbidden in (
            "PersonalArchiveCommandFilter",
            "WatermarkCommandFilter",
            "WatermarkCallback",
            "core_watermark",
            "_DRAFT_ACTIONS",
        ):
            self.assertNotIn(forbidden, source)
        self.assertFalse((CONTROLLERS / "workspace_product_experience.py").exists())

    def test_archive_command_controller_uses_public_dashboard_contract(self) -> None:
        source = (
            CONTROLLERS / "workspace_archive_controller.py"
        ).read_text(encoding="utf-8")

        self.assertIn("class PersonalArchiveCommandFilter", source)
        self.assertIn("handle_personal_archive_command", source)
        self.assertIn("build_workspace_archive_dashboard", source)
        self.assertNotIn("workspace_owner_controls", source)
        self.assertNotIn("_load_archive_characters", source)
        self.assertNotIn("_archive_dashboard_keyboard", source)
        self.assertNotIn("WatermarkCallback", source)

    def test_archive_dashboard_contract_owns_query_and_keyboard(self) -> None:
        source = (
            PRESENTATION / "workspace_archive_dashboard.py"
        ).read_text(encoding="utf-8")

        self.assertIn("class WorkspaceArchiveCharacter", source)
        self.assertIn("class WorkspaceArchiveDashboard", source)
        self.assertIn("async def load_workspace_archive_characters", source)
        self.assertIn("def build_workspace_archive_dashboard_keyboard", source)
        self.assertIn("async def build_workspace_archive_dashboard", source)
        self.assertIn("FROM characters AS character", source)
        self.assertNotIn("_legacy_load_archive_characters", source)
        self.assertNotIn("_legacy_archive_dashboard_keyboard", source)
        self.assertNotIn("_load_archive_characters as", source)
        self.assertNotIn("_archive_dashboard_keyboard as", source)

    def test_archive_dashboard_callback_has_bundle_registrar(self) -> None:
        source = (
            PRESENTATION / "workspace_archive_dashboard_controller.py"
        ).read_text(encoding="utf-8")

        self.assertIn("handle_workspace_archive_dashboard", source)
        self.assertIn("register_workspace_archive_dashboard", source)
        self.assertIn("router.callback_query.register", source)
        self.assertIn('module_key="archive"', source)
        self.assertIn('minimum_role="viewer"', source)
        self.assertNotIn("@router.callback_query", source)
        self.assertNotIn("_render_archive_dashboard", source)
        self.assertNotIn("_load_archive_characters", source)
        self.assertFalse(
            (ROUTERS / "workspace_archive_dashboard_controller.py").exists()
        )

    def test_archive_dashboard_registers_before_owner_controls_router(self) -> None:
        source = (ROUTERS / "archive_and_public.py").read_text(encoding="utf-8")

        canonical = source.index("register_workspace_archive_dashboard(router)")
        legacy = source.index(
            "router.include_router(workspace_owner_controls_router)"
        )
        self.assertLess(canonical, legacy)
        self.assertNotIn("workspace_archive_dashboard_router", source)

    def test_watermark_controller_owns_draft_flow(self) -> None:
        source = (
            CONTROLLERS / "workspace_watermark_draft_controller.py"
        ).read_text(encoding="utf-8")

        self.assertIn("class WatermarkCommandFilter", source)
        self.assertIn("handle_watermark_draft_callback", source)
        self.assertIn("handle_watermark_draft_color", source)
        self.assertNotIn("_load_archive_characters", source)

    def test_owner_menu_composes_specific_routers_before_legacy_watermark(self) -> None:
        source = (CONTROLLERS / "owner_menu.py").read_text(encoding="utf-8")

        archive = source.index("router.include_router(workspace_archive_router)")
        home_hint = source.index(
            "router.include_router(workspace_home_hint_router)"
        )
        draft = source.index(
            "router.include_router(workspace_watermark_draft_router)"
        )
        legacy = source.index("router.include_router(watermark_router)")

        self.assertLess(archive, home_hint)
        self.assertLess(home_hint, draft)
        self.assertLess(draft, legacy)


if __name__ == "__main__":
    unittest.main()
