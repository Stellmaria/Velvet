from __future__ import annotations

import asyncio
import os
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from velvet_bot.domains.local_inference_priority import (
    storage_librarian_full_archive_has_priority,
)
from velvet_bot.domains.vision_batches.worker import VisionBatchQueueConsumer
from velvet_bot.workers.adaptive import WorkerIterationOutcome


class _FakeConnection:
    def __init__(self, *, has_priority_work: bool) -> None:
        self.has_priority_work = has_priority_work
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchrow(self, query: str, *args: object):
        self.calls.append((query, args))
        return {"has_priority_work": self.has_priority_work}


class _FakeDatabase:
    def __init__(self, *, has_priority_work: bool) -> None:
        self.connection = _FakeConnection(has_priority_work=has_priority_work)

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


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
        database = _FakeDatabase(has_priority_work=True)
        with patch.dict(os.environ, {}, clear=True):
            blocked = await storage_librarian_full_archive_has_priority(database)  # type: ignore[arg-type]
        self.assertFalse(blocked)
        self.assertEqual([], database.connection.calls)

    async def test_gate_uses_storage_backlog_not_only_current_running_job(self) -> None:
        database = _FakeDatabase(has_priority_work=True)
        settings = SimpleNamespace(
            enabled=True,
            allowed_kinds=("diagnostics", "codex"),
            max_object_bytes=12 * 1024 * 1024,
            analyzer_version="velvet-librarian:test:v1",
        )
        env = {
            "STORAGE_LIBRARIAN_AUTO_ENQUEUE": "true",
            "STORAGE_LIBRARIAN_AUTO_BACKFILL": "true",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "velvet_bot.domains.local_inference_priority.StorageLibrarianSettings.from_env",
                return_value=settings,
            ),
        ):
            blocked = await storage_librarian_full_archive_has_priority(database)  # type: ignore[arg-type]
        self.assertTrue(blocked)
        self.assertEqual(1, len(database.connection.calls))
        query, args = database.connection.calls[0]
        self.assertIn("telegram_storage_analysis_jobs", query)
        self.assertIn("telegram_storage_objects", query)
        self.assertIn("existing_job.status IN ('completed', 'skipped')", query)
        self.assertEqual(["diagnostics", "codex"], args[0])
        self.assertEqual("velvet-librarian:test:v1", args[2])

    async def test_gate_opens_only_after_full_archive_has_no_priority_work(self) -> None:
        database = _FakeDatabase(has_priority_work=False)
        settings = SimpleNamespace(
            enabled=True,
            allowed_kinds=("diagnostics",),
            max_object_bytes=12 * 1024 * 1024,
            analyzer_version="velvet-librarian:test:v1",
        )
        env = {
            "STORAGE_LIBRARIAN_AUTO_ENQUEUE": "true",
            "STORAGE_LIBRARIAN_AUTO_BACKFILL": "true",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "velvet_bot.domains.local_inference_priority.StorageLibrarianSettings.from_env",
                return_value=settings,
            ),
        ):
            blocked = await storage_librarian_full_archive_has_priority(database)  # type: ignore[arg-type]
        self.assertFalse(blocked)

    async def test_invalid_librarian_config_blocks_vl_fail_closed(self) -> None:
        database = _FakeDatabase(has_priority_work=False)
        env = {
            "STORAGE_LIBRARIAN_AUTO_ENQUEUE": "true",
            "STORAGE_LIBRARIAN_AUTO_BACKFILL": "true",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "velvet_bot.domains.local_inference_priority.StorageLibrarianSettings.from_env",
                side_effect=ValueError("bad librarian config"),
            ),
        ):
            blocked = await storage_librarian_full_archive_has_priority(database)  # type: ignore[arg-type]
        self.assertTrue(blocked)
        self.assertEqual([], database.connection.calls)

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
