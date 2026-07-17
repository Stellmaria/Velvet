from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from velvet_bot import character_directory


ROOT = Path(__file__).resolve().parents[1]


class CharacterDirectoryCompatibilityTests(unittest.TestCase):
    def test_legacy_row_mapper_remains_available_for_partial_deployments(self) -> None:
        row = {
            "id": 17,
            "name": "Каэль",
            "created_by": 1,
            "created_in_chat": 2,
            "created_at": datetime.now(UTC),
            "archive_chat_id": -100123,
            "archive_thread_id": 7,
            "archive_topic_url": "https://t.me/c/123/7",
            "category": "male",
            "universe": "kr",
            "prompt_post_url": None,
            "story_id": 5,
            "story_short_label": "КР",
            "story_title": "История",
            "media_count": 3,
        }

        item = character_directory._row_to_directory_item(row)

        self.assertEqual(17, item.character.id)
        self.assertEqual("Каэль", item.character.name)
        self.assertEqual("male", item.category)
        self.assertEqual("kr", item.universe)
        self.assertEqual(5, item.story_id)
        self.assertEqual(3, item.media_count)

    def test_current_multi_story_facade_does_not_use_private_mapper(self) -> None:
        source = (ROOT / "velvet_bot/multi_story_support.py").read_text(encoding="utf-8")

        self.assertNotIn("_row_to_directory_item", source)
        self.assertIn("character_directory.list_character_directory", source)


if __name__ == "__main__":
    unittest.main()
