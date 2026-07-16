import unittest

from velvet_bot.analytics_callbacks import dashboard_link, management_link
from velvet_bot.analytics_review import ReviewPage
from velvet_bot.handlers.analytics_management import (
    _ALIAS_REPLY_RE,
    _TYPE_BUTTON_LABELS,
    _short,
)
from velvet_bot.post_classification import POST_TYPE_LABELS


class AnalyticsPhaseTwoCallbackTests(unittest.TestCase):
    def test_management_callbacks_fit_telegram_limit(self) -> None:
        callbacks = [
            management_link(
                "ptype",
                period="30d",
                page=123,
                token_id=9_223_372_036,
                value="low|collaboration",
            ),
            management_link(
                "tagassign",
                period="all",
                page=42,
                token_id=9_999_999,
                character_id=8_888_888,
            ),
            management_link(
                "aliasdelok",
                period="7d",
                page=15,
                character_id=8_179_531_132,
                alias_id=7_777_777,
            ),
        ]
        for callback in callbacks:
            self.assertLessEqual(len(callback.encode("utf-8")), 64, callback)

    def test_dashboard_back_link_keeps_existing_schema(self) -> None:
        callback = dashboard_link(
            "discussion",
            period="30d",
            page=2,
            source_id=-1003802812639,
        )
        self.assertTrue(callback.startswith("dash:"))
        self.assertLessEqual(len(callback.encode("utf-8")), 64)

    def test_every_post_type_has_manual_button(self) -> None:
        self.assertEqual(set(POST_TYPE_LABELS), set(_TYPE_BUTTON_LABELS))

    def test_alias_reply_marker_parses_character_id(self) -> None:
        match = _ALIAS_REPLY_RE.search("ALIAS_CHARACTER:8179531132")
        self.assertIsNotNone(match)
        self.assertEqual("8179531132", match.group(1))

    def test_short_text_is_bounded(self) -> None:
        self.assertEqual("коротко", _short("коротко", 10))
        result = _short("очень длинный текст для кнопки Telegram", 18)
        self.assertLessEqual(len(result), 18)
        self.assertTrue(result.endswith("…"))

    def test_review_page_calculates_total_pages(self) -> None:
        page = ReviewPage(items=[], page=0, page_size=6, total_items=13)
        self.assertEqual(3, page.total_pages)


if __name__ == "__main__":
    unittest.main()
