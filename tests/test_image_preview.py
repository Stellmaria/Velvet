import io
import unittest

from PIL import Image

from velvet_bot.image_preview import (
    BOT_API_DOWNLOAD_MAX_BYTES,
    TELEGRAM_PHOTO_TARGET_BYTES,
    ImagePreviewError,
    render_photo_preview,
)


class ImagePreviewTests(unittest.TestCase):
    def test_small_png_is_kept_byte_for_byte(self) -> None:
        source = io.BytesIO()
        image = Image.new("RGBA", (800, 1200), (255, 0, 0, 120))
        image.save(source, format="PNG")
        image.close()
        original = source.getvalue()

        payload, filename = render_photo_preview(original, "transparent.png")

        self.assertEqual(original, payload)
        self.assertEqual("transparent.png", filename)
        with Image.open(io.BytesIO(payload)) as result:
            self.assertEqual("PNG", result.format)
            self.assertEqual((800, 1200), result.size)
            self.assertEqual("RGBA", result.mode)

    def test_10_to_20_mb_png_keeps_full_dimensions(self) -> None:
        source = io.BytesIO()
        image = Image.effect_noise((3200, 2400), 80).convert("RGB")
        image.save(source, format="PNG")
        image.close()
        original = source.getvalue()
        self.assertGreater(len(original), 10 * 1024 * 1024)
        self.assertLessEqual(len(original), BOT_API_DOWNLOAD_MAX_BYTES)

        payload, filename = render_photo_preview(original, "large-original.png")

        self.assertTrue(filename.endswith("_telegram.jpg"))
        self.assertLessEqual(len(payload), TELEGRAM_PHOTO_TARGET_BYTES)
        with Image.open(io.BytesIO(payload)) as result:
            self.assertEqual("JPEG", result.format)
            self.assertEqual((3200, 2400), result.size)
            self.assertEqual("RGB", result.mode)

    def test_document_above_cloud_download_limit_is_rejected(self) -> None:
        with self.assertRaisesRegex(ImagePreviewError, "20 МБ"):
            render_photo_preview(
                b"x" * (BOT_API_DOWNLOAD_MAX_BYTES + 1),
                "too-large.png",
            )

    def test_invalid_document_is_rejected(self) -> None:
        with self.assertRaises(ImagePreviewError):
            render_photo_preview(b"not an image", "broken.png")


if __name__ == "__main__":
    unittest.main()
