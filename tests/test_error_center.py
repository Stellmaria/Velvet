import logging
import unittest
from datetime import UTC, datetime

from velvet_bot.error_center import (
    ErrorIncident,
    ErrorIncidentCenter,
    capture_log_record,
)


class ErrorCenterTests(unittest.TestCase):
    @staticmethod
    def _record(message: str, *args) -> logging.LogRecord:
        return logging.LogRecord(
            name="velvet_bot.ai_vision",
            level=logging.WARNING,
            pathname="velvet_bot/ai_vision.py",
            lineno=123,
            msg=message,
            args=args,
            exc_info=None,
        )

    def test_dynamic_ids_are_grouped_into_one_incident(self) -> None:
        first = capture_log_record(
            self._record("AI semantic analysis failed media_id=%s", 56)
        )
        second = capture_log_record(
            self._record("AI semantic analysis failed media_id=%s", 83)
        )

        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertNotEqual(first.summary, second.summary)

    def test_secrets_are_redacted_before_telegram(self) -> None:
        captured = capture_log_record(
            self._record(
                "Failed BOT_TOKEN=%s DATABASE_URL=%s",
                "123456789:abcdefghijklmnopqrstuvwxyzABCDE",
                "postgresql://velvet:secret@localhost:5432/velvet",
            )
        )

        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", captured.summary)
        self.assertNotIn("secret@localhost", captured.summary)
        self.assertIn("redacted", captured.summary)

    def test_ack_callback_fits_telegram_limit(self) -> None:
        markup = ErrorIncidentCenter._incident_markup(9223372036854775807)
        callback_data = markup.inline_keyboard[0][0].callback_data
        self.assertIsNotNone(callback_data)
        self.assertLessEqual(len(callback_data.encode("utf-8")), 64)

    def test_rendered_incident_contains_acknowledgement(self) -> None:
        center = ErrorIncidentCenter(
            bot=None,  # type: ignore[arg-type]
            repository=None,  # type: ignore[arg-type]
            log_chat_id=None,
            owner_user_ids=frozenset(),
        )
        now = datetime.now(UTC)
        incident = ErrorIncident(
            id=12,
            fingerprint="f" * 64,
            severity="ERROR",
            logger_name="velvet_bot.test",
            summary="Something failed",
            details="Traceback line",
            occurrence_count=3,
            first_seen_at=now,
            last_seen_at=now,
            acknowledged_at=now,
            acknowledged_by=7221553045,
            log_chat_message_id=10,
        )

        rendered = center._render_incident(incident)

        self.assertIn("Ошибка #12", rendered)
        self.assertIn("Повторов:</b> <code>3", rendered)
        self.assertIn("Отмечено просмотренным", rendered)


if __name__ == "__main__":
    unittest.main()
