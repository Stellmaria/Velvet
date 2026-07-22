from __future__ import annotations

import unittest

import asyncpg

from velvet_bot.presentation.telegram.router import _is_transient_telegram_error


class RootTelegramErrorClassificationTests(unittest.TestCase):
    def test_transient_telegram_transport_error_is_recoverable(self) -> None:
        error = RuntimeError(
            "TelegramNetworkError: HTTP Client says - ClientConnectorError: "
            "Cannot connect to host api.telegram.org:443"
        )
        self.assertTrue(_is_transient_telegram_error(error))

    def test_database_disconnect_is_not_misclassified_as_telegram(self) -> None:
        error = asyncpg.ConnectionDoesNotExistError(
            "connection was closed in the middle of operation"
        )
        self.assertFalse(_is_transient_telegram_error(error))

    def test_regular_handler_error_remains_non_recoverable(self) -> None:
        self.assertFalse(_is_transient_telegram_error(ValueError("bad payload")))


if __name__ == "__main__":
    unittest.main()
