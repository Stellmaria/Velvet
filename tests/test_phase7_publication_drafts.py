from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.enums import ChatType
from aiogram.types import Chat, Message, User

from velvet_bot.domains.publication import (
    PublicationDraft,
    PublicationDraftService,
    PublicationInboxItem,
    PublicationInboxPayload,
)
from velvet_bot.infrastructure.telegram import publication_payload_from_message


def make_draft(*, draft_id: int = 5, errors: int = 0) -> PublicationDraft:
    return PublicationDraft(
        id=draft_id,
        owner_id=10,
        target_chat_id=-100123,
        source_chat_id=10,
        source_message_id=20,
        source_media_group_id=None,
        text_content="Текст",
        status="checked",
        post_type="art",
        has_spoiler=False,
        content_hash="a" * 64,
        validation_status="failed" if errors else "passed",
        validation_error_count=errors,
        validation_warning_count=0,
        validation_report=(),
        scheduled_at=None,
        published_at=None,
        published_message_ids=(),
        attempt_count=0,
        last_error=None,
        created_at=datetime(2026, 7, 16, tzinfo=UTC),
        updated_at=datetime(2026, 7, 16, tzinfo=UTC),
        items=(),
    )


class PublicationDraftServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_aggregates_album_text_and_validates(self) -> None:
        source = PublicationInboxPayload(
            owner_id=10,
            source_chat_id=10,
            source_message_id=20,
            media_group_id="album",
            text_content="Первая часть",
            telegram_file_id="photo-1",
            telegram_file_unique_id="u1",
            media_type="photo",
            mime_type="image/jpeg",
            file_name="one.jpg",
            file_size=100,
            has_spoiler=False,
        )
        second = PublicationInboxPayload(
            owner_id=10,
            source_chat_id=10,
            source_message_id=21,
            media_group_id="album",
            text_content="Вторая часть",
            telegram_file_id="photo-2",
            telegram_file_unique_id="u2",
            media_type="photo",
            mime_type="image/jpeg",
            file_name="two.jpg",
            file_size=100,
            has_spoiler=True,
        )
        created = make_draft()
        commands = SimpleNamespace(
            capture_inbox=AsyncMock(),
            list_source_items=AsyncMock(
                return_value=(
                    PublicationInboxItem(1, source),
                    PublicationInboxItem(2, second),
                )
            ),
            create_draft=AsyncMock(return_value=created),
        )
        validator = AsyncMock(return_value=created)
        service = PublicationDraftService(
            drafts=SimpleNamespace(),
            commands=commands,
            validator=validator,
        )

        result = await service.create_from_payload(source, target_chat_id=-100123)

        self.assertEqual(result.id, 5)
        commands.capture_inbox.assert_awaited_once_with(source)
        create_call = commands.create_draft.await_args.kwargs
        self.assertEqual(create_call["text_content"], "Первая часть\n\nВторая часть")
        self.assertTrue(create_call["has_spoiler"])
        self.assertEqual(len(create_call["content_hash"]), 64)
        validator.assert_awaited_once_with(5, 10)

    async def test_schedule_rejects_invalid_draft(self) -> None:
        invalid = make_draft(errors=1)
        commands = SimpleNamespace(schedule=AsyncMock())
        service = PublicationDraftService(
            drafts=SimpleNamespace(),
            commands=commands,
            validator=AsyncMock(return_value=invalid),
        )

        with self.assertRaisesRegex(ValueError, "исправьте ошибки"):
            await service.schedule(
                5,
                owner_id=10,
                scheduled_at=datetime(2026, 7, 20, tzinfo=UTC),
            )

        commands.schedule.assert_not_awaited()

    def test_content_hash_is_stable_for_media_order(self) -> None:
        first = PublicationDraftService.content_hash(" Текст ", ["b", "a"])
        second = PublicationDraftService.content_hash("Текст", ["a", "b"])
        self.assertEqual(first, second)


class TelegramPublicationInboxTests(unittest.TestCase):
    def test_text_message_becomes_neutral_payload(self) -> None:
        chat = Chat(id=10, type=ChatType.PRIVATE)
        user = User(id=10, is_bot=False, first_name="Owner")
        message = Message(
            message_id=20,
            date=datetime(2026, 7, 16, tzinfo=UTC),
            chat=chat,
            from_user=user,
            text="Публикация",
        )

        payload = publication_payload_from_message(message, owner_id=10)

        self.assertEqual(payload.source_chat_id, 10)
        self.assertEqual(payload.source_message_id, 20)
        self.assertEqual(payload.text_content, "Публикация")
        self.assertEqual(payload.media_type, "text")
        self.assertIsNone(payload.telegram_file_id)


if __name__ == "__main__":
    unittest.main()
