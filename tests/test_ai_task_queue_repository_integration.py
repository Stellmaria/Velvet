from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import (
    AITaskQueueService,
    AITaskRepository,
    AITaskRequest,
    AITaskStatus,
)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class AITaskQueueRepositoryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database.acquire() as connection:
            await connection.execute(
                "TRUNCATE media_delivery_jobs, ai_tasks RESTART IDENTITY"
            )
            await connection.execute(
                """UPDATE ai_runtime_state
                   SET paused=FALSE,pause_reason=NULL,updated_by=NULL,updated_at=NOW()
                   WHERE singleton_id=1"""
            )
        self.repository = AITaskRepository(self.database)
        self.service = AITaskQueueService(self.repository)

    async def asyncTearDown(self) -> None:
        await self.database.close()

    @staticmethod
    def _request(
        *,
        dedupe_key: str | None = None,
        max_attempts: int = 2,
        task_type: str = "vision.semantic-profile",
    ) -> AITaskRequest:
        return AITaskRequest(
            scope=AIBudgetScope.VISION,
            task_type=task_type,
            payload={"media_id": 42},
            priority=50,
            dedupe_key=dedupe_key,
            max_attempts=max_attempts,
            created_by=100,
            estimated_cost_rub=Decimal("1.25"),
        )

    async def test_active_dedupe_key_returns_existing_task(self) -> None:
        first = await self.service.enqueue(self._request(dedupe_key="media:42"))
        second = await self.service.enqueue(self._request(dedupe_key="media:42"))

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.task.id, second.task.id)
        snapshot = await self.service.snapshot()
        self.assertEqual(1, snapshot.queued)

    async def test_two_workers_cannot_claim_same_task(self) -> None:
        await self.service.enqueue(self._request())
        results = await asyncio.gather(
            self.service.claim_next(worker_id="worker-a"),
            self.service.claim_next(worker_id="worker-b"),
        )

        claimed = [task for task in results if task is not None]
        self.assertEqual(1, len(claimed))
        self.assertEqual(AITaskStatus.RUNNING, claimed[0].status)
        self.assertIn(claimed[0].locked_by, {"worker-a", "worker-b"})

    async def test_paused_runtime_does_not_claim_tasks(self) -> None:
        await self.service.enqueue(self._request())
        async with self.database.acquire() as connection:
            await connection.execute(
                """UPDATE ai_runtime_state
                   SET paused=TRUE,pause_reason='maintenance',updated_at=NOW()
                   WHERE singleton_id=1"""
            )

        task = await self.service.claim_next(worker_id="worker-a")
        self.assertIsNone(task)
        snapshot = await self.service.snapshot()
        self.assertTrue(snapshot.paused)
        self.assertEqual("maintenance", snapshot.pause_reason)
        self.assertEqual(1, snapshot.queued)

    async def test_failure_retries_then_becomes_terminal_error(self) -> None:
        await self.service.enqueue(self._request(max_attempts=2))
        first_claim = await self.service.claim_next(worker_id="worker-a")
        assert first_claim is not None

        first_failure = await self.service.fail(
            task_id=first_claim.id,
            worker_id="worker-a",
            error=RuntimeError("temporary"),
            base_delay_seconds=0,
            max_delay_seconds=0,
        )
        assert first_failure is not None
        self.assertTrue(first_failure.will_retry)
        self.assertEqual(AITaskStatus.QUEUED, first_failure.task.status)
        self.assertEqual(1, first_failure.task.attempt_count)

        second_claim = await self.service.claim_next(worker_id="worker-b")
        assert second_claim is not None
        second_failure = await self.service.fail(
            task_id=second_claim.id,
            worker_id="worker-b",
            error=ValueError("permanent"),
            base_delay_seconds=0,
            max_delay_seconds=0,
        )
        assert second_failure is not None
        self.assertFalse(second_failure.will_retry)
        self.assertEqual(AITaskStatus.ERROR, second_failure.task.status)
        self.assertEqual(2, second_failure.task.attempt_count)
        self.assertEqual("ValueError", second_failure.task.last_error_type)

    async def test_complete_persists_result_and_releases_lock(self) -> None:
        await self.service.enqueue(self._request())
        claimed = await self.service.claim_next(worker_id="worker-a")
        assert claimed is not None

        completed = await self.service.complete(
            task_id=claimed.id,
            worker_id="worker-a",
            result={"profile_id": 7},
        )
        assert completed is not None
        self.assertEqual(AITaskStatus.SUCCESS, completed.status)
        self.assertEqual({"profile_id": 7}, completed.result)
        self.assertIsNone(completed.locked_by)
        self.assertIsNotNone(completed.completed_at)

    async def test_stale_lock_is_requeued_or_terminal(self) -> None:
        await self.service.enqueue(self._request(max_attempts=2, task_type="retryable"))
        retryable = await self.service.claim_next(worker_id="dead-worker")
        assert retryable is not None

        await self.service.enqueue(self._request(max_attempts=1, task_type="terminal"))
        terminal = await self.service.claim_next(worker_id="dead-worker-2")
        assert terminal is not None

        async with self.database.acquire() as connection:
            await connection.execute(
                """UPDATE ai_tasks
                   SET locked_at=NOW()-INTERVAL '2 hours'
                   WHERE status='running'"""
            )

        recovered = await self.service.recover_stale(
            older_than=datetime.now(timezone.utc) - timedelta(minutes=30),
        )
        by_type = {task.task_type: task for task in recovered}
        self.assertEqual(AITaskStatus.QUEUED, by_type["retryable"].status)
        self.assertEqual(AITaskStatus.ERROR, by_type["terminal"].status)
        self.assertEqual("StaleTaskLock", by_type["terminal"].last_error_type)

    async def test_cancel_and_requeue_terminal_task(self) -> None:
        enqueued = await self.service.enqueue(self._request(dedupe_key="cancel-me"))
        cancelled = await self.service.cancel(
            task_id=enqueued.task.id,
            reason="owner request",
        )
        assert cancelled is not None
        self.assertEqual(AITaskStatus.CANCELLED, cancelled.status)

        requeued = await self.service.requeue(task_id=cancelled.id)
        assert requeued is not None
        self.assertEqual(AITaskStatus.QUEUED, requeued.status)
        self.assertEqual(0, requeued.attempt_count)
        self.assertIsNone(requeued.last_error)


if __name__ == "__main__":
    unittest.main()
