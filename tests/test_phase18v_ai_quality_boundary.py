from __future__ import annotations

import inspect
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.ai_quality import AIQualityRepository


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


def _quality_row(*, media_id: int = 41, report=...):
    stored_report = (
        json.dumps({"summary_ru": "Проверено"}, ensure_ascii=False)
        if report is ...
        else report
    )
    return {
        "media_id": media_id,
        "file_name": "image.jpg",
        "media_type": "photo",
        "telegram_file_id": "telegram-file",
        "preview_file_id": "preview-file",
        "status": "ready",
        "verdict": "review",
        "quality_score": 76,
        "confidence": 84,
        "report": stored_report,
        "decision": None,
        "error_message": None,
    }


class AIQualityBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(AIQualityRepository)

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("self._database.acquire()"), 8)
        for method_name in (
            "claim_targets",
            "mark_ready",
            "mark_error",
            "summary",
            "list_items",
            "get_item",
            "set_decision",
            "retry",
        ):
            self.assertIn(
                "self._database.acquire()",
                inspect.getsource(getattr(AIQualityRepository, method_name)),
                method_name,
            )

    async def test_claim_targets_preserves_transaction_locking_and_batch_update(self) -> None:
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
        repository = AIQualityRepository(database)
        provider = "provider-" + ("x" * 80)
        model = "model-" + ("y" * 200)

        result = await repository.claim_targets(
            provider=provider,
            model=model,
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
        self.assertIn(
            "INSERT INTO media_ai_quality_checks",
            connection.execute.await_args_list[0].args[0],
        )
        self.assertIn(
            "status = 'pending'",
            connection.execute.await_args_list[1].args[0],
        )
        connection.fetch.assert_awaited_once()
        claim_sql, safe_attempts, safe_limit = connection.fetch.await_args.args
        self.assertIn("FOR UPDATE OF q SKIP LOCKED", claim_sql)
        self.assertEqual((safe_attempts, safe_limit), (10, 2))
        batch_call = connection.execute.await_args_list[2]
        self.assertIn("status = 'processing'", batch_call.args[0])
        self.assertEqual(batch_call.args[1], [41])
        self.assertEqual(batch_call.args[2], provider[:64])
        self.assertEqual(batch_call.args[3], model[:160])
        self.assertEqual(batch_call.args[4], 1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].media_id, 41)
        self.assertEqual(result[0].telegram_file_id, "telegram-file")
        self.assertEqual(result[0].preview_file_id, "preview-file")

    async def test_mark_ready_preserves_report_and_mark_error_clamps_attempts(self) -> None:
        ready_connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 1"))
        error_connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 1"))
        ready_context = _AsyncContext(ready_connection)
        error_context = _AsyncContext(error_connection)
        database = SimpleNamespace(acquire=Mock(side_effect=[ready_context, error_context]))
        repository = AIQualityRepository(database)
        report = {
            "verdict": "review",
            "quality_score": 76,
            "confidence": 84,
            "summary_ru": "Нужна проверка",
        }

        await repository.mark_ready(41, report)
        await repository.mark_error(
            42,
            RuntimeError("ошибка" * 600),
            max_attempts=99,
            permanent=True,
        )

        ready_sql, *ready_arguments = ready_connection.execute.await_args.args
        self.assertIn("SET status = 'ready'", ready_sql)
        self.assertEqual(ready_arguments[0:4], [41, "review", 76, 84])
        self.assertEqual(json.loads(ready_arguments[4]), report)
        self.assertIn("Нужна", ready_arguments[4])

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
            "unreviewed": 6,
            "accepted": 7,
            "fix_required": 8,
            "clean": 9,
            "warnings": 10,
            "critical": 11,
        }
        connection = SimpleNamespace(fetchrow=AsyncMock(return_value=row))
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = AIQualityRepository(database)

        result = await repository.summary()

        database.acquire.assert_called_once_with()
        sql = connection.fetchrow.await_args.args[0]
        self.assertIn("COUNT(*) FILTER", sql)
        self.assertEqual(result.pending, 1)
        self.assertEqual(result.fix_required, 8)
        self.assertEqual(result.critical, 11)

    async def test_list_items_preserves_section_pagination_and_mapping(self) -> None:
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=14),
            fetch=AsyncMock(return_value=[_quality_row()]),
        )
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = AIQualityRepository(database)

        result = await repository.list_items("review", page=99, page_size=50)

        database.acquire.assert_called_once_with()
        count_sql = connection.fetchval.await_args.args[0]
        self.assertIn("q.status = 'ready' AND q.decision IS NULL", count_sql)
        rows_sql, offset, page_size = connection.fetch.await_args.args
        self.assertIn("ORDER BY CASE q.verdict", rows_sql)
        self.assertEqual((offset, page_size), (10, 10))
        self.assertEqual(result.page, 1)
        self.assertEqual(result.page_size, 10)
        self.assertEqual(result.total_items, 14)
        self.assertEqual(result.total_pages, 2)
        self.assertEqual(result.items[0].media_id, 41)
        self.assertEqual(result.items[0].report, {"summary_ru": "Проверено"})

    async def test_get_item_decision_and_retry_preserve_guards(self) -> None:
        get_connection = SimpleNamespace(fetchrow=AsyncMock(return_value=_quality_row()))
        decision_connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 1"))
        retry_connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 0"))
        database = SimpleNamespace(
            acquire=Mock(
                side_effect=[
                    _AsyncContext(get_connection),
                    _AsyncContext(decision_connection),
                    _AsyncContext(retry_connection),
                ]
            )
        )
        repository = AIQualityRepository(database)

        item = await repository.get_item(41)
        decision_result = await repository.set_decision(41, "accepted", 8179531132)
        retry_result = await repository.retry(42)

        self.assertIsNotNone(item)
        self.assertEqual(item.telegram_file_id, "telegram-file")
        get_sql, media_id = get_connection.fetchrow.await_args.args
        self.assertIn("WHERE q.media_id = $1::BIGINT", get_sql)
        self.assertEqual(media_id, 41)

        decision_sql, *decision_arguments = decision_connection.execute.await_args.args
        self.assertIn("AND status = 'ready'", decision_sql)
        self.assertEqual(decision_arguments, [41, "accepted", 8179531132])
        self.assertTrue(decision_result)

        retry_sql, retry_media_id = retry_connection.execute.await_args.args
        self.assertIn("attempt_count = 0", retry_sql)
        self.assertIn("decision = NULL", retry_sql)
        self.assertEqual(retry_media_id, 42)
        self.assertFalse(retry_result)

    async def test_invalid_decision_is_rejected_before_database_access(self) -> None:
        database = SimpleNamespace(acquire=Mock())
        repository = AIQualityRepository(database)

        with self.assertRaisesRegex(ValueError, "Неизвестное решение"):
            await repository.set_decision(41, "invented", 8179531132)

        database.acquire.assert_not_called()


if __name__ == "__main__":
    unittest.main()
