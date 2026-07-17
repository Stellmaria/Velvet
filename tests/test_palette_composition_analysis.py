from __future__ import annotations

import io
import unittest

from PIL import Image

from velvet_bot.palette_composition_analysis import (
    build_palette_card,
    extract_palette_metrics,
    normalize_composition_report,
)
from velvet_bot.velvet_ai_ui import build_velvet_ai_menu


class PaletteExtractionTests(unittest.TestCase):
    @staticmethod
    def split_image() -> bytes:
        image = Image.new("RGB", (100, 50), (255, 0, 0))
        for x in range(50, 100):
            for y in range(50):
                image.putpixel((x, y), (0, 0, 255))
        output = io.BytesIO()
        image.save(output, format="PNG")
        image.close()
        return output.getvalue()

    def test_extracts_real_hex_colors_and_dimensions(self) -> None:
        metrics = extract_palette_metrics(self.split_image(), color_count=6)
        codes = {color.hex_code for color in metrics.colors}

        self.assertEqual(100, metrics.width)
        self.assertEqual(50, metrics.height)
        self.assertEqual(2.0, metrics.aspect_ratio)
        self.assertIn("#FF0000", codes)
        self.assertIn("#0000FF", codes)
        self.assertGreaterEqual(sum(color.share for color in metrics.colors), 99.0)

    def test_palette_card_is_valid_png(self) -> None:
        metrics = extract_palette_metrics(self.split_image())
        card = build_palette_card(metrics)

        self.assertTrue(card.startswith(b"\x89PNG\r\n\x1a\n"))
        with Image.open(io.BytesIO(card)) as image:
            self.assertEqual((960, 260), image.size)


class CompositionNormalizationTests(unittest.TestCase):
    @staticmethod
    def payload() -> dict[str, object]:
        return {
            "composition_score": 86,
            "balance_score": 84,
            "framing_score": 82,
            "hierarchy_score": 88,
            "depth_score": 80,
            "lighting_score": 90,
            "palette_harmony_score": 85,
            "confidence": 78,
            "verdict": "strong",
            "composition_pattern": "rule_of_thirds",
            "lighting_direction": "side",
            "lighting_quality": "soft",
            "crop_risk": "low",
            "summary_ru": "Композиция читается уверенно.",
            "focal_point_ru": "Лицо персонажа.",
            "subject_placement_ru": "Персонаж смещён к правой трети.",
            "crop_assessment_ru": "Важные детали не обрезаны.",
            "negative_space_ru": "Слева оставлено рабочее пространство.",
            "visual_flow_ru": "Взгляд идёт от лица к рукам.",
            "depth_summary_ru": "Передний план отделён от фона.",
            "lighting_summary_ru": "Мягкий боковой свет.",
            "palette_summary_ru": "Тёплые нейтральные оттенки согласованы.",
            "strengths": ["Выраженный главный фокус."],
            "issues": [],
            "recommendations": [],
        }

    def test_clean_high_score_is_strong(self) -> None:
        report = normalize_composition_report(self.payload())

        self.assertEqual("strong", report["verdict"])
        self.assertEqual("rule_of_thirds", report["composition_pattern"])
        self.assertEqual(86, report["composition_score"])

    def test_issues_reduce_strong_to_review(self) -> None:
        payload = self.payload()
        payload["issues"] = ["Кисть обрезана слишком близко к суставу."]

        report = normalize_composition_report(payload)

        self.assertEqual("review", report["verdict"])

    def test_invalid_enums_and_scores_are_normalized(self) -> None:
        payload = self.payload()
        payload["composition_pattern"] = "invented"
        payload["lighting_direction"] = "somewhere"
        payload["composition_score"] = 180
        payload["confidence"] = 10

        report = normalize_composition_report(payload)

        self.assertEqual("unclear", report["composition_pattern"])
        self.assertEqual("unclear", report["lighting_direction"])
        self.assertEqual(100, report["composition_score"])
        self.assertEqual("insufficient", report["verdict"])


class PaletteCompositionMenuTests(unittest.TestCase):
    def test_velvet_ai_menu_contains_visual_analysis(self) -> None:
        _, keyboard = build_velvet_ai_menu(
            enabled=True,
            provider="ollama",
            model="qwen3-vl:8b",
        )
        buttons = [button for row in keyboard.inline_keyboard for button in row]
        matches = [button for button in buttons if button.text == "🎨 Палитра и композиция"]

        self.assertEqual(1, len(matches))
        self.assertIn("visual_start", matches[0].callback_data or "")
        self.assertLessEqual(len((matches[0].callback_data or "").encode("utf-8")), 64)


if __name__ == "__main__":
    unittest.main()
