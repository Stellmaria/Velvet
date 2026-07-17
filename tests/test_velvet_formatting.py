from __future__ import annotations

import unittest

from velvet_bot.velvet_ai_ui import build_velvet_ai_menu
from velvet_bot.velvet_formatting import (
    normalize_formatting_payload,
    render_velvet_post,
)


class VelvetFormattingNormalizationTests(unittest.TestCase):
    @staticmethod
    def payload() -> dict[str, object]:
        return {
            "title_en": "Loft Session / Soft Morning Light / Body Study",
            "lens": "35mm",
            "ratio": "9:16",
            "light_en": "soft morning light",
            "location_en": "industrial loft",
            "description_ru": "Короткое описание сцены.",
            "palette_hex": ["#aa3300", "112233", "bad", "#AA3300"],
            "hashtags": ["#Ада", " body study ", "#Ада"],
            "important_ru": "В кадре один взрослый персонаж 25+.",
            "strict_ru": "Сохранить внешность.",
            "technical_ru": "Фотореализм, 35mm, 9:16.",
            "essence_ru": "Спокойная редакционная сцена.",
            "composition_ru": "Средний план, корпус в три четверти.",
            "face_ru": "Взгляд направлен в сторону.",
            "hands_ru": "Кисти видны полностью.",
            "body_ru": "Пропорции не менять.",
            "location_ru": "Индустриальный лофт.",
            "lighting_ru": "Мягкий утренний свет.",
            "palette_ru": "Терракотовые и графитовые оттенки.",
            "additional_ru": "Натуральная текстура кожи.",
            "negative_ru": "Без артефактов рук и пластиковой кожи.",
        }

    def test_normalizes_title_palette_and_hashtags(self) -> None:
        result = normalize_formatting_payload(self.payload(), "full")

        self.assertEqual(
            "loft session / soft morning light / body study",
            result["title_en"],
        )
        self.assertEqual(["#AA3300", "#112233"], result["palette_hex"])
        self.assertEqual(["#Ада", "#bodystudy"], result["hashtags"])

    def test_shell_ignores_generated_descriptions_and_sections(self) -> None:
        result = normalize_formatting_payload(self.payload(), "shell")

        self.assertEqual("", result["description_ru"])
        self.assertEqual("", result["important_ru"])
        self.assertEqual("", result["negative_ru"])

    def test_short_ignores_full_prompt_sections(self) -> None:
        result = normalize_formatting_payload(self.payload(), "short")

        self.assertEqual("Короткое описание сцены.", result["description_ru"])
        self.assertEqual("", result["composition_ru"])


class VelvetFormattingRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = normalize_formatting_payload(
            VelvetFormattingNormalizationTests.payload(),
            "full",
        )

    def test_shell_wraps_original_source_in_signature(self) -> None:
        shell_payload = normalize_formatting_payload(
            VelvetFormattingNormalizationTests.payload(),
            "shell",
        )
        source = "ВАЖНО:\nСохранить лицо и пропорции."
        rendered = render_velvet_post("shell", source, shell_payload)

        self.assertIn("Vᴇʟᴠᴇᴛ Sɪɢɴᴀᴛᴜʀᴇ", rendered)
        self.assertIn("Сохранить лицо и пропорции", rendered)
        self.assertIn("<blockquote expandable>", rendered)
        self.assertLessEqual(len(rendered), 4090)

    def test_short_contains_description_without_full_sections(self) -> None:
        payload = normalize_formatting_payload(
            VelvetFormattingNormalizationTests.payload(),
            "short",
        )
        rendered = render_velvet_post("short", "Исходные заметки", payload)

        self.assertIn("Короткое описание сцены", rendered)
        self.assertNotIn("<b>СТРОГО:</b>", rendered)
        self.assertLessEqual(len(rendered), 4090)

    def test_full_uses_canonical_section_order(self) -> None:
        rendered = render_velvet_post("full", "Исходные заметки", self.payload)

        important = rendered.index("<b>ВАЖНО:</b>")
        strict = rendered.index("<b>СТРОГО:</b>")
        technical = rendered.index("<b>Технический блок:</b>")
        composition = rendered.index("<b>Композиция и поза:</b>")
        negative = rendered.index("<b>Negative prompts:</b>")
        self.assertLess(important, strict)
        self.assertLess(strict, technical)
        self.assertLess(technical, composition)
        self.assertLess(composition, negative)
        self.assertLessEqual(len(rendered), 4090)

    def test_long_full_post_is_reduced_without_breaking_limit(self) -> None:
        payload = dict(self.payload)
        for field in (
            "important_ru",
            "strict_ru",
            "technical_ru",
            "essence_ru",
            "composition_ru",
            "face_ru",
            "hands_ru",
            "body_ru",
            "location_ru",
            "lighting_ru",
            "palette_ru",
            "additional_ru",
            "negative_ru",
        ):
            payload[field] = ("Подробное требование сохранить все заданные особенности. " * 30).strip()

        rendered = render_velvet_post("full", "Исходные заметки", payload)

        self.assertLessEqual(len(rendered), 4090)
        self.assertIn("<b>Vᴇʟᴠᴇᴛ Sɪɢɴᴀᴛᴜʀᴇ</b>", rendered)
        self.assertIn("<b>Negative prompts:</b>", rendered)


class VelvetFormattingMenuTests(unittest.TestCase):
    def test_velvet_ai_menu_contains_formatting_master(self) -> None:
        _, keyboard = build_velvet_ai_menu(
            enabled=True,
            provider="ollama",
            model="qwen3-vl:8b",
        )
        buttons = [button for row in keyboard.inline_keyboard for button in row]
        matches = [button for button in buttons if button.text == "✨ Оформление Velvet Anatomy"]

        self.assertEqual(1, len(matches))
        self.assertIn("format_menu", matches[0].callback_data or "")
        self.assertLessEqual(len((matches[0].callback_data or "").encode("utf-8")), 64)


if __name__ == "__main__":
    unittest.main()
