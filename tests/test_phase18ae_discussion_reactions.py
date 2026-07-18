from __future__ import annotations

import inspect
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.analytics_reactions import set_analytics_reaction_counts
from velvet_bot.discussion_thread_links import link_pending_threads_for_channel_post


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


class DiscussionReactionBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_queries_use_public_database_boundary(self) -> None:
        link_source = inspect.getsource(link_pending_threads_for_channel_post)
        reaction_source = inspect.getsource(set_analytics_reaction_counts)

        for source in (link_source, reaction_source):
            self.assertNotIn("._require_pool()", source)
            self.assertEqual(1, source.count("database.acquire()"))

    async def test_thread_link_preserves_update_contract(self) -> None:
        connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 2"))
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))

        result = await link_pending_threads_for_channel_post(
            database,
            channel_id="-10042",
            message_id="73",
        )

        database.acquire.assert_called_once_with()
        self.assertTrue(context.entered)
        self.assertTrue(context.exited)
        sql, channel_id, message_id = connection.execute.await_args.args
        self.assertIn("UPDATE discussion_threads AS thread", sql)
        self.assertIn("thread.channel_post_id IS NULL", sql)
        self.assertIn("WHEN thread.link_source LIKE 'pending%'", sql)
        self.assertEqual((channel_id, message_id), (-10042, 73))
        self.assertEqual(result, 2)

    async def test_thread_link_invalid_status_returns_zero(self) -> None:
        connection = SimpleNamespace(execute=AsyncMock(return_value=None))
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await link_pending_threads_for_channel_post(
            database,
            channel_id=1,
            message_id=2,
        )

        self.assertEqual(result, 0)

    async def test_reaction_update_preserves_cleaning_and_json_contract(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(return_value=1))
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))

        result = await set_analytics_reaction_counts(
            database,
            chat_id="-1007",
            message_id="19",
            breakdown={"❤": 3, "🔥": "2", "zero": 0, "negative": -4},
        )

        database.acquire.assert_called_once_with()
        self.assertTrue(context.entered)
        self.assertTrue(context.exited)
        sql, chat_id, message_id, total, payload = connection.fetchval.await_args.args
        self.assertIn("UPDATE channel_posts", sql)
        self.assertIn("reaction_breakdown = $4::JSONB", sql)
        self.assertEqual((chat_id, message_id), (-1007, 19))
        self.assertEqual(total, 5)
        self.assertEqual(json.loads(payload), {"❤": 3, "🔥": 2})
        self.assertNotIn("\\u", payload)
        self.assertTrue(result)

    async def test_missing_reaction_target_returns_false(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(return_value=None))
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await set_analytics_reaction_counts(
            database,
            chat_id=7,
            message_id=19,
            breakdown={},
        )

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
