from __future__ import annotations

import unittest

from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.app.auf_branding import _brand_auf_text, _brand_telegram_value
from velvet_bot.app.grs_campaign_retry import (
    _retry_delays_for_error,
    _violation_retry_stage,
)
from velvet_bot.app.telegram_progress_resilience import (
    _log_transient_progress_failure,
    _provider_reason_without_unsafe_chatter,
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

    def test_all_brand_spellings_are_replaced(self) -> None:
        branded = _brand_auf_text("МЯУ Мяу мяу MEOW Meow meow")

        self.assertEqual("АУФ Ауф ауф AUF Auf auf", branded)

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

    def test_identifier_fields_are_never_rebranded(self) -> None:
        payload = {
            "text": "Meow и мяу",
            "callback_data": "meow:runtime:Мяу",
            "url": "https://example.test/meow/Мяу",
            "file_id": "meow-Мяу-file",
        }

        branded = _brand_telegram_value(payload)

        self.assertEqual("Auf и ауф", branded["text"])
        self.assertEqual(payload["callback_data"], branded["callback_data"])
        self.assertEqual(payload["url"], branded["url"])
        self.assertEqual(payload["file_id"], branded["file_id"])


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

    def test_unsafe_image_chatter_is_not_a_provider_diagnostic(self) -> None:
        self.assertIsNone(
            _provider_reason_without_unsafe_chatter(
                "Извините, но я не могу создавать небезопасные изображения."
            )
        )
        self.assertEqual(
            "IMAGE_SAFETY",
            _provider_reason_without_unsafe_chatter("IMAGE_SAFETY"),
        )

    def test_transient_progress_disconnect_is_only_a_warning(self) -> None:
        error = TelegramNetworkError(
            method=SendMessage(chat_id=1, text="progress"),
            message="ServerDisconnectedError: Server disconnected",
        )

        with self.assertLogs(
            "velvet_bot.app.telegram_progress_resilience",
            level="WARNING",
        ) as captured:
            _log_transient_progress_failure("task-1", error)

        output = "\n".join(captured.output)
        self.assertIn("generation continues", output)
        self.assertNotIn("Traceback", output)


if __name__ == "__main__":
    unittest.main()
