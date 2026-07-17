from __future__ import annotations

import inspect
import json
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.quality_calibration import QualityCalibrationRepository


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


def _case_row(*, feedback_id: int = 7, report=...):
    decided_at = datetime(2026, 7, 17, 12, 30, tzinfo=UTC)
    stored_report = (
        json.dumps({"summary": "Полезный отчёт"}, ensure_ascii=False)
        if report is ...
        else report
    )
    return {
        "id": feedback_id,
        "media_id": 41,
        "file_name": "image.jpg",
        "predicted_verdict": "review",
        "quality_score": 72,
        "confidence": 81,
        "owner_decision": "fix_required",
        "outcome": "useful_warning",
        "report": stored_report,
        "decided_by": 8179531132,
        "decided_at": decided_at,
    }


class QualityCalibrationBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(QualityCalibrationRepository)

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("self._database.acquire()"), 3)
        for method_name in ("profile", "list_cases", "get_case"):
            self.assertIn(
                "self._database.acquire()",
                inspect.getsource(getattr(QualityCalibrationRepository, method_name)),
                method_name,
            )

    async def test_profile_preserves_filters_limit_clamp_and_mapping(self) -> None:
        rows = [
            {
                "predicted_verdict": "ready",
                "quality_score": 92,
                "confidence": 88,
                "owner_decision": "accepted",
                "outcome": "correct_clean",
            },
            {
                "predicted_verdict": "review",
                "quality_score": 61,
                "confidence": 70,
                "owner_decision": "fix_required",
                "outcome": "useful_warning",
            },
        ]
        connection = SimpleNamespace(fetch=AsyncMock(return_value=rows))
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = QualityCalibrationRepository(database)

        result = await repository.profile(
            provider="ollama",
            model="qwen2.5vl",
            limit=99999,
        )

        database.acquire.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        connection.fetch.assert_awaited_once()
        sql, *arguments = connection.fetch.await_args.args
        self.assertIn("FROM qwen_quality_feedback", sql)
        self.assertIn("LIMIT $3::INTEGER", sql)
        self.assertEqual(arguments, ["ollama", "qwen2.5vl", 5000])
        self.assertEqual(result.sample_count, 2)
        self.assertEqual(result.accepted_count, 1)
        self.assertEqual(result.fix_required_count, 1)
        self.assertEqual(result.useful_count, 2)
        self.assertFalse(result.active)

    async def test_list_cases_preserves_section_filter_and_safe_pagination(self) -> None:
        row = _case_row()
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=14),
            fetch=AsyncMock(return_value=[row]),
        )
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = QualityCalibrationRepository(database)

        result = await repository.list_cases(
            "errors",
            provider="ollama",
            model=None,
            page=99,
            page_size=50,
        )

        database.acquire.assert_called_once_with()
        connection.fetchval.assert_awaited_once()
        count_sql, *count_arguments = connection.fetchval.await_args.args
        self.assertIn("SELECT COUNT(*)", count_sql)
        self.assertEqual(
            count_arguments,
            ["ollama", None, ["false_alarm", "missed_problem"]],
        )
        connection.fetch.assert_awaited_once()
        rows_sql, *rows_arguments = connection.fetch.await_args.args
        self.assertIn("JOIN media_files AS media", rows_sql)
        self.assertIn("OFFSET $4::INTEGER LIMIT $5::INTEGER", rows_sql)
        self.assertEqual(
            rows_arguments,
            ["ollama", None, ["false_alarm", "missed_problem"], 10, 10],
        )
        self.assertEqual(result.page, 1)
        self.assertEqual(result.page_size, 10)
        self.assertEqual(result.total_items, 14)
        self.assertEqual(result.total_pages, 2)
        self.assertEqual(result.items[0].feedback_id, 7)
        self.assertEqual(result.items[0].report, {"summary": "Полезный отчёт"})
        self.assertEqual(result.items[0].decided_by, 8179531132)

    async def test_get_case_preserves_mapping_and_missing_result(self) -> None:
        first_connection = SimpleNamespace(fetchrow=AsyncMock(return_value=_case_row()))
        second_connection = SimpleNamespace(fetchrow=AsyncMock(return_value=None))
        first_context = _AsyncContext(first_connection)
        second_context = _AsyncContext(second_connection)
        database = SimpleNamespace(
            acquire=Mock(side_effect=[first_context, second_context])
        )
        repository = QualityCalibrationRepository(database)

        found = await repository.get_case(7)
        missing = await repository.get_case(999)

        self.assertEqual(database.acquire.call_count, 2)
        first_connection.fetchrow.assert_awaited_once()
        sql, feedback_id = first_connection.fetchrow.await_args.args
        self.assertIn("WHERE feedback.id = $1::BIGINT", sql)
        self.assertEqual(feedback_id, 7)
        second_connection.fetchrow.assert_awaited_once()
        self.assertEqual(second_connection.fetchrow.await_args.args[1], 999)
        self.assertIsNotNone(found)
        self.assertEqual(found.file_name, "image.jpg")
        self.assertEqual(found.outcome, "useful_warning")
        self.assertIsNone(missing)

    def test_unknown_section_is_rejected_before_database_access(self) -> None:
        database = SimpleNamespace(acquire=Mock())
        repository = QualityCalibrationRepository(database)

        with self.assertRaisesRegex(ValueError, "Неизвестный раздел"):
            repository._section_outcomes("invented")

        database.acquire.assert_not_called()


if __name__ == "__main__":
    unittest.main()
