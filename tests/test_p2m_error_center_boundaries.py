from __future__ import annotations

import asyncio
import logging
import unittest

import velvet_bot.error_center as module


class BrokenRecord(logging.LogRecord):
    def getMessage(self) -> str:
        raise RuntimeError("formatting failed")


class ErrorCenterBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_capture_uses_fallback_message(self) -> None:
        record = BrokenRecord("example", logging.ERROR, "test.py", 10, "fallback", (), None)
        captured = module.capture_log_record(record)
        self.assertEqual(captured.summary, "fallback")

    def test_polling_filter_uses_fallback_message(self) -> None:
        record = BrokenRecord(
            "aiogram.dispatcher",
            logging.ERROR,
            "test.py",
            10,
            "Failed to fetch updates TelegramNetworkError server disconnected",
            (),
            None,
        )
        self.assertTrue(module._is_recoverable_aiogram_polling_record(record))

    def test_logging_handler_does_not_raise(self) -> None:
        class Center:
            def enqueue_threadsafe(self, captured) -> None:
                raise RuntimeError("queue unavailable")

        handler = module.ErrorLoggingHandler(Center())
        record = logging.LogRecord(
            "example", logging.ERROR, "test.py", 10, "failure", (), None
        )
        handler.emit(record)

    async def test_consumer_isolates_item_failure_and_propagates_stop(self) -> None:
        center = module.ErrorIncidentCenter(
            bot=object(),
            repository=object(),
            log_chat_id=None,
            owner_user_ids=frozenset(),
        )
        first = module.CapturedLog(
            fingerprint="a",
            severity="ERROR",
            logger_name="test",
            summary="first",
            details=None,
            source=None,
        )
        second = module.CapturedLog(
            fingerprint="b",
            severity="ERROR",
            logger_name="test",
            summary="second",
            details=None,
            source=None,
        )
        await center._queue.put(first)
        await center._queue.put(second)
        calls = []

        async def process(item) -> None:
            calls.append(item.summary)
            if item is first:
                raise RuntimeError("item failed")
            raise asyncio.CancelledError

        center._process = process
        with self.assertRaises(asyncio.CancelledError):
            await center._consume()

        self.assertEqual(calls, ["first", "second"])
        self.assertEqual(center._queue._unfinished_tasks, 0)


if __name__ == "__main__":
    unittest.main()
