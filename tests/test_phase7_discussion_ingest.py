from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.enums import ChatType
from aiogram.types import Chat, Message, User

from velvet_bot.domains.discussions import (
    DiscussionIngestService,
    DiscussionMessageEvent,
)
from velvet_bot.infrastructure.telegram.discussion_events import (
    discussion_event_from_message,
)


def make_event(**changes) -> DiscussionMessageEvent:
    values = {
        "discussion_chat_id": -1001,
        "message_id": 50,
        "posted_at": datetime(2026, 7, 16, tzinfo=UTC),
        "edited_at": None,
        "sender_id": "user:10",
        "sender_name": "Owner",
        "text_content": "Комментарий #Каин",
        "media_group_id": None,
        "media_type": "text",
        "telegram_file_id": None,
        "telegram_file_unique_id": None,
        "file_size": None,
        "mime_type": None,
        "original_file_name": None,
        "has_spoiler": False,
        "reply_to_message_id": None,
        "is_automatic_forward": False,
        "forward_channel_id": None,
        "forward_message_id": None,
    }
    values.update(changes)
    return DiscussionMessageEvent(**values)


class DiscussionIngestServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_untracked_chat_is_ignored(self) -> None:
        repository = SimpleNamespace(
            get_parent_channel_id=AsyncMock(return_value=None),
            upsert_message=AsyncMock(),
        )
        service = DiscussionIngestService(repository)

        result = await service.ingest(make_event())

        self.assertFalse(result.stored)
        repository.upsert_message.assert_not_awaited()

    async def test_plain_message_becomes_its_own_root(self) -> None:
        repository = SimpleNamespace(
            get_parent_channel_id=AsyncMock(return_value=-2000),
            upsert_message=AsyncMock(),
        )
        service = DiscussionIngestService(repository)

        result = await service.ingest(make_event())

        self.assertTrue(result.stored)
        self.assertEqual(result.root_channel_id, -1001)
        self.assertEqual(result.root_message_id, 50)
        call = repository.upsert_message.await_args.kwargs
        self.assertEqual(call["hashtags"], ["Каин"])
        self.assertEqual(call["root_message_id"], 50)

    async def test_reply_uses_resolved_root(self) -> None:
        repository = SimpleNamespace(
            get_parent_channel_id=AsyncMock(return_value=-2000),
            resolve_root_reference=AsyncMock(return_value=(-2000, 77)),
            upsert_message=AsyncMock(),
        )
        service = DiscussionIngestService(repository)

        result = await service.ingest(make_event(reply_to_message_id=40))

        self.assertEqual((result.root_channel_id, result.root_message_id), (-2000, 77))
        repository.resolve_root_reference.assert_awaited_once_with(
            discussion_chat_id=-1001,
            message_id=40,
        )

    async def test_autoforward_uses_channel_post_match(self) -> None:
        event = make_event(
            is_automatic_forward=True,
            forward_channel_id=-2000,
            forward_message_id=77,
        )
        repository = SimpleNamespace(
            get_parent_channel_id=AsyncMock(return_value=-2000),
            match_autoforwarded_post=AsyncMock(return_value=(-2000, 77)),
            upsert_message=AsyncMock(),
        )
        service = DiscussionIngestService(repository)

        result = await service.ingest(event)

        self.assertEqual((result.root_channel_id, result.root_message_id), (-2000, 77))
        repository.match_autoforwarded_post.assert_awaited_once_with(
            event=event,
            parent_channel_id=-2000,
        )


class TelegramDiscussionEventTests(unittest.TestCase):
    def test_text_message_becomes_neutral_event(self) -> None:
        message = Message(
            message_id=50,
            date=datetime(2026, 7, 16, tzinfo=UTC),
            chat=Chat(id=-1001, type=ChatType.SUPERGROUP),
            from_user=User(id=10, is_bot=False, first_name="Owner"),
            text="Комментарий",
        )

        event = discussion_event_from_message(message)

        self.assertEqual(event.discussion_chat_id, -1001)
        self.assertEqual(event.sender_id, "user:10")
        self.assertEqual(event.media_type, "text")
        self.assertEqual(event.text_content, "Комментарий")


if __name__ == "__main__":
    unittest.main()
