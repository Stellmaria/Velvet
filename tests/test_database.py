import os
import unittest

from velvet_bot.archive_catalog import get_archive_page
from velvet_bot.database import Database, normalize_character_name
from velvet_bot.media import MediaDescriptor


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

    async def test_archive_page_returns_newest_media_and_wraps_offset(self) -> None:
        character, _ = await self.database.create_character(
            "Аид",
            created_by=1,
            created_in_chat=2,
        )

        first_media = MediaDescriptor(
            telegram_file_id="first-file-id",
            telegram_file_unique_id="first-unique-id",
            original_file_name="first.png",
            storage_file_name="first__hash.png",
            media_type="document",
            mime_type="image/png",
            file_size=100,
        )
        second_media = MediaDescriptor(
            telegram_file_id="second-file-id",
            telegram_file_unique_id="second-unique-id",
            original_file_name="second.png",
            storage_file_name="second__hash.png",
            media_type="document",
            mime_type="image/png",
            file_size=200,
        )

        await self.database.save_character_media(
            character,
            first_media,
            saved_by=1,
            saved_in_chat=2,
            source_chat_id=2,
            source_message_id=10,
            source_thread_id=None,
            command_message_id=11,
        )
        await self.database.save_character_media(
            character,
            second_media,
            saved_by=1,
            saved_in_chat=2,
            source_chat_id=2,
            source_message_id=20,
            source_thread_id=None,
            command_message_id=21,
        )

        newest = await get_archive_page(self.database, character.id, 0)
        older = await get_archive_page(self.database, character.id, 1)
        wrapped = await get_archive_page(self.database, character.id, 2)

        self.assertIsNotNone(newest)
        self.assertIsNotNone(older)
        self.assertIsNotNone(wrapped)
        self.assertEqual(2, newest.total)
        self.assertEqual("second.png", newest.media.original_file_name)
        self.assertEqual("first.png", older.media.original_file_name)
        self.assertEqual("second.png", wrapped.media.original_file_name)
