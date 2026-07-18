from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.handlers.velvet_ai_visual as module


class FakeMessage:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=17)
        self.photo_calls: list[dict[str, object]] = []
        self.photo_error: BaseException | None = None

    async def answer(self, *args, **kwargs) -> None:
        raise AssertionError('unexpected text answer')

    async def answer_photo(self, *args, **kwargs) -> None:
        self.photo_calls.append({'args': args, **kwargs})
        if self.photo_error is not None:
            raise self.photo_error


class FakeTracker:
    def __init__(self) -> None:
        self.job_id = 81
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


class FakeCompositionClient:
    failure: BaseException | None = None
    report: dict[str, object] = {'verdict': 'strong'}

    def __init__(self, **kwargs) -> None:
        self.provider = kwargs['provider']
        self.model = kwargs['model']

    async def analyze_composition(self, image, metrics):
        if self.failure is not None:
            raise self.failure
        return self.report


class FakeReportRepository:
    save_calls: list[dict[str, object]] = []

    def __init__(self, database) -> None:
        self.database = database

    async def save(self, **kwargs) -> int:
        self.save_calls.append(kwargs)
        return 91


class VisualAnalysisJobBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_result_file = module._result_file
        self.original_settings = module.load_settings
        self.original_tracker = module.AIJobTracker
        self.original_download = module._download_image
        self.original_extract = module.extract_palette_metrics
        self.original_client = module.CompositionAnalysisClient
        self.original_lock = module.get_local_ai_lock
        self.original_repository = module.PaletteCompositionReportRepository
        self.original_build_card = module.build_palette_card
        self.original_report_text = module._report_text
        self.original_palette_line = module._palette_line

        module._result_file = lambda message: ('result-file', 'result-unique')
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
        FakeCompositionClient.failure = None
        FakeCompositionClient.report = {'verdict': 'strong'}
        module.CompositionAnalysisClient = FakeCompositionClient
        module.get_local_ai_lock = lambda: FakeLock()
        FakeReportRepository.save_calls = []
        module.PaletteCompositionReportRepository = FakeReportRepository
        module.extract_palette_metrics = lambda image: SimpleNamespace(colors=[])
        module.build_palette_card = lambda metrics: b'palette-card'
        module._report_text = lambda report_id, metrics, report: 'rendered report'
        module._palette_line = lambda metrics: 'palette line'

    def tearDown(self) -> None:
        module._result_file = self.original_result_file
        module.load_settings = self.original_settings
        module.AIJobTracker = self.original_tracker
        module._download_image = self.original_download
        module.extract_palette_metrics = self.original_extract
        module.CompositionAnalysisClient = self.original_client
        module.get_local_ai_lock = self.original_lock
        module.PaletteCompositionReportRepository = self.original_repository
        module.build_palette_card = self.original_build_card
        module._report_text = self.original_report_text
        module._palette_line = self.original_palette_line

    async def test_failure_marks_job_error_with_request_metadata(self) -> None:
        error = RuntimeError('image download failed')

        async def fail_download(bot, file_id):
            raise error

        module._download_image = fail_download
        message = FakeMessage()
        database = object()

        await module.handle_visual_analysis_reply(message, database, object())

        tracker = FakeTrackerFactory.tracker
        self.assertEqual(tracker.stages, ['downloading'])
        self.assertEqual(tracker.errors, [error])
        self.assertEqual(tracker.ready_calls, [])
        self.assertEqual(message.photo_calls, [])
        call = FakeTrackerFactory.create_calls[0]
        self.assertIs(call['database'], database)
        self.assertIs(call['source_message'], message)
        self.assertEqual(call['kind'], 'palette_composition')
        self.assertEqual(call['provider'], 'ollama')
        self.assertEqual(call['model'], 'qwen')
        self.assertEqual(
            call['request_payload'],
            {
                'result_file_id': 'result-file',
                'result_file_unique_id': 'result-unique',
            },
        )

    async def test_cancellation_marks_interruption_and_propagates(self) -> None:
        async def cancel_download(bot, file_id):
            raise asyncio.CancelledError

        module._download_image = cancel_download

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_visual_analysis_reply(FakeMessage(), object(), object())

        tracker = FakeTrackerFactory.tracker
        self.assertEqual(tracker.stages, ['downloading'])
        self.assertEqual(
            tracker.errors,
            ['Задание прервано остановкой процесса.'],
        )
        self.assertEqual(tracker.ready_calls, [])

    async def test_compensation_failure_is_not_silently_swallowed(self) -> None:
        primary_error = RuntimeError('analysis failed')
        compensation_error = RuntimeError('job write failed')

        async def fail_download(bot, file_id):
            raise primary_error

        async def fail_error(value):
            raise compensation_error

        module._download_image = fail_download
        FakeTrackerFactory.tracker.error = fail_error

        with self.assertRaises(RuntimeError) as captured:
            await module.handle_visual_analysis_reply(FakeMessage(), object(), object())

        self.assertIs(captured.exception, compensation_error)

    async def test_palette_delivery_failure_does_not_reopen_ready_job(self) -> None:
        async def download(bot, file_id):
            return b'image'

        module._download_image = download
        message = FakeMessage()
        delivery_error = RuntimeError('telegram send failed')
        message.photo_error = delivery_error

        with self.assertRaises(RuntimeError) as captured:
            await module.handle_visual_analysis_reply(message, object(), object())

        self.assertIs(captured.exception, delivery_error)
        tracker = FakeTrackerFactory.tracker
        self.assertEqual(
            tracker.stages,
            ['downloading', 'preparing', 'analyzing', 'saving'],
        )
        self.assertEqual(tracker.errors, [])
        self.assertEqual(len(tracker.ready_calls), 1)
        ready = tracker.ready_calls[0]
        self.assertEqual(ready['reference_type'], 'palette_composition_report')
        self.assertEqual(ready['reference_id'], 91)
        self.assertEqual(len(message.photo_calls), 1)


if __name__ == '__main__':
    unittest.main()
