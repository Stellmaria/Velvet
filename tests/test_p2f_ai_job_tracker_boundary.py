from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.ai_job_runtime as runtime


class FakeRepository:
    def __init__(self) -> None:
        self.error_calls: list[tuple[int, object]] = []

    async def create(self, **kwargs) -> int:
        return 41

    async def get(self, job_id: int, *, created_by: int | None):
        return object()

    async def mark_error(self, job_id: int, error) -> None:
        self.error_calls.append((job_id, error))


class FailedMessage:
    from_user = SimpleNamespace(id=17)

    async def answer(self, *args, **kwargs):
        raise ValueError("status unavailable")


class CancelledMessage:
    from_user = SimpleNamespace(id=17)

    async def answer(self, *args, **kwargs):
        raise asyncio.CancelledError


class AIJobTrackerBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_marks_error_and_reraises(self) -> None:
        repo = FakeRepository()
        original_repo = runtime.AIJobRepository
        original_text = runtime.build_job_detail_text
        original_keyboard = runtime.build_job_keyboard
        runtime.AIJobRepository = lambda database: repo
        runtime.build_job_detail_text = lambda job: "status"
        runtime.build_job_keyboard = lambda job: None
        try:
            with self.assertRaises(ValueError):
                await runtime.AIJobTracker.create(
                    database=object(),
                    source_message=FailedMessage(),
                    kind="quality",
                    title="Quality",
                    provider="ollama",
                    model="qwen",
                )
        finally:
            runtime.AIJobRepository = original_repo
            runtime.build_job_detail_text = original_text
            runtime.build_job_keyboard = original_keyboard

        self.assertEqual(repo.error_calls[0][0], 41)
        self.assertIn("status unavailable", str(repo.error_calls[0][1]))

    async def test_cancellation_is_not_marked_error(self) -> None:
        repo = FakeRepository()
        original_repo = runtime.AIJobRepository
        original_text = runtime.build_job_detail_text
        original_keyboard = runtime.build_job_keyboard
        runtime.AIJobRepository = lambda database: repo
        runtime.build_job_detail_text = lambda job: "status"
        runtime.build_job_keyboard = lambda job: None
        try:
            with self.assertRaises(asyncio.CancelledError):
                await runtime.AIJobTracker.create(
                    database=object(),
                    source_message=CancelledMessage(),
                    kind="quality",
                    title="Quality",
                    provider="ollama",
                    model="qwen",
                )
        finally:
            runtime.AIJobRepository = original_repo
            runtime.build_job_detail_text = original_text
            runtime.build_job_keyboard = original_keyboard

        self.assertEqual(repo.error_calls, [])


if __name__ == "__main__":
    unittest.main()
