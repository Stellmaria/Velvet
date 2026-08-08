from __future__ import annotations

import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from velvet_bot.domains.vision_batches.worker import (
    VisionBatchQueueConsumer,
    storage_librarian_full_archive_has_priority,
)
from velvet_bot.workers.adaptive import WorkerIterationOutcome


class _FakeQueue:
    def __init__(self) -> None:
        self.claim_calls = 0
        self.task = SimpleNamespace(id=uuid4(), payload={"media_id": 77})
        self.completed = False

    async def claim_next(self, **kwargs):
        self.claim_calls += 1
        task, self.task = self.task, None
        return task

    async def complete(self, **kwargs):
        self.completed = True
        return SimpleNamespace(id=kwargs["task_id"])

    async def fail(self, **kwargs):
        return None

    async def heartbeat(self, **kwargs):
        return True


class _FakeProcessor:
    def __init__(self) -> None:
        self.calls: list[int] = []

    async def process_media_id(self, media_id: int) -> dict[str, object]:
        self.calls.append(media_id)
        return {"media_id": media_id}


class LocalInferencePriorityTests(unittest.IsolatedAsyncioTestCase):
    async def test_gate_is_open_when_full_archive_mode_is_not_enabled(self) -> None:
        repository = SimpleNamespace(
            full_archive_phase_active=AsyncMock(return_value=False),
            counts=AsyncMock(return_value={"queued": 1, "running": 0}),
            enqueue_pending=AsyncMock(return_value=1),
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "velvet_bot.domains.vision_batches.worker.ArthurStorageLibrarianRepository",
                return_value=repository,
            ),
        ):
            blocked = await storage_librarian_full_archive_has_priority(object())  # type: ignore[arg-type]
        self.assertFalse(blocked)
        repository.full_archive_phase_active.assert_awaited_once_with()
        repository.counts.assert_not_awaited()
        repository.enqueue_pending.assert_not_awaited()

    async def test_arthur_managed_archive_blocks_with_env_scheduler_disabled(self) -> None:
        settings = SimpleNamespace(enabled=True, allowed_kinds=("diagnostics",))
        repository = SimpleNamespace(
            full_archive_phase_active=AsyncMock(return_value=True),
            counts=AsyncMock(return_value={"queued": 1, "running": 0}),
            enqueue_pending=AsyncMock(return_value=0),
        )
        env = {
            "STORAGE_LIBRARIAN_AUTO_ENQUEUE": "false",
            "STORAGE_LIBRARIAN_AUTO_BACKFILL": "false",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "velvet_bot.domains.vision_batches.worker.StorageLibrarianSettings.from_env",
                return_value=settings,
            ),
            patch(
                "velvet_bot.domains.vision_batches.worker.ArthurStorageLibrarianRepository",
                return_value=repository,
            ),
        ):
            blocked = await storage_librarian_full_archive_has_priority(object())  # type: ignore[arg-type]
        self.assertTrue(blocked)
        repository.full_archive_phase_active.assert_awaited_once_with()
        repository.counts.assert_awaited_once_with()
        repository.enqueue_pending.assert_not_awaited()

    async def test_existing_arthur_job_blocks_without_enqueuing_more(self) -> None:
        settings = SimpleNamespace(enabled=True, allowed_kinds=("diagnostics",))
        repository = SimpleNamespace(
            full_archive_phase_active=AsyncMock(return_value=False),
            counts=AsyncMock(return_value={"queued": 1, "running": 0}),
            enqueue_pending=AsyncMock(return_value=1),
        )
        env = {
            "STORAGE_LIBRARIAN_AUTO_ENQUEUE": "true",
            "STORAGE_LIBRARIAN_AUTO_BACKFILL": "true",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "velvet_bot.domains.vision_batches.worker.StorageLibrarianSettings.from_env",
                return_value=settings,
            ),
            patch(
                "velvet_bot.domains.vision_batches.worker.ArthurStorageLibrarianRepository",
                return_value=repository,
            ),
        ):
            blocked = await storage_librarian_full_archive_has_priority(object())  # type: ignore[arg-type]
        self.assertTrue(blocked)
        repository.full_archive_phase_active.assert_not_awaited()
        repository.counts.assert_awaited_once_with()
        repository.enqueue_pending.assert_not_awaited()

    async def test_residual_archive_backlog_enqueues_one_and_keeps_vl_closed(self) -> None:
        settings = SimpleNamespace(enabled=True, allowed_kinds=("diagnostics",))
        repository = SimpleNamespace(
            full_archive_phase_active=AsyncMock(return_value=True),
            counts=AsyncMock(return_value={"queued": 0, "running": 0}),
            enqueue_pending=AsyncMock(return_value=1),
        )
        env = {
            "STORAGE_LIBRARIAN_AUTO_ENQUEUE": "false",
            "STORAGE_LIBRARIAN_AUTO_BACKFILL": "false",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "velvet_bot.domains.vision_batches.worker.StorageLibrarianSettings.from_env",
                return_value=settings,
            ),
            patch(
                "velvet_bot.domains.vision_batches.worker.ArthurStorageLibrarianRepository",
                return_value=repository,
            ),
        ):
            blocked = await storage_librarian_full_archive_has_priority(object())  # type: ignore[arg-type]
        self.assertTrue(blocked)
        repository.enqueue_pending.assert_awaited_once_with(settings=settings, limit=1)

    async def test_gate_opens_after_arthur_queue_and_archive_are_empty(self) -> None:
        settings = SimpleNamespace(enabled=True, allowed_kinds=("diagnostics",))
        repository = SimpleNamespace(
            full_archive_phase_active=AsyncMock(return_value=True),
            counts=AsyncMock(return_value={"queued": 0, "running": 0}),
            enqueue_pending=AsyncMock(return_value=0),
        )
        env = {
            "STORAGE_LIBRARIAN_AUTO_ENQUEUE": "false",
            "STORAGE_LIBRARIAN_AUTO_BACKFILL": "false",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "velvet_bot.domains.vision_batches.worker.StorageLibrarianSettings.from_env",
                return_value=settings,
            ),
            patch(
                "velvet_bot.domains.vision_batches.worker.ArthurStorageLibrarianRepository",
                return_value=repository,
            ),
        ):
            blocked = await storage_librarian_full_archive_has_priority(object())  # type: ignore[arg-type]
        self.assertFalse(blocked)
        repository.enqueue_pending.assert_awaited_once_with(settings=settings, limit=1)

    async def test_invalid_librarian_config_blocks_vl_fail_closed(self) -> None:
        repository = SimpleNamespace(
            full_archive_phase_active=AsyncMock(return_value=True),
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "velvet_bot.domains.vision_batches.worker.StorageLibrarianSettings.from_env",
                side_effect=ValueError("bad librarian config"),
            ),
            patch(
                "velvet_bot.domains.vision_batches.worker.ArthurStorageLibrarianRepository",
                return_value=repository,
            ),
        ):
            blocked = await storage_librarian_full_archive_has_priority(object())  # type: ignore[arg-type]
        self.assertTrue(blocked)

    async def test_archive_lease_probe_failure_blocks_vl_fail_closed(self) -> None:
        repository = SimpleNamespace(
            full_archive_phase_active=AsyncMock(side_effect=RuntimeError("lease probe failed")),
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "velvet_bot.domains.vision_batches.worker.ArthurStorageLibrarianRepository",
                return_value=repository,
            ),
        ):
            blocked = await storage_librarian_full_archive_has_priority(object())  # type: ignore[arg-type]
        self.assertTrue(blocked)

    async def test_vl_consumer_does_not_claim_task_while_arthur_has_priority(self) -> None:
        queue = _FakeQueue()
        processor = _FakeProcessor()
        priority_gate = AsyncMock(return_value=True)
        consumer = VisionBatchQueueConsumer(
            queue_service=queue,  # type: ignore[arg-type]
            processor=processor,  # type: ignore[arg-type]
            priority_gate=priority_gate,
            heartbeat_seconds=3600,
        )

        result = await consumer.process_once()

        self.assertEqual(WorkerIterationOutcome.EMPTY, result.outcome)
        self.assertEqual(0, queue.claim_calls)
        self.assertEqual([], processor.calls)
        self.assertIsNotNone(queue.task)
        priority_gate.assert_awaited_once_with()

    async def test_vl_consumer_runs_after_arthur_priority_clears(self) -> None:
        queue = _FakeQueue()
        processor = _FakeProcessor()
        priority_gate = AsyncMock(return_value=False)
        lock = asyncio.Lock()
        consumer = VisionBatchQueueConsumer(
            queue_service=queue,  # type: ignore[arg-type]
            processor=processor,  # type: ignore[arg-type]
            priority_gate=priority_gate,
            local_ai_lock=lock,
            heartbeat_seconds=3600,
        )

        result = await consumer.process_once()

        self.assertEqual(WorkerIterationOutcome.PROCESSED, result.outcome)
        self.assertEqual(1, queue.claim_calls)
        self.assertEqual([77], processor.calls)
        self.assertTrue(queue.completed)
        self.assertFalse(lock.locked())


if __name__ == "__main__":
    unittest.main()
