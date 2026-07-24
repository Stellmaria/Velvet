from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import WorkspaceModuleSetting
from velvet_bot.presentation.telegram.routers.workspace_owner_controls import (
    _workspace_home_keyboard,
)
from velvet_bot.presentation.telegram.workspace_command_menu import (
    install_workspace_scoped_commands,
    workspace_commands,
)

ROOT = Path(__file__).resolve().parents[1]


def _workspace(*, system: bool = False) -> Workspace:
    now = datetime.now(UTC)
    return Workspace(9, "private-9", "Мой архив", system, now, now)


def _modules() -> tuple[WorkspaceModuleSetting, ...]:
    now = datetime.now(UTC)
    return tuple(
        WorkspaceModuleSetting(
            workspace_id=9,
            module_key=key,  # type: ignore[arg-type]
            is_allowed=True,
            is_enabled=True,
            updated_by_user_id=1,
            created_at=now,
            updated_at=now,
        )
        for key in ("characters", "archive", "references", "watermark")
    )


def _labels(*, show_button_hints: bool) -> list[str]:
    keyboard = _workspace_home_keyboard(
        _workspace(),
        public_enabled=False,
        modules=_modules(),
        show_button_hints=show_button_hints,
    )
    return [button.text for row in keyboard.inline_keyboard for button in row]


class WorkspaceHomeKeyboardContractTests(unittest.TestCase):
    def test_hidden_hints_use_explicit_keyboard_parameter(self) -> None:
        labels = _labels(show_button_hints=False)

        self.assertNotIn("ℹ️", labels)
        self.assertIn("ℹ️ Показать подсказки", labels)
        self.assertNotIn("🙈 Скрыть все подсказки", labels)

    def test_visible_hints_keep_help_buttons_and_toggle(self) -> None:
        labels = _labels(show_button_hints=True)

        self.assertIn("ℹ️", labels)
        self.assertIn("🙈 Скрыть все подсказки", labels)
        self.assertNotIn("ℹ️ Показать подсказки", labels)

    def test_editor_command_contract_contains_mutating_actions(self) -> None:
        commands = {item.command for item in workspace_commands("editor")}

        self.assertTrue(
            {"archive", "save", "refs", "refadd", "refdel", "watermark"}
            .issubset(commands)
        )

    def test_viewer_command_contract_is_read_only(self) -> None:
        commands = {item.command for item in workspace_commands("viewer")}

        self.assertIn("archive", commands)
        self.assertIn("refs", commands)
        self.assertNotIn("save", commands)
        self.assertNotIn("watermark", commands)


class WorkspaceCommandMenuTests(unittest.IsolatedAsyncioTestCase):
    async def test_scoped_commands_use_callback_user_when_message_is_missing(self) -> None:
        bot = SimpleNamespace(set_my_commands=AsyncMock())
        callback = SimpleNamespace(
            message=None,
            from_user=SimpleNamespace(id=77),
            bot=bot,
        )

        await install_workspace_scoped_commands(callback, role="viewer")

        bot.set_my_commands.assert_awaited_once()
        commands, = bot.set_my_commands.await_args.args
        self.assertIn("archive", {item.command for item in commands})
        self.assertEqual(77, bot.set_my_commands.await_args.kwargs["scope"].chat_id)


class WorkspaceHomeArchitectureTests(unittest.TestCase):
    def test_product_controller_has_no_home_runtime_installer(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
            "workspace_product_experience.py"
        ).read_text(encoding="utf-8")

        for forbidden in (
            "ContextVar",
            "_SHOW_BUTTON_HINTS",
            "_ORIGINAL_HOME_KEYBOARD",
            "_ORIGINAL_RENDER_HOME",
            "_ORIGINAL_RENDER_MEMBER_HOME",
            "def _home_keyboard_with_hint_toggle",
            "def _render_home_with_preferences",
            "def _render_member_home_with_commands",
            "def install_workspace_product_experience",
            "workspace_owner_controls._workspace_home_keyboard =",
            "workspace_owner_controls._render_home =",
            "workspace_owner_controls._render_member_home =",
        ):
            self.assertNotIn(forbidden, source)

    def test_owner_menu_does_not_call_runtime_installer(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
            "owner_menu.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("install_workspace_product_experience", source)
        self.assertIn("workspace_product_experience_router", source)

    def test_canonical_render_uses_public_preferences_and_command_contract(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/"
            "workspace_owner_controls.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn(
            "workspace_product_service._workspaces.get_settings",
            source,
        )
        self.assertIn("workspace_product_service.get_button_hints", source)
        self.assertIn("show_button_hints=show_button_hints", source)
        self.assertIn("install_workspace_scoped_commands", source)


if __name__ == "__main__":
    unittest.main()
