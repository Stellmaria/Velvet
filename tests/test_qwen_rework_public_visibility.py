from __future__ import annotations

import os
import unittest
from pathlib import Path

from velvet_bot.database import Database
from velvet_bot.domains.archive import ArchiveRepository
from velvet_bot.domains.media_rework import MediaReworkRepository
from velvet_bot.domains.public_archive import PublicArchiveRepository
from velvet_bot.domains.public_archive.visibility import public_media_visibility_sql
from velvet_bot.media import MediaDescriptor


class QwenReworkVisibilityContractTests(unittest.TestCase):
    def test_active_rework_is_part_of_public_visibility_predicate(self) -> None:
        public_sql = public_media_visibility_sql()
        manager_sql = public_media_visibility_sql(include_active_rework=True)

        self.assertIn("NOT EXISTS", public_sql)
        self.assertIn("media_rework_items", public_sql)
        for status in ("needs_fix", "checking", "ready_for_review"):
            self.assertIn(status, public_sql)
        self.assertNotIn("media_rework_items", manager_sql)

    def test_direct_public_download_reuses_shared_visibility_rule(self) -> None:
        source = Path(
            "velvet_bot/domains/public_archive/repository.py"
        ).read_text(encoding="utf-8")
        method = source.split("async def resolve_download_source", maxsplit=1)[1]
        method = method.split("async def record_download", maxsplit=1)[0]

        self.assertIn("public_media_visibility_sql", method)
        self.assertIn("visibility_sql", method)
        self.assertNotIn("AND cm.is_public = TRUE", method)

    def test_stel_items_are_ordered_before_qwen_only_items(self) -> None:
        source = Path(
            "velvet_bot/domains/media_rework/repository.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "CASE WHEN r.source IN ('admin', 'mixed') THEN 1 ELSE 0 END DESC",
            source,
        )
        self.assertIn("AS stel_priority", source)
        self.assertIn("AS qwen_only", source)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class QwenReworkVisibilityIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                TRUNCATE media_rework_events,
                         media_rework_items,
                         media_ai_quality_checks,
                         character_media,
                         media_files,
                         characters
                RESTART IDENTITY CASCADE
                """
            )

        self.character, _ = await self.database.create_character(
            "Qwen Visibility Test",
            created_by=7221553045,
            created_in_chat=7221553045,
        )
        saved = await self.database.save_character_media(
            self.character,
            MediaDescriptor(
                telegram_file_id="qwen-public-file",
                telegram_file_unique_id="qwen-public-unique",
                original_file_name="qwen-public.png",
                storage_file_name="qwen-public-storage.png",
                media_type="document",
                mime_type="image/png",
                file_size=2048,
            ),
            saved_by=7221553045,
            saved_in_chat=7221553045,
            source_chat_id=7221553045,
            source_message_id=101,
            source_thread_id=None,
            command_message_id=100,
        )
        self.media_id = saved.media_id

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def test_manual_rework_hides_public_but_not_manager_and_restores_after_accept(self) -> None:
        archive = ArchiveRepository(self.database)
        public = PublicArchiveRepository(self.database)
        rework = MediaReworkRepository(self.database)

        initial = await archive.get_page(
            character_id=self.character.id,
            offset=0,
            public_only=True,
            include_adult_restricted=True,
            include_oversized_images=True,
        )
        self.assertIsNotNone(initial)
        self.assertIsNotNone(initial.media)
        self.assertIsNotNone(
            await public.resolve_download_source(
                character_id=self.character.id,
                media_id=self.media_id,
                member_access=True,
            )
        )

        async with self.database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO media_rework_items (
                    media_id,
                    status,
                    source,
                    reason,
                    requested_by,
                    last_action_by
                )
                VALUES (
                    $1::BIGINT,
                    'needs_fix',
                    'admin',
                    'Стэл отправила на доработку',
                    7221553045,
                    7221553045
                )
                """,
                self.media_id,
            )

        hidden = await archive.get_page(
            character_id=self.character.id,
            offset=0,
            public_only=True,
            include_adult_restricted=True,
            include_oversized_images=True,
        )
        manager = await archive.get_page(
            character_id=self.character.id,
            offset=0,
            public_only=False,
            include_adult_restricted=True,
            include_oversized_images=True,
        )
        self.assertIsNotNone(hidden)
        self.assertIsNone(hidden.media)
        self.assertIsNotNone(manager)
        self.assertIsNotNone(manager.media)
        self.assertIsNone(
            await public.resolve_download_source(
                character_id=self.character.id,
                media_id=self.media_id,
                member_access=True,
            )
        )

        self.assertTrue(await rework.accept(self.media_id, 7221553045))

        restored = await archive.get_page(
            character_id=self.character.id,
            offset=0,
            public_only=True,
            include_adult_restricted=True,
            include_oversized_images=True,
        )
        self.assertIsNotNone(restored)
        self.assertIsNotNone(restored.media)
        self.assertIsNotNone(
            await public.resolve_download_source(
                character_id=self.character.id,
                media_id=self.media_id,
                member_access=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
