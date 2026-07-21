from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.ai_quality import AIQualitySummary
from velvet_bot.domains.media_quality.models import DuplicatePage
from velvet_bot.domains.media_quality.reset_repository import DuplicateResetRepository
from velvet_bot.quality_audit import QualitySummary
from velvet_bot.quality_operations import QualityOperationsRepository
from velvet_bot.quality_ui import QualityCallback, build_duplicate_list, build_quality_dashboard


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False


class QwenDuplicateRetryControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_qwen_retry_resets_quality_and_semantic_queues(self) -> None:
        connection = SimpleNamespace(
            execute=AsyncMock(side_effect=["UPDATE 3", "UPDATE 4"]),
            transaction=Mock(return_value=_AsyncContext(None)),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        count = await QualityOperationsRepository(database).retry_errors()

        self.assertEqual(count, 7)
        self.assertEqual(connection.execute.await_count, 2)
        quality_sql = connection.execute.await_args_list[0].args[0]
        semantic_sql = connection.execute.await_args_list[1].args[0]
        self.assertIn("media_ai_quality_checks", quality_sql)
        self.assertIn("media_ai_profiles", semantic_sql)
        self.assertIn("status IN ('error', 'skipped')", quality_sql)
        self.assertIn("status IN ('error', 'skipped')", semantic_sql)
        self.assertIn("analysis = '{}'::JSONB", semantic_sql)
        self.assertNotIn("analysis = NULL", semantic_sql)

    async def test_duplicate_reset_clears_results_and_requeues_available_media(self) -> None:
        connection = SimpleNamespace(
            execute=AsyncMock(side_effect=["DELETE 5", "DELETE 8", "UPDATE 13"]),
            transaction=Mock(return_value=_AsyncContext(None)),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await DuplicateResetRepository(database).reset_all()

        self.assertEqual(result.candidates_deleted, 5)
        self.assertEqual(result.fingerprints_deleted, 8)
        self.assertEqual(result.media_reset, 13)
        self.assertEqual(connection.execute.await_count, 3)
        for call in connection.execute.await_args_list:
            self.assertEqual(call.args[-1], 20 * 1024 * 1024)
            self.assertIn("preview_file_id IS NOT NULL", call.args[0])

    def test_quality_dashboard_exposes_qwen_retry_button(self) -> None:
        summary = QualitySummary(
            pending_duplicates=0,
            confirmed_duplicates=0,
            pending_scans=0,
            scan_errors=0,
            broken_files=0,
            unchecked_files=0,
            missing_category=0,
            missing_universe=0,
            missing_story=0,
            empty_characters=0,
            media_without_prompt=0,
            orphan_media=0,
            unresolved_hashtags=0,
        )
        ai_summary = AIQualitySummary(
            pending=0,
            processing=0,
            ready=0,
            errors=2,
            skipped=1,
            unreviewed=0,
            accepted=0,
            fix_required=0,
            clean=0,
            warnings=0,
            critical=0,
        )

        _, keyboard = build_quality_dashboard(summary, ai_summary)
        actions = {
            QualityCallback.unpack(button.callback_data).action
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        }

        self.assertIn("quality_retry_errors", actions)

    def test_duplicate_list_exposes_confirmed_full_reset(self) -> None:
        page = DuplicatePage(items=(), page=0, page_size=6, total_items=0)

        _, keyboard = build_duplicate_list(page, status="pending")
        actions = {
            QualityCallback.unpack(button.callback_data).action
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        }

        self.assertIn("dupresetask", actions)


if __name__ == "__main__":
    unittest.main()
