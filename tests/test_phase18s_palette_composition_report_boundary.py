from __future__ import annotations

import inspect
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.palette_composition_analysis import PaletteColor, PaletteMetrics
from velvet_bot.palette_composition_reports import PaletteCompositionReportRepository


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


class PaletteCompositionReportBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(PaletteCompositionReportRepository)

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("self._database.acquire()"), 1)

    async def test_save_preserves_metrics_scores_and_json_payloads(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(return_value=52))
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = PaletteCompositionReportRepository(database)
        provider = "provider-" + ("x" * 80)
        model = "model-" + ("y" * 200)
        metrics = PaletteMetrics(
            width=1080,
            height=1920,
            aspect_ratio=0.5625,
            brightness=54,
            contrast=63,
            saturation=71,
            temperature="warm",
            colors=(
                PaletteColor(
                    hex_code="#6B4032",
                    red=107,
                    green=64,
                    blue=50,
                    share=0.42,
                    luminance=72,
                    role="dominant",
                ),
            ),
        )
        report = {
            "composition_score": 91,
            "balance_score": 90,
            "framing_score": 89,
            "hierarchy_score": 88,
            "depth_score": 87,
            "lighting_score": 86,
            "palette_harmony_score": 85,
            "confidence": 84,
            "verdict": "strong",
            "palette_summary_ru": "Тёплая палитра сохранена",
        }

        result = await repository.save(
            result_file_id="result-file",
            result_file_unique_id="result-unique",
            provider=provider,
            model=model,
            metrics=metrics,
            report=report,
            created_by=8179531132,
        )

        self.assertEqual(result, 52)
        database.acquire.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        connection.fetchval.assert_awaited_once()
        sql, *arguments = connection.fetchval.await_args.args
        self.assertIn("INSERT INTO palette_composition_reports", sql)
        self.assertIn("analysis_version", sql)
        self.assertIn("RETURNING id", sql)
        self.assertEqual(len(arguments), 18)
        self.assertEqual(arguments[0:2], ["result-file", "result-unique"])
        self.assertEqual(arguments[2], provider[:64])
        self.assertEqual(arguments[3], model[:160])
        self.assertEqual(arguments[4:6], [1080, 1920])
        stored_metrics = json.loads(arguments[6])
        self.assertEqual(stored_metrics, metrics.as_dict())
        self.assertEqual(arguments[7:15], [91, 90, 89, 88, 87, 86, 85, 84])
        self.assertEqual(arguments[15], "strong")
        stored_report = json.loads(arguments[16])
        self.assertEqual(stored_report, report)
        self.assertIn("Тёплая", arguments[16])
        self.assertEqual(arguments[17], 8179531132)


if __name__ == "__main__":
    unittest.main()
