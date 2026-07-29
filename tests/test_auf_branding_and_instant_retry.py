from __future__ import annotations

import unittest

from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.app.auf_branding import _brand_auf_text, _brand_telegram_value
from velvet_bot.app.grs_campaign_retry import (
    _retry_delays_for_error,
    _violation_retry_stage,
)
from velvet_bot.domains.media_generation import KieTaskRecord, KieTaskState
from velvet_bot.infrastructure.ai import KieTaskFailed


class AufBrandingTests(unittest.TestCase):
    def test_plain_brand_text_uses_auf_and_dog_icon(self) -> None:
        self.assertEqual("🐕 Ауф", _brand_auf_text("🐈 Мяу"))
        self.assertEqual(
            "<b>Ауф создаёт</b>",
            _brand_auf_text("<b>Мяу создаёт</b>"),
        )

    def test_telegram_method_and_nested_button_are_branded(self) -> None:
        method = SendMessage(
            chat_id=1,
            text="<b>Мяу не смог завершить генерацию</b>",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🐈 Мяу", callback_data="workspace:meow")]
                ]
            ),
        )

        branded = _brand_telegram_value(method)

        self.assertIn("Ауф", branded.text)
        self.assertNotIn("Мяу", branded.text)
        self.assertEqual(
            "🐕 Ауф",
            branded.reply_markup.inline_keyboard[0][0].text,
        )
        self.assertEqual(
            "workspace:meow",
            branded.reply_markup.inline_keyboard[0][0].callback_data,
        )


class InstantGrsViolationRetryTests(unittest.TestCase):
    def test_confirmed_violation_uses_zero_retry_delay(self) -> None:
        error = KieTaskFailed(
            KieTaskRecord(
                task_id="grs:moderated",
                state=KieTaskState.FAIL,
                failure_code="violation",
                failure_message="content policy",
                raw={"status": "violation"},
            )
        )

        self.assertEqual((0, 0), _retry_delays_for_error(error, 5, 30))

    def test_unrelated_errors_keep_existing_backoff(self) -> None:
        self.assertEqual(
            (5, 30),
            _retry_delays_for_error(RuntimeError("network"), 5, 30),
        )

    def test_retry_message_says_restart_is_immediate(self) -> None:
        stage = _violation_retry_stage(
            provider_attempt=3,
            max_attempts=50,
            delay_seconds=30,
            reason_text="GRS AI не передал техническую категорию.",
        )

        self.assertIn("попытку 3/50", stage)
        self.assertIn("запускается сразу", stage)
        self.assertNotIn("через 30 сек", stage)


if __name__ == "__main__":
    unittest.main()
