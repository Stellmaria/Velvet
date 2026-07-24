from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import WorkspaceModuleSetting
from velvet_bot.presentation.telegram.workspace_command_menu import (
    install_workspace_scoped_commands,
    workspace_commands,
)
from velvet_bot.presentation.telegram.workspace_home_presentation import (
    build_workspace_home_presentation,
    build_workspace_owner_home_keyboard,
)

ROOT = Path(__file__).resolve().parents[1]
PRESENTATION = ROOT / "velvet_bot/presentation/telegram"
ROUTERS = PRESENTATION / "routers"


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
    keyboard = build_workspace_owner_home_keyboard(
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


class WorkspaceHomePresentationTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_presentation_loads_public_service_contracts(self) -> None:
        workspace = _workspace()
        membership = SimpleNamespace(role="owner")
        settings = SimpleNamespace(public_archive_enabled=False)
        workspace_service = SimpleNamespace(
            require_role=AsyncMock(return_value=membership),
        )
        product_service = SimpleNamespace(
            get_settings=AsyncMock(return_value=settings),
            list_modules=AsyncMock(return_value=_modules()),
            list_modules_for_member=AsyncMock(),
            get_button_hints=AsyncMock(return_value=False),
        )

        presentation = await build_workspace_home_presentation(
            workspace=workspace,
            user_id=77,
            workspace_service=workspace_service,
            workspace_product_service=product_service,
            global_owner=False,
        )

        self.assertEqual("owner", presentation.role)
        self.assertIn("Роль: <b>владелец</b>", presentation.text)
        labels = [
            button.text
            for row in presentation.keyboard.inline_keyboard
            for button in row
        ]
        self.assertIn("ℹ️ Показать подсказки", labels)
        product_service.list_modules.assert_awaited_once()
        product_service.list_modules_for_member.assert_not_awaited()
        product_service.get_button_hints.assert_awaited_once_with(9)

    async def test_member_presentation_uses_role_filtered_modules(self) -> None:
        workspace = _workspace()
        membership = SimpleNamespace(role="viewer")
        settings = SimpleNamespace(public_archive_enabled=False)
        workspace_service = SimpleNamespace(
            require_role=AsyncMock(return_value=membership),
        )
        product_service = SimpleNamespace(
            get_settings=AsyncMock(return_value=settings),
            list_modules=AsyncMock(),
            list_modules_for_member=AsyncMock(return_value=_modules()),
            get_button_hints=AsyncMock(),
        )

        presentation = await build_workspace_home_presentation(
            workspace=workspace,
            user_id=77,
            workspace_service=workspace_service,
            workspace_product_service=product_service,
            global_owner=False,
        )

        self.assertEqual("viewer", presentation.role)
        self.assertIn("Роль: <b>наблюдатель</b>", presentation.text)
        self.assertIn("Показаны только разделы", presentation.text)
        product_service.list_modules.assert_not_awaited()
        product_service.list_modules_for_member.assert_awaited_once()
        product_service.get_button_hints.assert_not_awaited()


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
    def test_home_hint_controller_uses_public_presentation(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
            "workspace_home_hint_controller.py"
        ).read_text(encoding="utf-8")

        self.assertIn("build_workspace_home_presentation", source)
        self.assertNotIn("workspace_owner_controls", source)
        self.assertNotIn("_workspace_home_keyboard", source)
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
        self.assertIn("workspace_home_hint_router", source)
        self.assertNotIn("workspace_product_experience_router", source)

    def test_home_contract_has_no_owner_controls_dependency(self) -> None:
        source = (PRESENTATION / "workspace_home_presentation.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("class WorkspaceHomePresentation", source)
        self.assertIn("def build_workspace_owner_home_keyboard", source)
        self.assertIn("async def build_workspace_home_presentation", source)
        self.assertIn("workspace_product_service.get_button_hints", source)
        self.assertIn("install_workspace_scoped_commands", (
            PRESENTATION / "workspace_home_controller.py"
        ).read_text(encoding="utf-8"))
        self.assertNotIn("workspace_owner_controls", source)
        self.assertNotIn("._workspaces", source)

    def test_canonical_home_is_registered_before_owner_controls(self) -> None:
        source = (ROUTERS / "archive_and_public.py").read_text(encoding="utf-8")

        registration = source.index("register_workspace_home(router)")
        owner_controls = source.index(
            "router.include_router(workspace_owner_controls_router)"
        )
        self.assertLess(registration, owner_controls)

    def test_legacy_owner_home_is_no_longer_the_runtime_entry(self) -> None:
        controller_source = (PRESENTATION / "workspace_home_controller.py").read_text(
            encoding="utf-8"
        )
        legacy_source = (
            ROUTERS / "workspace_owner_controls.py"
        ).read_text(encoding="utf-8")

        self.assertIn("register_workspace_home", controller_source)
        self.assertIn("handle_workspace_owner_home", legacy_source)
        self.assertNotIn("workspace_owner_controls", controller_source)


if __name__ == "__main__":
    unittest.main()
