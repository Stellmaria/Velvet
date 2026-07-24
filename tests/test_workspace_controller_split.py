from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.presentation.telegram.routers.core_operations_controllers.workspace_command_filtering import (
    command_name,
)
from velvet_bot.presentation.telegram.workspace_archive_dashboard import (
    build_workspace_archive_dashboard,
)

ROOT = Path(__file__).resolve().parents[1]
CONTROLLERS = (
    ROOT
    / "velvet_bot/presentation/telegram/routers/core_operations_controllers"
)
PRESENTATION = ROOT / "velvet_bot/presentation/telegram"


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
        rows = [
            {"id": 3, "name": "Каэль", "archive_topic_url": None, "media_count": 2},
            {"id": 4, "name": "Эрик", "archive_topic_url": None, "media_count": 0},
        ]
        keyboard = Mock()

        with (
            patch(
                "velvet_bot.presentation.telegram.workspace_archive_dashboard."
                "_legacy_load_archive_characters",
                new=AsyncMock(return_value=rows),
            ) as loader,
            patch(
                "velvet_bot.presentation.telegram.workspace_archive_dashboard."
                "_legacy_archive_dashboard_keyboard",
                return_value=keyboard,
            ) as keyboard_builder,
        ):
            dashboard = await build_workspace_archive_dashboard(
                SimpleNamespace(),  # type: ignore[arg-type]
                workspace,
                command_context=True,
            )

        self.assertEqual(2, dashboard.character_count)
        self.assertIn("Архив · Мой архив", dashboard.text)
        self.assertIn("Персонажей: <b>2</b>", dashboard.text)
        self.assertIn("активного пользовательского пространства", dashboard.text)
        self.assertIs(keyboard, dashboard.keyboard)
        loader.assert_awaited_once_with(SimpleNamespace(), workspace_id=9)
        keyboard_builder.assert_called_once_with(workspace_id=9, rows=rows)


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

    def test_archive_controller_uses_public_dashboard_contract(self) -> None:
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

    def test_archive_dashboard_contract_contains_compatibility_boundary(self) -> None:
        source = (
            PRESENTATION / "workspace_archive_dashboard.py"
        ).read_text(encoding="utf-8")

        self.assertIn("class WorkspaceArchiveDashboard", source)
        self.assertIn("async def build_workspace_archive_dashboard", source)
        self.assertIn("_legacy_load_archive_characters", source)
        self.assertIn("_legacy_archive_dashboard_keyboard", source)
        self.assertIn("character_count", source)

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
