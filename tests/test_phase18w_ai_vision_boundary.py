from __future__ import annotations

import inspect
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.ai_vision import MediaAIRepository


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


class MediaAIVisionBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(MediaAIRepository)

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("self._database.acquire()"), 4)
        for method_name in ("claim_targets", "mark_ready", "mark_error", "summary"):
            self.assertIn(
                "self._database.acquire()",
                inspect.getsource(getattr(MediaAIRepository, method_name)),
                method_name,
            )

    async def test_claim_targets_preserves_transaction_and_locked_batch_claim(self) -> None:
        rows = [
            {
                "media_id": 41,
                "telegram_file_id": "telegram-file",
                "preview_file_id": "preview-file",
                "mime_type": "image/jpeg",
            }
        ]
        connection = SimpleNamespace(
            execute=AsyncMock(side_effect=["INSERT 0 1", "UPDATE 1", "UPDATE 1"]),
            fetch=AsyncMock(return_value=rows),
            transaction=Mock(),
        )
        transaction_context = _AsyncContext(None)
        connection.transaction.return_value = transaction_context
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = MediaAIRepository(database)

        result = await repository.claim_targets(
            provider="ollama",
            model="qwen2.5vl:" + ("x" * 200),
            max_attempts=99,
            limit=99,
        )

        database.acquire.assert_called_once_with()
        connection.transaction.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        self.assertTrue(transaction_context.entered)
        self.assertTrue(transaction_context.exited)
        self.assertEqual(connection.execute.await_count, 3)
        self.assertIn("INSERT INTO media_ai_profiles", connection.execute.await_args_list[0].args[0])
        self.assertIn("status = 'pending'", connection.execute.await_args_list[1].args[0])
        claim_sql, safe_attempts, safe_limit = connection.fetch.await_args.args
        self.assertIn("FOR UPDATE OF p SKIP LOCKED", claim_sql)
        self.assertEqual((safe_attempts, safe_limit), (10, 4))
        batch_call = connection.execute.await_args_list[2]
        self.assertIn("status = 'processing'", batch_call.args[0])
        self.assertEqual(batch_call.args[1], [41])
        self.assertEqual(batch_call.args[2], "ollama")
        self.assertEqual(len(batch_call.args[3]), 160)
        self.assertEqual(batch_call.args[4], 1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].media_id, 41)
        self.assertEqual(result[0].preview_file_id, "preview-file")

    async def test_mark_ready_and_mark_error_preserve_payload_and_attempt_clamp(self) -> None:
        ready_connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 1"))
        error_connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 1"))
        database = SimpleNamespace(
            acquire=Mock(
                side_effect=[
                    _AsyncContext(ready_connection),
                    _AsyncContext(error_connection),
                ]
            )
        )
        repository = MediaAIRepository(database)
        profile = {
            "series_title_ru": "Дикий Запад",
            "summary_ru": "Общий художественный контекст.",
            "series_keywords": ["western"],
        }

        await repository.mark_ready(41, profile)
        await repository.mark_error(
            42,
            RuntimeError("ошибка" * 600),
            max_attempts=99,
            permanent=True,
        )

        ready_sql, *ready_arguments = ready_connection.execute.await_args.args
        self.assertIn("SET status = 'ready'", ready_sql)
        self.assertEqual(ready_arguments[0], 41)
        self.assertEqual(json.loads(ready_arguments[1]), profile)
        self.assertIn("Дикий Запад", ready_arguments[2])

        error_sql, *error_arguments = error_connection.execute.await_args.args
        self.assertIn("THEN 'skipped'", error_sql)
        self.assertEqual(error_arguments[0], 42)
        self.assertLessEqual(len(error_arguments[1]), 2000)
        self.assertTrue(error_arguments[2])
        self.assertEqual(error_arguments[3], 10)

    async def test_summary_preserves_aggregate_mapping(self) -> None:
        row = {
            "pending": 1,
            "processing": 2,
            "ready": 3,
            "errors": 4,
            "skipped": 5,
        }
        connection = SimpleNamespace(fetchrow=AsyncMock(return_value=row))
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = MediaAIRepository(database)

        result = await repository.summary()

        database.acquire.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        self.assertIn("COUNT(*) FILTER", connection.fetchrow.await_args.args[0])
        self.assertEqual(result.pending, 1)
        self.assertEqual(result.processing, 2)
        self.assertEqual(result.ready, 3)
        self.assertEqual(result.errors, 4)
        self.assertEqual(result.skipped, 5)


if __name__ == "__main__":
    unittest.main()
