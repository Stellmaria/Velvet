from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.handlers.velvet_ai_formatting as module


class FakeMessage:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=17)
        self.answers: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs) -> None:
        self.answers.append((args, kwargs))


class FakeTracker:
    def __init__(self) -> None:
        self.job_id = 71
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


class FakeLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeFormattingClient:
    failure: BaseException | None = None

    def __init__(self, **kwargs) -> None:
        self.provider = kwargs['provider']
        self.model = kwargs['model']

    async def format(self, mode, source):
        if self.failure is not None:
            raise self.failure
        return {'title': 'unused'}


class FormattingBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_source_text = module._source_text
        self.original_settings = module.load_settings
        self.original_tracker = module.AIJobTracker
        self.original_client = module.VelvetFormattingClient
        self.original_lock = module.get_local_ai_lock

        module.load_settings = lambda: SimpleNamespace(
            ai_vision_enabled=True,
            ai_vision_provider='ollama',
            ai_vision_base_url='http://localhost',
            ai_vision_model='qwen',
            ai_vision_api_key=None,
            ai_vision_timeout_seconds=90,
        )
        FakeTrackerFactory.tracker = FakeTracker()
        FakeTrackerFactory.create_calls = []
        module.AIJobTracker = FakeTrackerFactory
        FakeFormattingClient.failure = None
        module.VelvetFormattingClient = FakeFormattingClient
        module.get_local_ai_lock = lambda: FakeLock()

    def tearDown(self) -> None:
        module._source_text = self.original_source_text
        module.load_settings = self.original_settings
        module.AIJobTracker = self.original_tracker
        module.VelvetFormattingClient = self.original_client
        module.get_local_ai_lock = self.original_lock

    async def test_expected_value_error_is_answered_before_job_creation(self) -> None:
        async def fail_source(message, bot):
            raise ValueError('file too large')

        module._source_text = fail_source
        message = FakeMessage()

        await module.handle_formatting_reply(message, 'shell', object(), object())

        self.assertEqual(len(message.answers), 1)
        self.assertIn('file too large', message.answers[0][0][0])
        self.assertEqual(FakeTrackerFactory.create_calls, [])

    async def test_expected_runtime_error_is_answered_before_job_creation(self) -> None:
        async def fail_source(message, bot):
            raise RuntimeError('download failed')

        module._source_text = fail_source
        message = FakeMessage()

        await module.handle_formatting_reply(message, 'short', object(), object())

        self.assertEqual(len(message.answers), 1)
        self.assertIn('download failed', message.answers[0][0][0])
        self.assertEqual(FakeTrackerFactory.create_calls, [])

    async def test_unexpected_source_type_error_is_not_swallowed(self) -> None:
        error = TypeError('broken source adapter')

        async def fail_source(message, bot):
            raise error

        module._source_text = fail_source

        with self.assertRaises(TypeError) as captured:
            await module.handle_formatting_reply(FakeMessage(), 'full', object(), object())

        self.assertIs(captured.exception, error)
        self.assertEqual(FakeTrackerFactory.create_calls, [])

    async def test_source_cancellation_is_not_swallowed(self) -> None:
        async def cancel_source(message, bot):
            raise asyncio.CancelledError

        module._source_text = cancel_source

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_formatting_reply(FakeMessage(), 'shell', object(), object())

        self.assertEqual(FakeTrackerFactory.create_calls, [])

    async def test_job_failure_marks_tracker_error_with_request_metadata(self) -> None:
        source = 'Detailed Velvet source material.'

        async def source_text(message, bot):
            return source

        error = RuntimeError('format provider failed')
        module._source_text = source_text
        FakeFormattingClient.failure = error
        message = FakeMessage()
        database = object()

        await module.handle_formatting_reply(message, 'short', database, object())

        tracker = FakeTrackerFactory.tracker
        self.assertEqual(tracker.stages, ['analyzing'])
        self.assertEqual(tracker.errors, [error])
        self.assertEqual(tracker.ready_calls, [])
        self.assertEqual(len(FakeTrackerFactory.create_calls), 1)
        call = FakeTrackerFactory.create_calls[0]
        self.assertIs(call['database'], database)
        self.assertIs(call['source_message'], message)
        self.assertEqual(call['kind'], 'velvet_formatting')
        self.assertEqual(call['provider'], 'ollama')
        self.assertEqual(call['model'], 'qwen')
        self.assertEqual(
            call['request_payload'],
            {'mode': 'short', 'source_length': len(source)},
        )

    async def test_job_cancellation_marks_interruption_and_propagates(self) -> None:
        async def source_text(message, bot):
            return 'Detailed Velvet source material.'

        module._source_text = source_text
        FakeFormattingClient.failure = asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_formatting_reply(FakeMessage(), 'full', object(), object())

        tracker = FakeTrackerFactory.tracker
        self.assertEqual(tracker.stages, ['analyzing'])
        self.assertEqual(
            tracker.errors,
            ['Задание прервано остановкой процесса.'],
        )
        self.assertEqual(tracker.ready_calls, [])

    async def test_compensation_failure_is_not_silently_swallowed(self) -> None:
        async def source_text(message, bot):
            return 'Detailed Velvet source material.'

        provider_error = RuntimeError('provider failed')
        compensation_error = RuntimeError('job write failed')

        async def fail_error(value):
            raise compensation_error

        module._source_text = source_text
        FakeFormattingClient.failure = provider_error
        FakeTrackerFactory.tracker.error = fail_error

        with self.assertRaises(RuntimeError) as captured:
            await module.handle_formatting_reply(FakeMessage(), 'shell', object(), object())

        self.assertIs(captured.exception, compensation_error)


if __name__ == '__main__':
    unittest.main()
