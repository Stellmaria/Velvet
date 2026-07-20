from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.presentation.telegram.routers.quality_operations_controllers.quality_set_ai as module


class FakeMessage:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(type=module.ChatType.PRIVATE, id=23)
        self.from_user = SimpleNamespace(id=17)
        self.answers: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs) -> None:
        self.answers.append((args, kwargs))


class FakeCallback:
    def __init__(self) -> None:
        self.message = FakeMessage()
        self.from_user = SimpleNamespace(id=17)
        self.answers: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs) -> None:
        self.answers.append((args, kwargs))


class FakeTracker:
    def __init__(self) -> None:
        self.job_id = 41
        self.errors: list[object] = []
        self.ready_calls: list[dict[str, object]] = []

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


class SetAnalysisJobBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_message = module.Message
        self.original_tracker = module.AIJobTracker
        self.original_settings = module.load_settings
        self.original_analyze = module._analyze_set
        self.original_safe_edit = module._safe_edit

        module.Message = FakeMessage
        module.AIJobTracker = FakeTrackerFactory
        module.load_settings = lambda: SimpleNamespace(
            ai_vision_enabled=True,
            ai_vision_provider="ollama",
            ai_vision_model="qwen",
        )
        FakeTrackerFactory.tracker = FakeTracker()
        FakeTrackerFactory.create_calls = []
        self.edit_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

        async def safe_edit(*args, **kwargs):
            self.edit_calls.append((args, kwargs))

        module._safe_edit = safe_edit

    def tearDown(self) -> None:
        module.Message = self.original_message
        module.AIJobTracker = self.original_tracker
        module.load_settings = self.original_settings
        module._analyze_set = self.original_analyze
        module._safe_edit = self.original_safe_edit

    @staticmethod
    def _data() -> SimpleNamespace:
        return SimpleNamespace(item_id=12, page=3)

    async def test_callback_failure_marks_job_and_renders_failure_state(self) -> None:
        error = RuntimeError("set analysis failed")

        async def fail_analysis(*args, **kwargs):
            raise error

        module._analyze_set = fail_analysis
        callback = FakeCallback()

        await module.handle_set_analyze(callback, self._data(), object(), object())

        tracker = FakeTrackerFactory.tracker
        self.assertEqual(tracker.errors, [error])
        self.assertEqual(tracker.ready_calls, [])
        self.assertEqual(callback.answers[0][0][0], "AI-задание #41 зарегистрировано.")
        self.assertEqual(len(self.edit_calls), 1)
        self.assertIn("Проверка сета #12 не завершена", self.edit_calls[0][0][1])
        call = FakeTrackerFactory.create_calls[0]
        self.assertEqual(call["kind"], "media_set_consistency")
        self.assertEqual(call["title"], "Целостность медиасета #12")
        self.assertEqual(call["provider"], "ollama")
        self.assertEqual(call["model"], "qwen")
        self.assertIs(call["source_message"], callback.message)
        self.assertEqual(call["request_payload"], {"set_id": 12})

    async def test_callback_cancellation_marks_interruption_and_propagates(self) -> None:
        async def cancel_analysis(*args, **kwargs):
            raise asyncio.CancelledError

        module._analyze_set = cancel_analysis
        callback = FakeCallback()

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_set_analyze(callback, self._data(), object(), object())

        self.assertEqual(
            FakeTrackerFactory.tracker.errors,
            ["Задание прервано остановкой процесса."],
        )
        self.assertEqual(self.edit_calls, [])

    async def test_command_failure_marks_job_error(self) -> None:
        error = RuntimeError("set command failed")

        async def fail_analysis(*args, **kwargs):
            raise error

        module._analyze_set = fail_analysis
        message = FakeMessage()
        command = SimpleNamespace(args="12")

        await module.handle_set_analysis_command(message, command, object(), object())

        tracker = FakeTrackerFactory.tracker
        self.assertEqual(tracker.errors, [error])
        self.assertEqual(tracker.ready_calls, [])
        call = FakeTrackerFactory.create_calls[0]
        self.assertEqual(call["title"], "Целостность медиасета #12")
        self.assertEqual(call["provider"], "ollama")
        self.assertEqual(call["model"], "qwen")
        self.assertEqual(call["request_payload"], {"set_id": 12, "source": "slash_command"})
        self.assertIs(call["source_message"], message)

    async def test_command_cancellation_marks_interruption_and_propagates(self) -> None:
        async def cancel_analysis(*args, **kwargs):
            raise asyncio.CancelledError

        module._analyze_set = cancel_analysis
        message = FakeMessage()
        command = SimpleNamespace(args="12")

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_set_analysis_command(message, command, object(), object())

        self.assertEqual(
            FakeTrackerFactory.tracker.errors,
            ["Задание прервано остановкой процесса."],
        )


if __name__ == "__main__":
    unittest.main()
