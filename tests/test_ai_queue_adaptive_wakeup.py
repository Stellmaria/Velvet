from __future__ import annotations

import asyncio
import os
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import AITaskRequest, build_ai_task_queue_service
from velvet_bot.domains.ai_usage.task_service import AITaskQueueService
from velvet_bot.domains.vision_batches.worker import VisionBatchQueueConsumer
from velvet_bot.infrastructure.postgres.ai_task_wakeup_repository import (
    PostgresAITaskListener,
)
from velvet_bot.workers import PeriodicWorkerSpec, WorkerManager
from velvet_bot.workers.adaptive import (
    AdaptiveQueueWait,
    WorkerIterationOutcome,
    WorkerIterationResult,
)


class _WakeupStub:
    def __init__(self, results: list[bool] | None = None) -> None:
        self.results = list(results or [])
        self.delays: list[float] = []
        self.closed = False
        self._wakeups = 0
        self._fallback_polls = 0

    @property
    def wakeups(self) -> int:
        return self._wakeups

    @property
    def fallback_polls(self) -> int:
        return self._fallback_polls

    @property
    def reconnects(self) -> int:
        return 0

    @property
    def errors(self) -> int:
        return 0

    async def wait(self, timeout_seconds: float) -> bool:
        self.delays.append(timeout_seconds)
        result = self.results.pop(0) if self.results else False
        if result:
            self._wakeups += 1
        else:
            self._fallback_polls += 1
        await asyncio.sleep(0)
        return result

    async def close(self) -> None:
        self.closed = True


class AdaptiveQueueWaitTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_claims_back_off_and_notification_resets_delay(self) -> None:
        wakeup = _WakeupStub([False, False, True, False])
        wait = AdaptiveQueueWait(
            wakeup,
            empty_delays_seconds=(3, 5, 10, 20, 30),
            jitter_ratio=0,
        )
        empty = WorkerIterationResult(WorkerIterationOutcome.EMPTY)
        self.assertEqual(3, wait.delay_for(empty, default_interval_seconds=3))
        await wait.wait(3)
        self.assertEqual(5, wait.delay_for(empty, default_interval_seconds=3))
        await wait.wait(5)
        self.assertEqual(10, wait.delay_for(empty, default_interval_seconds=3))
        self.assertTrue(await wait.wait(10))
        self.assertEqual(3, wait.delay_for(empty, default_interval_seconds=3))
        snapshot = wait.snapshot()
        self.assertEqual(4, snapshot.empty_runs)
        self.assertEqual(1, snapshot.wakeups)
        self.assertEqual(2, snapshot.fallback_polls)

    async def test_processed_and_failure_outcomes_do_not_increase_empty_backoff(self) -> None:
        wakeup = _WakeupStub()
        wait = AdaptiveQueueWait(wakeup, jitter_ratio=0)
        empty = WorkerIterationResult(WorkerIterationOutcome.EMPTY)
        self.assertEqual(3, wait.delay_for(empty, default_interval_seconds=3))
        processed = WorkerIterationResult(
            WorkerIterationOutcome.PROCESSED,
            processed_items=2,
        )
        self.assertEqual(0, wait.delay_for(processed, default_interval_seconds=3))
        transient = WorkerIterationResult(WorkerIterationOutcome.TRANSIENT_FAILURE)
        self.assertEqual(3, wait.delay_for(transient, default_interval_seconds=3))
        self.assertEqual(2, wait.snapshot().processed_items)

    async def test_jitter_stays_within_configured_bounds(self) -> None:
        wakeup = _WakeupStub()
        values = iter((0.0, 1.0))
        wait = AdaptiveQueueWait(
            wakeup,
            jitter_ratio=0.1,
            random_value=lambda: next(values),
        )
        empty = WorkerIterationResult(WorkerIterationOutcome.EMPTY)
        self.assertAlmostEqual(
            2.7, wait.delay_for(empty, default_interval_seconds=3)
        )
        self.assertAlmostEqual(
            5.5, wait.delay_for(empty, default_interval_seconds=3)
        )

    async def test_manager_failure_is_typed_without_growing_empty_backoff(self) -> None:
        async def runner() -> WorkerIterationResult:
            raise ConnectionResetError("database unavailable")

        wakeup = _WakeupStub()
        manager = WorkerManager()
        controller = AdaptiveQueueWait(
            wakeup,
            empty_delays_seconds=(0.01, 0.02),
            jitter_ratio=0,
        )
        spec = PeriodicWorkerSpec(
            name="adaptive-failure",
            description="adaptive failure",
            interval_seconds=0.01,
            runner=runner,
            wait_controller=controller,
        )
        manager.register(spec)
        self.assertFalse(await manager._execute_once(spec))
        succeeded, result = await manager._execute_once_with_result(spec)
        self.assertFalse(succeeded)
        self.assertEqual(
            WorkerIterationOutcome.TRANSIENT_FAILURE,
            result.outcome,  # type: ignore[attr-defined]
        )
        delay = controller.delay_for(result, default_interval_seconds=0.01)
        self.assertEqual(0.01, delay)
        snapshot = controller.snapshot()
        self.assertEqual("transient_failure", snapshot.last_outcome)
        self.assertEqual(0, snapshot.empty_runs)

    async def test_manager_exposes_adaptive_diagnostics_without_overlapping_runs(self) -> None:
        active = 0
        max_active = 0
        calls = 0
        enough = asyncio.Event()

        async def runner() -> WorkerIterationResult:
            nonlocal active, max_active, calls
            active += 1
            max_active = max(max_active, active)
            try:
                await asyncio.sleep(0.005)
                calls += 1
                if calls >= 3:
                    enough.set()
                return WorkerIterationResult(
                    WorkerIterationOutcome.EMPTY,
                    oldest_queued_age_seconds=12.5,
                )
            finally:
                active -= 1

        wakeup = _WakeupStub()
        manager = WorkerManager()
        manager.register(
            PeriodicWorkerSpec(
                name="adaptive",
                description="adaptive",
                interval_seconds=0.01,
                runner=runner,
                wait_controller=AdaptiveQueueWait(
                    wakeup,
                    empty_delays_seconds=(0.01, 0.02),
                    jitter_ratio=0,
                ),
            )
        )
        await manager.start_all()
        try:
            await asyncio.wait_for(enough.wait(), timeout=1)
            snapshot = manager.snapshot("adaptive")
            assert snapshot is not None
            self.assertEqual("empty", snapshot.last_outcome)
            self.assertGreaterEqual(snapshot.empty_runs, 2)
            self.assertEqual(12.5, snapshot.oldest_queued_age_seconds)
            self.assertEqual(1, max_active)
        finally:
            await manager.stop_all()
        self.assertTrue(wakeup.closed)


class _ConsumerQueueStub:
    def __init__(self, task=None, failure=None) -> None:
        self.task = task
        self.failure = failure

    async def claim_next(self, **kwargs):
        del kwargs
        task, self.task = self.task, None
        return task

    async def complete(self, **kwargs):
        return SimpleNamespace(id=kwargs["task_id"])

    async def fail(self, **kwargs):
        del kwargs
        return self.failure

    async def heartbeat(self, **kwargs):
        del kwargs
        return True


class _ConsumerDiagnosticsStub:
    async def oldest_queued_age_seconds(self) -> float:
        return 42.0


class _ConsumerProcessorStub:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error

    async def process_media_id(self, media_id: int):
        if self.error is not None:
            raise self.error
        return {"media_id": media_id}


class VisionBatchOutcomeTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_claim_reports_age_without_becoming_failure(self) -> None:
        consumer = VisionBatchQueueConsumer(
            queue_service=_ConsumerQueueStub(),  # type: ignore[arg-type]
            processor=_ConsumerProcessorStub(),  # type: ignore[arg-type]
            diagnostics=_ConsumerDiagnosticsStub(),  # type: ignore[arg-type]
        )
        result = await consumer.process_once()
        self.assertEqual(WorkerIterationOutcome.EMPTY, result.outcome)
        self.assertEqual(42.0, result.oldest_queued_age_seconds)

    async def test_retryable_task_failure_is_not_classified_as_empty(self) -> None:
        task = SimpleNamespace(id=uuid4(), payload={"media_id": 17})
        failure = SimpleNamespace(will_retry=True)
        consumer = VisionBatchQueueConsumer(
            queue_service=_ConsumerQueueStub(task, failure),  # type: ignore[arg-type]
            processor=_ConsumerProcessorStub(RuntimeError("provider timeout")),  # type: ignore[arg-type]
            heartbeat_seconds=3600,
        )
        result = await consumer.process_once()
        self.assertEqual(WorkerIterationOutcome.TRANSIENT_FAILURE, result.outcome)
        self.assertNotEqual(WorkerIterationOutcome.EMPTY, result.outcome)


