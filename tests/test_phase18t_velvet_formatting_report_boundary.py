from __future__ import annotations

import inspect
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.velvet_formatting_reports import VelvetFormattingReportRepository


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


class VelvetFormattingReportBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(VelvetFormattingReportRepository)

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("self._database.acquire()"), 1)

    async def test_save_preserves_mode_text_limits_and_json(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(return_value=63))
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = VelvetFormattingReportRepository(database)
        provider = "provider-" + ("x" * 80)
        model = "model-" + ("y" * 200)
        payload = {
            "title_en": "window study / warm light / portrait",
            "description_ru": "Сохранён русский текст",
            "palette_hex": ["#6B4032", "#D7B39A"],
        }

        result = await repository.save(
            mode="full",
            source_text="Исходный материал",
            provider=provider,
            model=model,
            payload=payload,
            rendered_text="Готовое оформление Velvet Anatomy",
            created_by=8179531132,
        )

        self.assertEqual(result, 63)
        database.acquire.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        connection.fetchval.assert_awaited_once()
        sql, *arguments = connection.fetchval.await_args.args
        self.assertIn("INSERT INTO velvet_formatting_reports", sql)
        self.assertIn("analysis_version", sql)
        self.assertIn("RETURNING id", sql)
        self.assertEqual(len(arguments), 7)
        self.assertEqual(arguments[0], "full")
        self.assertEqual(arguments[1], "Исходный материал")
        self.assertEqual(arguments[2], provider[:64])
        self.assertEqual(arguments[3], model[:160])
        stored_payload = json.loads(arguments[4])
        self.assertEqual(stored_payload, payload)
        self.assertIn("русский", arguments[4])
        self.assertEqual(arguments[5], "Готовое оформление Velvet Anatomy")
        self.assertEqual(arguments[6], 8179531132)


if __name__ == "__main__":
    unittest.main()
