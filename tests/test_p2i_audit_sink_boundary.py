from __future__ import annotations

import asyncio
import unittest

from velvet_bot.audit import TelegramAuditLogger


class FailingBot:
    async def send_message(self, **kwargs) -> None:
        raise RuntimeError("log chat unavailable")


class CancelledBot:
    async def send_message(self, **kwargs) -> None:
        raise asyncio.CancelledError


class AuditSinkBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_delivery_failure_does_not_break_application_flow(self) -> None:
        logger = TelegramAuditLogger(FailingBot(), 123)
        await logger.send("event", value="x")

    async def test_cancellation_is_not_swallowed(self) -> None:
        logger = TelegramAuditLogger(CancelledBot(), 123)
        with self.assertRaises(asyncio.CancelledError):
            await logger.send("event")


if __name__ == "__main__":
    unittest.main()
