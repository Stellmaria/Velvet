import io
import unittest

from PIL import Image

from velvet_bot.image_preview import (
    PREVIEW_MAX_BYTES,
    PREVIEW_MAX_EDGE,
    ImagePreviewError,
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


if __name__ == "__main__":
    unittest.main()
