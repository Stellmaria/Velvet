from __future__ import annotations

import asyncio
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncpg

from velvet_bot.infrastructure.transient_connections import (
    RecoverablePollingNoiseFilter,
    install_recoverable_polling_filter,
    is_recoverable_diagnostic_delivery,
    is_recoverable_polling_message,
    is_transient_connection_error,
    looks_like_transient_connection_message,
    recover_database_pool,
)
from velvet_bot.workers import PeriodicWorkerSpec, WorkerManager


class TransientConnectionClassifierTests(unittest.TestCase):
    def test_asyncpg_connection_closed_is_transient(self) -> None:
        error = asyncpg.ConnectionDoesNotExistError(
            "connection was closed in the middle of operation"
        )
        self.assertTrue(is_transient_connection_error(error))

    def test_windows_local_abort_message_is_transient(self) -> None:
        self.assertTrue(
            looks_like_transient_connection_message(
                "ClientOSError: [WinError 1236] Подключение к сети было разорвано"
            )
        )

    def test_request_timeout_message_is_transient(self) -> None:
        self.assertTrue(
            looks_like_transient_connection_message(
                "TelegramNetworkError: HTTP Client says - Request timeout error"
            )
        )

    def test_regular_application_error_is_not_transient(self) -> None:
        self.assertFalse(is_transient_connection_error(ValueError("bad payload")))

    def test_polling_filter_drops_recoverable_aiogram_record(self) -> None:
        record = logging.LogRecord(
            "aiogram.dispatcher",
            logging.ERROR,
            "dispatcher.py",
            1,
            (
                "Failed to fetch updates - TelegramNetworkError: HTTP Client says - "
                "ClientOSError: [WinError 1236] network connection aborted"
            ),
            (),
            None,
        )
        self.assertFalse(RecoverablePollingNoiseFilter().filter(record))

    def test_polling_filter_drops_bad_gateway_record(self) -> None:
        message = (
            "Failed to fetch updates - TelegramServerError: "
            "Telegram server says - Bad Gateway"
        )
        record = logging.LogRecord(
            "aiogram.dispatcher",
            logging.ERROR,
            "dispatcher.py",
            1,
            message,
            (),
            None,
        )
        self.assertTrue(is_recoverable_polling_message(message))
        self.assertFalse(RecoverablePollingNoiseFilter().filter(record))

    def test_polling_filter_drops_retry_after_record(self) -> None:
        message = (
            "Failed to fetch updates - TelegramRetryAfter: Telegram server says - "
            "Flood control exceeded on method 'GetUpdates'. Retry in 5 seconds. "
            "Original description: Too Many Requests: retry after 5"
        )
        record = logging.LogRecord(
            "aiogram.dispatcher",
            logging.ERROR,
            "dispatcher.py",
            1,
            message,
            (),
            None,
        )
        self.assertTrue(is_recoverable_polling_message(message))
        self.assertFalse(RecoverablePollingNoiseFilter().filter(record))

    def test_filter_drops_transient_diagnostic_delivery_feedback(self) -> None:
        message = (
            "Could not deliver automatic diagnostic bundle to owner 7221553045: "
            "Telegram server says - Bad Gateway"
        )
        record = logging.LogRecord(
            "velvet_bot.services.diagnostic_bundle",
            logging.WARNING,
            "diagnostic_bundle.py",
            1,
            message,
            (),
            None,
        )
        self.assertTrue(
            is_recoverable_diagnostic_delivery(record.name, message)
        )
        self.assertFalse(RecoverablePollingNoiseFilter().filter(record))

    def test_polling_filter_keeps_non_network_error(self) -> None:
        record = logging.LogRecord(
            "aiogram.dispatcher",
            logging.ERROR,
            "dispatcher.py",
            1,
            "Unhandled update handler error",
            (),
            None,
        )
        self.assertTrue(RecoverablePollingNoiseFilter().filter(record))

    def test_filter_installation_is_idempotent(self) -> None:
        handler = logging.NullHandler()
        center = SimpleNamespace(_handler=handler)
        self.assertTrue(install_recoverable_polling_filter(center))
        self.assertTrue(install_recoverable_polling_filter(center))
        filters = [item for item in handler.filters if isinstance(item, RecoverablePollingNoiseFilter)]
        self.assertEqual(1, len(filters))


class TransientConnectionRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_pool_connections_are_expired(self) -> None:
        pool = SimpleNamespace(expire_connections=AsyncMock())
        database = SimpleNamespace(_pool=pool)
        error = asyncpg.ConnectionDoesNotExistError("connection closed")

        await recover_database_pool(database, error)

        pool.expire_connections.assert_awaited_once_with()

    async def test_worker_recovers_on_next_scheduled_iteration(self) -> None:
        calls = 0
        recovery = AsyncMock()

        async def runner() -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise asyncpg.ConnectionDoesNotExistError(
                    "connection was closed in the middle of operation"
                )

        manager = WorkerManager(transient_failure_handler=recovery)
        manager.register(
            PeriodicWorkerSpec(
                name="network-worker",
                description="Network worker",
                interval_seconds=0.01,
                runner=runner,
            )
        )
        await manager.start_all()
        try:
            for _ in range(100):
                snapshot = manager.snapshot("network-worker")
                if snapshot is not None and snapshot.successful_runs >= 1:
                    break
                await asyncio.sleep(0.01)
            snapshot = manager.snapshot("network-worker")
            self.assertIsNotNone(snapshot)
            assert snapshot is not None
            self.assertEqual(1, snapshot.failed_runs)
            self.assertGreaterEqual(snapshot.successful_runs, 1)
            self.assertEqual(0, snapshot.consecutive_failures)
            recovery.assert_awaited_once()
        finally:
            await manager.stop_all()

    async def test_persistent_outage_opens_one_generic_alert_at_threshold(self) -> None:
        async def runner() -> None:
            raise asyncpg.ConnectionDoesNotExistError(
                "connection was closed in the middle of operation"
            )

        async def recover(_: BaseException) -> None:
            return None

        manager = WorkerManager(transient_failure_handler=recover)
        manager.register(
            PeriodicWorkerSpec(
                name="persistent-worker",
                description="Persistent worker",
                interval_seconds=60,
                runner=runner,
                run_immediately=False,
            )
        )
        await manager.start_all()
        try:
            self.assertFalse(await manager.run_now("persistent-worker"))
            self.assertFalse(await manager.run_now("persistent-worker"))
            with self.assertLogs("velvet_bot.workers.manager", level="ERROR") as logs:
                self.assertFalse(await manager.run_now("persistent-worker"))
            self.assertEqual(1, len(logs.output))
            self.assertIn("transient outage persists", logs.output[0])
        finally:
            await manager.stop_all()


if __name__ == "__main__":
    unittest.main()
