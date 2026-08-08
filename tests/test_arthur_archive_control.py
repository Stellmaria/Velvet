from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace

from velvet_bot.application.arthur_librarian import ArthurLibrarianApplication


ROOT = Path(__file__).resolve().parents[1]


class _FakeRepository:
    def __init__(self) -> None:
        self.enqueue_calls = 0

    async def enqueue_pending(self, *, settings: object, limit: int) -> int:
        self.enqueue_calls += 1
        return 1

    async def counts(self) -> dict[str, int]:
        return {
            "queued": 3,
            "running": 1,
            "completed": 7,
            "failed": 0,
            "skipped": 0,
        }


class _FakeService:
    def __init__(self) -> None:
        self.processed = 0

    async def process_once(self, *, auto_enqueue: bool) -> int:
        self.processed += 1
        return 1


class ArthurArchiveControlTests(unittest.IsolatedAsyncioTestCase):
    def _application(self) -> tuple[ArthurLibrarianApplication, _FakeRepository, _FakeService]:
        app = ArthurLibrarianApplication.__new__(ArthurLibrarianApplication)
        repository = _FakeRepository()
        service = _FakeService()
        app.librarian_settings = SimpleNamespace(
            enabled=True,
            analyzer_version="test-archive:v1",
            scan_interval_seconds=60,
        )
        app.repository = repository
        app._analysis_lock = asyncio.Lock()
        app._archive_control_lock = asyncio.Lock()
        app._archive_stop_event = asyncio.Event()
        app._archive_task = None
        app._archive_last_error = None
        app._service = lambda **_: service  # type: ignore[method-assign]
        return app, repository, service

    async def test_start_is_idempotent_and_stop_is_cooperative(self) -> None:
        app, repository, service = self._application()

        self.assertTrue(await app.start_archive())
        self.assertFalse(await app.start_archive())
        await asyncio.sleep(0)

        status = await app.archive_status()
        self.assertTrue(status.active)
        self.assertFalse(status.stopping)
        self.assertEqual("test-archive:v1", status.analyzer_version)

        self.assertTrue(await app.stop_archive())
        stopping = await app.archive_status()
        self.assertTrue(stopping.active)
        self.assertTrue(stopping.stopping)

        await app.shutdown()
        stopped = await app.archive_status()
        self.assertFalse(stopped.active)
        self.assertGreaterEqual(repository.enqueue_calls, 1)
        self.assertGreaterEqual(service.processed, 0)

    async def test_stop_when_idle_is_noop(self) -> None:
        app, _, _ = self._application()
        self.assertFalse(await app.stop_archive())


class ArthurArchiveTelegramContractTests(unittest.TestCase):
    def test_archive_command_and_runtime_shutdown_are_wired(self) -> None:
        presentation = (
            ROOT
            / "velvet_bot"
            / "presentation"
            / "telegram"
            / "arthur_librarian.py"
        ).read_text(encoding="utf-8")
        runtime = (
            ROOT
            / "velvet_bot"
            / "presentation"
            / "telegram"
            / "arthur_runtime.py"
        ).read_text(encoding="utf-8")
        application = (
            ROOT
            / "velvet_bot"
            / "application"
            / "arthur_librarian.py"
        ).read_text(encoding="utf-8")

        self.assertIn('Command("archive")', presentation)
        self.assertIn('action == "start"', presentation)
        self.assertIn('action == "stop"', presentation)
        self.assertIn('action == "status"', presentation)
        self.assertIn('KeyboardButton(text="/archive start")', presentation)
        self.assertIn('KeyboardButton(text="/archive stop")', presentation)
        self.assertIn('KeyboardButton(text="/archive status")', presentation)
        self.assertIn("await arthur_app.start_archive()", presentation)
        self.assertIn("await arthur_app.stop_archive()", presentation)
        self.assertIn('BotCommand(command="archive"', runtime)
        self.assertIn("await application.shutdown()", runtime)
        self.assertIn("await self.repository.enqueue_pending(", application)
        self.assertIn("self._analysis_lock = asyncio.Lock()", application)
        self.assertIn("stop_event.wait()", application)


if __name__ == "__main__":
    unittest.main()
