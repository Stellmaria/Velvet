from __future__ import annotations

import inspect
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.prompt_result_reports import PromptResultReportRepository


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


class PromptResultReportBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(PromptResultReportRepository)

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("self._database.acquire()"), 1)

    async def test_save_preserves_sql_argument_order_and_json(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(return_value=41))
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = PromptResultReportRepository(database)
        provider = "provider-" + ("x" * 80)
        model = "model-" + ("y" * 200)
        report = {
            "overall_score": 91,
            "subject_score": 90,
            "composition_score": 89,
            "lighting_score": 88,
            "palette_score": 87,
            "environment_score": 86,
            "style_score": 85,
            "technical_score": 84,
            "confidence": 83,
            "verdict": "соответствует",
            "comment": "Точный отчёт без потери кириллицы",
        }

        result = await repository.save(
            result_file_id="result-file",
            result_file_unique_id="result-unique",
            prompt_text="исходный промт",
            provider=provider,
            model=model,
            report=report,
            created_by=8179531132,
        )

        self.assertEqual(result, 41)
        database.acquire.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        connection.fetchval.assert_awaited_once()
        sql, *arguments = connection.fetchval.await_args.args
        self.assertIn("INSERT INTO prompt_result_comparison_reports", sql)
        self.assertIn("analysis_version", sql)
        self.assertIn("RETURNING id", sql)
        self.assertEqual(len(arguments), 17)
        self.assertEqual(arguments[0:3], ["result-file", "result-unique", "исходный промт"])
        self.assertEqual(arguments[3], provider[:64])
        self.assertEqual(arguments[4], model[:160])
        self.assertEqual(arguments[5:14], [91, 90, 89, 88, 87, 86, 85, 84, 83])
        self.assertEqual(arguments[14], "соответствует")
        stored_report = json.loads(arguments[15])
        self.assertEqual(stored_report, report)
        self.assertIn("кириллицы", arguments[15])
        self.assertEqual(arguments[16], 8179531132)


if __name__ == "__main__":
    unittest.main()
