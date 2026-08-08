from __future__ import annotations

import asyncio
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.application.arthur_librarian import ArthurLibrarianApplication
from velvet_bot.domains.telegram_storage.arthur_repository import (
    ArthurStorageLibrarianRepository,
)
from velvet_bot.domains.telegram_storage.librarian_models import StorageLibrarianError


ROOT = Path(__file__).resolve().parents[1]


class _FakeRepository:
    def __init__(self) -> None:
        self.enqueue_calls = 0
        self.phase_entries = 0
        self.phase_active = False

    @asynccontextmanager
    async def full_archive_phase(self):
        self.phase_entries += 1
        self.phase_active = True
        try:
            yield
        finally:
            self.phase_active = False

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


class _FailingPhaseRepository(_FakeRepository):
    @asynccontextmanager
    async def full_archive_phase(self):
        raise StorageLibrarianError("archive lease unavailable")
        yield  # pragma: no cover


class _FakeService:
    def __init__(self) -> None:
        self.processed = 0

    async def process_once(self, *, auto_enqueue: bool) -> int:
        self.processed += 1
        return 1


class _Acquire:
    def __init__(self, connection: object) -> None:
        self.connection = connection

    async def __aenter__(self) -> object:
        return self.connection

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeDatabase:
    def __init__(self, connection: object) -> None:
        self.connection = connection

    def acquire(self) -> _Acquire:
        return _Acquire(self.connection)


class ArthurArchiveRepositoryLeaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_inactive_phase_probe_releases_temporary_advisory_lock(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(side_effect=[True, True]))
        repository = ArthurStorageLibrarianRepository(  # type: ignore[arg-type]
            _FakeDatabase(connection)
        )

        self.assertFalse(await repository.full_archive_phase_active())
        self.assertEqual(2, connection.fetchval.await_count)
        self.assertIn("pg_try_advisory_lock", connection.fetchval.await_args_list[0].args[0])
        self.assertIn("pg_advisory_unlock", connection.fetchval.await_args_list[1].args[0])

    async def test_active_phase_probe_does_not_unlock_foreign_lease(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(return_value=False))
        repository = ArthurStorageLibrarianRepository(  # type: ignore[arg-type]
            _FakeDatabase(connection)
        )

        self.assertTrue(await repository.full_archive_phase_active())
        connection.fetchval.assert_awaited_once()

    async def test_phase_context_holds_and_releases_one_session_lock(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(side_effect=[True, True]))
        repository = ArthurStorageLibrarianRepository(  # type: ignore[arg-type]
            _FakeDatabase(connection)
        )

        async with repository.full_archive_phase():
            self.assertEqual(1, connection.fetchval.await_count)

        self.assertEqual(2, connection.fetchval.await_count)
        self.assertIn("pg_try_advisory_lock", connection.fetchval.await_args_list[0].args[0])
        self.assertIn("pg_advisory_unlock", connection.fetchval.await_args_list[1].args[0])


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

    async def test_start_holds_phase_before_reporting_success(self) -> None:
        app, repository, _ = self._application()

        self.assertTrue(await app.start_archive())
        self.assertTrue(repository.phase_active)
        self.assertEqual(1, repository.phase_entries)

        await app.shutdown()
        self.assertFalse(repository.phase_active)

    async def test_start_fails_without_creating_task_when_phase_lease_unavailable(self) -> None:
        app, _, _ = self._application()
        app.repository = _FailingPhaseRepository()

        with self.assertRaisesRegex(StorageLibrarianError, "archive lease unavailable"):
            await app.start_archive()

        self.assertIsNone(app._archive_task)

    async def test_start_is_idempotent_and_stop_is_cooperative(self) -> None:
        app, repository, service = self._application()

        self.assertTrue(await app.start_archive())
        self.assertTrue(repository.phase_active)
        self.assertFalse(await app.start_archive())

        status = await app.archive_status()
        self.assertTrue(status.active)
        self.assertFalse(status.stopping)
        self.assertEqual("test-archive:v1", status.analyzer_version)

        self.assertTrue(await app.stop_archive())
        self.assertTrue(repository.phase_active)
        stopping = await app.archive_status()
        self.assertTrue(stopping.active)
        self.assertTrue(stopping.stopping)

        await app.shutdown()
        stopped = await app.archive_status()
        self.assertFalse(stopped.active)
        self.assertFalse(repository.phase_active)
        self.assertEqual(1, repository.phase_entries)
        self.assertGreaterEqual(repository.enqueue_calls, 0)
        self.assertGreaterEqual(service.processed, 0)

    async def test_stop_when_idle_is_noop(self) -> None:
        app, repository, _ = self._application()
        self.assertFalse(await app.stop_archive())
        self.assertFalse(repository.phase_active)


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
        self.assertIn("archive_phase = self.repository.full_archive_phase()", application)
        self.assertIn("await archive_phase.__aenter__()", application)
        self.assertIn("stop_event.wait()", application)


if __name__ == "__main__":
    unittest.main()
