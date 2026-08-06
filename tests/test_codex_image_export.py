from __future__ import annotations

import io
import unittest

from PIL import Image

from velvet_bot.domains.codex_image import (
    export_dimensions,
    export_jpeg,
    native_export_dimensions,
)


class CodexImageExportTests(unittest.TestCase):
    def test_legacy_export_dimensions_remain_readable(self) -> None:
        self.assertEqual(export_dimensions("1K", "16:9"), (1024, 576))
        self.assertEqual(export_dimensions("2K", "9:16"), (1152, 2048))
        self.assertEqual(export_dimensions("4K", "1:1"), (3840, 3840))

    def test_native_dimensions_crop_without_upscale(self) -> None:
        self.assertEqual(native_export_dimensions(640, 480, "16:9"), (640, 360))
        self.assertEqual(native_export_dimensions(1024, 1536, "9:16"), (864, 1536))

    def test_export_preserves_native_pixels_for_every_legacy_profile(self) -> None:
        source = io.BytesIO()
        Image.new("RGB", (640, 480), "white").save(source, format="PNG")
        sizes: list[tuple[int, int]] = []
        for resolution in ("1K", "2K", "4K"):
            payload, size = export_jpeg(
                source.getvalue(),
                resolution=resolution,
                aspect_ratio="16:9",
            )
            sizes.append(size)
            self.assertTrue(payload.startswith(b"\xff\xd8\xff"))
            with Image.open(io.BytesIO(payload)) as image:
                self.assertEqual(image.size, (640, 360))
                self.assertEqual(image.format, "JPEG")
        self.assertEqual([(640, 360)] * 3, sizes)


if __name__ == "__main__":
    unittest.main()
