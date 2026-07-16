from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.public_archive import PublicArchiveService


class PublicArchiveServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_filters_are_always_public(self) -> None:
        characters = SimpleNamespace(
            list_category_summaries=AsyncMock(return_value=("category",)),
            list_universe_summaries=AsyncMock(return_value=("universe",)),
            list_directory=AsyncMock(return_value="page"),
        )
        stories = SimpleNamespace(list_summaries=AsyncMock(return_value=["story"]))
        service = PublicArchiveService(
            repository=SimpleNamespace(),
            characters=characters,
            stories=stories,
        )

        self.assertEqual(await service.list_categories(), ["category"])
        self.assertEqual(await service.list_universes(category="male"), ["universe"])
        self.assertEqual(
            await service.list_stories(category="male", universe="kr"),
            ["story"],
        )
        self.assertEqual(
            await service.list_characters(category="male", universe="kr"),
            "page",
        )
        characters.list_category_summaries.assert_awaited_once_with(public_only=True)
        characters.list_universe_summaries.assert_awaited_once_with(
            category="male", public_only=True
        )
        stories.list_summaries.assert_awaited_once_with(
            category="male", universe="kr", public_only=True
        )

    async def test_like_and_delivery_are_delegated(self) -> None:
        repository = SimpleNamespace(
            toggle_like=AsyncMock(return_value="like-result"),
            mark_notification_delivered=AsyncMock(return_value=True),
        )
        service = PublicArchiveService(
            repository=repository,
            characters=SimpleNamespace(),
            stories=SimpleNamespace(),
        )
        self.assertEqual(
            await service.toggle_like(character_id=1, media_id=2, user_id=3),
            "like-result",
        )
        notice = SimpleNamespace(character_id=1, media_id=2, user_id=3)
        self.assertTrue(await service.mark_notification_delivered(notice))


if __name__ == "__main__":
    unittest.main()
