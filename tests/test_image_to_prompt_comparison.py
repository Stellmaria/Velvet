from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from velvet_bot.image_to_prompt import _IMAGE_TO_PROMPT_INSTRUCTION
from velvet_bot.presentation.telegram.routers.quality_operations_controllers import (
    velvet_ai_image_prompt,
)


class ImageToPromptComparisonTests(unittest.TestCase):
    def test_single_model_when_compare_model_is_empty(self) -> None:
        with patch.dict(os.environ, {"AI_VISION_COMPARE_MODEL": ""}, clear=False):
            self.assertEqual(("primary",), velvet_ai_image_prompt._comparison_models("primary"))

    def test_second_distinct_model_is_added(self) -> None:
        with patch.dict(
            os.environ,
            {"AI_VISION_COMPARE_MODEL": "qwen3-vl:8b"},
            clear=False,
        ):
            self.assertEqual(
                ("primary", "qwen3-vl:8b"),
                velvet_ai_image_prompt._comparison_models("primary"),
            )

    def test_duplicate_compare_model_is_ignored(self) -> None:
        with patch.dict(
            os.environ,
            {"AI_VISION_COMPARE_MODEL": "primary"},
            clear=False,
        ):
            self.assertEqual(("primary",), velvet_ai_image_prompt._comparison_models("primary"))

    def test_velvet_anatomy_editorial_contract_is_present(self) -> None:
        required_sections = (
            "Vᴇʟᴠᴇᴛ Sɪɢɴᴀᴛᴜʀᴇ",
            "ВАЖНО:",
            "СТРОГО:",
            "Технический блок:",
            "Суть:",
            "Композиция и поза:",
            "Лицо и взгляд:",
            "Руки:",
            "Тело:",
            "Волосы и детали внешности:",
            "Локация и фон:",
            "Освещение:",
            "Цветовая палитра:",
            "Дополнительно:",
            "Negative prompts:",
            "PALETTE:",
        )
        for section in required_sections:
            with self.subTest(section=section):
                self.assertIn(section, _IMAGE_TO_PROMPT_INSTRUCTION)

    def test_prompt_contract_preserves_source_instead_of_forcing_channel_defaults(self) -> None:
        self.assertIn("Не превращай обычный портрет в арт-ню", _IMAGE_TO_PROMPT_INSTRUCTION)
        self.assertIn("не навязывай 9:16", _IMAGE_TO_PROMPT_INSTRUCTION.casefold())
        self.assertIn("одно изображение", _IMAGE_TO_PROMPT_INSTRUCTION)
        self.assertIn("ровно 5 или 6 строк", _IMAGE_TO_PROMPT_INSTRUCTION)


if __name__ == "__main__":
    unittest.main()
