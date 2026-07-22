from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from velvet_bot.access import (
    is_public_callback_data,
    is_workspace_member_command_text,
    is_workspace_member_callback_data,
    is_workspace_member_fsm_state_name,
)
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import WorkspaceModuleSetting
from velvet_bot.presentation.telegram.routers.workspace_guided_ui import (
    guided_workspace_callback,
)
from velvet_bot.presentation.telegram.routers.workspace_onboarding import (
    WorkspaceOnboardingCallback,
)
from velvet_bot.presentation.telegram.routers.workspace_owner_controls import (
    WorkspacePersonalArchiveCallback,
    WorkspaceReferenceEntryCallback,
)
from velvet_bot.workspace_ui import (
    WorkspaceCallback,
    build_start_keyboard,
    build_workspace_home_keyboard,
    build_workspace_member_home_keyboard,
    build_workspace_selector_keyboard,
    workspace_callback,
)


ROOT = Path(__file__).resolve().parents[1]


def _workspace(workspace_id: int, name: str) -> Workspace:
    now = datetime.now(UTC)
    return Workspace(workspace_id, f"space-{workspace_id}", name, False, now, now)


def _modules(*keys: str) -> tuple[WorkspaceModuleSetting, ...]:
    now = datetime.now(UTC)
    return tuple(
        WorkspaceModuleSetting(
            workspace_id=7,
            module_key=key,  # type: ignore[arg-type]
            is_allowed=True,
            is_enabled=True,
            updated_by_user_id=1,
            created_at=now,
            updated_at=now,
        )
        for key in keys
    )


