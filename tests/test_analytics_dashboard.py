import unittest

from velvet_bot.analytics_dashboard import DashboardPage, DashboardRankItem, normalize_period
from velvet_bot.handlers.analytics_dashboard import (
    AnalyticsCallback,
    _main_keyboard,
    _page_keyboard,
)


class AnalyticsDashboardTests(unittest.TestCase):
    def test_period_is_normalized(self) -> None:
        self.assertEqual("7d", normalize_period("7d"))
        self.assertEqual("30d", normalize_period("30d"))
        self.assertEqual("all", normalize_period("something"))

    def test_main_keyboard_contains_requested_sections(self) -> None:
        keyboard = _main_keyboard("30d")
        labels = [
            button.text
            for row in keyboard.inline_keyboard
            for button in row
        ]
        self.assertIn("📊 Обзор канала", labels)
        self.assertIn("📝 Промты", labels)
        self.assertIn("👥 Персонажи", labels)
        self.assertIn("#️⃣ Хэштеги", labels)
        self.assertIn("🏷 Типы постов", labels)
        self.assertIn("❓ Не распознано", labels)
        self.assertIn("💬 Обсуждения", labels)

    def test_discussion_callback_fits_telegram_limit(self) -> None:
        packed = AnalyticsCallback(
            action="participants",
            period="30d",
            page=999,
            source_id=-1003802812639,
        ).pack()
        self.assertLessEqual(len(packed.encode("utf-8")), 64)
        unpacked = AnalyticsCallback.unpack(packed)
        self.assertEqual(-1003802812639, unpacked.source_id)
        self.assertEqual("participants", unpacked.action)

    def test_rank_keyboard_has_pagination(self) -> None:
        page = DashboardPage(
            items=[DashboardRankItem("a", "Аид", 10, 8)],
            page=1,
            page_size=8,
            total_items=30,
        )
        keyboard = _page_keyboard("characters", "all", page)
        labels = [
            button.text
            for row in keyboard.inline_keyboard
            for button in row
        ]
        self.assertIn("2 / 4", labels)
        self.assertIn("◀️", labels)
        self.assertIn("▶️", labels)


if __name__ == "__main__":
    unittest.main()
