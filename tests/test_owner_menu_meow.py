from __future__ import annotations

import unittest

from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.owner_menu import build_owner_main_keyboard
from velvet_bot.workspace_ui import workspace_callback


class OwnerMenuMeowTests(unittest.TestCase):
    def test_owner_menu_opens_meow_for_system_workspace(self) -> None:
        keyboard = build_owner_main_keyboard()
        buttons = [
            button
            for row in keyboard.inline_keyboard
            for button in row
        ]
        meow = next(button for button in buttons if button.text == "🐈 Мяу")

        self.assertEqual(
            meow.callback_data,
            workspace_callback(
                "meow",
                workspace_id=DEFAULT_WORKSPACE_ID,
            ),
        )


if __name__ == "__main__":
    unittest.main()
