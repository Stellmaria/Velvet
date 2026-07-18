from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

import velvet_bot.handlers.velvet_ai as module


class FakeMessage:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(id=23)
        self.from_user = SimpleNamespace(id=17)
        self.answers: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs) -> None:
        self.answers.append((args, kwargs))


class FakeTracker:
    def __init__(self) -> None:
        self.job_id = 61
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


class PromptResultJobBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_result_file = module._result_file
        self.original_settings = module.load_settings
        self.original_tracker = module.AIJobTracker
        self.original_download = module._download_image
        self.original_sessions = dict(module._sessions)

        module._result_file = lambda message: ('result-file', 'result-unique')
        module.load_settings = lambda: SimpleNamespace(
            ai_vision_enabled=True,
            ai_vision_provider='ollama',
            ai_vision_model='qwen',
        )
        FakeTrackerFactory.tracker = FakeTracker()
        FakeTrackerFactory.create_calls = []
        module.AIJobTracker = FakeTrackerFactory
        module._sessions.clear()
        module._sessions[(23, 17)] = module.PromptCheckSession(
            prompt_text='A sufficiently detailed prompt for comparison.',
            created_at=datetime.now(UTC),
        )

    def tearDown(self) -> None:
        module._result_file = self.original_result_file
        module.load_settings = self.original_settings
        module.AIJobTracker = self.original_tracker
        module._download_image = self.original_download
        module._sessions.clear()
        module._sessions.update(self.original_sessions)

    async def test_failure_marks_job_error_and_keeps_prompt_session(self) -> None:
        error = RuntimeError('download failed')

        async def fail_download(bot, file_id):
            raise error

        module._download_image = fail_download
        message = FakeMessage()
        database = object()

        await module.handle_prompt_check_reply(
            message,
            'image',
            database,
            object(),
        )

        tracker = FakeTrackerFactory.tracker
        self.assertEqual(tracker.stages, ['downloading'])
        self.assertEqual(tracker.errors, [error])
        self.assertEqual(tracker.ready_calls, [])
        self.assertIn((23, 17), module._sessions)
        self.assertEqual(len(FakeTrackerFactory.create_calls), 1)
        call = FakeTrackerFactory.create_calls[0]
        self.assertIs(call['database'], database)
        self.assertIs(call['source_message'], message)
        self.assertEqual(call['kind'], 'prompt_result')
        self.assertEqual(call['title'], 'Промт против результата')
        self.assertEqual(call['provider'], 'ollama')
        self.assertEqual(call['model'], 'qwen')
        self.assertEqual(
            call['request_payload'],
            {
                'result_file_id': 'result-file',
                'result_file_unique_id': 'result-unique',
                'prompt_length': len(module._sessions[(23, 17)].prompt_text),
            },
        )

    async def test_cancellation_marks_interruption_keeps_session_and_propagates(self) -> None:
        async def cancel_download(bot, file_id):
            raise asyncio.CancelledError

        module._download_image = cancel_download

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_prompt_check_reply(
                FakeMessage(),
                'image',
                object(),
                object(),
            )

        tracker = FakeTrackerFactory.tracker
        self.assertEqual(tracker.stages, ['downloading'])
        self.assertEqual(
            tracker.errors,
            ['Задание прервано остановкой процесса.'],
        )
        self.assertEqual(tracker.ready_calls, [])
        self.assertIn((23, 17), module._sessions)

    async def test_compensation_failure_is_not_silently_swallowed(self) -> None:
        primary_error = RuntimeError('provider failed')
        compensation_error = RuntimeError('job persistence failed')

        async def fail_download(bot, file_id):
            raise primary_error

        async def fail_error(value):
            raise compensation_error

        module._download_image = fail_download
        FakeTrackerFactory.tracker.error = fail_error

        with self.assertRaises(RuntimeError) as captured:
            await module.handle_prompt_check_reply(
                FakeMessage(),
                'image',
                object(),
                object(),
            )

        self.assertIs(captured.exception, compensation_error)
        self.assertIn((23, 17), module._sessions)


if __name__ == '__main__':
    unittest.main()
