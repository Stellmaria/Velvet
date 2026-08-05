from __future__ import annotations

import io
import unittest

from PIL import Image

from velvet_bot.domains.codex_image import export_dimensions, export_jpeg


class CodexImageExportTests(unittest.TestCase):
    def test_export_dimensions_are_ratio_aware(self) -> None:
        self.assertEqual(export_dimensions("1K", "16:9"), (1024, 576))
        self.assertEqual(export_dimensions("2K", "9:16"), (1152, 2048))
        self.assertEqual(export_dimensions("4K", "1:1"), (3840, 3840))

    def test_export_is_high_quality_jpeg_at_selected_size(self) -> None:
        source = io.BytesIO()
        Image.new("RGB", (640, 480), "white").save(source, format="PNG")
        payload, size = export_jpeg(
            source.getvalue(),
            resolution="2K",
            aspect_ratio="16:9",
        )
        self.assertEqual(size, (2048, 1152))
        self.assertTrue(payload.startswith(b"\xff\xd8\xff"))
        with Image.open(io.BytesIO(payload)) as image:
            self.assertEqual(image.size, size)
            self.assertEqual(image.format, "JPEG")


if __name__ == "__main__":
    unittest.main()
