from __future__ import annotations

import unittest
from datetime import UTC, datetime

from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import WorkspaceModuleSetting
from velvet_bot.workspace_ui import (
    build_start_keyboard,
    build_workspace_member_home_keyboard,
)


def _workspace() -> Workspace:
    now = datetime.now(UTC)
    return Workspace(
        id=42,
        slug="team-archive",
        name="Командный архив",
        is_system=False,
        created_at=now,
        updated_at=now,
    )


def _module(key: str) -> WorkspaceModuleSetting:
    now = datetime.now(UTC)
    return WorkspaceModuleSetting(
        workspace_id=42,
        module_key=key,  # type: ignore[arg-type]
        is_allowed=True,
        is_enabled=True,
        updated_by_user_id=1,
        created_at=now,
        updated_at=now,
    )


class WorkspaceMemberDashboardTests(unittest.TestCase):
    def test_start_has_a_separate_team_workspace_entry(self) -> None:
        keyboard = build_start_keyboard(
            can_create=False,
            has_workspace=False,
            has_member_workspace=True,
        )
        labels = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertIn("👥 Пространство команды", labels)
        self.assertNotIn("⚙️ Моё пространство", labels)

    def test_viewer_sees_only_existing_viewer_module_routes(self) -> None:
        keyboard = build_workspace_member_home_keyboard(
            _workspace().id,
            role="viewer",
            modules=tuple(_module(key) for key in ("archive", "references", "qwen")),
        )
        labels = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertEqual(["🖼 Архив", "🧬 Референсы", "↩️ Другие пространства", "✖ Закрыть"], labels)

    def test_member_router_rechecks_membership_before_rendering_dashboard(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "velvet_bot/presentation/telegram/routers/workspace_member_home.py"
        ).read_text(encoding="utf-8")

        self.assertIn("set_active_workspace(", source)
        self.assertIn('minimum_role="viewer"', source)
        self.assertIn("list_modules_for_member(", source)
        self.assertNotIn('action="visibility"', source)
        self.assertNotIn('action="modtoggle"', source)


if __name__ == "__main__":
    unittest.main()
