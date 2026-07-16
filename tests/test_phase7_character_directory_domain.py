from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.characters import (
    CharacterDirectoryService,
    normalize_category,
    normalize_universe,
)


class CharacterDirectoryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_directory_filter_is_rejected_before_repository(self) -> None:
        repository = SimpleNamespace(list_directory=AsyncMock())
        service = CharacterDirectoryService(repository)

        with self.assertRaisesRegex(ValueError, "Неизвестная категория"):
            await service.list_directory(
                category="mystery",
                public_only=True,
            )

        repository.list_directory.assert_not_awaited()

    async def test_story_filter_requires_universe(self) -> None:
        repository = SimpleNamespace(list_directory=AsyncMock())
        service = CharacterDirectoryService(repository)

        with self.assertRaisesRegex(ValueError, "сначала нужна вселенная"):
            await service.list_directory(
                category="male",
                public_only=True,
                story_id=7,
            )

    async def test_text_category_is_normalized_before_persistence(self) -> None:
        repository = SimpleNamespace(set_category=AsyncMock())
        service = CharacterDirectoryService(repository)

        result = await service.set_category_from_text(
            character_id=12,
            value="МУЖСКОЙ",
        )

        self.assertEqual(result, "male")
        repository.set_category.assert_awaited_once_with(
            character_id=12,
            category="male",
        )

    async def test_unassigned_universe_is_stored_as_null(self) -> None:
        repository = SimpleNamespace(set_universe=AsyncMock())
        service = CharacterDirectoryService(repository)

        result = await service.set_universe_from_text(
            character_id=12,
            value="без",
            allow_unassigned=True,
        )

        self.assertIsNone(result)
        repository.set_universe.assert_awaited_once_with(
            character_id=12,
            universe=None,
        )


class CharacterCatalogTests(unittest.TestCase):
    def test_catalog_normalization_is_domain_owned(self) -> None:
        self.assertEqual(normalize_category("мжм"), "mfm")
        self.assertEqual(normalize_universe("BG3"), "bg3")


if __name__ == "__main__":
    unittest.main()
