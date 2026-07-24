from __future__ import annotations

import os
import unittest

from velvet_bot.database import Database
from velvet_bot.domains.watermark.models import WatermarkSettings, WatermarkWorkItem
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

    async def _create_job(
        self,
        *,
        source_message_id: int = 30,
        revision_status: str = "pending",
    ) -> WatermarkWorkItem:
        return await self.repository.create_job(
            owner_user_id=10,
            chat_id=20,
            source_message_id=source_message_id,
            source_file_id=f"telegram-file-{source_message_id}",
            source_file_unique_id=f"telegram-unique-{source_message_id}",
            source_path=f"/bridge/sources/source-{source_message_id}.png",
            settings=WatermarkSettings(),
            revision_status=revision_status,  # type: ignore[arg-type]
        )

    async def _claim_and_ready(
        self,
        item: WatermarkWorkItem,
        *,
        output_path: str,
    ) -> WatermarkWorkItem:
        claimed = await self.repository.claim_pending()
        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(item.job.id, claimed.job.id)
        self.assertEqual(item.revision.revision, claimed.revision.revision)
        await self.repository.set_dispatched_paths(
            job_id=item.job.id,
            revision=item.revision.revision,
            request_path=f"/bridge/requests/job-{item.job.id}-r{item.revision.revision}.json",
            output_path=output_path,
            response_path=f"/bridge/responses/job-{item.job.id}-r{item.revision.revision}.json",
        )
        self.assertTrue(
            await self.repository.mark_ready(
                job_id=item.job.id,
                revision=item.revision.revision,
                telegram_preview_file_id="preview-file",
            )
        )
        current = await self.repository.get_current(item.job.id)
        self.assertIsNotNone(current)
        assert current is not None
        return current

    async def test_revisions_undo_ready_and_approve_use_real_schema(self) -> None:
        first = await self._create_job()
        self.assertEqual(
            (1, "bottom_right", "pending"),
            (
                first.revision.revision,
                first.revision.settings.position,
                first.revision.status,
            ),
        )

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
        self.assertEqual(
            (2, "top_left", "#d8c8b8"),
            (
                second.revision.revision,
                second.revision.settings.position,
                second.revision.settings.color,
            ),
        )

        undone = await self.repository.undo(first.job.id)
        self.assertEqual(
            (3, "bottom_right", "auto"),
            (
                undone.revision.revision,
                undone.revision.settings.position,
                undone.revision.settings.color,
            ),
        )

        ready = await self._claim_and_ready(
            undone,
            output_path="/bridge/outputs/job.png",
        )
        self.assertEqual("ready", ready.revision.status)
        approved = await self.repository.approve(first.job.id)
        self.assertEqual("approved", approved.job.status)
        self.assertEqual("/bridge/outputs/job.png", approved.job.final_path)
        self.assertEqual(3, approved.revision.revision)
        self.assertEqual("ready", approved.revision.status)

    async def test_stale_ready_revision_cannot_be_approved(self) -> None:
        first = await self._create_job(source_message_id=31)
        await self._claim_and_ready(
            first,
            output_path="/bridge/outputs/job-old.png",
        )
        current = await self.repository.create_revision(
            first.job.id,
            settings=WatermarkSettings(position="top_right"),
        )
        self.assertEqual(2, current.revision.revision)
        self.assertEqual("pending", current.revision.status)

        with self.assertRaisesRegex(ValueError, "Текущая версия ещё не готова"):
            await self.repository.approve(first.job.id)

        unchanged = await self.repository.get_current(first.job.id)
        self.assertIsNotNone(unchanged)
        assert unchanged is not None
        self.assertEqual("active", unchanged.job.status)
        self.assertIsNone(unchanged.job.final_path)
        self.assertEqual(2, unchanged.revision.revision)

    async def test_draft_revision_is_not_claimed_until_explicitly_queued(self) -> None:
        draft = await self._create_job(
            source_message_id=34,
            revision_status="draft",
        )
        self.assertEqual("draft", draft.revision.status)
        self.assertIsNone(await self.repository.claim_pending())

        queued = await self.repository.queue_revision(
            job_id=draft.job.id,
            revision=draft.revision.revision,
        )
        self.assertEqual("pending", queued.revision.status)

        claimed = await self.repository.claim_pending()
        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(draft.job.id, claimed.job.id)
        self.assertEqual("processing", claimed.revision.status)

    async def test_stale_draft_revision_cannot_be_queued(self) -> None:
        first = await self._create_job(
            source_message_id=35,
            revision_status="draft",
        )
        current = await self.repository.create_revision(
            first.job.id,
            settings=WatermarkSettings(position="top_right"),
            revision_status="draft",
        )
        self.assertEqual(2, current.revision.revision)

        with self.assertRaisesRegex(ValueError, "Черновик уже изменился"):
            await self.repository.queue_revision(
                job_id=first.job.id,
                revision=first.revision.revision,
            )
        self.assertIsNone(await self.repository.claim_pending())

    async def test_approved_job_is_idempotently_protected_from_cancel(self) -> None:
        first = await self._create_job(source_message_id=32)
        await self._claim_and_ready(
            first,
            output_path="/bridge/outputs/job-approved.png",
        )
        approved = await self.repository.approve(first.job.id)
        self.assertEqual("approved", approved.job.status)

        self.assertEqual("approved", await self.repository.cancel(first.job.id))
        with self.assertRaisesRegex(ValueError, "уже подтверждён"):
            await self.repository.approve(first.job.id)

        current = await self.repository.get_current(first.job.id)
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual("approved", current.job.status)
        self.assertEqual("/bridge/outputs/job-approved.png", current.job.final_path)

    async def test_cancel_is_guarded_and_repeatable(self) -> None:
        first = await self._create_job(source_message_id=33)
        self.assertEqual("cancelled", await self.repository.cancel(first.job.id))
        self.assertEqual("already_cancelled", await self.repository.cancel(first.job.id))
        current = await self.repository.get_current(first.job.id)
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual("cancelled", current.job.status)


if __name__ == "__main__":
    unittest.main()
