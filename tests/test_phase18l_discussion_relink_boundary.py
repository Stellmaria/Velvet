from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.domains.discussions import DiscussionRelinkRepository


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


class DiscussionRelinkBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary(self) -> None:
        path = ROOT / "velvet_bot/domains/discussions/relink_repository.py"
        source = path.read_text(encoding="utf-8")

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("self._database.acquire()"), 1)

    async def test_rebuild_uses_public_acquire_and_one_transaction(self) -> None:
        connection = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    "UPDATE 2",
                    "UPDATE 7",
                    "INSERT 0 3",
                    "UPDATE 1",
                ]
            ),
            transaction=Mock(),
        )
        transaction_context = _AsyncContext(None)
        connection.transaction.return_value = transaction_context
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = DiscussionRelinkRepository(database)

        result = await repository.rebuild(-10077)

        database.acquire.assert_called_once_with()
        connection.transaction.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        self.assertTrue(transaction_context.entered)
        self.assertTrue(transaction_context.exited)
        self.assertEqual(connection.execute.await_count, 4)

        roots_call, comments_call, threads_call, backfill_call = (
            connection.execute.await_args_list
        )
        self.assertIn("UPDATE channel_posts AS post", roots_call.args[0])
        self.assertIn("WITH RECURSIVE reply_tree", comments_call.args[0])
        self.assertIn("INSERT INTO discussion_threads", threads_call.args[0])
        self.assertIn("UPDATE discussion_threads AS thread", backfill_call.args[0])
        for call in connection.execute.await_args_list:
            self.assertEqual(call.args[1], -10077)

        self.assertEqual(result.roots_marked, 2)
        self.assertEqual(result.comments_linked, 7)
        self.assertEqual(result.threads_linked, 3)


if __name__ == "__main__":
    unittest.main()
