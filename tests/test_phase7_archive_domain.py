from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.archive import ArchiveService, ArchivedMedia


class ArchiveServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_url_is_validated_before_repository(self) -> None:
        repository = SimpleNamespace(set_prompt=AsyncMock())
        service = ArchiveService(repository)

        with self.assertRaisesRegex(ValueError, "ссылка на пост Telegram"):
            await service.set_prompt(
                character_id=1,
                media_id=2,
                prompt_post_url="https://example.com/post",
            )

        repository.set_prompt.assert_not_awaited()

    async def test_prompt_url_is_delegated_after_validation(self) -> None:
        repository = SimpleNamespace(set_prompt=AsyncMock(return_value=True))
        service = ArchiveService(repository)

        result = await service.set_prompt(
            character_id=1,
            media_id=2,
            prompt_post_url="https://t.me/velvet/123",
        )

        self.assertTrue(result)
        repository.set_prompt.assert_awaited_once_with(
            character_id=1,
            media_id=2,
            prompt_post_url="https://t.me/velvet/123",
        )

    async def test_toggle_spoiler_is_delegated(self) -> None:
        repository = SimpleNamespace(toggle_spoiler=AsyncMock(return_value=True))
        service = ArchiveService(repository)

        result = await service.toggle_spoiler(character_id=1, media_id=2)

        self.assertTrue(result)
        repository.toggle_spoiler.assert_awaited_once_with(
            character_id=1,
            media_id=2,
        )


class ArchivedMediaTests(unittest.TestCase):
    def test_image_document_detection_is_domain_owned(self) -> None:
        media = ArchivedMedia(
            id=1,
            telegram_file_id="file",
            media_type="document",
            original_file_name="image.png",
            storage_file_name="stored.bin",
            mime_type="image/png",
            file_size=100,
            linked_at=datetime(2026, 7, 16, tzinfo=UTC),
        )
        self.assertTrue(media.is_image_document)
        self.assertEqual(media.display_file_name, "image.png")


if __name__ == "__main__":
    unittest.main()
