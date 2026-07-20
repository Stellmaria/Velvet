from __future__ import annotations

import os
import unittest
from pathlib import Path

from velvet_bot.database import Database
from velvet_bot.domains.media_rework import MediaReworkRepository


class MediaReworkContractTests(unittest.TestCase):
    def test_migration_defines_status_history_and_quality_trigger(self) -> None:
        migration = Path(
            "migrations/z001_unified_media_rework_queue.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS media_rework_items", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS media_rework_events", migration)
        self.assertIn("ready_for_review", migration)
        self.assertIn("sync_media_rework_from_quality", migration)
        self.assertIn("COALESCE(NEW.quality_score, 100) < 70", migration)
        self.assertIn("NEW.verdict = 'critical'", migration)
        self.assertIn("NEW.decision = 'fix_required'", migration)

    def test_telegram_entry_reuses_quality_router_without_new_child_router(self) -> None:
        bundle = Path(
            "velvet_bot/presentation/telegram/routers/quality_operations.py"
        ).read_text(encoding="utf-8")
        entry = Path(
            "velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_rework_entry.py"
        ).read_text(encoding="utf-8")
        controller = Path(
            "velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_rework.py"
        ).read_text(encoding="utf-8")
        self.assertIn("register_quality_rework_entry(router)", bundle)
        self.assertIn('Command("rework", "reworks", "quality_rework")', entry)
        self.assertIn("router.callback_query.register", controller)
        self.assertNotIn("@router.callback_query", controller)
        self.assertIn("Вернуть на проверку Qwen", controller)
        self.assertIn("✅ Принять", controller)
        self.assertIn("🗑 Снять", controller)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class MediaReworkIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                TRUNCATE media_rework_events,
                         media_rework_items,
                         media_ai_quality_checks,
                         media_files
                RESTART IDENTITY CASCADE
                """
            )
            self.media_id = int(
                await connection.fetchval(
                    """
                    INSERT INTO media_files (
                        telegram_file_id,
                        telegram_file_unique_id,
                        original_file_name,
                        storage_file_name,
                        media_type,
                        mime_type,
                        file_size
                    )
                    VALUES (
                        'rework-file',
                        'rework-unique',
                        'rework.png',
                        'rework-storage.png',
                        'document',
                        'image/png',
                        2048
                    )
                    RETURNING id
                    """
                )
            )

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def test_qwen_and_admin_decisions_share_one_rework_item(self) -> None:
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO media_ai_quality_checks (
                    media_id,
                    status,
                    verdict,
                    quality_score,
                    confidence,
                    report,
                    analyzed_at
                )
                VALUES (
                    $1::BIGINT,
                    'ready',
                    'critical',
                    42,
                    91,
                    '{"summary_ru":"Проблемы с руками."}'::JSONB,
                    NOW()
                )
                """,
                self.media_id,
            )
            row = await connection.fetchrow(
                """
                SELECT status, source, qwen_score
                FROM media_rework_items
                WHERE media_id = $1::BIGINT
                """,
                self.media_id,
            )
            self.assertEqual(("needs_fix", "qwen", 42), tuple(row))

            await connection.execute(
                """
                UPDATE media_ai_quality_checks
                SET decision = 'fix_required',
                    decided_by = 7221553045,
                    decided_at = NOW()
                WHERE media_id = $1::BIGINT
                """,
                self.media_id,
            )
            mixed = await connection.fetchrow(
                """
                SELECT status, source, requested_by
                FROM media_rework_items
                WHERE media_id = $1::BIGINT
                """,
                self.media_id,
            )
            self.assertEqual(
                ("needs_fix", "mixed", 7221553045),
                tuple(mixed),
            )

        repository = MediaReworkRepository(self.database)
        self.assertTrue(await repository.retry(self.media_id, 7221553045))
        async with self.database.acquire() as connection:
            checking = await connection.fetchrow(
                """
                SELECT r.status, q.status
                FROM media_rework_items AS r
                JOIN media_ai_quality_checks AS q ON q.media_id = r.media_id
                WHERE r.media_id = $1::BIGINT
                """,
                self.media_id,
            )
        self.assertEqual(("checking", "pending"), tuple(checking))

    async def test_good_recheck_waits_for_admin_acceptance(self) -> None:
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO media_rework_items (
                    media_id, status, source, reason
                )
                VALUES ($1::BIGINT, 'checking', 'admin', 'Проверить снова')
                """,
                self.media_id,
            )
            await connection.execute(
                """
                INSERT INTO media_ai_quality_checks (
                    media_id, status, verdict, quality_score, confidence, report
                )
                VALUES (
                    $1::BIGINT,
                    'ready',
                    'ready',
                    88,
                    90,
                    '{"summary_ru":"Критичных дефектов нет."}'::JSONB
                )
                """,
                self.media_id,
            )
            status = await connection.fetchval(
                """
                SELECT status
                FROM media_rework_items
                WHERE media_id = $1::BIGINT
                """,
                self.media_id,
            )
        self.assertEqual("ready_for_review", status)

        repository = MediaReworkRepository(self.database)
        self.assertTrue(await repository.accept(self.media_id, 7221553045))
        async with self.database.acquire() as connection:
            accepted = await connection.fetchrow(
                """
                SELECT r.status, q.decision
                FROM media_rework_items AS r
                JOIN media_ai_quality_checks AS q ON q.media_id = r.media_id
                WHERE r.media_id = $1::BIGINT
                """,
                self.media_id,
            )
        self.assertEqual(("accepted", "accepted"), tuple(accepted))


if __name__ == "__main__":
    unittest.main()
