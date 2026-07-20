from __future__ import annotations

import unittest
from pathlib import Path


class PublicArchiveNoopEditTests(unittest.TestCase):
    def test_unchanged_media_edit_does_not_retry_same_keyboard(self) -> None:
        for relative in (
            "velvet_bot/public_archive_display.py",
            "velvet_bot/public_preview_overrides.py",
        ):
            with self.subTest(path=relative):
                source = Path(relative).read_text(encoding="utf-8")
                self.assertIn(
                    'if "message is not modified" in str(error).casefold():\n            return',
                    source,
                )
                self.assertNotIn(
                    "await callback.message.edit_reply_markup(reply_markup=keyboard)",
                    source,
                )


if __name__ == "__main__":
    unittest.main()
