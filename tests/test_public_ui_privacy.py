from __future__ import annotations

import unittest

from aiogram.methods import SendMessage

from velvet_bot.app.auf_branding import _brand_telegram_value
from velvet_bot.app.auf_public_text import sanitize_auf_text
from velvet_bot.presentation.telegram.routers.workspace_auf_grs import (
    model_selection_text,
)
from velvet_bot.presentation.telegram.routers.workspace_auf_root import (
    _build_root_keyboard,
)


class AufPublicUiPrivacyTests(unittest.TestCase):
    def test_auf_sanitizer_removes_provider_and_runtime_details(self) -> None:
        text = (
            "<b>Ауф создаёт</b>\n\n"
            "Провайдер: <b>GRS AI</b>\n"
            "Баланс GRS: <b>12000</b> кредитов\n"
            "Ожидаемая стоимость: <b>$0.12 · 10 ₽</b>\n"
            "Попытка: <b>2/50</b>\n"
            "Задача провайдера: <code>grs:secret-task</code>\n"
            "Нужно заполнить GRS_API_KEY и открыть https://grsai.com/private."
        )

        public = sanitize_auf_text(text)

        for private_value in (
            "GRS AI",
            "Kie.ai",
            "GRS_API_KEY",
            "Провайдер:",
            "Баланс GRS",
            "$0.12",
            "2/50",
            "secret-task",
            "grsai.com",
        ):
            self.assertNotIn(private_value, public)

    def test_final_telegram_guard_redacts_stale_ui_copy(self) -> None:
        method = SendMessage(
            chat_id=1,
            text=(
                "Kie.ai выключен на сервере.\n"
                "Провайдер: <b>Kie.ai</b>\n"
                "Задача провайдера: <code>secret-task</code>\n"
                "Ошибка доставки: <code>https://kie.ai/private?api_key=secret</code>\n"
                "Нужно заполнить KIE_API_KEY и model id."
            ),
        )

        public = _brand_telegram_value(method)

        self.assertEqual(1, public.chat_id)
        for private_value in (
            "Kie.ai",
            "KIE_API_KEY",
            "Провайдер:",
            "secret-task",
            "api_key=secret",
            "model id",
        ):
            self.assertNotIn(private_value, public.text)

    def test_root_keyboard_has_no_provider_balance_controls(self) -> None:
        keyboard = _build_root_keyboard(
            workspace_id=1,
            enabled=True,
            grs_enabled=True,
            global_owner=True,
            module_visible=True,
        )
        labels = "\n".join(
            button.text
            for row in keyboard.inline_keyboard
            for button in row
        )

        self.assertNotIn("Kie", labels)
        self.assertNotIn("GRS", labels)
        self.assertNotIn("провайдер", labels.casefold())
        self.assertIn("Ауф · баланс", labels)

    def test_model_selection_copy_does_not_disclose_routing(self) -> None:
        for enabled in (True, False):
            text = model_selection_text(grs_enabled=enabled)
            self.assertNotIn("Kie", text)
            self.assertNotIn("GRS", text)
            self.assertNotIn("API_KEY", text)
            self.assertNotIn("провайдер", text.casefold())


if __name__ == "__main__":
    unittest.main()
