from __future__ import annotations

import unittest
from pathlib import Path

from velvet_bot.presentation.telegram.routers.workspace_guided_actions import (
    _quick_keyboard,
)

ROOT = Path(__file__).resolve().parents[1]


def _labels(enabled: frozenset[str]) -> list[str]:
    keyboard = _quick_keyboard(9, enabled)
    return [button.text for row in keyboard.inline_keyboard for button in row]


class WorkspaceQuickReferencesContractTests(unittest.TestCase):
    def test_references_button_is_part_of_canonical_quick_keyboard(self) -> None:
        labels = _labels(frozenset({"characters", "archive", "references"}))

        self.assertEqual(1, labels.count("🧬 Референсы"))
        self.assertLess(
            labels.index("🧬 Референсы"),
            labels.index("🧭 Настройка архива"),
        )

    def test_references_button_is_hidden_when_module_is_disabled(self) -> None:
        labels = _labels(frozenset({"characters", "archive"}))

        self.assertNotIn("🧬 Референсы", labels)

    def test_references_callback_targets_workspace_module(self) -> None:
        keyboard = _quick_keyboard(9, frozenset({"references"}))
        button = next(
            button
            for row in keyboard.inline_keyboard
            for button in row
            if button.text == "🧬 Референсы"
        )

        self.assertIsNotNone(button.callback_data)
        self.assertTrue(button.callback_data.startswith("wsp:module:"))
        self.assertIn(":9:", button.callback_data)
        self.assertTrue(button.callback_data.endswith(":references"))


class WorkspaceQuickReferencesArchitectureTests(unittest.TestCase):
    def test_workspace_installer_does_not_patch_quick_keyboard(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
            "workspace_product_experience.py"
        ).read_text(encoding="utf-8")

        for forbidden in (
            "_ORIGINAL_QUICK_KEYBOARD",
            "def _quick_keyboard_with_references",
            "workspace_guided_actions._quick_keyboard =",
            "from velvet_bot.presentation.telegram.routers import workspace_guided_actions",
        ):
            self.assertNotIn(forbidden, source)

    def test_canonical_keyboard_contains_reference_contract(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_guided_actions.py"
        ).read_text(encoding="utf-8")

        self.assertIn('if "references" in enabled:', source)
        self.assertIn('text="🧬 Референсы"', source)
        self.assertIn('module_key="references"', source)


if __name__ == "__main__":
    unittest.main()