def _callbacks(markup) -> set[str]:
    return {
        str(button.callback_data)
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


class WorkspaceCallbackRecoveryTests(unittest.TestCase):
    def test_every_personal_callback_prefix_passes_member_route_classification(self) -> None:
        callbacks = (
            WorkspaceCallback(action="quick", workspace_id=7).pack(),
            guided_workspace_callback("cnew", workspace_id=7),
            WorkspaceOnboardingCallback(action="intro", workspace_id=7).pack(),
            WorkspacePersonalArchiveCallback(action="open", workspace_id=7).pack(),
            WorkspaceReferenceEntryCallback(action="open", workspace_id=7).pack(),
            "ref:open:7",
            "pubq:menu:0:0",
            "dash:menu:0",
            "wteam:list:7:0",
            "wlogo:show:7",
            "wm:show:7",
        )
        for callback in callbacks:
            with self.subTest(callback=callback):
                self.assertTrue(is_workspace_member_callback_data(callback))

    def test_quick_and_workspace_selector_are_reachable_without_an_active_archive(self) -> None:
        self.assertTrue(is_public_callback_data(workspace_callback("quick", workspace_id=7)))
        self.assertTrue(is_public_callback_data(workspace_callback("spaces")))

    def test_cancel_is_a_workspace_recovery_command_not_an_anonymous_public_command(self) -> None:
        self.assertTrue(is_workspace_member_command_text("/cancel"))

    def test_only_known_personal_workspace_forms_bypass_global_message_gate(self) -> None:
        for value in (
            "WorkspaceForm:waiting_workspace_name",
            "GuidedWorkspaceForm:character_name",
            "WorkspaceTeamForm:waiting_member_id",
            "WorkspaceWatermarkForm:waiting_asset",
        ):
            with self.subTest(value=value):
                self.assertTrue(is_workspace_member_fsm_state_name(value))
        self.assertFalse(is_workspace_member_fsm_state_name("OtherForm:waiting"))
        self.assertFalse(is_workspace_member_fsm_state_name(None))

    def test_quick_save_is_hidden_until_both_character_and_archive_modules_are_enabled(self) -> None:
        workspace = _workspace(7, "Personal")
        only_characters = build_workspace_home_keyboard(
            workspace,
            public_enabled=False,
            modules=_modules("characters"),
        )
        both_enabled = build_workspace_home_keyboard(
            workspace,
            public_enabled=False,
            modules=_modules("characters", "archive"),
        )
        self.assertTrue(any(value.startswith("wsp:quick:") for value in _callbacks(only_characters)))
        self.assertNotIn("💾 Сохранить", {button.text for row in only_characters.inline_keyboard for button in row})
        self.assertIn("🖼 Архив", {button.text for row in both_enabled.inline_keyboard for button in row})

    def test_public_visibility_button_is_not_offered_when_its_module_is_disabled(self) -> None:
        keyboard = build_workspace_home_keyboard(
            _workspace(7, "Personal"),
            public_enabled=False,
            modules=_modules("characters", "archive"),
        )
        labels = {button.text for row in keyboard.inline_keyboard for button in row}
        self.assertNotIn("🌐 Сделать публичным", labels)

    def test_multiple_owned_or_team_spaces_open_a_selector(self) -> None:
        start = build_start_keyboard(
            can_create=False,
            has_workspace=True,
            workspace_count=2,
            has_owned_workspace=True,
        )
        self.assertIn("wsp:spaces:0:", _callbacks(start))
        selector = build_workspace_selector_keyboard(
            owned_workspaces=(_workspace(7, "Первый"),),
            member_workspaces=(_workspace(8, "Команда"),),
        )
        labels = {button.text for row in selector.inline_keyboard for button in row}
        self.assertIn("⚙️ Первый", labels)
        self.assertIn("🤝 Команда", labels)
        self.assertIn("wsp:home:7:", _callbacks(selector))
        self.assertIn("wsp:home:8:", _callbacks(selector))

    def test_member_menu_only_exposes_entries_accepted_by_the_role(self) -> None:
        keyboard = build_workspace_member_home_keyboard(
            _workspace(7, "Команда"),
            role="reviewer",
            modules=_modules(
                "characters",
                "archive",
                "references",
                "qwen",
                "publications",
                "analytics",
                "watermark",
                "team",
            ),
        )
        callbacks = _callbacks(keyboard)
        self.assertIn("wsp:module:7:archive", callbacks)
        self.assertIn("wsp:module:7:references", callbacks)
        self.assertIn("wsp:module:7:qwen", callbacks)
        self.assertIn("wsp:module:7:analytics", callbacks)
        self.assertNotIn("wsp:module:7:characters", callbacks)
        self.assertNotIn("wsp:module:7:publications", callbacks)
        self.assertNotIn("wsp:module:7:watermark", callbacks)
        self.assertNotIn("wsp:module:7:team", callbacks)


class WorkspaceRecoverySourceContractsTests(unittest.TestCase):
    def test_start_and_cancel_are_state_recovery_routes_before_workspace_forms(self) -> None:
        bundle = (
            ROOT / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        self.assertLess(
            bundle.index("router.include_router(start_router)"),
            bundle.index("router.include_router(workspace_guided_actions_router)"),
        )
        start = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/archive_and_public_controllers/start.py"
        ).read_text(encoding="utf-8")
        guided = (
            ROOT / "velvet_bot/presentation/telegram/routers/workspace_guided_actions.py"
        ).read_text(encoding="utf-8")
        self.assertIn("await state.clear()", start)
        self.assertIn('Command("cancel")', guided)
        self.assertIn("save_upload_sessions.stop", guided)

    def test_picker_and_guided_creation_use_the_button_first_auto_topic_flow(self) -> None:
        picker = (
            ROOT / "velvet_bot/presentation/telegram/routers/workspace_character_pickers.py"
        ).read_text(encoding="utf-8")
        guided = (
            ROOT / "velvet_bot/presentation/telegram/routers/workspace_guided_actions.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Opening the picker now also recovers", picker)
        self.assertIn("await state.clear()", picker)
        self.assertIn("ensure_character_archive_topic", guided)
        self.assertIn("topic_value=None", guided)

    def test_visible_module_entries_have_real_scoped_handlers_and_stale_target_guards(self) -> None:
        checks = {
            "workspace_reference_library.py": "handle_workspace_qwen_entry",
            "workspace_publications.py": "handle_workspace_publication_entry",
            "workspace_analytics.py": "handle_workspace_analytics_entry",
        }
        for filename, handler in checks.items():
            source = (
                ROOT / "velvet_bot/presentation/telegram/routers" / filename
            ).read_text(encoding="utf-8")
            with self.subTest(filename=filename):
                self.assertIn(handler, source)
                self.assertIn("callback_data.workspace_id !=", source)

    def test_unbind_removes_wizard_metadata_and_runtime_channel_in_one_transaction(self) -> None:
        source = (
            ROOT / "velvet_bot/domains/workspaces/onboarding.py"
        ).read_text(encoding="utf-8")
        self.assertIn("async def configure_destination", source)
        self.assertIn("INSERT INTO workspace_channels", source)
        self.assertIn("async def unbind_destination", source)
        self.assertIn("async with connection.transaction()", source)
        self.assertIn("DELETE FROM workspace_channels", source)


if __name__ == "__main__":
    unittest.main()
