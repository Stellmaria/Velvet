from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiogram.types import InlineKeyboardMarkup

from velvet_bot.domains.archive.models import ArchivePage, ArchivedMedia
from velvet_bot.domains.characters.models import CharacterRecord
from velvet_bot.image_preview import BOT_API_DOWNLOAD_MAX_BYTES
from velvet_bot.public_preview_overrides import (
    _open_image_document_as_file,
    send_viewer_archive_page,
)


def _page(*, file_size: int) -> ArchivePage:
    now = datetime.now(timezone.utc)
    return ArchivePage(
        character=CharacterRecord(
            id=17,
            name="Макс Кроу",
            created_by=1,
            created_in_chat=2,
            created_at=now,
            archive_chat_id=None,
            archive_thread_id=None,
            archive_topic_url=None,
        ),
        media=ArchivedMedia(
            id=33,
            telegram_file_id="large-public-image-file-id",
            media_type="document",
            original_file_name="large-image.png",
            storage_file_name="large-image__hash.png",
            mime_type="image/png",
            file_size=file_size,
            linked_at=now,
        ),
        offset=0,
        total=1,
    )


class PublicManagerLargeFileOpenTests(unittest.IsolatedAsyncioTestCase):
    def test_large_image_file_mode_requires_manager_or_member_access(self) -> None:
        page = _page(file_size=BOT_API_DOWNLOAD_MAX_BYTES + 1)
        self.assertTrue(
            _open_image_document_as_file(
                page,
                manager_access=True,
                member_access=False,
            )
        )
        self.assertTrue(
            _open_image_document_as_file(
                page,
                manager_access=False,
                member_access=True,
            )
        )
        self.assertFalse(
            _open_image_document_as_file(
                page,
                manager_access=False,
                member_access=False,
            )
        )
        self.assertFalse(
            _open_image_document_as_file(
                _page(file_size=BOT_API_DOWNLOAD_MAX_BYTES),
                manager_access=True,
                member_access=False,
            )
        )

    async def test_owner_or_moderator_view_sends_original_large_document(self) -> None:
        sent = SimpleNamespace(message_id=101)
        bot = SimpleNamespace(
            send_document=AsyncMock(return_value=sent),
            send_photo=AsyncMock(),
            send_video=AsyncMock(),
            send_animation=AsyncMock(),
        )
        page = _page(file_size=72 * 1024 * 1024)

        with (
            patch(
                "velvet_bot.public_preview_overrides.public_display.load_public_state",
                new=AsyncMock(return_value=SimpleNamespace()),
            ),
            patch(
                "velvet_bot.public_preview_overrides.public_display.build_viewer_keyboard",
                new=AsyncMock(
                    return_value=InlineKeyboardMarkup(inline_keyboard=[])
                ),
            ),
            patch(
                "velvet_bot.public_preview_overrides.public_display.build_viewer_caption",
                new=Mock(return_value="Макс Кроу"),
            ),
            patch(
                "velvet_bot.public_preview_overrides.resolve_archive_image_preview",
                new=AsyncMock(),
            ) as resolver,
        ):
            result = await send_viewer_archive_page(
                bot=bot,
                database=SimpleNamespace(),
                chat_id=7221553045,
                page=page,
                viewer_user_id=8179531132,
                manager_access=True,
                member_access=False,
            )

        self.assertIs(result, sent)
        resolver.assert_not_awaited()
        bot.send_photo.assert_not_awaited()
        bot.send_document.assert_awaited_once()
        kwargs = bot.send_document.await_args.kwargs
        self.assertEqual(kwargs["document"], "large-public-image-file-id")
        self.assertEqual(kwargs["chat_id"], 7221553045)
        self.assertTrue(kwargs["protect_content"])

    async def test_public_viewer_keeps_photo_preview_pipeline(self) -> None:
        sent = SimpleNamespace(message_id=102, photo=[])
        bot = SimpleNamespace(
            send_document=AsyncMock(),
            send_photo=AsyncMock(return_value=sent),
            send_video=AsyncMock(),
            send_animation=AsyncMock(),
        )
        page = _page(file_size=72 * 1024 * 1024)

        with (
            patch(
                "velvet_bot.public_preview_overrides.public_display.load_public_state",
                new=AsyncMock(return_value=SimpleNamespace()),
            ),
            patch(
                "velvet_bot.public_preview_overrides.public_display.build_viewer_keyboard",
                new=AsyncMock(
                    return_value=InlineKeyboardMarkup(inline_keyboard=[])
                ),
            ),
            patch(
                "velvet_bot.public_preview_overrides.public_display.build_viewer_caption",
                new=Mock(return_value="Макс Кроу"),
            ),
            patch(
                "velvet_bot.public_preview_overrides.resolve_archive_image_preview",
                new=AsyncMock(return_value="preview-file-id"),
            ) as resolver,
            patch(
                "velvet_bot.public_preview_overrides.persist_preview_from_sent_message",
                new=AsyncMock(),
            ),
        ):
            await send_viewer_archive_page(
                bot=bot,
                database=SimpleNamespace(),
                chat_id=123,
                page=page,
                viewer_user_id=456,
                manager_access=False,
                member_access=False,
            )

        resolver.assert_awaited_once()
        bot.send_photo.assert_awaited_once()
        bot.send_document.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
