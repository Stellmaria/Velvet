from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.handlers.channel_analytics as module


class FakeAudit:
    def __init__(self) -> None:
        self.errors: list[tuple[str, BaseException, dict[str, object]]] = []

    async def error(self, title: str, error: BaseException, **fields) -> None:
        self.errors.append((title, error, fields))


class ChannelAnalyticsBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_ingest = module.ingest_channel_post
        self.message = SimpleNamespace(
            chat=SimpleNamespace(id=-1001),
            message_id=77,
        )

    def tearDown(self) -> None:
        module.ingest_channel_post = self.original_ingest

    async def test_ingest_failure_is_reported_without_escaping(self) -> None:
        error = RuntimeError("analytics database unavailable")
        audit = FakeAudit()

        async def fail_ingest(database, message):
            raise error

        module.ingest_channel_post = fail_ingest

        await module._capture_channel_post(
            self.message,
            object(),
            frozenset({-1001}),
            audit,
        )

        self.assertEqual(len(audit.errors), 1)
        title, recorded_error, fields = audit.errors[0]
        self.assertEqual(title, "Ошибка аналитики канала")
        self.assertIs(recorded_error, error)
        self.assertEqual(fields["channel_id"], -1001)
        self.assertEqual(fields["message_id"], 77)

    async def test_cancellation_is_not_converted_to_audit_error(self) -> None:
        audit = FakeAudit()

        async def cancel_ingest(database, message):
            raise asyncio.CancelledError

        module.ingest_channel_post = cancel_ingest

        with self.assertRaises(asyncio.CancelledError):
            await module._capture_channel_post(
                self.message,
                object(),
                frozenset({-1001}),
                audit,
            )

        self.assertEqual(audit.errors, [])

    async def test_untracked_channel_skips_ingest(self) -> None:
        calls: list[int] = []

        async def record_ingest(database, message):
            calls.append(message.message_id)

        module.ingest_channel_post = record_ingest

        await module._capture_channel_post(
            self.message,
            object(),
            frozenset({-2002}),
            FakeAudit(),
        )

        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
