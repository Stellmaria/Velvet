from __future__ import annotations

import os
import unittest

from velvet_bot.ai_jobs import AIJobRepository
from velvet_bot.database import Database


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class AIJobPostgreSQLTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database.acquire() as connection:
            await connection.execute("TRUNCATE ai_jobs RESTART IDENTITY")
        self.repository = AIJobRepository(self.database)

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def test_job_lifecycle_and_owner_history(self) -> None:
        job_id = await self.repository.create(
            kind="prompt_result",
            title="Промт против результата",
            provider="ollama",
            model="qwen3-vl:8b",
            request_payload={"file_id": "telegram-file"},
            created_by=1001,
        )
        created = await self.repository.get(job_id, created_by=1001)
        self.assertIsNotNone(created)
        self.assertEqual("pending", created.status)
        self.assertEqual("queued", created.stage)
        self.assertIsNone(await self.repository.get(job_id, created_by=1002))

        self.assertTrue(await self.repository.mark_stage(job_id, "analyzing"))
        processing = await self.repository.get(job_id, created_by=1001)
        self.assertEqual("processing", processing.status)
        self.assertEqual("analyzing", processing.stage)
        self.assertIsNotNone(processing.started_at)

        self.assertTrue(
            await self.repository.mark_ready(
                job_id,
                result_text="<b>Готовый отчёт</b>",
                result_payload={"overall_score": 91},
                reference_type="prompt_result_report",
                reference_id=77,
            )
        )
        ready = await self.repository.get(job_id, created_by=1001)
        self.assertEqual("ready", ready.status)
        self.assertEqual("completed", ready.stage)
        self.assertEqual("<b>Готовый отчёт</b>", ready.result_text)
        self.assertEqual(91, ready.result_payload["overall_score"])
        self.assertEqual(77, ready.result_reference_id)
        self.assertIsNotNone(ready.finished_at)

        page = await self.repository.list_recent(created_by=1001)
        self.assertEqual(1, page.total_items)
        self.assertEqual(job_id, page.items[0].id)

    async def test_error_and_stale_job_are_visible(self) -> None:
        error_id = await self.repository.create(
            kind="palette_composition",
            title="Палитра",
            provider="ollama",
            model="qwen3-vl:8b",
            request_payload={},
            created_by=1001,
        )
        self.assertTrue(await self.repository.mark_error(error_id, "provider unavailable"))
        failed = await self.repository.get(error_id, created_by=1001)
        self.assertEqual("error", failed.status)
        self.assertEqual("failed", failed.stage)
        self.assertIn("provider unavailable", failed.error_message)

        stale_id = await self.repository.create(
            kind="velvet_formatting",
            title="Оформление",
            provider="ollama",
            model="qwen3-vl:8b",
            request_payload={},
            created_by=1001,
        )
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                UPDATE ai_jobs
                SET status = 'processing',
                    stage = 'analyzing',
                    updated_at = NOW() - INTERVAL '2 hours'
                WHERE id = $1::BIGINT
                """,
                stale_id,
            )
        expired = await self.repository.get(stale_id, created_by=1001)
        self.assertEqual("error", expired.status)
        self.assertEqual("interrupted", expired.stage)
        self.assertIn("прервано", expired.error_message)


if __name__ == "__main__":
    unittest.main()
