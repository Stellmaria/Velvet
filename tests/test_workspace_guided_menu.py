from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.onboarding import required_destination_keys
from velvet_bot.domains.workspaces.product_models import WorkspaceModuleSetting
from velvet_bot.presentation.telegram.routers.workspace_guided_ui import (
    guided_workspace_callback,
)
from velvet_bot.workspace_ui import (
    build_modules_keyboard,
    build_workspace_home_keyboard,
)


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceGuidedMenuTests(unittest.TestCase):
    def test_first_run_requires_only_main_archive_chat(self) -> None:
        self.assertEqual(
            ("characters",),
            required_destination_keys(
                {"characters", "archive", "references", "publications", "analytics"}
            ),
        )
        self.assertEqual((), required_destination_keys({"taxonomy", "team"}))

    def test_guided_callbacks_fit_telegram_limit(self) -> None:
        packed = guided_workspace_callback(
            "deleteconfirm",
            workspace_id=9_223_372_036_854_775_807,
            character_id=9_223_372_036_854_775_807,
            item_id=9_223_372_036_854_775_807,
            page=999,
        )
        self.assertLessEqual(len(packed.encode("utf-8")), 64)

    def test_workspace_home_has_quick_actions(self) -> None:
        now = datetime.now(UTC)
        workspace = Workspace(7, "personal", "Personal", False, now, now)
        modules = (
            WorkspaceModuleSetting(
                workspace_id=7,
                module_key="characters",
                is_allowed=True,
                is_enabled=True,
                updated_by_user_id=1,
                created_at=now,
                updated_at=now,
            ),
        )
        keyboard = build_workspace_home_keyboard(
            workspace,
            public_enabled=False,
            modules=modules,
        )
        callbacks = {
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        }
        self.assertTrue(any(value.startswith("wsp:quick:") for value in callbacks))

    def test_module_help_from_modules_returns_to_modules(self) -> None:
        now = datetime.now(UTC)
        modules = (
            WorkspaceModuleSetting(
                workspace_id=7,
                module_key="characters",
                is_allowed=True,
                is_enabled=True,
                updated_by_user_id=1,
                created_at=now,
                updated_at=now,
            ),
        )
        keyboard = build_modules_keyboard(7, modules)
        info = next(
            button
            for row in keyboard.inline_keyboard
            for button in row
            if button.text == "ℹ️"
        )
        self.assertIn("modulehelpmodules", str(info.callback_data))

    def test_character_and_taxonomy_back_buttons_use_real_parents(self) -> None:
        picker = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_character_pickers.py"
        ).read_text(encoding="utf-8")
        ui = (ROOT / "velvet_bot/workspace_ui.py").read_text(encoding="utf-8")
        self.assertIn('workspace_callback("home", workspace_id=workspace_id)', picker)
        self.assertIn('workspace_callback("taxonomy", workspace_id=workspace_id)', ui)
        self.assertNotIn("➕ Как создать персонажа", picker)

    def test_onboarding_no_longer_demands_every_destination(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/routers/workspace_onboarding.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Для каждой функции откройте нужный чат", source)
        self.assertIn("Основной архивный чат", source)


if __name__ == "__main__":
    unittest.main()
