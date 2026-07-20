from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery
from aiogram.types import Chat, Message

import velvet_bot.presentation.telegram.routers.supervisor.status as status_module
import velvet_supervisor.runtime_extended  # noqa: F401 - installs the production filter
from velvet_supervisor.runtime import _looks_like_error


class SupervisorPollingFilterTests(unittest.TestCase):
    def test_all_observed_recoverable_polling_failures_are_not_alerts(self) -> None:
        lines = (
            "2026-07-19 14:08:27 | ERROR | aiogram.dispatcher | "
            "Failed to fetch updates - TelegramNetworkError: HTTP Client says - "
            "ServerDisconnectedError: Server disconnected",
            "2026-07-19 14:09:24 | ERROR | aiogram.dispatcher | "
            "Failed to fetch updates - TelegramNetworkError: HTTP Client says - "
            "ClientConnectorError: Cannot connect to host api.telegram.org:443 "
            "ssl:default [Превышен таймаут семафора]",
            "2026-07-19 14:21:53 | ERROR | aiogram.dispatcher | "
            "Failed to fetch updates - TelegramNetworkError: HTTP Client says - "
            "ClientOSError: [WinError 1236] Подключение к сети было разорвано "
            "локальной системой",
            "2026-07-19 14:21:53 | WARNING | aiogram.dispatcher | "
            "Sleep for 1.000000 seconds and try again...",
        )
        for line in lines:
            with self.subTest(line=line):
                self.assertFalse(_looks_like_error(line))

    def test_real_dispatcher_failure_remains_an_alert(self) -> None:
        self.assertTrue(
            _looks_like_error(
                "2026-07-19 14:24:20 | ERROR | aiogram.dispatcher | "
                "Unhandled bot error: database transaction failed"
            )
        )


class _CallbackStub:
    def __init__(self, message: Message, events: list[str]) -> None:
        self.message = message
        self.events = events

    async def answer(self, text=None, show_alert=False) -> None:
        self.events.append("answer")


class SupervisorStatusCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_callback_is_acknowledged_before_supervisor_io(self) -> None:
        events: list[str] = []
        message = Message(
            message_id=1,
            date=datetime.now(UTC),
            chat=Chat(id=1, type="private"),
        )
        callback = _CallbackStub(message, events)

        async def load(_client):
            events.append("load")
            return {}

        async def edit(_message, _text, _keyboard):
            events.append("edit")

        with (
            patch.object(status_module, "load_supervisor_status", side_effect=load),
            patch.object(status_module, "_safe_edit", side_effect=edit),
            patch.object(status_module, "_status_text", return_value="status"),
            patch.object(status_module, "_main_keyboard", return_value=None),
        ):
            await status_module.handle_supervisor_status_callback(
                callback,  # type: ignore[arg-type]
                SimpleNamespace(action="status"),  # type: ignore[arg-type]
                object(),  # type: ignore[arg-type]
            )

        self.assertEqual(["answer", "load", "edit"], events)

    async def test_expired_callback_answer_is_safely_ignored(self) -> None:
        class ExpiredCallback:
            async def answer(self, text=None, show_alert=False) -> None:
                raise TelegramBadRequest(
                    method=AnswerCallbackQuery(callback_query_id="expired"),
                    message=(
                        "Bad Request: query is too old and response timeout expired "
                        "or query ID is invalid"
                    ),
                )

        result = await status_module._acknowledge_callback(  # noqa: SLF001
            ExpiredCallback()  # type: ignore[arg-type]
        )
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
