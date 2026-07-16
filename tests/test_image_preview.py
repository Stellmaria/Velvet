import io
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from PIL import Image

from velvet_bot.archive_catalog import ArchivedMedia
from velvet_bot.image_preview import (
    PREVIEW_MAX_BYTES,
    PREVIEW_MAX_EDGE,
    TELEGRAM_BOT_DOWNLOAD_MAX_BYTES,
    ImagePreviewError,
    build_image_document_preview,
    render_photo_preview,
)


class ImagePreviewTests(unittest.TestCase):
    def test_large_png_becomes_telegram_photo_jpeg(self) -> None:
        source = io.BytesIO()
        image = Image.effect_noise((3200, 2400), 80).convert("RGB")
        image.save(source, format="PNG")
        image.close()

        payload, filename = render_photo_preview(
            source.getvalue(),
            "large-original.png",
        )

        self.assertTrue(filename.endswith("_preview.jpg"))
        self.assertLessEqual(len(payload), PREVIEW_MAX_BYTES)
        with Image.open(io.BytesIO(payload)) as preview:
            self.assertEqual("JPEG", preview.format)
            self.assertLessEqual(max(preview.size), PREVIEW_MAX_EDGE)
            self.assertEqual("RGB", preview.mode)

    def test_transparent_png_is_flattened_for_photo_preview(self) -> None:
        source = io.BytesIO()
        image = Image.new("RGBA", (800, 1200), (255, 0, 0, 120))
        image.save(source, format="PNG")
        image.close()

        payload, _ = render_photo_preview(source.getvalue(), "transparent.png")

        with Image.open(io.BytesIO(payload)) as preview:
            self.assertEqual("RGB", preview.mode)
            self.assertEqual((800, 1200), preview.size)

    def test_invalid_document_is_rejected(self) -> None:
        with self.assertRaises(ImagePreviewError):
            render_photo_preview(b"not an image", "broken.png")


class ImagePreviewDownloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_oversized_document_skips_telegram_download(self) -> None:
        bot = AsyncMock()
        media = ArchivedMedia(
            id=17,
            telegram_file_id="oversized-file-id",
            media_type="document",
            original_file_name="oversized.png",
            storage_file_name="oversized.png",
            mime_type="image/png",
            file_size=TELEGRAM_BOT_DOWNLOAD_MAX_BYTES + 1,
            linked_at=datetime.now(timezone.utc),
        )

        with self.assertRaisesRegex(ImagePreviewError, "лимит скачивания"):
            await build_image_document_preview(bot, media)

        bot.download.assert_not_awaited()

    async def test_downloadable_document_still_builds_preview(self) -> None:
        source = io.BytesIO()
        image = Image.new("RGB", (320, 480), (120, 80, 40))
        image.save(source, format="PNG")
        image.close()
        source_payload = source.getvalue()

        bot = AsyncMock()

        async def download(_file_id, *, destination, seek):
            destination.write(source_payload)
            if seek:
                destination.seek(0)

        bot.download.side_effect = download
        media = ArchivedMedia(
            id=18,
            telegram_file_id="downloadable-file-id",
            media_type="document",
            original_file_name="downloadable.png",
            storage_file_name="downloadable.png",
            mime_type="image/png",
            file_size=len(source_payload),
            linked_at=datetime.now(timezone.utc),
        )

        preview = await build_image_document_preview(bot, media)

        bot.download.assert_awaited_once()
        self.assertTrue(preview.filename.endswith("_preview.jpg"))


if __name__ == "__main__":
    unittest.main()
