from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import (
    AITaskQueueService,
    AITaskRepository,
    AITaskRequest,
)
from velvet_bot.domains.vision_batches import (
    VisionBatchRepository,
    VisionBatchStatus,
)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class VisionBatchPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database.acquire() as connection:
            await connection.execute(
                "TRUNCATE media_delivery_items, media_delivery_jobs, ai_tasks, ai_task_batches RESTART IDENTITY"
            )
            await connection.execute(
                """
                UPDATE ai_runtime_state
                SET paused=FALSE,pause_reason=NULL,updated_by=NULL,updated_at=NOW()
                WHERE singleton_id=1
                """
            )
        self.repository = VisionBatchRepository(self.database)
        self.queue = AITaskQueueService(AITaskRepository(self.database))

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def _create_plan(self, *, expired: bool = False):
        return await self.repository.create_plan(
            plan_id=uuid4(),
            candidate_ids=(101,),
            max_cost_per_item_rub=Decimal("1.25"),
            estimated_cost_rub=Decimal("1.25"),
            prompt_version=4,
            created_by=77,
            expires_at=datetime.now(timezone.utc)
            + (timedelta(seconds=-1) if expired else timedelta(minutes=10)),
            metadata={"source": "test"},
        )

    async def test_queue_insert_assigns_batch_id_from_payload(self) -> None:
        plan = await self._create_plan()
        claimed = await self.repository.claim_start(plan_id=plan.id)
        self.assertIsNotNone(claimed)

        enqueued = await self.queue.enqueue(
            AITaskRequest(
                scope=AIBudgetScope.VISION,
                task_type="vision.semantic-profile",
                payload={
                    "media_id": 101,
                    "batch_id": str(plan.id),
                    "prompt_version": 4,
                },
                dedupe_key="vision.semantic-profile:101:v4",
                estimated_cost_rub=Decimal("1.25"),
            )
        )
        async with self.database.acquire() as connection:
            batch_id = await connection.fetchval(
                "SELECT batch_id FROM ai_tasks WHERE id=$1::UUID",
                enqueued.task.id,
            )
        self.assertEqual(plan.id, batch_id)

        queued = await self.repository.mark_queued(
            plan_id=plan.id,
            created_task_count=1,
            deduplicated_task_count=0,
        )
        self.assertEqual(VisionBatchStatus.QUEUED, queued.status)

        task = await self.queue.claim_next(
            worker_id="vision-test",
            task_types=("vision.semantic-profile",),
        )
        assert task is not None
        await self.queue.complete(
            task_id=task.id,
            worker_id="vision-test",
            result={"media_id": 101},
        )
        progress = await self.repository.progress(plan_id=plan.id)
        assert progress is not None
        self.assertEqual(VisionBatchStatus.COMPLETED, progress.plan.status)
        self.assertEqual(1, progress.success)

    async def test_expired_plan_cannot_be_claimed(self) -> None:
        plan = await self._create_plan(expired=True)
        claimed = await self.repository.claim_start(plan_id=plan.id)
        self.assertIsNone(claimed)
        stored = await self.repository.get(plan_id=plan.id)
        assert stored is not None
        self.assertEqual(VisionBatchStatus.EXPIRED, stored.status)

    async def test_cancel_plan_cancels_queued_tasks(self) -> None:
        plan = await self._create_plan()
        claimed = await self.repository.claim_start(plan_id=plan.id)
        self.assertIsNotNone(claimed)
        enqueued = await self.queue.enqueue(
            AITaskRequest(
                scope=AIBudgetScope.VISION,
                task_type="vision.semantic-profile",
                payload={"media_id": 101, "batch_id": str(plan.id)},
                dedupe_key="vision.semantic-profile:101:cancel",
            )
        )
        await self.repository.mark_queued(
            plan_id=plan.id,
            created_task_count=1,
            deduplicated_task_count=0,
        )

        cancelled = await self.repository.cancel(
            plan_id=plan.id,
            reason="owner test",
        )
        assert cancelled is not None
        self.assertEqual(VisionBatchStatus.CANCELLED, cancelled.status)
        task = await self.queue.get(task_id=enqueued.task.id)
        assert task is not None
        self.assertEqual("cancelled", task.status.value)


if __name__ == "__main__":
    unittest.main()
