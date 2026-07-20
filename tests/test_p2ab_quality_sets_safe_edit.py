from __future__ import annotations

import asyncio
import unittest

import velvet_bot.presentation.telegram.routers.quality_operations_controllers.quality_sets as module


class FakeTelegramBadRequest(Exception):
    pass


class FakeMessage:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def edit_text(self, text: str, **kwargs) -> None:
        self.calls.append({"text": text, **kwargs})
        if self.error is not None:
            raise self.error


class QualitySetsSafeEditTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_bad_request = module.TelegramBadRequest
        module.TelegramBadRequest = FakeTelegramBadRequest

    def tearDown(self) -> None:
        module.TelegramBadRequest = self.original_bad_request

    async def test_message_not_modified_is_ignored(self) -> None:
        message = FakeMessage(FakeTelegramBadRequest("message is not modified"))

        await module._safe_edit(message, "body", "keyboard")

        self.assertEqual(
            message.calls,
            [{"text": "body", "reply_markup": "keyboard"}],
        )

    async def test_other_telegram_bad_request_is_propagated(self) -> None:
        error = FakeTelegramBadRequest("chat not found")
        message = FakeMessage(error)

        with self.assertRaises(FakeTelegramBadRequest) as captured:
            await module._safe_edit(message, "body", "keyboard")

        self.assertIs(captured.exception, error)

    async def test_runtime_error_is_not_treated_as_telegram_not_modified(self) -> None:
        error = RuntimeError("renderer failed")
        message = FakeMessage(error)

        with self.assertRaises(RuntimeError) as captured:
            await module._safe_edit(message, "body", "keyboard")

        self.assertIs(captured.exception, error)

    async def test_cancellation_is_not_swallowed(self) -> None:
        message = FakeMessage(asyncio.CancelledError())

        with self.assertRaises(asyncio.CancelledError):
            await module._safe_edit(message, "body", "keyboard")


if __name__ == "__main__":
    unittest.main()
