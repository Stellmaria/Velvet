from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.presentation.telegram.workspace_deletion_controller import (
    WorkspaceDeleteCommandFilter,
    build_workspace_delete_keyboard,
)
from velvet_bot.presentation.telegram.workspace_reference_dashboard import (
    WorkspaceReferenceCharacter,
    build_workspace_reference_dashboard,
    build_workspace_reference_dashboard_keyboard,
    parse_workspace_reference_callback,
)

ROOT = Path(__file__).resolve().parents[1]
PRESENTATION = ROOT / "velvet_bot/presentation/telegram"
ROUTERS = PRESENTATION / "routers"


def _workspace() -> Workspace:
    now = datetime.now(UTC)
    return Workspace(9, "private-9", "Мой архив", False, now, now)


def _labels(keyboard) -> list[str]:
    return [button.text for row in keyboard.inline_keyboard for button in row]


class WorkspaceReferenceDashboardContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_returns_typed_ready_to_render_view(self) -> None:
        characters = (
            WorkspaceReferenceCharacter(3, "Каэль", 2),
            WorkspaceReferenceCharacter(4, "Эрик", 0),
        )
        database = SimpleNamespace()

        with patch(
            "velvet_bot.presentation.telegram.workspace_reference_dashboard."
            "load_workspace_reference_characters",
            new=AsyncMock(return_value=characters),
        ) as loader:
            dashboard = await build_workspace_reference_dashboard(
                database,  # type: ignore[arg-type]
                _workspace(),
            )

        self.assertEqual(2, dashboard.character_count)
        self.assertIn("Референсы · Мой архив", dashboard.text)
        self.assertIn("Персонажей: <b>2</b>", dashboard.text)
        self.assertIn("🧬 Каэль · 2", _labels(dashboard.keyboard))
        self.assertIn("🧬 Эрик · 0", _labels(dashboard.keyboard))
        loader.assert_awaited_once_with(database, workspace_id=9)

    def test_keyboard_keeps_help_and_home_navigation(self) -> None:
        keyboard = build_workspace_reference_dashboard_keyboard(
            workspace_id=9,
            characters=(WorkspaceReferenceCharacter(3, "Каэль", 1),),
        )
        labels = _labels(keyboard)
        buttons = [button for row in keyboard.inline_keyboard for button in row]

        self.assertIn("➕ Как добавить референс", labels)
        self.assertIn("↩️ Моё пространство", labels)
        open_button = next(button for button in buttons if button.text.startswith("🧬"))
        back_button = next(button for button in buttons if button.text == "↩️ Моё пространство")
        action = parse_workspace_reference_callback(open_button.callback_data)
        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual("open", action.action)
        self.assertEqual(9, action.workspace_id)
        self.assertEqual(3, action.character_id)
        self.assertIsNotNone(back_button.callback_data)
        self.assertTrue(back_button.callback_data.startswith("wsp:home:9:"))


class WorkspaceDeletionContractTests(unittest.IsolatedAsyncioTestCase):
    def test_confirmation_keyboard_is_explicit_and_reversible(self) -> None:
        keyboard = build_workspace_delete_keyboard(9)
        labels = _labels(keyboard)
        buttons = [button for row in keyboard.inline_keyboard for button in row]

        self.assertEqual(
            ["🗑 Да, удалить безвозвратно", "↩️ Отмена"],
            labels,
        )
        confirm = next(button for button in buttons if button.text.startswith("🗑"))
        cancel = next(button for button in buttons if button.text == "↩️ Отмена")
        self.assertIsNotNone(confirm.callback_data)
        self.assertTrue(confirm.callback_data.startswith("wsp:deleteconfirm:9:"))
        self.assertIsNotNone(cancel.callback_data)
        self.assertTrue(cancel.callback_data.startswith("wsp:deletecancel:9:"))

    async def test_delete_command_filter_accepts_bot_suffix(self) -> None:
        message = SimpleNamespace(
            text="/workspace_delete@DominusVelvetBot 9",
            caption=None,
        )

        self.assertTrue(await WorkspaceDeleteCommandFilter()(message))


class WorkspaceOwnerBoundaryTests(unittest.TestCase):
    def test_reference_contract_owns_query_and_callback_parser(self) -> None:
        source = (
            PRESENTATION / "workspace_reference_dashboard.py"
        ).read_text(encoding="utf-8")

        self.assertIn("class WorkspaceReferenceAction", source)
        self.assertIn("class WorkspaceReferenceCharacter", source)
        self.assertIn("class WorkspaceReferenceDashboard", source)
        self.assertIn("async def load_workspace_reference_characters", source)
        self.assertIn("def parse_workspace_reference_callback", source)
        self.assertIn('REFERENCE_CALLBACK_PREFIX = "wref"', source)
        self.assertIn("FROM characters AS character", source)
        self.assertNotIn("CallbackData", source)
        self.assertNotIn("workspace_owner_controls", source)

    def test_reference_controller_owns_module_and_open_flows(self) -> None:
        source = (
            PRESENTATION / "workspace_reference_dashboard_controller.py"
        ).read_text(encoding="utf-8")

        self.assertIn("class WorkspaceReferenceActionFilter", source)
        self.assertIn("handle_workspace_reference_entry", source)
        self.assertIn("handle_workspace_reference_action", source)
        self.assertIn("register_workspace_reference_dashboard", source)
        self.assertIn('module_key="references"', source)
        self.assertIn('minimum_role="viewer"', source)
        self.assertNotIn("workspace_owner_controls", source)
        self.assertNotIn("@router.callback_query", source)

    def test_deletion_controller_owns_transaction_and_home_cancel(self) -> None:
        source = (
            PRESENTATION / "workspace_deletion_controller.py"
        ).read_text(encoding="utf-8")

        self.assertIn("class WorkspaceDeleteCommandFilter", source)
        self.assertIn("async def delete_workspace_data", source)
        self.assertIn("FOR UPDATE", source)
        self.assertIn("DELETE FROM workspaces", source)
        self.assertIn("build_workspace_home_presentation", source)
        self.assertIn("register_workspace_deletion", source)
        self.assertNotIn('Command("workspace_delete")', source)
        self.assertNotIn("workspace_owner_controls", source)
        self.assertNotIn("@router.callback_query", source)

    def test_bundle_registers_canonical_flows_before_owner_controls(self) -> None:
        source = (ROUTERS / "archive_and_public.py").read_text(encoding="utf-8")
        owner = source.index("router.include_router(workspace_owner_controls_router)")

        for registration in (
            "register_workspace_reference_dashboard(router)",
            "register_workspace_deletion(router)",
        ):
            self.assertLess(source.index(registration), owner)


if __name__ == "__main__":
    unittest.main()
