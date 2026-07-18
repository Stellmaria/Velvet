from __future__ import annotations

import asyncio
import unittest

import velvet_bot.handlers.quality_duplicates as module


class FakeTelegramBadRequest(Exception):
    pass


class FakeMessage:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, object]] = []

    async def edit_text(self, text: str, *, reply_markup) -> None:
        self.calls.append((text, reply_markup))
        if self.error is not None:
            raise self.error


class QualityDuplicateSafeEditTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_bad_request = module.TelegramBadRequest
        module.TelegramBadRequest = FakeTelegramBadRequest

    def tearDown(self) -> None:
        module.TelegramBadRequest = self.original_bad_request

    async def test_message_not_modified_is_ignored(self) -> None:
        message = FakeMessage(FakeTelegramBadRequest("Bad Request: message is not modified"))

        await module._safe_edit(message, "text", "keyboard")

        self.assertEqual(message.calls, [("text", "keyboard")])

    async def test_other_bad_request_is_reraised(self) -> None:
        error = FakeTelegramBadRequest("Bad Request: message to edit not found")
        message = FakeMessage(error)

        with self.assertRaises(FakeTelegramBadRequest) as captured:
            await module._safe_edit(message, "text", "keyboard")

        self.assertIs(captured.exception, error)

    async def test_runtime_error_is_not_swallowed(self) -> None:
        error = RuntimeError("formatter failed")
        message = FakeMessage(error)

        with self.assertRaises(RuntimeError) as captured:
            await module._safe_edit(message, "text", "keyboard")

        self.assertIs(captured.exception, error)

    async def test_cancellation_is_not_swallowed(self) -> None:
        message = FakeMessage(asyncio.CancelledError())

        with self.assertRaises(asyncio.CancelledError):
            await module._safe_edit(message, "text", "keyboard")


if __name__ == "__main__":
    unittest.main()
