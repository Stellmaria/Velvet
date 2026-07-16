from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.publication import (
    PublicationDraft,
    PublicationIssue,
    PublicationItem,
    PublicationService,
)
from velvet_bot.infrastructure.telegram.publication_delivery import (
    TelegramPublicationDelivery,
    split_publication_text,
)


def make_draft(*, status: str = "checked", errors: int = 0) -> PublicationDraft:
    item = PublicationItem(
        id=1,
        draft_id=2,
        position=0,
        telegram_file_id="photo-id",
        telegram_file_unique_id="unique-id",
        media_type="photo",
        mime_type="image/jpeg",
        file_name="image.jpg",
        file_size=100,
        source_message_id=50,
        has_spoiler=False,
    )
    return PublicationDraft(
        id=2,
        owner_id=10,
        target_chat_id=-100123,
        source_chat_id=10,
        source_message_id=50,
        source_media_group_id=None,
        text_content="Публикация",
        status=status,
        post_type="art",
        has_spoiler=False,
        content_hash="0" * 64,
        validation_status="failed" if errors else "passed",
        validation_error_count=errors,
        validation_warning_count=0,
        validation_report=(
            (PublicationIssue("error", "error", "Ошибка", "Описание"),)
            if errors
            else ()
        ),
        scheduled_at=None,
        published_at=None,
        published_message_ids=(),
        attempt_count=0,
        last_error=None,
        created_at=datetime(2026, 7, 16, tzinfo=UTC),
        updated_at=datetime(2026, 7, 16, tzinfo=UTC),
        items=(item,),
    )


class PublicationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_coordinates_repository_and_delivery(self) -> None:
        draft = make_draft()
        published = make_draft(status="published")
        repository = SimpleNamespace(
            get_draft=AsyncMock(side_effect=[draft, draft, published]),
            claim_for_publishing=AsyncMock(return_value=True),
            mark_published=AsyncMock(),
            mark_error=AsyncMock(),
            list_due_draft_ids=AsyncMock(return_value=[]),
        )
        delivery = SimpleNamespace(send=AsyncMock(return_value=[101]))
        validator = AsyncMock(return_value=draft)
        service = PublicationService(
            repository=repository,
            delivery=delivery,
            validator=validator,
        )

        result = await service.publish(2, owner_id=10, actor_id=10)

        self.assertEqual(result.status, "published")
        validator.assert_awaited_once_with(2, 10)
        delivery.send.assert_awaited_once_with(draft)
        repository.mark_published.assert_awaited_once_with(
            2,
            message_ids=[101],
            actor_id=10,
        )
        repository.mark_error.assert_not_awaited()

    async def test_delivery_error_is_persisted(self) -> None:
        draft = make_draft()
        repository = SimpleNamespace(
            get_draft=AsyncMock(side_effect=[draft, draft]),
            claim_for_publishing=AsyncMock(return_value=True),
            mark_published=AsyncMock(),
            mark_error=AsyncMock(),
        )
        delivery = SimpleNamespace(send=AsyncMock(side_effect=RuntimeError("Telegram down")))
        service = PublicationService(
            repository=repository,
            delivery=delivery,
            validator=AsyncMock(return_value=draft),
        )

        with self.assertRaisesRegex(RuntimeError, "Telegram down"):
            await service.publish(2, actor_id=None)

        repository.mark_error.assert_awaited_once()
        repository.mark_published.assert_not_awaited()

    async def test_validation_errors_block_delivery(self) -> None:
        draft = make_draft(errors=1)
        repository = SimpleNamespace(get_draft=AsyncMock(return_value=draft))
        delivery = SimpleNamespace(send=AsyncMock())
        service = PublicationService(
            repository=repository,
            delivery=delivery,
            validator=AsyncMock(return_value=draft),
        )

        with self.assertRaisesRegex(ValueError, "заблокирована"):
            await service.publish(2)

        delivery.send.assert_not_awaited()


class TelegramPublicationDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def test_text_split_preserves_limit(self) -> None:
        chunks = split_publication_text("слово " * 2000)
        self.assertTrue(chunks)
        self.assertTrue(all(len(chunk) <= 4096 for chunk in chunks))

    async def test_single_photo_uses_spoiler_and_caption(self) -> None:
        sent = SimpleNamespace(message_id=77)
        bot = SimpleNamespace(send_photo=AsyncMock(return_value=sent))
        delivery = TelegramPublicationDelivery(bot)
        draft = make_draft()

        result = await delivery.send(draft)

        self.assertEqual(result, [77])
        bot.send_photo.assert_awaited_once()
        call = bot.send_photo.await_args
        self.assertEqual(call.kwargs["photo"], "photo-id")
        self.assertEqual(call.kwargs["caption"], "Публикация")


if __name__ == "__main__":
    unittest.main()