class _RepositoryStub:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def enqueue(self, request):
        del request
        self.events.append("committed")
        return SimpleNamespace(created=True, task=SimpleNamespace(id=uuid4()))

    async def enqueue_many(self, requests):
        self.events.append("committed-many")
        return tuple(
            SimpleNamespace(created=True, task=SimpleNamespace(id=uuid4()))
            for _ in requests
        )


class _NotifierStub:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def notify(self) -> None:
        self.events.append("notified")


class QueueNotifierTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_notifies_only_after_repository_commit(self) -> None:
        repository = _RepositoryStub()
        service = AITaskQueueService(
            repository,  # type: ignore[arg-type]
            notifier=_NotifierStub(repository.events),
        )
        await service.enqueue(SimpleNamespace())  # type: ignore[arg-type]
        self.assertEqual(["committed", "notified"], repository.events)


class _ListenerConnection:
    def __init__(self) -> None:
        self.notification = None
        self.termination = None
        self.closed = False

    async def add_listener(self, channel, callback) -> None:
        del channel
        self.notification = callback

    async def remove_listener(self, channel, callback) -> None:
        del channel, callback
        self.notification = None

    def add_termination_listener(self, callback) -> None:
        self.termination = callback

    def remove_termination_listener(self, callback) -> None:
        if self.termination is callback:
            self.termination = None

    async def close(self) -> None:
        self.closed = True

    def is_closed(self) -> bool:
        return self.closed

    def emit(self) -> None:
        assert self.notification is not None
        self.notification(self, 1, "velvet_ai_task_queue", "queued")

    def terminate(self) -> None:
        self.closed = True
        assert self.termination is not None
        self.termination(self)


class PostgresListenerTests(unittest.IsolatedAsyncioTestCase):
    async def test_listener_reconnects_after_termination(self) -> None:
        first = _ListenerConnection()
        second = _ListenerConnection()
        connect = AsyncMock(side_effect=[first, second])
        listener = PostgresAITaskListener("postgresql://test")
        with patch(
            "velvet_bot.infrastructure.postgres.ai_task_wakeup_repository.asyncpg.connect",
            connect,
        ):
            first_wait = asyncio.create_task(listener.wait(1))
            while first.notification is None:
                await asyncio.sleep(0)
            first.emit()
            self.assertTrue(await first_wait)
            first.terminate()
            second_wait = asyncio.create_task(listener.wait(1))
            while second.notification is None:
                await asyncio.sleep(0)
            second.emit()
            self.assertTrue(await second_wait)
            await listener.close()
        self.assertEqual(1, listener.reconnects)
        self.assertEqual(2, listener.wakeups)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgresQueueWakeupIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_committed_enqueue_wakes_listener(self) -> None:
        database = Database(os.environ["TEST_DATABASE_URL"])
        await database.initialize()
        listener = PostgresAITaskListener(database.database_url)
        try:
            service = build_ai_task_queue_service(database=database)
            waiting = asyncio.create_task(listener.wait(3))
            await asyncio.sleep(0.05)
            result = await service.enqueue(
                AITaskRequest(
                    scope=AIBudgetScope.VISION,
                    task_type="test.queue-wakeup",
                    payload={"test": True},
                    dedupe_key=f"test-queue-wakeup-{uuid4()}",
                    estimated_cost_rub=Decimal("0"),
                )
            )
            self.assertTrue(result.created)
            self.assertTrue(await waiting)
        finally:
            await listener.close()
            await database.close()


if __name__ == "__main__":
    unittest.main()
