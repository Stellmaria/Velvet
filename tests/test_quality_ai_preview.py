from __future__ import annotations

import unittest

from velvet_bot.ai_quality import AIQualityItem
from velvet_bot.handlers import quality_ai as quality_ai_module
import velvet_bot.handlers.quality_ai_preview  # noqa: F401


class QualityAIPreviewButtonTests(unittest.TestCase):
    def test_report_keyboard_contains_explicit_preview_button(self) -> None:
        item = AIQualityItem(
            media_id=77,
            file_name="media-77 · image/jpeg",
            media_type="photo",
            telegram_file_id="telegram-file",
            preview_file_id=None,
            status="ready",
            verdict="review",
            quality_score=74,
            confidence=80,
            report={"summary_ru": "Нужна проверка."},
            decision=None,
            error_message=None,
        )

        markup = quality_ai_module._report_keyboard(
            item,
            section="review",
            page=0,
        )
        buttons = [button for row in markup.inline_keyboard for button in row]
        preview = [button for button in buttons if button.text == "🖼 Посмотреть фото"]

        self.assertEqual(1, len(preview))
        self.assertIn("qpreview", preview[0].callback_data or "")
        self.assertIn("77", preview[0].callback_data or "")


if __name__ == "__main__":
    unittest.main()
