from __future__ import annotations

import unittest
from datetime import UTC, datetime

from aiogram.enums import ChatType
from aiogram.types import Chat, Message, User

from velvet_bot.infrastructure.telegram.discussion_events import (
    _coerce_telegram_datetime,
    discussion_event_from_message,
)


class TelegramDiscussionEventTests(unittest.TestCase):
    def test_text_message_becomes_neutral_event(self) -> None:
        message = Message(
            message_id=50,
            date=datetime(2026, 7, 16, tzinfo=UTC),
            chat=Chat(
                id=-1003859952761,
                type=ChatType.SUPERGROUP,
                title="Velvet discussion",
            ),
            from_user=User(
                id=10,
                is_bot=False,
                first_name="Анна",
            ),
            text="Комментарий #Каэль",
        )

        event = discussion_event_from_message(message)

        self.assertEqual(-1003859952761, event.chat_id)
        self.assertEqual("user10", event.sender_id)
        self.assertEqual("Анна", event.sender_name)
        self.assertEqual("text", event.media_type)
        self.assertEqual("Комментарий #Каэль", event.text_content)
        self.assertFalse(event.sender_is_bot)

    def test_raw_unix_timestamp_becomes_utc_datetime(self) -> None:
        timestamp = 1784532152

        value = _coerce_telegram_datetime(timestamp, required=True)

        self.assertEqual(datetime.fromtimestamp(timestamp, tz=UTC), value)
        assert value is not None
        self.assertIs(UTC, value.tzinfo)

    def test_naive_datetime_is_marked_as_utc(self) -> None:
        value = _coerce_telegram_datetime(datetime(2026, 7, 20, 10, 22, 29))

        self.assertEqual(datetime(2026, 7, 20, 10, 22, 29, tzinfo=UTC), value)


if __name__ == "__main__":
    unittest.main()
