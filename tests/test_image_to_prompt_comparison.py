from __future__ import annotations

import os
import unittest
from html import escape
from pathlib import Path
from unittest.mock import patch

from velvet_bot.infrastructure.image_to_prompt import (
    _IMAGE_TO_PROMPT_INSTRUCTION,
    _is_complete,
    _merge_recovery,
    _missing_sections,
    _recovery_section,
)
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
        self.assertIn("Не переноси кисти", _IMAGE_TO_PROMPT_INSTRUCTION)

    def test_completion_notice_reports_full_and_partial_results(self) -> None:
        complete = velvet_ai_image_prompt._completion_notice(
            7,
            total_models=2,
            prompts={"first": "one", "second": "two"},
            errors={},
        )
        partial = velvet_ai_image_prompt._completion_notice(
            8,
            total_models=2,
            prompts={"first": "one"},
            errors={"second": "timeout"},
        )

        self.assertIn("✅ Image-to-prompt #7 завершён", complete)
        self.assertIn("2 из 2", complete)
        self.assertIn("⚠️ Image-to-prompt #8 завершён частично", partial)
        self.assertIn("1 из 2", partial)
        self.assertIn("Ошибок: <b>1</b>", partial)

    def test_prompt_chunks_fit_inside_telegram_pre_block_limit(self) -> None:
        source = ("строка <tag> & данные\n" * 600).strip()
        chunks = velvet_ai_image_prompt._split_preformatted(source)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            with self.subTest(length=len(chunk)):
                self.assertLessEqual(
                    len(escape(chunk)),
                    velvet_ai_image_prompt._PRE_BLOCK_CONTENT_LIMIT,
                )

    def test_controller_sends_text_instead_of_document(self) -> None:
        source = Path(velvet_ai_image_prompt.__file__).read_text(encoding="utf-8")
        self.assertNotIn("answer_document(", source)
        self.assertNotIn("BufferedInputFile", source)
        self.assertIn("_send_prompt_messages", source)

    def test_truncated_body_recovers_from_body_section(self) -> None:
        partial = """
Vᴇʟᴠᴇᴛ Sɪɢɴᴀᴛᴜʀᴇ
ВАЖНО:
Два взрослых персонажа.
СТРОГО:
Сохранить видимые особенности.
Технический блок:
Фотореализм и вертикальный кадр.
Суть:
Два человека в постановочной сцене.
Композиция и поза:
Передний и задний персонажи описаны раздельно.
Лицо и взгляд:
Направления взгляда указаны точно.
Руки:
Кисти и касания перечислены.
Тело:
Телосложение, плечи, груд
""".strip()
        self.assertEqual("Тело:", _recovery_section(partial))
        self.assertIn("Волосы и детали внешности:", _missing_sections(partial))

        recovery = """
Тело:
Телосложение и все видимые линии тела описаны полностью.
Волосы и детали внешности:
Волосы и украшения описаны по изображению.
Локация и фон:
Комната, мебель и глубина фона описаны полностью.
Освещение:
Направление и температура света указаны.
Цветовая палитра:
Тёмно-коричневый, чёрный, телесный, красный и янтарный.
Дополнительно:
Photorealistic editorial, shallow depth of field.
Negative prompts:
wrong pose, wrong hands, wrong rope placement, extra fingers, text, watermark.
PALETTE:
🌑 #120D0B espresso black
🟤 #3B241C dark umber
🟥 #8B1018 velvet red
🟠 #B66B38 amber brown
🟡 #D6A377 warm skin
""".strip()
        merged = _merge_recovery(partial, recovery, "Тело:")
        self.assertTrue(_is_complete(merged))
        self.assertNotIn("плечи, груд\n", merged)
        self.assertEqual(1, merged.count("Тело:"))

    def test_palette_with_too_few_hex_colors_is_incomplete(self) -> None:
        prompt = """
ВАЖНО:\na
СТРОГО:\na
Технический блок:\na
Суть:\na
Композиция и поза:\na
Лицо и взгляд:\na
Руки:\na
Тело:\na
Волосы и детали внешности:\na
Локация и фон:\na
Освещение:\na
Цветовая палитра:\na
Дополнительно:\na
Negative prompts:\na
PALETTE:\n#111111\n#222222
""".strip()
        self.assertFalse(_is_complete(prompt))
        self.assertEqual("PALETTE:", _recovery_section(prompt))


if __name__ == "__main__":
    unittest.main()
