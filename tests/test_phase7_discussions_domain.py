from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.discussions import DiscussionService


class DiscussionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_reaction_delta_is_ignored(self) -> None:
        repository = SimpleNamespace(apply_reaction_delta=AsyncMock())
        service = DiscussionService(repository)

        result = await service.apply_reaction_delta(
            discussion_chat_id=-1001,
            discussion_message_id=5,
            delta={"   ": 1, "emoji:🔥": 0},
        )

        self.assertFalse(result)
        repository.apply_reaction_delta.assert_not_awaited()

    async def test_reaction_delta_is_normalized_and_delegated(self) -> None:
        repository = SimpleNamespace(apply_reaction_delta=AsyncMock(return_value=True))
        service = DiscussionService(repository)

        result = await service.apply_reaction_delta(
            discussion_chat_id=-1001,
            discussion_message_id=5,
            delta={" emoji:🔥 ": 1, "emoji:👍": -1},
        )

        self.assertTrue(result)
        repository.apply_reaction_delta.assert_awaited_once_with(
            discussion_chat_id=-1001,
            discussion_message_id=5,
            delta={"emoji:🔥": 1, "emoji:👍": -1},
        )

    async def test_reaction_counts_are_delegated(self) -> None:
        repository = SimpleNamespace(set_reaction_counts=AsyncMock(return_value=True))
        service = DiscussionService(repository)

        result = await service.set_reaction_counts(
            discussion_chat_id=-1001,
            discussion_message_id=5,
            reaction_breakdown={"emoji:🔥": 4},
        )

        self.assertTrue(result)
        repository.set_reaction_counts.assert_awaited_once_with(
            discussion_chat_id=-1001,
            discussion_message_id=5,
            reaction_breakdown={"emoji:🔥": 4},
        )

    async def test_reports_are_delegated(self) -> None:
        repository = SimpleNamespace(
            get_overview=AsyncMock(return_value="overview"),
            list_participant_stats=AsyncMock(return_value=["participant"]),
        )
        service = DiscussionService(repository)

        self.assertEqual(await service.get_overview(-1001), "overview")
        self.assertEqual(
            await service.list_participant_stats(-1001, limit=25),
            ["participant"],
        )
        repository.get_overview.assert_awaited_once_with(-1001)
        repository.list_participant_stats.assert_awaited_once_with(
            -1001,
            limit=25,
        )


if __name__ == "__main__":
    unittest.main()
