from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from velvet_bot.domains.workspaces.administration import (
    WorkspaceAdminSummary,
    WorkspaceGrantAdminSummary,
)
from velvet_bot.domains.workspaces.product_models import WorkspaceModuleSetting
from velvet_bot.owner_menu import build_owner_main_keyboard
from velvet_bot.presentation.telegram.routers.core_operations_controllers.workspace_admin_ui import (
    build_grant_modules_keyboard,
    build_workspace_modules_keyboard,
    workspace_admin_callback,
)


ROOT = Path(__file__).resolve().parents[1]


def _now() -> datetime:
    return datetime.now(UTC)


class WorkspaceAdminPanelTests(unittest.TestCase):
    def test_owner_menu_opens_admin_panel_instead_of_system_workspace(self) -> None:
        keyboard = build_owner_main_keyboard()
        spaces = next(
            button
            for row in keyboard.inline_keyboard
            for button in row
            if button.text == "🏛 Пространства"
        )
        self.assertIsNotNone(spaces.callback_data)
        self.assertTrue(str(spaces.callback_data).startswith("wad:home:"))
        self.assertNotIn("wsp:home:1", str(spaces.callback_data))

    def test_admin_callbacks_fit_telegram_limit(self) -> None:
        packed = workspace_admin_callback(
            "wmt",
            workspace_id=9_223_372_036_854_775_807,
            module_key="public_archive",
            page=999,
        )
        self.assertLessEqual(len(packed.encode("utf-8")), 64)

    def test_future_grant_and_existing_workspace_have_separate_switches(self) -> None:
        now = _now()
        grant = WorkspaceGrantAdminSummary(
            user_id=8179531132,
            allowed_modules=("characters", "archive"),
            max_workspaces=1,
            is_active=True,
            owned_workspace_count=1,
            granted_at=now,
            updated_at=now,
        )
        workspace = WorkspaceAdminSummary(
            workspace_id=7,
            name="Dominus Velvet",
            slug="user-8179531132-1",
            owner_user_id=8179531132,
            public_archive_enabled=False,
            character_count=2,
            created_at=now,
            updated_at=now,
        )
        modules = (
            WorkspaceModuleSetting(
                workspace_id=7,
                module_key="characters",
                is_allowed=True,
                is_enabled=False,
                updated_by_user_id=7221553045,
                created_at=now,
                updated_at=now,
            ),
            WorkspaceModuleSetting(
                workspace_id=7,
                module_key="qwen",
                is_allowed=False,
                is_enabled=False,
                updated_by_user_id=7221553045,
                created_at=now,
                updated_at=now,
            ),
        )

        grant_keyboard = build_grant_modules_keyboard(grant)
        workspace_keyboard = build_workspace_modules_keyboard(workspace, modules)
        grant_callbacks = {
            button.callback_data
            for row in grant_keyboard.inline_keyboard
            for button in row
            if button.callback_data
        }
        workspace_callbacks = {
            button.callback_data
            for row in workspace_keyboard.inline_keyboard
            for button in row
            if button.callback_data
        }
        self.assertTrue(any(value.startswith("wad:gmt:") for value in grant_callbacks))
        self.assertTrue(any(value.startswith("wad:wmt:") for value in workspace_callbacks))
        self.assertFalse(grant_callbacks & workspace_callbacks)

    def test_telegram_controller_contains_no_sql_or_database_acquire(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
            "workspace_admin_panel.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("database.acquire", source)
        for keyword in ("SELECT ", "INSERT ", "UPDATE ", "DELETE FROM"):
            self.assertNotIn(keyword, source)

    def test_admin_domain_is_global_owner_guarded(self) -> None:
        source = (
            ROOT / "velvet_bot/domains/workspaces/administration.py"
        ).read_text(encoding="utf-8")
        self.assertIn("GLOBAL_WORKSPACE_CREATOR_ID", source)
        self.assertIn("_require_stel", source)


if __name__ == "__main__":
    unittest.main()
