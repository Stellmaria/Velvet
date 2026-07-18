from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.handlers.quality_operations as module


class FakeTracker:
    def __init__(self) -> None:
        self.job_id = 9
        self.stages: list[str] = []
        self.errors: list[object] = []
        self.ready_calls: list[dict[str, object]] = []

    async def stage(self, name: str) -> None:
        self.stages.append(name)

    async def error(self, value: object) -> None:
        self.errors.append(value)

    async def ready(self, **kwargs) -> None:
        self.ready_calls.append(kwargs)


class FakeTrackerFactory:
    tracker = FakeTracker()
    create_calls: list[dict[str, object]] = []

    @classmethod
    async def create(cls, **kwargs):
        cls.create_calls.append(kwargs)
        return cls.tracker


class ManualQualityJobBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_tracker = module.AIJobTracker
        self.original_result_file = module._result_file
        self.original_settings = module.load_settings
        self.original_download = module._download_image

        FakeTrackerFactory.tracker = FakeTracker()
        FakeTrackerFactory.create_calls = []
        module.AIJobTracker = FakeTrackerFactory
        module._result_file = lambda message: ("file-id", "unique-id")
        module.load_settings = lambda: SimpleNamespace(
            ai_vision_enabled=True,
            ai_vision_provider="ollama",
            ai_vision_model="qwen",
        )

    def tearDown(self) -> None:
        module.AIJobTracker = self.original_tracker
        module._result_file = self.original_result_file
        module.load_settings = self.original_settings
        module._download_image = self.original_download

    async def test_download_failure_marks_created_job_error(self) -> None:
        error = RuntimeError("download failed")

        async def fail_download(bot, file_id):
            raise error

        module._download_image = fail_download
        message = object()
        database = object()
        bot = object()

        await module.handle_quality_upload_reply(message, database, bot)

        tracker = FakeTrackerFactory.tracker
        self.assertEqual(tracker.stages, ["downloading"])
        self.assertEqual(tracker.errors, [error])
        self.assertEqual(tracker.ready_calls, [])
        self.assertEqual(len(FakeTrackerFactory.create_calls), 1)
        call = FakeTrackerFactory.create_calls[0]
        self.assertIs(call["database"], database)
        self.assertIs(call["source_message"], message)
        self.assertEqual(call["kind"], "quality_image")
        self.assertEqual(call["title"], "Проверка качества изображения")
        self.assertEqual(call["provider"], "ollama")
        self.assertEqual(call["model"], "qwen")
        self.assertEqual(
            call["request_payload"],
            {"file_id": "file-id", "file_unique_id": "unique-id"},
        )

    async def test_cancellation_marks_interrupted_job_and_propagates(self) -> None:
        async def cancel_download(bot, file_id):
            raise asyncio.CancelledError

        module._download_image = cancel_download

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_quality_upload_reply(object(), object(), object())

        tracker = FakeTrackerFactory.tracker
        self.assertEqual(tracker.stages, ["downloading"])
        self.assertEqual(
            tracker.errors,
            ["Задание прервано остановкой процесса."],
        )
        self.assertEqual(tracker.ready_calls, [])

    async def test_compensation_failure_is_not_silently_swallowed(self) -> None:
        primary_error = RuntimeError("analysis failed")
        compensation_error = RuntimeError("job persistence failed")

        async def fail_download(bot, file_id):
            raise primary_error

        async def fail_error(value):
            raise compensation_error

        module._download_image = fail_download
        FakeTrackerFactory.tracker.error = fail_error

        with self.assertRaises(RuntimeError) as captured:
            await module.handle_quality_upload_reply(object(), object(), object())

        self.assertIs(captured.exception, compensation_error)


if __name__ == "__main__":
    unittest.main()
