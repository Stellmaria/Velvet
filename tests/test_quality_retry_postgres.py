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
                    media_ai_quality_queue_plans,
                    media_ai_quality_checks,
                    media_ai_profiles,
                    media_files,
                    characters
                RESTART IDENTITY CASCADE
                """
            )

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def test_quality_error_plan_never_resets_semantic_profile(self) -> None:
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
            await connection.execute(
                """
                INSERT INTO media_ai_quality_checks (
                    media_id,
                    status,
                    error_message,
                    attempt_count
                )
                VALUES ($1::BIGINT, 'skipped', 'quality failed', 1)
                """,
                media.media_id,
            )

        repository = QualityOperationsRepository(self.database)
        plan = await repository.plan_errors(requested_by=77, limit=10)

        self.assertEqual((media.media_id,), plan.media_ids)
        async with self.database._require_pool().acquire() as connection:
            before_start = await connection.fetchrow(
                """
                SELECT status, queue_plan_id
                FROM media_ai_quality_checks
                WHERE media_id = $1::BIGINT
                """,
                media.media_id,
            )
        self.assertEqual("skipped", before_start["status"])
        self.assertIsNone(before_start["queue_plan_id"])

        started = await repository.start_plan(plan.plan_id, requested_by=77)
        self.assertEqual(1, started)

        async with self.database._require_pool().acquire() as connection:
            semantic = await connection.fetchrow(
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
            quality = await connection.fetchrow(
                """
                SELECT status, attempt_count, queue_plan_id, error_message
                FROM media_ai_quality_checks
                WHERE media_id = $1::BIGINT
                """,
                media.media_id,
            )

        self.assertEqual("error", semantic["status"])
        self.assertEqual('{"summary": "stale"}', semantic["analysis_text"])
        self.assertEqual("stale semantic text", semantic["semantic_text"])
        self.assertEqual("provider failed", semantic["error_message"])
        self.assertEqual(4, semantic["attempt_count"])
        self.assertIsNotNone(semantic["analyzed_at"])

        self.assertEqual("pending", quality["status"])
        self.assertEqual(0, quality["attempt_count"])
        self.assertEqual(plan.plan_id, quality["queue_plan_id"])
        self.assertIsNone(quality["error_message"])


if __name__ == "__main__":
    unittest.main()
