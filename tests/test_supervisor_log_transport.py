from __future__ import annotations

import logging
import os
import unittest
from unittest.mock import patch

from velvet_bot.error_center import ErrorLoggingHandler
from velvet_supervisor.runtime import _child_environment, _looks_like_error


class _CapturedCenter:
    def __init__(self) -> None:
        self.items = []

    def enqueue_threadsafe(self, captured) -> None:
        self.items.append(captured)


class SupervisorLogTransportTests(unittest.TestCase):
    def test_child_environment_forces_utf8_for_redirected_windows_output(self) -> None:
        with patch.dict(os.environ, {"EXISTING_VALUE": "kept"}, clear=True):
            environment = _child_environment()

        self.assertEqual(environment["PYTHONUTF8"], "1")
        self.assertEqual(environment["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(environment["EXISTING_VALUE"], "kept")

    def test_recoverable_aiogram_polling_disconnect_is_not_an_alert(self) -> None:
        line = (
            "2026-07-17 11:24:02,306 | ERROR | aiogram.dispatcher | "
            "Failed to fetch updates - TelegramNetworkError: HTTP Client says - "
            "ServerDisconnectedError: Server disconnected"
        )
        self.assertFalse(_looks_like_error(line))

    def test_real_dispatcher_error_still_opens_an_alert(self) -> None:
        line = (
            "2026-07-17 11:24:02,306 | ERROR | aiogram.dispatcher | "
            "Unhandled bot error: database transaction failed"
        )
        self.assertTrue(_looks_like_error(line))

    def test_error_center_ignores_only_recoverable_polling_disconnect(self) -> None:
        center = _CapturedCenter()
        handler = ErrorLoggingHandler(center)  # type: ignore[arg-type]
        transient = logging.LogRecord(
            name="aiogram.dispatcher",
            level=logging.ERROR,
            pathname="dispatcher.py",
            lineno=1,
            msg=(
                "Failed to fetch updates - TelegramNetworkError: "
                "ServerDisconnectedError: Server disconnected"
            ),
            args=(),
            exc_info=None,
        )
        handler.emit(transient)
        self.assertEqual([], center.items)

        real = logging.LogRecord(
            name="aiogram.dispatcher",
            level=logging.ERROR,
            pathname="dispatcher.py",
            lineno=2,
            msg="Unhandled bot error: database transaction failed",
            args=(),
            exc_info=None,
        )
        handler.emit(real)
        self.assertEqual(1, len(center.items))


if __name__ == "__main__":
    unittest.main()
