from __future__ import annotations

import os
import unittest

from velvet_bot.database import Database
from velvet_bot.media import MediaDescriptor
from velvet_bot.quality_operations import QualityOperationsRepository


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class QualityRetryPostgreSQLTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database._require_pool().acquire() as connection:
            await connection.execute(
                """
                TRUNCATE
                    media_ai_quality_checks,
                    media_ai_profiles,
                    media_files,
                    characters
                RESTART IDENTITY CASCADE
                """
            )

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def test_retry_resets_not_null_analysis_to_empty_json(self) -> None:
        character_id, _ = await self.database.create_character(
            "Retry test",
            created_by=1,
            created_in_chat=1,
        )
        media = await self.database.save_character_media(
            character_id,
            MediaDescriptor(
                telegram_file_id="retry-file",
                telegram_file_unique_id="retry-unique",
                original_file_name="retry.jpg",
                storage_file_name="retry.jpg",
                media_type="photo",
                mime_type="image/jpeg",
                file_size=1024,
            ),
            saved_by=1,
            saved_in_chat=1,
            source_chat_id=1,
            source_message_id=1,
            source_thread_id=None,
            command_message_id=2,
        )

        async with self.database._require_pool().acquire() as connection:
            await connection.execute(
                """
                INSERT INTO media_ai_profiles (
                    media_id,
                    status,
                    analysis,
                    semantic_text,
                    error_message,
                    attempt_count,
                    analyzed_at
                )
                VALUES (
                    $1::BIGINT,
                    'error',
                    '{"summary":"stale"}'::JSONB,
                    'stale semantic text',
                    'provider failed',
                    4,
                    NOW()
                )
                """,
                media.media_id,
            )

        count = await QualityOperationsRepository(self.database).retry_errors()

        async with self.database._require_pool().acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    status,
                    analysis::TEXT AS analysis_text,
                    semantic_text,
                    error_message,
                    attempt_count,
                    analyzed_at
                FROM media_ai_profiles
                WHERE media_id = $1::BIGINT
                """,
                media.media_id,
            )

        self.assertEqual(1, count)
        self.assertIsNotNone(row)
        self.assertEqual("pending", row["status"])
        self.assertEqual("{}", row["analysis_text"])
        self.assertIsNone(row["semantic_text"])
        self.assertIsNone(row["error_message"])
        self.assertEqual(0, row["attempt_count"])
        self.assertIsNone(row["analyzed_at"])


if __name__ == "__main__":
    unittest.main()
