import os
import unittest

from velvet_bot.database import Database, normalize_character_name


class CharacterNameTests(unittest.TestCase):
    def test_character_name_is_case_insensitive(self) -> None:
        self.assertEqual(
            normalize_character_name("Каин"),
            normalize_character_name("  КАИН  "),
        )


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database._require_pool().acquire() as connection:
            await connection.execute(
                "TRUNCATE character_media, media_files, characters "
                "RESTART IDENTITY CASCADE"
            )

    async def asyncTearDown(self) -> None:
        await self.database.close()

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

    async def test_character_can_be_found_by_archive_topic(self) -> None:
        character, _ = await self.database.create_character(
            "Аид",
            created_by=1,
            created_in_chat=2,
        )
        bound = await self.database.bind_character_topic(
            character.id,
            archive_chat_id=-1003951213065,
            archive_thread_id=1398,
            archive_topic_url="https://t.me/c/3951213065/1398",
        )

        found = await self.database.get_character_by_archive_topic(
            -1003951213065,
            1398,
        )

        self.assertEqual(character.id, bound.id)
        self.assertIsNotNone(found)
        self.assertEqual(character.id, found.id)
        self.assertEqual(1398, found.archive_thread_id)
