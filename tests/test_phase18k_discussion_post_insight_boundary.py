from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.domains.discussions import DiscussionPostInsightRepository


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


def _post_row(*, post_id: int = 91, first_comment_seconds: int | None = 120):
    return {
        "post_id": post_id,
        "publication_key": f"channel:{post_id}",
        "posted_at": datetime(2026, 7, 17, 10, 0, tzinfo=UTC),
        "text_content": "Archive publication",
        "message_url": f"https://t.me/velvet/{post_id}",
        "view_count": 300,
        "channel_reactions": 14,
        "comment_count": 8,
        "first_comment_seconds": first_comment_seconds,
        "unique_participants": 5,
        "comment_reactions": 11,
    }


class DiscussionPostInsightBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary(self) -> None:
        path = ROOT / "velvet_bot/domains/discussions/post_insight_repository.py"
        source = path.read_text(encoding="utf-8")

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("self._database.acquire()"), 2)

    async def test_list_posts_uses_public_acquire_and_preserves_page(self) -> None:
        since = datetime(2026, 7, 1, tzinfo=UTC)
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=13),
            fetch=AsyncMock(return_value=[_post_row()]),
        )
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = DiscussionPostInsightRepository(database)

        page = await repository.list_posts(
            discussion_chat_id=-10077,
            parent_channel_id=-10011,
            since=since,
            page=99,
        )

        database.acquire.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        self.assertIn(
            "COUNT(DISTINCT source.publication_key)",
            connection.fetchval.await_args.args[0],
        )
        self.assertEqual(
            connection.fetchval.await_args.args[1:],
            (-10077, -10011, since),
        )
        self.assertIn("WITH publications", connection.fetch.await_args.args[0])
        self.assertIn("ORDER BY comments.comment_count DESC", connection.fetch.await_args.args[0])
        self.assertEqual(
            connection.fetch.await_args.args[1:],
            (-10077, -10011, since, 12, 6),
        )
        self.assertEqual(page.page, 2)
        self.assertEqual(page.page_size, 6)
        self.assertEqual(page.total_items, 13)
        self.assertEqual(page.total_pages, 3)
        self.assertEqual(page.items[0].post_id, 91)
        self.assertEqual(page.items[0].comment_count, 8)
        self.assertEqual(page.items[0].first_comment_seconds, 120)

    async def test_get_post_uses_public_acquire_and_maps_nullable_delay(self) -> None:
        since = datetime(2026, 7, 1, tzinfo=UTC)
        connection = SimpleNamespace(
            fetchrow=AsyncMock(return_value=_post_row(post_id=92, first_comment_seconds=None))
        )
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = DiscussionPostInsightRepository(database)

        post = await repository.get_post(
            discussion_chat_id=-10077,
            parent_channel_id=-10011,
            post_id=92,
            since=since,
        )

        database.acquire.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        self.assertIn("WITH selected", connection.fetchrow.await_args.args[0])
        self.assertEqual(
            connection.fetchrow.await_args.args[1:],
            (-10077, -10011, 92, since),
        )
        self.assertIsNotNone(post)
        assert post is not None
        self.assertEqual(post.post_id, 92)
        self.assertEqual(post.publication_key, "channel:92")
        self.assertIsNone(post.first_comment_seconds)
        self.assertEqual(post.view_count, 300)
        self.assertEqual(post.comment_reactions, 11)


if __name__ == "__main__":
    unittest.main()
