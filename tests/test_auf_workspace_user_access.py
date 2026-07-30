from __future__ import annotations

import unittest
from pathlib import Path

from velvet_bot.core.access import (
    is_workspace_member_callback_data,
    is_workspace_member_command_text,
    is_workspace_member_fsm_state_name,
)
from velvet_bot.presentation.telegram.workspace_command_menu import workspace_commands


ROOT = Path(__file__).resolve().parents[1]


def _command_names(role: str) -> set[str]:
    return {item.command for item in workspace_commands(role)}


class AufWorkspaceUserAccessTests(unittest.TestCase):
    def test_auf_command_passes_personal_workspace_access_gate(self) -> None:
        self.assertTrue(is_workspace_member_command_text("/auf"))
        self.assertTrue(is_workspace_member_command_text("/auf@VelvetBot"))

    def test_current_and_legacy_auf_callbacks_pass_workspace_access_gate(self) -> None:
        callbacks = (
            "auf:create:42::0:0",
            "aufv:model:42:grok:0:0",
            "aufv|model|42|grok|0|0",
            "mrt:cancel_task:42:value",
            "meow:create:42::0:0",
            "meowv:model:42:grok:0:0",
            "meowv|model|42|grok|0|0",
        )
        for callback in callbacks:
            with self.subTest(callback=callback):
                self.assertTrue(is_workspace_member_callback_data(callback))

    def test_current_and_legacy_auf_forms_pass_workspace_access_gate(self) -> None:
        states = (
            "AufForm:waiting_prompt",
            "AufPhotoForm:collecting_input",
            "AufVideoForm:waiting_reference",
            "AufRuntimeForm:waiting_limit",
            "MeowForm:waiting_prompt",
            "MeowPhotoForm:collecting_input",
            "MeowVideoForm:waiting_reference",
            "MeowRuntimeForm:waiting_limit",
        )
        for state in states:
            with self.subTest(state=state):
                self.assertTrue(is_workspace_member_fsm_state_name(state))

    def test_auf_command_is_shown_only_to_workspace_owner(self) -> None:
        self.assertIn("auf", _command_names("owner"))
        for role in ("admin", "editor", "reviewer", "viewer"):
            with self.subTest(role=role):
                self.assertNotIn("auf", _command_names(role))


class AufWorkspaceUserAccessSourceContracts(unittest.TestCase):
    def test_command_is_registered_before_form_handlers(self) -> None:
        source = (
            ROOT / "velvet_bot/app/auf_workspace_ui_install.py"
        ).read_text(encoding="utf-8")
        registration = 'router.message.register(handle_auf_workspace_command, Command("auf"))'
        self.assertIn(registration, source)
        self.assertLess(source.index(registration), source.index("original_register(router)"))
        self.assertIn("build_auf_root_view", source)
        self.assertIn("resolve_active_workspace", source)

    def test_access_contract_is_not_patched_only_at_runtime(self) -> None:
        source = (ROOT / "velvet_bot/core/access/__init__.py").read_text(
            encoding="utf-8"
        )
        installer = (
            ROOT / "velvet_bot/app/auf_workspace_ui_install.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"auf"', source)
        self.assertIn('"auf:"', source)
        self.assertIn('"aufv|"', source)
        self.assertIn('"mrt:"', source)
        self.assertNotIn("policy.WORKSPACE_MEMBER_CALLBACK_PREFIXES", installer)
        self.assertNotIn("policy.WORKSPACE_MEMBER_FSM_STATE_PREFIXES", installer)


if __name__ == "__main__":
    unittest.main()
