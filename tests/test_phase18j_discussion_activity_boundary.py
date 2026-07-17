from __future__ import annotations

import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.domains.discussions import DiscussionActivityRepository


ROOT = Path(__file__).resolve().parents[1]


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self.value

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        self.exited = True
        return False


class DiscussionActivityBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary(self) -> None:
        path = ROOT / "velvet_bot/domains/discussions/activity_repository.py"
        source = path.read_text(encoding="utf-8")

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("self._database.acquire()"), 3)

    async def test_silent_publications_use_public_acquire_and_preserve_page(self) -> None:
        since = datetime(2026, 7, 1, tzinfo=UTC)
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=17),
            fetch=AsyncMock(
                return_value=[
                    {
                        "item_key": "91",
                        "item_label": "Публикация без комментариев",
                        "item_count": 0,
                        "secondary_count": 0,
                        "detail": "17.07.2026 14:00",
                    }
                ]
            ),
        )
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = DiscussionActivityRepository(database)

        page = await repository.list_publications_without_comments(
            discussion_chat_id=-10077,
            parent_channel_id=-10011,
            since=since,
            page=99,
        )

        database.acquire.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        self.assertIn("WITH publications", connection.fetchval.await_args.args[0])
        self.assertEqual(
            connection.fetchval.await_args.args[1:],
            (-10077, -10011, since),
        )
        self.assertIn("ORDER BY posted_at DESC", connection.fetch.await_args.args[0])
        self.assertEqual(
            connection.fetch.await_args.args[1:],
            (-10077, -10011, since, 16, 8),
        )
        self.assertEqual(page.page, 2)
        self.assertEqual(page.page_size, 8)
        self.assertEqual(page.total_items, 17)
        self.assertEqual(page.total_pages, 3)
        self.assertEqual(page.items[0].key, "91")
        self.assertEqual(page.items[0].count, 0)
        self.assertEqual(page.items[0].detail, "17.07.2026 14:00")

    async def test_breakdown_and_daily_activity_keep_bucket_contracts(self) -> None:
        since = datetime(2026, 7, 1, tzinfo=UTC)
        connection = SimpleNamespace(
            fetch=AsyncMock(
                side_effect=[
                    [
                        {"bucket": 1, "item_count": 3},
                        {"bucket": 7, "item_count": 5},
                        {"bucket": 9, "item_count": 99},
                    ],
                    [
                        {"bucket": 0, "item_count": 2},
                        {"bucket": 23, "item_count": 4},
                        {"bucket": None, "item_count": 99},
                    ],
                    [
                        {"activity_day": date(2026, 7, 16), "comment_count": 6},
                        {"activity_day": date(2026, 7, 17), "comment_count": 8},
                    ],
                ]
            )
        )
        database = SimpleNamespace(
            acquire=Mock(
                side_effect=[
                    _AsyncContext(connection),
                    _AsyncContext(connection),
                ]
            )
        )
        repository = DiscussionActivityRepository(database)

        breakdown = await repository.get_activity_breakdown(
            discussion_chat_id=-10077,
            since=since,
            timezone_name="Europe/Berlin",
        )
        daily = await repository.list_daily_activity(
            discussion_chat_id=-10077,
            since=since,
            timezone_name="Europe/Berlin",
        )

        self.assertEqual(database.acquire.call_count, 2)
        self.assertEqual(breakdown.weekdays, (3, 0, 0, 0, 0, 0, 5))
        self.assertEqual(breakdown.hours[0], 2)
        self.assertEqual(breakdown.hours[23], 4)
        self.assertEqual(sum(breakdown.hours), 6)
        self.assertEqual(
            [(item.day, item.comment_count) for item in daily],
            [(date(2026, 7, 16), 6), (date(2026, 7, 17), 8)],
        )
        for call in connection.fetch.await_args_list:
            self.assertEqual(call.args[1:], (-10077, since, "Europe/Berlin"))


if __name__ == "__main__":
    unittest.main()
