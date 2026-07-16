import io
import unittest

from PIL import Image, ImageDraw

from velvet_bot.quality_audit import QualitySummary
from velvet_bot.quality_ui import QualityCallback, build_quality_dashboard
from velvet_bot.visual_fingerprint import (
    build_visual_fingerprint,
    compare_fingerprints,
    hamming_distance,
)


def _sample_image() -> Image.Image:
    image = Image.new("RGB", (640, 960), (28, 24, 26))
    draw = ImageDraw.Draw(image)
    draw.rectangle((70, 80, 560, 840), outline=(220, 188, 160), width=18)
    draw.ellipse((145, 190, 495, 540), fill=(124, 72, 76))
    draw.polygon([(150, 760), (320, 570), (505, 785)], fill=(204, 162, 130))
    draw.line((80, 650, 555, 320), fill=(245, 230, 212), width=14)
    return image


def _encode(image: Image.Image, *, quality: int = 90) -> bytes:
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=quality, optimize=True)
    return output.getvalue()


class VisualFingerprintTests(unittest.TestCase):
    def test_same_image_after_resize_and_jpeg_compression_is_candidate(self) -> None:
        original = _sample_image()
        resized = original.resize((320, 480), Image.Resampling.LANCZOS)
        try:
            first = build_visual_fingerprint(_encode(original, quality=94))
            second = build_visual_fingerprint(_encode(resized, quality=62))
        finally:
            original.close()
            resized.close()
        comparison = compare_fingerprints(first, second)
        self.assertTrue(comparison.is_candidate)
        self.assertGreaterEqual(comparison.similarity_score, 75)

    def test_small_centered_crop_is_still_detected(self) -> None:
        original = _sample_image()
        cropped = original.crop((30, 45, 610, 915)).resize(
            original.size,
            Image.Resampling.LANCZOS,
        )
        try:
            first = build_visual_fingerprint(_encode(original, quality=90))
            second = build_visual_fingerprint(_encode(cropped, quality=82))
        finally:
            original.close()
            cropped.close()
        comparison = compare_fingerprints(first, second)
        self.assertLessEqual(comparison.phash_distance, 10)

    def test_visually_different_image_is_not_exact(self) -> None:
        first_image = _sample_image()
        second_image = Image.new("RGB", (640, 960), (240, 240, 240))
        draw = ImageDraw.Draw(second_image)
        draw.rectangle((0, 0, 320, 960), fill=(10, 10, 10))
        try:
            first = build_visual_fingerprint(_encode(first_image))
            second = build_visual_fingerprint(_encode(second_image))
        finally:
            first_image.close()
            second_image.close()
        comparison = compare_fingerprints(first, second)
        self.assertFalse(comparison.exact_bytes)
        self.assertGreater(hamming_distance(first.phash, second.phash), 0)

    def test_quality_callback_stays_within_telegram_limit(self) -> None:
        packed = QualityCallback(
            action="duplicate",
            section="unresolved_hashtags",
            page=999,
            item_id=9_223_372_036_854_775_000,
        ).pack()
        self.assertLessEqual(len(packed.encode("utf-8")), 64)

    def test_dashboard_contains_quality_sections(self) -> None:
        summary = QualitySummary(
            pending_duplicates=2,
            confirmed_duplicates=1,
            pending_scans=3,
            scan_errors=4,
            broken_files=5,
            unchecked_files=6,
            missing_category=7,
            missing_universe=8,
            missing_story=9,
            empty_characters=10,
            media_without_prompt=11,
            orphan_media=12,
            unresolved_hashtags=13,
        )
        text, keyboard = build_quality_dashboard(summary)
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertIn("Контроль качества", text)
        self.assertTrue(any("Дубли" in label for label in labels))
        self.assertTrue(any("Без истории" in label for label in labels))
        self.assertTrue(any("Битые файлы" in label for label in labels))


if __name__ == "__main__":
    unittest.main()
