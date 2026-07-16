import unittest
from types import SimpleNamespace

from velvet_bot.archive_preview import _message_thumbnail
from velvet_bot.media import extract_media


class LargeImagePreviewTests(unittest.TestCase):
    @staticmethod
    def _document_source():
        thumbnail = SimpleNamespace(
            file_id="thumb-file-id",
            file_unique_id="thumb-unique-id",
            width=320,
            height=480,
        )
        document = SimpleNamespace(
            file_id="document-file-id",
            file_unique_id="document-unique-id",
            file_name="large_render.png",
            mime_type="image/png",
            file_size=72 * 1024 * 1024,
            thumbnail=thumbnail,
        )
        return SimpleNamespace(
            photo=None,
            video=None,
            animation=None,
            document=document,
        ), thumbnail

    def test_image_document_keeps_telegram_thumbnail(self) -> None:
        source, _ = self._document_source()
        descriptor = extract_media(source)
        self.assertIsNotNone(descriptor)
        assert descriptor is not None
        self.assertEqual("document", descriptor.media_type)
        self.assertEqual("thumb-file-id", descriptor.preview_file_id)
        self.assertEqual("thumb-unique-id", descriptor.preview_file_unique_id)
        self.assertEqual(320, descriptor.preview_width)
        self.assertEqual(480, descriptor.preview_height)
        self.assertEqual("source_thumbnail", descriptor.preview_source)

    def test_forwarded_document_thumbnail_is_recoverable(self) -> None:
        source, thumbnail = self._document_source()
        message = SimpleNamespace(
            document=source.document,
            video=None,
            animation=None,
            photo=None,
        )
        self.assertIs(thumbnail, _message_thumbnail(message))


if __name__ == "__main__":
    unittest.main()
