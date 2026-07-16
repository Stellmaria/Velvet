from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.stories import (
    StoryService,
    clean_story_short_label,
    format_story_release,
    make_story_key,
)


class StoryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_universe_is_rejected_before_repository(self) -> None:
        repository = SimpleNamespace(list=AsyncMock())
        service = StoryService(repository)

        with self.assertRaisesRegex(ValueError, "Неизвестная вселенная"):
            await service.list(universe="unknown")

        repository.list.assert_not_awaited()

    async def test_create_normalizes_fields_and_unknown_date(self) -> None:
        repository = SimpleNamespace(create=AsyncMock(return_value="story"))
        service = StoryService(repository)

        result = await service.create(
            universe="kr",
            short_label=" тс 2 ",
            title="  Тени   Сентфора 2 ",
            released_on=None,
            release_precision="year",
        )

        self.assertEqual(result, "story")
        repository.create.assert_awaited_once_with(
            universe="kr",
            key="тс2",
            short_label="ТС2",
            title="Тени Сентфора 2",
            released_on=None,
            release_precision="unknown",
        )

    async def test_character_assignment_is_delegated(self) -> None:
        repository = SimpleNamespace(set_character_story=AsyncMock())
        service = StoryService(repository)

        await service.set_character_story(character_id=5, story_id=12)

        repository.set_character_story.assert_awaited_once_with(
            character_id=5,
            story_id=12,
        )

    async def test_find_empty_value_does_not_query_repository(self) -> None:
        repository = SimpleNamespace(find=AsyncMock())
        service = StoryService(repository)

        result = await service.find(universe="kr", value="   ")

        self.assertIsNone(result)
        repository.find.assert_not_awaited()


class StoryCatalogRuleTests(unittest.TestCase):
    def test_rules_are_domain_owned(self) -> None:
        self.assertEqual(clean_story_short_label(" снр "), "СНР")
        self.assertEqual(make_story_key("СНР"), "снр")
        self.assertEqual(
            format_story_release(date(2026, 7, 1), "month"),
            "07.2026",
        )


if __name__ == "__main__":
    unittest.main()
