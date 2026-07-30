from __future__ import annotations

import unittest

from velvet_bot.presentation.telegram.routers.workspace_auf_grs import (
    build_model_keyboard,
    model_selection_text,
)


def _labels(keyboard) -> list[str]:
    return [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]


class GrsMeowAvailabilityTests(unittest.TestCase):
    def test_banana_models_are_hidden_until_grs_key_is_configured(self) -> None:
        labels = _labels(
            build_model_keyboard(
                workspace_id=9,
                grs_enabled=False,
            )
        )
        self.assertEqual(
            ["Seedream 5 Pro", "↩️ К проверке", "Отмена"],
            labels,
        )
        text = model_selection_text(grs_enabled=False)
        self.assertIn("GRS_API_KEY", text)
        self.assertNotIn("отправляются через GRS AI", text)


if __name__ == "__main__":
    unittest.main()
