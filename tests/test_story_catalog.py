import json
import unittest
from datetime import UTC, date, datetime
from pathlib import Path

from velvet_bot.character_directory import CharacterDirectoryItem
from velvet_bot.database import Character
from velvet_bot.handlers.admin_stories import AdminStoryCallback, build_story_picker
from velvet_bot.public_manager_ui import manager_callback
from velvet_bot.public_ui import PublicArchiveCallback
from velvet_bot.story_catalog import (
    CharacterStory,
    StoryPage,
    clean_story_short_label,
    format_story_release,
    make_story_key,
    universe_requires_story,
)


class StoryCatalogTests(unittest.TestCase):
    def test_visual_novel_universes_require_story(self) -> None:
        for universe in {"shs", "kr", "lm", "idm", "lagerta"}:
            with self.subTest(universe=universe):
                self.assertTrue(universe_requires_story(universe))
        for universe in {"bg3", "original"}:
            with self.subTest(universe=universe):
                self.assertFalse(universe_requires_story(universe))

    def test_short_label_is_normalized(self) -> None:
        self.assertEqual("СНР", clean_story_short_label(" снр "))
        self.assertEqual("снр", make_story_key("СНР"))

    def test_release_label_respects_precision(self) -> None:
        released = date(2026, 1, 1)
        self.assertEqual("2026", format_story_release(released, "year"))
        self.assertEqual("01.2026", format_story_release(released, "month"))
        self.assertEqual("01.01.2026", format_story_release(released, "day"))
        self.assertEqual("дата не указана", format_story_release(None, "unknown"))

    def test_exported_catalog_is_current_and_unique(self) -> None:
        path = Path(__file__).resolve().parents[1] / "data" / "story_catalog.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        universes = payload["universes"]
        stories = [
            (universe, *entry)
            for universe, entries in universes.items()
            for entry in entries
        ]
        self.assertEqual("2026-07-20", payload["as_of"])
        self.assertGreaterEqual(len(stories), 92)

        keys = {(item[0], item[1]) for item in stories}
        initials = {(item[0], item[2]) for item in stories}
        self.assertEqual(len(stories), len(keys))
        self.assertEqual(len(stories), len(initials))

        self.assertEqual(58, len(universes["kr"]))
        self.assertGreaterEqual(len(universes["lm"]), 16)
        self.assertEqual(15, len(universes["shs"]))
        self.assertGreaterEqual(len(universes["idm"]), 1)
        self.assertEqual(2, len(universes["lagerta"]))

        self.assertIn(("kr", "РС"), initials)
        self.assertIn(("kr", "ТС2"), initials)
        self.assertIn(("lm", "СП"), initials)
        expected_shs_labels = {
            "ПОН",
            "ПЖЗ",
            "ЭФ",
            "СА",
            "НДВ",
            "СБ",
            "ИС",
            "СДР",
            "НА",
            "ЦД",
            "ДБ",
            "МОР",
            "К49",
            "РИМ",
            "МФ",
        }
        self.assertEqual(
            expected_shs_labels,
            {label for universe, label in initials if universe == "shs"},
        )
        self.assertIn(("lagerta", "ОНХ"), initials)
        self.assertIn(("lagerta", "ПН"), initials)
        self.assertNotIn(("lagerta", "ПРЗ"), initials)

        for universe, entries in universes.items():
            orders = [entry[3] for entry in entries]
            with self.subTest(universe=universe):
                self.assertEqual(sorted(orders), orders)

    def test_complete_shs_catalog_migration_contains_every_story(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "029_complete_shs_story_catalog.sql"
        )
        sql = path.read_text(encoding="utf-8")
        expected_keys = {
            "celestial_legend",
            "villains_last_wish",
            "age_of_fatum",
            "heart_of_atlanta",
            "bride_for_vampire",
            "deadly_biome",
            "illusion_glory",
            "ragnarok_dragon_saga",
            "legacy_of_almazar",
            "chains_of_agreement",
            "child_of_abyss",
            "morvain",
            "frame_49",
            "rome_temptation_of_wisdom",
            "mission_fortune",
        }
        for key in expected_keys:
            with self.subTest(key=key):
                self.assertIn(f"'shs', '{key}'", sql)

    def test_owner_picker_is_paginated_newest_first(self) -> None:
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
        stories = [
            CharacterStory(
                id=12 + index,
                universe="kr",
                key=f"story_{index}",
                short_label=f"И{index}",
                title=f"История {index}",
                sort_order=100 - index,
                release_order=100 - index,
                released_on=date(2026 - index, 1, 1),
                release_precision="year",
            )
            for index in range(7)
        ]
        story_page = StoryPage(
            items=stories,
            universe="kr",
            page=0,
            page_size=7,
            total_stories=58,
        )
        keyboard = build_story_picker(
            item,
            story_page,
            category="male",
            directory_page=3,
        )

        first = keyboard.inline_keyboard[0][0]
        self.assertIn("2026", first.text)
        self.assertIn("И0", first.text)
        callback = AdminStoryCallback.unpack(first.callback_data)
        self.assertEqual("set", callback.action)
        self.assertEqual(12, callback.story_id)
        self.assertEqual(3, callback.directory_page)

        next_button = next(
            button
            for row in keyboard.inline_keyboard
            for button in row
            if button.text == "Старее ▶️"
        )
        next_callback = AdminStoryCallback.unpack(next_button.callback_data)
        self.assertEqual("page", next_callback.action)
        self.assertEqual(1, next_callback.story_page)
        self.assertLessEqual(len(next_button.callback_data.encode("utf-8")), 64)

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

    def test_manager_callbacks_fit_telegram_limit(self) -> None:
        packed = manager_callback(
            "pstp",
            character_id=123456,
            offset=999,
            media_id=999999,
            page=99,
            universe="lagerta",
            story_id=9999,
        )
        self.assertLessEqual(len(packed.encode("utf-8")), 64)


if __name__ == "__main__":
    unittest.main()
