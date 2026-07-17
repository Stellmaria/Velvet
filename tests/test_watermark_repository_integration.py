from __future__ import annotations

import os
import unittest

from velvet_bot.database import Database
from velvet_bot.domains.watermark.models import WatermarkSettings
from velvet_bot.domains.watermark.repository import WatermarkRepository


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class WatermarkRepositoryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database.acquire() as connection:
            await connection.execute(
                "TRUNCATE watermark_revisions, watermark_jobs RESTART IDENTITY CASCADE"
            )
        self.repository = WatermarkRepository(self.database)

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def test_revisions_undo_ready_and_approve_use_real_schema(self) -> None:
        first = await self.repository.create_job(
            owner_user_id=10,
            chat_id=20,
            source_message_id=30,
            source_file_id="telegram-file",
            source_file_unique_id="telegram-unique",
            source_path="/bridge/sources/source.png",
            settings=WatermarkSettings(),
        )
        self.assertEqual((1, "bottom_right", "pending"), (
            first.revision.revision,
            first.revision.settings.position,
            first.revision.status,
        ))

        second = await self.repository.create_revision(
            first.job.id,
            settings=WatermarkSettings(
                position="top_left",
                color="#d8c8b8",
                opacity=55,
                size=18.0,
                margin=5.0,
            ),
        )
        self.assertEqual((2, "top_left", "#d8c8b8"), (
            second.revision.revision,
            second.revision.settings.position,
            second.revision.settings.color,
        ))

        undone = await self.repository.undo(first.job.id)
        self.assertEqual((3, "bottom_right", "#ffffff"), (
            undone.revision.revision,
            undone.revision.settings.position,
            undone.revision.settings.color,
        ))

        await self.repository.set_dispatched_paths(
            job_id=first.job.id,
            revision=undone.revision.revision,
            request_path="/bridge/requests/job.json",
            output_path="/bridge/outputs/job.png",
            response_path="/bridge/responses/job.json",
        )
        self.assertTrue(
            await self.repository.mark_ready(
                job_id=first.job.id,
                revision=undone.revision.revision,
                telegram_preview_file_id="preview-file",
            )
        )
        approved = await self.repository.approve(first.job.id)
        self.assertEqual("approved", approved.job.status)
        self.assertEqual("/bridge/outputs/job.png", approved.job.final_path)

        current = await self.repository.get_current(first.job.id)
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(3, current.revision.revision)
        self.assertEqual("ready", current.revision.status)
        self.assertEqual("preview-file", current.revision.telegram_preview_file_id)


if __name__ == "__main__":
    unittest.main()
