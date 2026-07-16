from __future__ import annotations

import unittest

from velvet_bot.ai_quality_schema_compat import _item_from_row


class AIQualitySchemaCompatibilityTests(unittest.TestCase):
    def test_item_label_does_not_require_file_name_column(self) -> None:
        item = _item_from_row(
            {
                "media_id": 42,
                "media_type": "photo",
                "mime_type": "image/jpeg",
                "telegram_file_id": "telegram-file",
                "preview_file_id": None,
                "status": "ready",
                "verdict": "review",
                "quality_score": 78,
                "confidence": 81,
                "report": {"summary_ru": "Проверка завершена."},
                "decision": None,
                "error_message": None,
            }
        )

        self.assertEqual(42, item.media_id)
        self.assertEqual("media-42 · image/jpeg", item.file_name)
        self.assertEqual("photo", item.media_type)
        self.assertEqual("review", item.verdict)

    def test_compatibility_queries_do_not_reference_missing_column(self) -> None:
        from pathlib import Path

        source = Path("velvet_bot/ai_quality_schema_compat.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("mf.file_name", source)
        self.assertIn("mf.mime_type", source)


if __name__ == "__main__":
    unittest.main()
