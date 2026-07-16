import unittest

from velvet_bot.handlers.admin_stories import AdminStoryCallback
from velvet_bot.public_manager_ui import manager_callback


class MultiStoryKrTests(unittest.TestCase):
    def test_admin_multi_story_callback_fits_telegram_limit(self) -> None:
        payload = AdminStoryCallback(
            action="mtoggle",
            category="female",
            directory_page=123,
            story_page=456,
            character_id=987654321,
            story_id=123456789,
        ).pack()
        self.assertLessEqual(len(payload.encode("utf-8")), 64)

    def test_public_multi_story_callback_fits_telegram_limit(self) -> None:
        payload = manager_callback(
            "pmst",
            character_id=987654321,
            offset=123,
            media_id=456789,
            page=12,
            story_id=123456789,
        )
        self.assertLessEqual(len(payload.encode("utf-8")), 64)

    def test_multi_story_actions_are_distinct(self) -> None:
        actions = {"mtoggle", "mpage", "mclear", "mdone", "mnoop"}
        self.assertEqual(5, len(actions))


if __name__ == "__main__":
    unittest.main()
