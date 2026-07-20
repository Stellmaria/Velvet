from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.presentation.telegram.routers.core_operations_controllers.error_center as module


class FakeCenter:
    def __init__(self, count: int = 3) -> None:
        self.count = count
        self.calls: list[int] = []

    async def acknowledge_all(self, user_id: int) -> int:
        self.calls.append(user_id)
        return self.count


class FakeCallback:
    def __init__(self, message) -> None:
        self.from_user = SimpleNamespace(id=17)
        self.message = message
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs) -> None:
        self.answers.append(text)


class ErrorCenterMarkupBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_markup_failure_is_logged_after_acknowledgement(self) -> None:
        class FailedMessage:
            async def edit_reply_markup(self, **kwargs) -> None:
                raise RuntimeError("message unavailable")

        callback = FakeCallback(FailedMessage())
        center = FakeCenter(count=4)

        with self.assertLogs(module.logger.name, level="WARNING") as captured:
            await module.acknowledge_all_errors_callback(callback, center)

        self.assertEqual(center.calls, [17])
        self.assertEqual(callback.answers, ["Просмотрено ошибок: 4."])
        self.assertTrue(any("message unavailable" in line for line in captured.output))

    async def test_markup_cancellation_is_not_swallowed(self) -> None:
        class CancelledMessage:
            async def edit_reply_markup(self, **kwargs) -> None:
                raise asyncio.CancelledError

        callback = FakeCallback(CancelledMessage())
        center = FakeCenter(count=2)

        with self.assertRaises(asyncio.CancelledError):
            await module.acknowledge_all_errors_callback(callback, center)

        self.assertEqual(center.calls, [17])
        self.assertEqual(callback.answers, ["Просмотрено ошибок: 2."])

    async def test_missing_message_needs_no_cleanup(self) -> None:
        callback = FakeCallback(None)
        center = FakeCenter(count=1)

        await module.acknowledge_all_errors_callback(callback, center)

        self.assertEqual(center.calls, [17])
        self.assertEqual(callback.answers, ["Просмотрено ошибок: 1."])


if __name__ == "__main__":
    unittest.main()
