from __future__ import annotations

import inspect
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.telegram_export_import import (
    import_telegram_export,
    list_tracked_discussions,
    register_tracked_source,
)


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


class TelegramImportBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_module_uses_public_database_boundary(self) -> None:
        import velvet_bot.telegram_export_import as module

        source = inspect.getsource(module)
        self.assertNotIn("._require_pool()", source)
        self.assertEqual(4, source.count("database.acquire()"))
        self.assertEqual(1, source.count("async with connection.transaction():"))

    async def test_register_tracked_source_preserves_upsert_arguments(self) -> None:
        connection = SimpleNamespace(execute=AsyncMock(return_value="INSERT 0 1"))
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))

        await register_tracked_source(
            database,
            chat_id=-100123,
            title="Discussion",
            username="velvet_chat",
            source_kind="discussion",
            parent_channel_id=-100456,
        )

        database.acquire.assert_called_once_with()
        self.assertTrue(context.entered)
        self.assertTrue(context.exited)
        sql, *arguments = connection.execute.await_args.args
        self.assertIn("INSERT INTO tracked_channels", sql)
        self.assertEqual(
            arguments,
            [-100123, "Discussion", "velvet_chat", "discussion", -100456],
        )

    async def test_list_tracked_discussions_preserves_filter_and_mapping(self) -> None:
        connection = SimpleNamespace(
            fetch=AsyncMock(
                return_value=[
                    {"chat_id": -1002, "title": "Beta"},
                    {"chat_id": -1001, "title": None},
                ]
            )
        )
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))

        result = await list_tracked_discussions(
            database,
            parent_channel_id=-100999,
        )

        sql, parent_channel_id = connection.fetch.await_args.args
        self.assertIn("source_kind = 'discussion'", sql)
        self.assertIn("parent_channel_id = $1", sql)
        self.assertEqual(parent_channel_id, -100999)
        self.assertEqual(result, [(-1002, "Beta"), (-1001, None)])

    async def test_duplicate_import_short_circuits_before_transaction(self) -> None:
        raw = json.dumps(
            {
                "id": 123,
                "type": "public_channel",
                "name": "Velvet",
                "messages": [],
            }
        ).encode("utf-8")
        transaction = Mock()
        connection = SimpleNamespace(
            fetchrow=AsyncMock(
                return_value={
                    "imported_messages": 7,
                    "publication_count": 3,
                    "metadata": {
                        "prompt_publications": 2,
                        "hashtag_count": 4,
                        "character_matches": 1,
                        "reaction_count": 9,
                    },
                }
            ),
            transaction=transaction,
        )
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))

        summary = await import_telegram_export(
            database,
            raw=raw,
            file_name="result.json",
            source_kind="channel",
        )

        self.assertTrue(summary.duplicate_import)
        self.assertEqual(summary.imported_messages, 7)
        self.assertEqual(summary.publication_count, 3)
        transaction.assert_not_called()

    async def test_new_import_preserves_single_transaction_and_history_write(self) -> None:
        raw = json.dumps(
            {
                "id": 123,
                "type": "public_channel",
                "name": "Velvet",
                "messages": [],
            }
        ).encode("utf-8")
        transaction_context = _AsyncContext(None)
        connection = SimpleNamespace(
            fetchrow=AsyncMock(return_value=None),
            fetch=AsyncMock(return_value=[]),
            execute=AsyncMock(return_value="INSERT 0 1"),
            transaction=Mock(return_value=transaction_context),
        )
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))

        summary = await import_telegram_export(
            database,
            raw=raw,
            file_name="result.json",
            source_kind="channel",
            imported_by=77,
        )

        connection.transaction.assert_called_once_with()
        self.assertTrue(transaction_context.entered)
        self.assertTrue(transaction_context.exited)
        self.assertEqual(connection.execute.await_count, 2)
        first_sql = connection.execute.await_args_list[0].args[0]
        last_sql = connection.execute.await_args_list[-1].args[0]
        self.assertIn("INSERT INTO tracked_channels", first_sql)
        self.assertIn("INSERT INTO telegram_export_imports", last_sql)
        self.assertFalse(summary.duplicate_import)
        self.assertEqual(summary.imported_messages, 0)


if __name__ == "__main__":
    unittest.main()
