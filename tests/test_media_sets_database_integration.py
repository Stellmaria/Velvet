from __future__ import annotations

import os
import unittest

from velvet_bot.database import Database
from velvet_bot.domains.archive.repository import ArchiveRepository
from velvet_bot.media import MediaDescriptor
from velvet_bot.media_set_actions import create_media_set
from velvet_bot.media_sets import (
    discover_media_set_candidates,
    list_media_set_candidates,
)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class MediaSetsPostgreSQLTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database._require_pool().acquire() as connection:
            await connection.execute(
                """
                TRUNCATE
                    media_set_candidate_items,
                    media_set_candidates,
                    media_sets,
                    media_files,
                    characters
                RESTART IDENTITY CASCADE
                """
            )

    async def asyncTearDown(self) -> None:
        await self.database.close()

    @staticmethod
    def descriptor(number: int, character: str) -> MediaDescriptor:
        return MediaDescriptor(
            telegram_file_id=f"telegram-file-{number}",
            telegram_file_unique_id=f"unique-file-{number}",
            original_file_name=f"wild-west-{character}.jpg",
            storage_file_name=f"wild-west-{character}__{number:024x}.jpg",
            media_type="photo",
            mime_type="image/jpeg",
            file_size=1024,
        )

    async def test_shared_prompt_creates_set_and_stays_synchronized(self) -> None:
        ada, _ = await self.database.create_character(
            "Ада",
            created_by=1,
            created_in_chat=1,
        )
        eric, _ = await self.database.create_character(
            "Эрик",
            created_by=1,
            created_in_chat=1,
        )
        first = await self.database.save_character_media(
            ada,
            self.descriptor(1, "ada"),
            saved_by=1,
            saved_in_chat=1,
            source_chat_id=1,
            source_message_id=101,
            source_thread_id=None,
            command_message_id=201,
        )
        second = await self.database.save_character_media(
            eric,
            self.descriptor(2, "eric"),
            saved_by=1,
            saved_in_chat=1,
            source_chat_id=1,
            source_message_id=102,
            source_thread_id=None,
            command_message_id=202,
        )

        archive = ArchiveRepository(self.database)
        prompt_url = "https://t.me/velvet/100"
        self.assertTrue(
            await archive.set_prompt(
                character_id=ada.id,
                media_id=first.media_id,
                prompt_post_url=prompt_url,
            )
        )
        self.assertTrue(
            await archive.set_prompt(
                character_id=eric.id,
                media_id=second.media_id,
                prompt_post_url=prompt_url,
            )
        )

        created_candidates = await discover_media_set_candidates(self.database)
        self.assertEqual(1, created_candidates)
        page = await list_media_set_candidates(self.database)
        self.assertEqual(1, page.total_items)
        candidate = page.items[0]
        self.assertEqual(2, candidate.selected_count)
        self.assertEqual(prompt_url, candidate.prompt_post_url)

        created_set = await create_media_set(
            self.database,
            candidate_id=candidate.id,
            created_by=1,
        )
        self.assertEqual(
            {first.media_id, second.media_id},
            set(created_set.media_ids),
        )

        first_page = await archive.get_page(character_id=ada.id, offset=0)
        second_page = await archive.get_page(character_id=eric.id, offset=0)
        self.assertIsNotNone(first_page)
        self.assertIsNotNone(second_page)
        self.assertIsNotNone(first_page.media)
        self.assertIsNotNone(second_page.media)
        self.assertEqual(created_set.id, first_page.media.media_set_id)
        self.assertEqual(created_set.id, second_page.media.media_set_id)
        self.assertEqual(created_set.title, first_page.media.media_set_title)
        self.assertEqual(prompt_url, first_page.media.prompt_post_url)
        self.assertEqual(prompt_url, second_page.media.prompt_post_url)

        replacement_url = "https://t.me/velvet/200"
        self.assertTrue(
            await archive.set_prompt(
                character_id=ada.id,
                media_id=first.media_id,
                prompt_post_url=replacement_url,
            )
        )
        first_page = await archive.get_page(character_id=ada.id, offset=0)
        second_page = await archive.get_page(character_id=eric.id, offset=0)
        async with self.database._require_pool().acquire() as connection:
            set_prompt = await connection.fetchval(
                "SELECT prompt_post_url FROM media_sets WHERE id = $1::BIGINT",
                created_set.id,
            )
        self.assertEqual(replacement_url, set_prompt)
        self.assertEqual(replacement_url, first_page.media.prompt_post_url)
        self.assertEqual(replacement_url, second_page.media.prompt_post_url)

        self.assertTrue(
            await archive.set_prompt(
                character_id=eric.id,
                media_id=second.media_id,
                prompt_post_url=None,
            )
        )
        first_page = await archive.get_page(character_id=ada.id, offset=0)
        second_page = await archive.get_page(character_id=eric.id, offset=0)
        self.assertIsNone(first_page.media.prompt_post_url)
        self.assertIsNone(second_page.media.prompt_post_url)


if __name__ == "__main__":
    unittest.main()
