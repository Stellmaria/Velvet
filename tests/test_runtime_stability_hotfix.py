from __future__ import annotations

import logging
import unittest

import velvet_bot.error_center as error_center
import velvet_bot.runtime_stability as module


def _record(
    message: str,
    *,
    level: int = logging.ERROR,
    name: str = "aiogram.dispatcher",
) -> logging.LogRecord:
    return logging.LogRecord(name, level, "test.py", 10, message, (), None)


class _Connection:
    def __init__(self, result: str = "UPDATE 3") -> None:
        self.result = result
        self.queries: list[str] = []

    async def execute(self, query: str) -> str:
        self.queries.append(query)
        return self.result


class _Acquire:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _Database:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def acquire(self) -> _Acquire:
        return _Acquire(self.connection)


class RuntimeStabilityTests(unittest.IsolatedAsyncioTestCase):
    def test_filters_transient_connector_failures(self) -> None:
        messages = (
            "Failed to fetch updates - TelegramNetworkError: "
            "ClientConnectorError: Cannot connect to host api.telegram.org:443",
            "Failed to fetch updates - TelegramNetworkError: "
            "ClientConnectorError: Превышен таймаут семафора",
            "Failed to fetch updates - TelegramNetworkError: ServerDisconnectedError",
            "Sleep for 1.000000 seconds and try again... (tryings = 0)",
        )
        for message in messages:
            with self.subTest(message=message):
                self.assertTrue(
                    module.is_recoverable_aiogram_polling_record(_record(message))
                )

    def test_keeps_non_network_polling_failures(self) -> None:
        messages = (
            "Failed to fetch updates - TelegramConflictError: "
            "terminated by other getUpdates request",
            "Unhandled bot error: database unavailable",
        )
        for message in messages:
            with self.subTest(message=message):
                self.assertFalse(
                    module.is_recoverable_aiogram_polling_record(_record(message))
                )
        self.assertFalse(
            module.is_recoverable_aiogram_polling_record(
                _record(
                    "Failed to fetch updates - TelegramNetworkError: ClientConnectorError",
                    name="velvet_bot.worker",
                )
            )
        )

    async def test_acknowledges_only_known_legacy_noise(self) -> None:
        connection = _Connection()
        repository = type(
            "Repository",
            (),
            {"_database": _Database(connection)},
        )()

        updated = await module.acknowledge_legacy_polling_noise(repository)

        self.assertEqual(updated, 3)
        self.assertEqual(len(connection.queries), 1)
        query = connection.queries[0].casefold()
        self.assertIn("logger_name = 'aiogram.dispatcher'", query)
        self.assertIn("telegramnetworkerror", query)
        self.assertIn("clientconnectorerror", query)
        self.assertIn("sleep for % seconds and try again", query)
        self.assertIn("velvet_bot.presentation.telegram.router", query)
        self.assertIn("подключение к сети было разорвано", query)

    async def test_missing_database_is_safe(self) -> None:
        self.assertEqual(
            0,
            await module.acknowledge_legacy_polling_noise(object()),
        )

    def test_install_is_idempotent_and_replaces_filter(self) -> None:
        previous_installed = module._INSTALLED
        previous_original = module._ORIGINAL_ERROR_CENTER_START
        previous_filter = error_center._is_recoverable_aiogram_polling_record
        previous_start = error_center.ErrorIncidentCenter.start
        try:
            module._INSTALLED = False
            module._ORIGINAL_ERROR_CENTER_START = None
            module.install_runtime_stability()
            installed_start = error_center.ErrorIncidentCenter.start
            module.install_runtime_stability()

            self.assertIs(
                error_center._is_recoverable_aiogram_polling_record,
                module.is_recoverable_aiogram_polling_record,
            )
            self.assertIs(error_center.ErrorIncidentCenter.start, installed_start)
        finally:
            error_center._is_recoverable_aiogram_polling_record = previous_filter
            error_center.ErrorIncidentCenter.start = previous_start
            module._INSTALLED = previous_installed
            module._ORIGINAL_ERROR_CENTER_START = previous_original


if __name__ == "__main__":
    unittest.main()
