import json
import unittest
from datetime import UTC, datetime
from pathlib import Path

from velvet_bot.character_directory import CharacterDirectoryItem
from velvet_bot.database import Character
from velvet_bot.handlers.admin_directory import AdminDirectoryCallback
from velvet_bot.handlers.admin_stories import build_story_picker
from velvet_bot.public_ui import PublicArchiveCallback
from velvet_bot.story_catalog import (
    CharacterStory,
    clean_story_short_label,
    make_story_key,
    universe_requires_story,
)


class StoryCatalogTests(unittest.TestCase):
    def test_visual_novel_universes_require_story(self) -> None:
        for universe in {"shs", "kr", "lm", "idm"}:
            with self.subTest(universe=universe):
                self.assertTrue(universe_requires_story(universe))
        for universe in {"bg3", "lagerta", "original"}:
            with self.subTest(universe=universe):
                self.assertFalse(universe_requires_story(universe))

    def test_short_label_is_normalized(self) -> None:
        self.assertEqual("СНР", clean_story_short_label(" снр "))
        self.assertEqual("снр", make_story_key("СНР"))

    def test_exported_catalog_has_unique_keys_and_initials(self) -> None:
        path = Path(__file__).resolve().parents[1] / "data" / "story_catalog.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        stories = payload["stories"]
        self.assertGreaterEqual(len(stories), 60)
        keys = {(item["universe"], item["key"]) for item in stories}
        initials = {(item["universe"], item["short_label"]) for item in stories}
        self.assertEqual(len(stories), len(keys))
        self.assertEqual(len(stories), len(initials))
        self.assertIn(
            ("shs", "ЦД"),
            initials,
        )
        self.assertIn(
            ("kr", "СНР"),
            initials,
        )
        self.assertIn(
            ("idm", "ЛКБ"),
            initials,
        )

    def test_owner_picker_uses_initials_and_story_id(self) -> None:
        character = Character(
            id=17,
            name="Каин",
            created_by=1,
            created_in_chat=2,
            created_at=datetime(2026, 7, 15, tzinfo=UTC),
            archive_chat_id=None,
            archive_thread_id=None,
            archive_topic_url=None,
        )
        item = CharacterDirectoryItem(
            character=character,
            category="male",
            prompt_post_url=None,
            media_count=4,
            universe="kr",
        )
        story = CharacterStory(
            id=12,
            universe="kr",
            key="heavens_secret_requiem",
            short_label="СНР",
            title="Секрет Небес: Реквием",
            sort_order=10,
        )
        keyboard = build_story_picker(
            item,
            [story],
            category="male",
            page=0,
        )
        button = keyboard.inline_keyboard[0][0]
        self.assertIn("СНР", button.text)
        callback = AdminDirectoryCallback.unpack(button.callback_data)
        self.assertEqual("setstory", callback.action)
        self.assertEqual(12, callback.story_id)
        self.assertLessEqual(len(button.callback_data.encode("utf-8")), 64)

    def test_public_callback_with_story_fits_telegram_limit(self) -> None:
        packed = PublicArchiveCallback(
            action="download",
            character_id=123456,
            offset=999,
            media_id=999999,
            page=99,
            category="mfm",
            universe="original",
            story_id=9999,
        ).pack()
        self.assertLessEqual(len(packed.encode("utf-8")), 64)


if __name__ == "__main__":
    unittest.main()
