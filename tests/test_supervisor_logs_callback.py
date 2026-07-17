from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.enums import ChatType
from aiogram.types import Chat, Message

from velvet_bot.handlers.supervisor_logs import handle_supervisor_logs_callback


def _message() -> Message:
    return Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=1, type=ChatType.PRIVATE),
    )


class SupervisorLogsCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_callback_is_answered_before_supervisor_request(self) -> None:
        events: list[str] = []

        async def answer(*args, **kwargs) -> None:
            events.append("answer")

        async def logs(*, lines: int):
            events.append(f"logs:{lines}")
            return {"lines": ["line"]}

        async def edit(*args, **kwargs) -> None:
            events.append("edit")

        callback = SimpleNamespace(message=_message(), answer=AsyncMock(side_effect=answer))
        callback_data = SimpleNamespace(action="logs.150")
        supervisor_client = SimpleNamespace(logs=AsyncMock(side_effect=logs))

        with patch(
            "velvet_bot.handlers.supervisor_logs._safe_edit",
            new=AsyncMock(side_effect=edit),
        ):
            await handle_supervisor_logs_callback(
                callback,
                callback_data,
                supervisor_client,
            )

        self.assertEqual(events, ["answer", "logs:150", "edit"])
        callback.answer.assert_awaited_once_with(None)

    async def test_file_callback_is_acknowledged_before_large_log_request(self) -> None:
        events: list[str] = []

        async def answer(*args, **kwargs) -> None:
            events.append("answer")

        async def logs(*, lines: int):
            events.append(f"logs:{lines}")
            return {"lines": ["line"]}

        async def answer_document(*args, **kwargs) -> None:
            events.append("file")

        callback = SimpleNamespace(message=_message(), answer=AsyncMock(side_effect=answer))
        callback_data = SimpleNamespace(action="logs.file")
        supervisor_client = SimpleNamespace(logs=AsyncMock(side_effect=logs))

        with patch.object(
            Message,
            "answer_document",
            new=AsyncMock(side_effect=answer_document),
        ):
            await handle_supervisor_logs_callback(
                callback,
                callback_data,
                supervisor_client,
            )

        self.assertEqual(events, ["answer", "logs:2000", "file"])
        callback.answer.assert_awaited_once_with("Готовлю файл журнала…")


if __name__ == "__main__":
    unittest.main()
