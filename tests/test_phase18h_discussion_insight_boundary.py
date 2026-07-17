from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.domains.discussions import DiscussionInsightRepository


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


class DiscussionInsightBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary(self) -> None:
        path = ROOT / "velvet_bot/domains/discussions/insight_repository.py"
        source = path.read_text(encoding="utf-8")

        self.assertNotIn("._require_pool()", source)
        self.assertIn("self._database.acquire()", source)

    async def test_summary_uses_public_acquire_and_preserves_aggregates(self) -> None:
        first_comment_at = datetime(2026, 7, 16, 10, 0, tzinfo=UTC)
        last_comment_at = datetime(2026, 7, 17, 11, 30, tzinfo=UTC)
        since = datetime(2026, 7, 1, tzinfo=UTC)
        connection = SimpleNamespace(
            fetchrow=AsyncMock(
                side_effect=[
                    {
                        "linked_threads": 4,
                        "total_comments": 19,
                        "unique_participants": 7,
                        "total_comment_reactions": 28,
                        "first_comment_at": first_comment_at,
                        "last_comment_at": last_comment_at,
                    },
                    {
                        "publication_count": 8,
                        "without_comments": 3,
                        "average_comments": 2.375,
                    },
                ]
            )
        )
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = DiscussionInsightRepository(database)

        summary = await repository.get_summary(
            discussion_chat_id=-10077,
            parent_channel_id=-10011,
            since=since,
        )

        database.acquire.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        self.assertEqual(connection.fetchrow.await_count, 2)

        comment_call = connection.fetchrow.await_args_list[0]
        self.assertIn("WITH linked_comments", comment_call.args[0])
        self.assertEqual(comment_call.args[1:], (-10077, since))

        publication_call = connection.fetchrow.await_args_list[1]
        self.assertIn("WITH publications", publication_call.args[0])
        self.assertEqual(publication_call.args[1:], (-10011, since, -10077))

        self.assertEqual(summary.discussion_chat_id, -10077)
        self.assertEqual(summary.parent_channel_id, -10011)
        self.assertEqual(summary.linked_threads, 4)
        self.assertEqual(summary.total_comments, 19)
        self.assertEqual(summary.unique_participants, 7)
        self.assertEqual(summary.total_comment_reactions, 28)
        self.assertEqual(summary.published_publications, 8)
        self.assertEqual(summary.publications_without_comments, 3)
        self.assertEqual(summary.average_comments_per_publication, 2.375)
        self.assertEqual(summary.first_comment_at, first_comment_at)
        self.assertEqual(summary.last_comment_at, last_comment_at)


if __name__ == "__main__":
    unittest.main()
