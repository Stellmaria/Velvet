import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.media import (
    MediaDescriptor,
    build_storage_file_name,
    extract_media,
    sanitize_file_name,
    send_media_to_topic,
)


class MediaFileNameTests(unittest.TestCase):
    def test_same_file_always_gets_same_storage_name(self) -> None:
        first = build_storage_file_name(
            "Каин портрет.png",
            "unique-file-id",
            default_extension=".png",
        )
        second = build_storage_file_name(
            "Каин портрет.png",
            "unique-file-id",
            default_extension=".png",
        )
        self.assertEqual(first, second)

    def test_different_files_with_same_original_name_do_not_collide(self) -> None:
        first = build_storage_file_name(
            "portrait.png",
            "first-unique-id",
            default_extension=".png",
        )
        second = build_storage_file_name(
            "portrait.png",
            "second-unique-id",
            default_extension=".png",
        )
        self.assertNotEqual(first, second)

    def test_windows_reserved_characters_are_removed(self) -> None:
        self.assertEqual("bad_name_.png", sanitize_file_name("bad:name?.png"))

    def test_media_can_be_extracted_from_external_reply_shape(self) -> None:
        source = SimpleNamespace(
            photo=None,
            video=None,
            animation=None,
            document=SimpleNamespace(
                file_id="document-file-id",
                file_unique_id="document-unique-id",
                file_name="result.png",
                mime_type="image/png",
                file_size=123,
            ),
        )

        media = extract_media(source)

        self.assertIsNotNone(media)
        self.assertEqual("document-file-id", media.telegram_file_id)
        self.assertEqual("result.png", media.original_file_name)
        self.assertEqual("document", media.media_type)


class ArchiveSendTests(unittest.IsolatedAsyncioTestCase):
    async def test_document_is_sent_without_source_caption(self) -> None:
        bot = SimpleNamespace(send_document=AsyncMock(return_value="sent-message"))
        media = MediaDescriptor(
            telegram_file_id="file-id",
            telegram_file_unique_id="unique-id",
            original_file_name="result.png",
            storage_file_name="result__hash.png",
            media_type="document",
            mime_type="image/png",
            file_size=123,
        )

        result = await send_media_to_topic(
            bot,
            media,
            chat_id=-100123,
            thread_id=456,
            caption="Текст источника не должен попасть в архив",
        )

        self.assertEqual("sent-message", result)
        bot.send_document.assert_awaited_once_with(
            document="file-id",
            chat_id=-100123,
            message_thread_id=456,
        )
