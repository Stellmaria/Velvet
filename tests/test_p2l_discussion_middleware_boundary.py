from __future__ import annotations

import asyncio
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path

from aiogram.enums import ChatType
from aiogram.types import Chat, Message

import velvet_bot.discussion_analytics_middleware as middleware_module
from scripts.update_p2_stability_inventory import build_inventory

ROOT = Path(__file__).resolve().parents[1]


def _message() -> Message:
    return Message(
        message_id=77,
        date=datetime.now(UTC),
        chat=Chat(id=-1001, type=ChatType.SUPERGROUP, title="Discussion"),
        text="hello",
    )


class DiscussionMiddlewareBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_ingest_failure_does_not_consume_handler(self) -> None:
        calls: list[str] = []

        async def failing_ingest(database, event) -> None:
            calls.append("ingest")
            raise RuntimeError("analytics unavailable")

        async def handler(event, data):
            calls.append("handler")
            return "handled"

        original = middleware_module.ingest_live_discussion_message
        middleware_module.ingest_live_discussion_message = failing_ingest
        try:
            result = await middleware_module.DiscussionAnalyticsMiddleware()(
                handler,
                _message(),
                {"database": object()},
            )
        finally:
            middleware_module.ingest_live_discussion_message = original

        self.assertEqual(result, "handled")
        self.assertEqual(calls, ["ingest", "handler"])

    async def test_cancellation_is_not_swallowed(self) -> None:
        async def cancelled_ingest(database, event) -> None:
            raise asyncio.CancelledError

        async def handler(event, data):
            self.fail("handler must not run after cancellation")

        original = middleware_module.ingest_live_discussion_message
        middleware_module.ingest_live_discussion_message = cancelled_ingest
        try:
            with self.assertRaises(asyncio.CancelledError):
                await middleware_module.DiscussionAnalyticsMiddleware()(
                    handler,
                    _message(),
                    {"database": object()},
                )
        finally:
            middleware_module.ingest_live_discussion_message = original

    def test_generator_reproduces_inventory_counts(self) -> None:
        checked = json.loads(
            (ROOT / "docs/p2_stability_inventory.json").read_text(encoding="utf-8")
        )
        actual = build_inventory(
            generated_from=checked["generated_from_commit"],
            schema_version=checked["schema_version"],
        )
        keys = (
            "broad_exception_total",
            "broad_exception_files",
            "broad_exception_approved",
            "broad_exception_unresolved",
            "broad_exception_unresolved_files",
            "callback_total",
            "risky_callback_total",
            "guarded_callback_total",
            "delegated_callback_total",
            "next_slice",
        )
        self.assertEqual(
            {key: actual[key] for key in keys},
            {key: checked[key] for key in keys},
        )


if __name__ == "__main__":
    unittest.main()
