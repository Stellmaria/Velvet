from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.discussions import DiscussionService
from velvet_bot.presentation.telegram.analytics_navigation import (
    AnalyticsCallback,
    _cb,
    _period_row,
)


ROOT = Path(__file__).resolve().parents[1]


class DiscussionNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_parent_channel_lookup_is_delegated(self) -> None:
        repository = SimpleNamespace(
            get_parent_channel_id=AsyncMock(return_value=-1003802812639)
        )
        service = DiscussionService(repository)

        result = await service.get_parent_channel_id(-1003859952761)

        self.assertEqual(result, -1003802812639)
        repository.get_parent_channel_id.assert_awaited_once_with(-1003859952761)

    def test_navigation_contract_is_shared(self) -> None:
        packed = _cb("menu", period="30d", page=-1, source_id=-1001)
        unpacked = AnalyticsCallback.unpack(packed)
        self.assertEqual(unpacked.period, "30d")
        self.assertEqual(unpacked.page, 0)
        self.assertEqual(len(_period_row("menu", "30d")), 3)
        self.assertLessEqual(len(packed.encode("utf-8")), 64)

    def test_discussion_handler_has_no_handler_import_or_sql(self) -> None:
        source = (
            ROOT / "velvet_bot/handlers/analytics_discussion_overrides.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("from velvet_bot.handlers.analytics_dashboard", source)
        self.assertNotIn("database._require_pool()", source)
        self.assertNotIn("SELECT parent_channel_id", source)


if __name__ == "__main__":
    unittest.main()
