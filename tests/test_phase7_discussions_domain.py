from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.discussions import DiscussionService


class DiscussionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_reaction_key_is_rejected_before_repository(self) -> None:
        repository = SimpleNamespace(apply_reaction_delta=AsyncMock())
        service = DiscussionService(repository)

        with self.assertRaisesRegex(ValueError, "Пустая реакция"):
            await service.apply_reaction_delta(
                discussion_chat_id=-1001,
                discussion_message_id=5,
                reaction_key="   ",
                delta=1,
            )

        repository.apply_reaction_delta.assert_not_awaited()

    async def test_zero_reaction_delta_is_ignored(self) -> None:
        repository = SimpleNamespace(apply_reaction_delta=AsyncMock())
        service = DiscussionService(repository)

        await service.apply_reaction_delta(
            discussion_chat_id=-1001,
            discussion_message_id=5,
            reaction_key="emoji:🔥",
            delta=0,
        )

        repository.apply_reaction_delta.assert_not_awaited()

    async def test_reaction_counts_are_delegated(self) -> None:
        repository = SimpleNamespace(set_reaction_counts=AsyncMock())
        service = DiscussionService(repository)

        await service.set_reaction_counts(
            discussion_chat_id=-1001,
            discussion_message_id=5,
            reaction_counts={"emoji:🔥": 4},
        )

        repository.set_reaction_counts.assert_awaited_once_with(
            discussion_chat_id=-1001,
            discussion_message_id=5,
            reaction_counts={"emoji:🔥": 4},
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
