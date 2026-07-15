import tempfile
import unittest
from pathlib import Path

from velvet_bot.database import Database


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_directory.name) / "velvet.db")
        await self.database.initialize()

    async def asyncTearDown(self) -> None:
        self.temp_directory.cleanup()

    async def test_duplicate_character_names_are_not_created(self) -> None:
        first, first_created = await self.database.create_character(
            "Каин",
            created_by=1,
            created_in_chat=2,
        )
        second, second_created = await self.database.create_character(
            "  КАИН  ",
            created_by=3,
            created_in_chat=4,
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.id, second.id)
        self.assertEqual("Каин", second.name)

    async def test_list_characters_returns_saved_profiles(self) -> None:
        await self.database.create_character(
            "Каин",
            created_by=None,
            created_in_chat=None,
        )
        await self.database.create_character(
            "Эрик",
            created_by=None,
            created_in_chat=None,
        )

        characters = await self.database.list_characters()

        self.assertEqual(["Каин", "Эрик"], [item.name for item in characters])
