from __future__ import annotations

import asyncio
import unittest

from velvet_bot.app.bootstrap import _close_application_resources


class BrokenResource:
    def __init__(self, calls: list[str], name: str) -> None:
        self.calls = calls
        self.name = name
        self.session = self

    async def stop_all(self) -> None:
        self.calls.append("workers")
        raise RuntimeError("workers")

    async def send(self, *args, **kwargs) -> None:
        self.calls.append("audit")
        raise RuntimeError("audit")

    async def stop(self) -> None:
        self.calls.append("center")
        raise RuntimeError("center")

    async def close(self) -> None:
        self.calls.append(self.name)
        raise RuntimeError(self.name)


class CancelledWorkers:
    async def stop_all(self) -> None:
        raise asyncio.CancelledError


class BootstrapCleanupBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_attempts_every_resource_after_ordinary_failures(self) -> None:
        calls: list[str] = []
        await _close_application_resources(
            worker_manager=BrokenResource(calls, "unused"),
            audit_logger=BrokenResource(calls, "unused"),
            error_center=BrokenResource(calls, "unused"),
            bot=BrokenResource(calls, "bot"),
            database=BrokenResource(calls, "database"),
        )
        self.assertEqual(calls, ["workers", "audit", "center", "bot", "database"])

    async def test_cancellation_is_not_swallowed(self) -> None:
        calls: list[str] = []
        with self.assertRaises(asyncio.CancelledError):
            await _close_application_resources(
                worker_manager=CancelledWorkers(),
                audit_logger=BrokenResource(calls, "unused"),
                error_center=BrokenResource(calls, "unused"),
                bot=BrokenResource(calls, "bot"),
                database=BrokenResource(calls, "database"),
            )
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
