from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.discussions import DiscussionInsightService


class DiscussionInsightServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_period_delegates_without_lower_bound(self) -> None:
        repository = SimpleNamespace(get_summary=AsyncMock(return_value="summary"))
        service = DiscussionInsightService(repository)

        result = await service.get_summary(
            discussion_chat_id=-1003859952761,
            parent_channel_id=-1003802812639,
            period="all",
        )

        self.assertEqual("summary", result)
        repository.get_summary.assert_awaited_once_with(
            discussion_chat_id=-1003859952761,
            parent_channel_id=-1003802812639,
            since=None,
        )


if __name__ == "__main__":
    unittest.main()
