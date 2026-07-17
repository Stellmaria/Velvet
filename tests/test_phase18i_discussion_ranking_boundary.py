from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.domains.discussions import DiscussionRankingRepository


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


class DiscussionRankingBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary(self) -> None:
        path = ROOT / "velvet_bot/domains/discussions/ranking_repository.py"
        source = path.read_text(encoding="utf-8")

        self.assertNotIn("._require_pool()", source)
        self.assertIn("self._database.acquire()", source)

    async def test_rank_page_uses_public_acquire_and_preserves_pagination(self) -> None:
        since = datetime(2026, 7, 1, tzinfo=UTC)
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=25),
            fetch=AsyncMock(
                return_value=[
                    {
                        "item_key": "42",
                        "item_label": "Author",
                        "item_count": 9,
                        "secondary_count": 4,
                        "detail": None,
                    }
                ]
            ),
        )
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = DiscussionRankingRepository(database)

        result = await repository.list_active_participants(
            discussion_chat_id=-10077,
            since=since,
            page=99,
        )

        database.acquire.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        connection.fetchval.assert_awaited_once()
        self.assertIn("COUNT(DISTINCT sender_id)", connection.fetchval.await_args.args[0])
        self.assertEqual(connection.fetchval.await_args.args[1:], (-10077, since))

        rows_call = connection.fetch.await_args
        self.assertIn("ORDER BY item_count DESC", rows_call.args[0])
        self.assertEqual(rows_call.args[1:], (-10077, since, 24, 8))

        self.assertEqual(result.page, 3)
        self.assertEqual(result.page_size, 8)
        self.assertEqual(result.total_items, 25)
        self.assertEqual(result.total_pages, 4)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].key, "42")
        self.assertEqual(result.items[0].label, "Author")
        self.assertEqual(result.items[0].count, 9)
        self.assertEqual(result.items[0].secondary_count, 4)
        self.assertIsNone(result.items[0].detail)


if __name__ == "__main__":
    unittest.main()
