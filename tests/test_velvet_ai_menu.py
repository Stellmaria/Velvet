from __future__ import annotations

import unittest

from velvet_bot.owner_menu import build_owner_main_keyboard
from velvet_bot.velvet_ai_ui import build_velvet_ai_menu


class VelvetAIMenuTests(unittest.TestCase):
    def test_owner_menu_opens_velvet_ai(self) -> None:
        keyboard = build_owner_main_keyboard()
        buttons = [button for row in keyboard.inline_keyboard for button in row]
        velvet = [button for button in buttons if button.text == "🤖 Velvet AI"]

        self.assertEqual(1, len(velvet))
        self.assertIn("ai_menu", velvet[0].callback_data or "")

    def test_ai_menu_contains_all_completed_phases(self) -> None:
        text, keyboard = build_velvet_ai_menu(
            enabled=True,
            provider="ollama",
            model="qwen3-vl:8b",
        )
        labels = {button.text for row in keyboard.inline_keyboard for button in row}

        self.assertIn("Локальный анализ: <b>включён</b>", text)
        self.assertIn("🧠 Проверка качества", labels)
        self.assertIn("🔎 Сравнение с референсом", labels)
        self.assertIn("📝 Промт против результата", labels)
        self.assertIn("🎞 Целостность медиасетов", labels)
        self.assertIn("🎛 Калибровка Qwen", labels)
        self.assertIn("🧬 Архивный аудит", labels)

    def test_callback_data_fit_telegram_limit(self) -> None:
        _, keyboard = build_velvet_ai_menu(
            enabled=False,
            provider="ollama",
            model="qwen3-vl:8b",
        )
        for row in keyboard.inline_keyboard:
            for button in row:
                if button.callback_data:
                    self.assertLessEqual(len(button.callback_data.encode("utf-8")), 64)


if __name__ == "__main__":
    unittest.main()
