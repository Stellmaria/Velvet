from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.handlers.reference_comparison_help as module


class FakeMessage:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=17)
        self.answers: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs) -> None:
        self.answers.append((args, kwargs))


class FakeTracker:
    def __init__(self) -> None:
        self.job_id = 51
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


class ReferenceFormJobBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_result_file = module._result_file
        self.original_get_page = module.get_reference_page
        self.original_settings = module.load_settings
        self.original_tracker = module.AIJobTracker
        self.original_download = module._download_file

        module._result_file = lambda message: ('result-file', 'result-unique')

        async def get_page(database, character_id, offset):
            return SimpleNamespace(
                character=SimpleNamespace(id=7, name='Ada'),
                reference=SimpleNamespace(id=11, telegram_file_id='reference-file'),
                offset=2,
                total=4,
            )

        module.get_reference_page = get_page
        module.load_settings = lambda: SimpleNamespace(
            ai_vision_enabled=True,
            ai_vision_provider='ollama',
            ai_vision_model='qwen',
        )
        FakeTrackerFactory.tracker = FakeTracker()
        FakeTrackerFactory.create_calls = []
        module.AIJobTracker = FakeTrackerFactory

    def tearDown(self) -> None:
        module._result_file = self.original_result_file
        module.get_reference_page = self.original_get_page
        module.load_settings = self.original_settings
        module.AIJobTracker = self.original_tracker
        module._download_file = self.original_download

    async def test_failure_marks_created_job_error(self) -> None:
        error = RuntimeError('comparison failed')

        async def fail_download(bot, file_id):
            raise error

        module._download_file = fail_download
        message = FakeMessage()
        database = object()

        await module.handle_reference_comparison_reply(
            message,
            7,
            11,
            2,
            database,
            object(),
        )

        tracker = FakeTrackerFactory.tracker
        self.assertEqual(tracker.stages, ['downloading'])
        self.assertEqual(tracker.errors, [error])
        self.assertEqual(tracker.ready_calls, [])
        self.assertEqual(len(FakeTrackerFactory.create_calls), 1)
        call = FakeTrackerFactory.create_calls[0]
        self.assertIs(call['database'], database)
        self.assertIs(call['source_message'], message)
        self.assertEqual(call['kind'], 'reference_comparison')
        self.assertEqual(call['provider'], 'ollama')
        self.assertEqual(call['model'], 'qwen')
        self.assertEqual(
            call['request_payload'],
            {
                'character_id': 7,
                'reference_id': 11,
                'reference_index': 3,
                'result_file_id': 'result-file',
                'result_file_unique_id': 'result-unique',
            },
        )

    async def test_cancellation_marks_interruption_and_propagates(self) -> None:
        async def cancel_download(bot, file_id):
            raise asyncio.CancelledError

        module._download_file = cancel_download

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_reference_comparison_reply(
                FakeMessage(),
                7,
                11,
                2,
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

    async def test_compensation_failure_is_not_silently_swallowed(self) -> None:
        primary_error = RuntimeError('provider failed')
        compensation_error = RuntimeError('job write failed')

        async def fail_download(bot, file_id):
            raise primary_error

        async def fail_error(value):
            raise compensation_error

        module._download_file = fail_download
        FakeTrackerFactory.tracker.error = fail_error

        with self.assertRaises(RuntimeError) as captured:
            await module.handle_reference_comparison_reply(
                FakeMessage(),
                7,
                11,
                2,
                object(),
                object(),
            )

        self.assertIs(captured.exception, compensation_error)


if __name__ == '__main__':
    unittest.main()
