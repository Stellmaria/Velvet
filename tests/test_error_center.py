import asyncio
import logging
import unittest
import xml.etree.ElementTree as ElementTree
from datetime import UTC, datetime
from types import SimpleNamespace

from velvet_bot.error_center import (
    ErrorIncident,
    ErrorIncidentCenter,
    capture_log_record,
)


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(message_id=1)


class FakeRepository:
    def __init__(self, incidents: tuple[ErrorIncident, ...]) -> None:
        self.incidents = incidents
        self.marked = False

    async def unacknowledged_counts(self) -> dict[str, int]:
        return {
            "total": len(self.incidents),
            "warnings": 0,
            "errors": len(self.incidents),
            "critical": 0,
        }

    async def digest_due(self, *, cooldown_seconds: int) -> bool:
        return True

    async def unacknowledged(self, *, limit: int = 5) -> tuple[ErrorIncident, ...]:
        return self.incidents[:limit]

    async def mark_digest_sent(self) -> None:
        self.marked = True


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

    @staticmethod
    def _center() -> ErrorIncidentCenter:
        return ErrorIncidentCenter(
            bot=None,  # type: ignore[arg-type]
            repository=None,  # type: ignore[arg-type]
            log_chat_id=None,
            owner_user_ids=frozenset(),
        )

    @staticmethod
    def _incident(
        *,
        incident_id: int = 12,
        severity: str = "ERROR",
        logger_name: str = "velvet_bot.test",
        summary: str = "Something failed",
        details: str | None = "Traceback line",
        acknowledged: bool = False,
    ) -> ErrorIncident:
        now = datetime.now(UTC)
        return ErrorIncident(
            id=incident_id,
            fingerprint="f" * 64,
            severity=severity,
            logger_name=logger_name,
            summary=summary,
            details=details,
            occurrence_count=3,
            first_seen_at=now,
            last_seen_at=now,
            acknowledged_at=now if acknowledged else None,
            acknowledged_by=7221553045 if acknowledged else None,
            log_chat_message_id=10,
        )

    def _assert_valid_telegram_html(self, text: str) -> None:
        root = ElementTree.fromstring(f"<root>{text}</root>")
        parsed_text = "".join(root.itertext())
        self.assertLessEqual(len(parsed_text), 4096)

    def test_dynamic_ids_are_grouped_into_one_incident(self) -> None:
        first = capture_log_record(
            self._record("AI semantic analysis failed media_id=%s", 56)
        )
        second = capture_log_record(
            self._record("AI semantic analysis failed media_id=%s", 83)
        )

        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertNotEqual(first.summary, second.summary)

    def test_explicit_media_keys_keep_different_files_separate(self) -> None:
        first = capture_log_record(
            self._record(
                "AI semantic analysis failed media_id=%s: media_key=m56 unavailable",
                56,
            )
        )
        second = capture_log_record(
            self._record(
                "AI semantic analysis failed media_id=%s: media_key=m83 unavailable",
                83,
            )
        )

        self.assertNotEqual(first.fingerprint, second.fingerprint)

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
        rendered = self._center()._render_incident(
            self._incident(acknowledged=True)
        )

        self.assertIn("Ошибка #12", rendered)
        self.assertIn("Повторов:</b> <code>3", rendered)
        self.assertIn("Отмечено просмотренным", rendered)
        self._assert_valid_telegram_html(rendered)

    def test_long_incident_does_not_cut_html_entity_or_tag(self) -> None:
        summary = ("Сообщение <tag> & кавычки \" ' Юникод " * 100)[:1200]
        details = (
            "TRACE START\n"
            + ("<&> traceback line\n" * 500)
            + "TAIL<&>"
        )[-6000:]
        rendered = self._center()._render_incident(
            self._incident(
                logger_name=("velvet_bot.<danger>&" * 40)[:500],
                summary=summary,
                details=details,
                acknowledged=True,
            )
        )

        self._assert_valid_telegram_html(rendered)
        self.assertIn("TAIL&lt;&amp;&gt;", rendered)
        self.assertEqual(rendered.count("<code>"), rendered.count("</code>"))
        self.assertEqual(rendered.count("<pre>"), rendered.count("</pre>"))
        self.assertTrue(rendered.endswith("</code>"))

    def test_long_incident_without_traceback_keeps_summary_valid(self) -> None:
        rendered = self._center()._render_incident(
            self._incident(
                summary=("<&>" * 400)[:1200],
                details=None,
            )
        )

        self._assert_valid_telegram_html(rendered)
        self.assertIn("<b>Сообщение:</b>", rendered)
        self.assertNotIn("<b>Traceback:</b>", rendered)

    def test_owner_digest_does_not_cut_escaped_summaries(self) -> None:
        incidents = tuple(
            self._incident(
                incident_id=index,
                summary=("summary <&> with unicode Ю " * 60)[:1200],
                details=None,
            )
            for index in range(1, 6)
        )
        bot = FakeBot()
        repository = FakeRepository(incidents)
        center = ErrorIncidentCenter(
            bot=bot,  # type: ignore[arg-type]
            repository=repository,  # type: ignore[arg-type]
            log_chat_id=None,
            owner_user_ids=frozenset({17}),
        )

        sent = asyncio.run(center._send_owner_digest(cooldown_seconds=120))

        self.assertEqual(sent, 1)
        self.assertTrue(repository.marked)
        text = str(bot.sent[0]["text"])
        self._assert_valid_telegram_html(text)
        for index in range(1, 6):
            self.assertIn(f"• #{index}", text)
        self.assertIn("Прочитано / беру в работу", text)


if __name__ == "__main__":
    unittest.main()
